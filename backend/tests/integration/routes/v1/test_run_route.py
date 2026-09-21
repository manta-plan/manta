import time
from pathlib import Path

import httpx2
import psycopg
from dotenv import dotenv_values
from mypy_boto3_s3.client import S3Client
from prefect.client.orchestration import SyncPrefectClient
from prefect.exceptions import ObjectNotFound

from manta.services.run_service import PLAYBOOK_DEPLOYMENT

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
NETWORK_FIXTURE = FIXTURES / "network.nc"
BACKEND_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"

# The flow-serving subprocess (spawned by create_app()) needs to start up and
# register its deployment with the Prefect server before `POST /runs` can
# submit a run against it — a cold start.
_DEPLOYMENT_REGISTRATION_TIMEOUT = 60.0

_RUN_CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}

# These tests are about the run listing API, not about execution: they create
# runs and read them back without waiting for any step to run, so they stay fast
# and cannot flake on how far a playbook has got. Execution end to end is
# test_playbook_run_route.py's job.


def _bucket() -> str:
    return dotenv_values(BACKEND_ENV_FILE)["S3_BUCKET"]


def _create_project(app_server: str) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": "Run Listing Project", "description": "Integration test project"},
    )
    assert response.status_code == 201
    return response.json()["uuid"]


def _wait_for_deployment_registered(
    prefect_service: dict[str, str], timeout: float = _DEPLOYMENT_REGISTRATION_TIMEOUT
) -> None:
    """Poll Prefect's API for the flow deployment's existence."""
    api_url = f"http://{prefect_service['host']}:{prefect_service['port']}/api"
    deadline = time.monotonic() + timeout
    with SyncPrefectClient(api=api_url) as client:
        while time.monotonic() < deadline:
            try:
                client.read_deployment_by_name(PLAYBOOK_DEPLOYMENT)
                return
            except ObjectNotFound:
                time.sleep(0.25)
    raise TimeoutError(f"Deployment {PLAYBOOK_DEPLOYMENT} was not registered within {timeout}s")


def _create_run(app_server: str, project_uuid: str) -> dict:
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={
            "project_uuid": project_uuid,
            "playbook_name": "cluster-expand-dispatch",
            "config": _RUN_CONFIG,
            "input_file": "network.nc",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _project_with_runs(
    app_server: str, s3_client: S3Client, prefect_service: dict[str, str], count: int
) -> tuple[str, list[str]]:
    project_uuid = _create_project(app_server)
    s3_client.upload_file(str(NETWORK_FIXTURE), _bucket(), f"{project_uuid}/network.nc")
    _wait_for_deployment_registered(prefect_service)
    return project_uuid, [_create_run(app_server, project_uuid)["uuid"] for _ in range(count)]


def test_run_is_cascade_deleted_when_project_is_deleted(
    app_server: str,
    s3_client: S3Client,
    db_connection: psycopg.Connection,
    prefect_service: dict[str, str],
) -> None:
    # Given a project with a run against it
    project_uuid, (run_uuid,) = _project_with_runs(app_server, s3_client, prefect_service, count=1)

    # When the project is deleted
    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM projects WHERE uuid = %s", (project_uuid,))

    # Then the run row is cascade-deleted along with it
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM runs WHERE uuid = %s", (run_uuid,))
        run_row = cursor.fetchone()

    assert run_row is None

    # And the run is no longer reachable via the API
    response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}")
    assert response.status_code == 404


def test_list_runs_returns_project_runs_with_pagination_and_summary(
    app_server: str, s3_client: S3Client, prefect_service: dict[str, str]
) -> None:
    # Given a project with three runs
    project_uuid, run_uuids = _project_with_runs(app_server, s3_client, prefect_service, count=3)

    # When fetching the first page
    first_page_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "limit": 2, "offset": 0},
    )

    # Then pagination metadata, project scoping, and summary counts are returned
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total"] == 3
    assert first_page["limit"] == 2
    assert first_page["offset"] == 0
    assert len(first_page["items"]) == 2
    assert {item["uuid"] for item in first_page["items"]}.issubset(set(run_uuids))
    assert {item["project_uuid"] for item in first_page["items"]} == {project_uuid}
    assert {item["playbook_name"] for item in first_page["items"]} == {"cluster-expand-dispatch"}
    assert first_page["summary"]["total"] == 3
    assert sum(first_page["summary"]["statuses"].values()) == 3

    # And the second page returns the remaining run
    second_page_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "limit": 2, "offset": 2},
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["total"] == 3
    assert second_page["offset"] == 2
    assert len(second_page["items"]) == 1
    assert second_page["items"][0]["uuid"] in run_uuids


def test_list_runs_filters_project_runs_by_status(
    app_server: str, s3_client: S3Client, prefect_service: dict[str, str]
) -> None:
    # Given a project with two runs, in whatever state they have reached
    project_uuid, run_uuids = _project_with_runs(app_server, s3_client, prefect_service, count=2)
    listed = httpx2.get(
        f"{app_server}/v1/runs", params={"project_uuid": project_uuid, "limit": 10, "offset": 0}
    ).json()
    statuses = sorted({item["status"] for item in listed["items"]})

    # When filtering by the statuses those runs actually report
    matching_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={
            "project_uuid": project_uuid,
            "statuses": statuses,
            "limit": 10,
            "offset": 0,
        },
    )

    # Then all of them come back
    assert matching_response.status_code == 200
    matching_body = matching_response.json()
    assert matching_body["total"] == 2
    assert {item["uuid"] for item in matching_body["items"]} == set(run_uuids)

    # And a filter nothing matches returns an empty page while preserving the
    # project's summary, which is not scoped by the filter
    missing_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "statuses": "CANCELLED", "limit": 10, "offset": 0},
    )
    assert missing_response.status_code == 200
    missing_body = missing_response.json()
    assert missing_body["items"] == []
    assert missing_body["total"] == 0
    assert missing_body["summary"]["total"] == 2


def test_get_run_summary_returns_project_counts(
    app_server: str, s3_client: S3Client, prefect_service: dict[str, str]
) -> None:
    # Given a project with two runs
    project_uuid, _ = _project_with_runs(app_server, s3_client, prefect_service, count=2)

    # When fetching its summary
    response = httpx2.get(f"{app_server}/v1/runs/summary", params={"project_uuid": project_uuid})

    # Then counts are scoped to that project
    assert response.status_code == 200
    summary = response.json()
    assert summary["total"] == 2
    assert sum(summary["statuses"].values()) == 2


def test_list_runs_with_unknown_project_returns_404(app_server: str) -> None:
    # Given an unknown project UUID
    project_uuid = "00000000-0000-0000-0000-000000000000"

    # When listing its runs
    response = httpx2.get(f"{app_server}/v1/runs", params={"project_uuid": project_uuid})

    # Then the API reports that the project does not exist
    assert response.status_code == 404
