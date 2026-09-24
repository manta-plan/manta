import time
from uuid import UUID

import httpx2
import psycopg
from prefect.client.orchestration import SyncPrefectClient
from prefect.exceptions import ObjectNotFound
from runner.flows import PLAYBOOK_DEPLOYMENT

_LIBRARY_PLAYBOOK = "cluster-expand-dispatch"
"""Runs cluster → expansion_overnight → dispatch under the library's own
default config (globals.expansion_mode: overnight) — three real blocks, a
real PyPSA/HiGHS solve each, dispatched through the actual docker work pool."""

# The provisioner registers this deployment as part of bringing the stack up
# (see docker_services in conftest.py, which waits on it via `--wait`), so this
# is normally instant — a defensive check with a clear failure message rather
# than a hard requirement.
_DEPLOYMENT_REGISTRATION_TIMEOUT = 30.0
# A real playbook run: three blocks, each its own throwaway container (image
# pull is a no-op — already built locally — but container start/stop and a
# real, if tiny, PyPSA/HiGHS solve all add up across three sequential steps.
_RUN_COMPLETION_TIMEOUT = 240.0
# Prefect ships flow-run logs to the API asynchronously in batches
# (`PREFECT_LOGGING_TO_API_BATCH_INTERVAL`, 2s by default on the playbook
# worker), so the final log lines can still be in flight for a moment after
# the flow's state already reports COMPLETED. Poll for logs to actually show
# up rather than assuming they're there the instant the run finishes.
_LOGS_AVAILABLE_TIMEOUT = 15.0


def _create_project(app_server: str) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": "Cluster Expand Dispatch Project", "description": "Integration test project"},
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


def _create_run(app_server: str, project_uuid: str, data_record_url: str) -> dict:
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={
            "project_uuid": project_uuid,
            "playbook": _LIBRARY_PLAYBOOK,
            "data_record_url": data_record_url,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _wait_for_terminal_status(
    app_server: str, run_uuid: str, timeout: float = _RUN_COMPLETION_TIMEOUT
) -> str:
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}")
        assert response.status_code == 200
        last_status = response.json()["status"]
        if last_status in ("COMPLETED", "FAILED", "CRASHED", "CANCELLED"):
            return last_status
        time.sleep(0.5)
    raise TimeoutError(
        f"Run {run_uuid} did not reach a terminal status within {timeout}s "
        f"(last status: {last_status})"
    )


def _wait_for_logs(
    app_server: str, run_uuid: str, timeout: float = _LOGS_AVAILABLE_TIMEOUT
) -> dict:
    deadline = time.monotonic() + timeout
    last_body = None
    while time.monotonic() < deadline:
        response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}/logs")
        assert response.status_code == 200
        last_body = response.json()
        if last_body["logs"]:
            return last_body
        time.sleep(0.25)
    raise TimeoutError(
        f"Run {run_uuid} did not have any logs within {timeout}s (last response: {last_body})"
    )


def _create_completed_runs(
    app_server: str,
    prefect_service: dict[str, str],
    project_uuid: str,
    data_record_url: str,
    count: int,
) -> list[str]:
    _wait_for_deployment_registered(prefect_service)
    run_uuids = []

    for _ in range(count):
        run_uuid = _create_run(app_server, project_uuid, data_record_url)["uuid"]
        assert _wait_for_terminal_status(app_server, run_uuid) == "COMPLETED"
        run_uuids.append(run_uuid)

    return run_uuids


def test_create_and_run_a_playbook(
    app_server: str,
    db_connection: psycopg.Connection,
    prefect_db_connection: psycopg.Connection,
    prefect_service: dict[str, str],
    data_record_url: str,
) -> None:
    # Given a project, and the provisioner's deployment registered with the
    # Prefect server
    project_uuid = _create_project(app_server)
    _wait_for_deployment_registered(prefect_service)

    # When a run is created against it
    body = _create_run(app_server, project_uuid, data_record_url)

    # Then it's accepted and returns a run uuid linked to the project
    run_uuid = body["uuid"]
    assert UUID(run_uuid)
    assert body["project_uuid"] == project_uuid

    # And it eventually completes: dispatched through a real Prefect server,
    # the playbook worker walking the playbook, and three real block
    # containers — cluster_time, overnight_capacity_expansion,
    # rolling_horizon_dispatch — each solving the tiny example network for real.
    status = _wait_for_terminal_status(app_server, run_uuid)
    assert status == "COMPLETED"

    # And the playbook flow run's own logs are reachable (its child steps'
    # solver output lives on their own flow runs, not this one — there is no
    # endpoint for those yet).
    logs_body = _wait_for_logs(app_server, run_uuid)
    assert logs_body["uuid"] == run_uuid
    assert logs_body["run_status"] == "COMPLETED"
    assert logs_body["logs"]

    # And the Run row is persisted with the right linkage
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT id FROM projects WHERE uuid = %s", (project_uuid,))
        project_row = cursor.fetchone()
        cursor.execute(
            "SELECT project_id, prefect_flow_run_id FROM runs WHERE uuid = %s", (run_uuid,)
        )
        run_row = cursor.fetchone()

    assert project_row is not None
    assert run_row is not None
    run_project_id, prefect_flow_run_id = run_row
    assert run_project_id == project_row[0]
    assert prefect_flow_run_id is not None

    # And the flow run is persisted in Prefect's own Postgres database — proof
    # it's actually backed by Postgres rather than an ephemeral/SQLite store
    with prefect_db_connection.cursor() as cursor:
        cursor.execute("SELECT id FROM flow_run WHERE id = %s", (prefect_flow_run_id,))
        flow_run_row = cursor.fetchone()

    assert flow_run_row is not None


def test_create_run_with_unknown_playbook_returns_404(
    app_server: str, data_record_url: str
) -> None:
    # Given a project
    project_uuid = _create_project(app_server)

    # When a run is requested against a playbook that doesn't exist
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={
            "project_uuid": project_uuid,
            "playbook": "does-not-exist",
            "data_record_url": data_record_url,
        },
    )

    # Then the API reports that the playbook does not exist, and nothing is dispatched
    assert response.status_code == 404


def test_run_is_cascade_deleted_when_project_is_deleted(
    app_server: str,
    db_connection: psycopg.Connection,
    prefect_service: dict[str, str],
    data_record_url: str,
) -> None:
    # Given a project with a run against it
    project_uuid = _create_project(app_server)
    _wait_for_deployment_registered(prefect_service)
    body = _create_run(app_server, project_uuid, data_record_url)
    run_uuid = body["uuid"]

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
    app_server: str, prefect_service: dict[str, str], data_record_url: str
) -> None:
    # Given a project with multiple completed runs
    project_uuid = _create_project(app_server)
    run_uuids = _create_completed_runs(
        app_server, prefect_service, project_uuid, data_record_url, count=3
    )

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
    assert {item["status"] for item in first_page["items"]} == {"COMPLETED"}
    assert first_page["summary"] == {
        "total": 3,
        "statuses": {"COMPLETED": 3},
    }

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
    app_server: str, prefect_service: dict[str, str], data_record_url: str
) -> None:
    # Given a project with completed runs
    project_uuid = _create_project(app_server)
    run_uuids = _create_completed_runs(
        app_server, prefect_service, project_uuid, data_record_url, count=2
    )

    # When filtering by completed status
    completed_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "statuses": "COMPLETED", "limit": 10, "offset": 0},
    )

    # Then matching runs are returned
    assert completed_response.status_code == 200
    completed_body = completed_response.json()
    assert completed_body["total"] == 2
    assert {item["uuid"] for item in completed_body["items"]} == set(run_uuids)
    assert {item["status"] for item in completed_body["items"]} == {"COMPLETED"}

    # And non-matching filters return an empty page while preserving project summary
    running_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "statuses": "RUNNING", "limit": 10, "offset": 0},
    )
    assert running_response.status_code == 200
    running_body = running_response.json()
    assert running_body["items"] == []
    assert running_body["total"] == 0
    assert running_body["summary"]["total"] == 2
    assert running_body["summary"]["statuses"] == {"COMPLETED": 2}


def test_get_run_summary_returns_project_counts(
    app_server: str, prefect_service: dict[str, str], data_record_url: str
) -> None:
    # Given a project with completed runs
    project_uuid = _create_project(app_server)
    _create_completed_runs(app_server, prefect_service, project_uuid, data_record_url, count=2)

    # When fetching its summary
    response = httpx2.get(f"{app_server}/v1/runs/summary", params={"project_uuid": project_uuid})

    # Then counts are scoped to that project
    assert response.status_code == 200
    assert response.json() == {
        "total": 2,
        "statuses": {"COMPLETED": 2},
    }


def test_list_runs_with_unknown_project_returns_404(app_server: str) -> None:
    # Given an unknown project UUID
    project_uuid = "00000000-0000-0000-0000-000000000000"

    # When listing its runs
    response = httpx2.get(f"{app_server}/v1/runs", params={"project_uuid": project_uuid})

    # Then the API reports that the project does not exist
    assert response.status_code == 404
