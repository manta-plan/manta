import re
import time
from uuid import UUID

import httpx2
import psycopg
from prefect.client.orchestration import SyncPrefectClient
from prefect.exceptions import ObjectNotFound

from manta.services.run_service import PI_DIGIT_STATS_DEPLOYMENT

# The flow-serving subprocess (spawned by create_app()) needs to start up and
# register its deployment with the Prefect server before `POST /runs` can
# submit a run against it — a cold start.
_DEPLOYMENT_REGISTRATION_TIMEOUT = 60.0
# Then the flow itself needs to actually get scheduled and executed by that
# same subprocess.
_RUN_COMPLETION_TIMEOUT = 90.0
# Prefect ships flow-run logs to the API asynchronously in batches
# (`PREFECT_LOGGING_TO_API_BATCH_INTERVAL`, 2s by default), so the final log
# lines can still be in flight for a moment after the flow's state already
# reports COMPLETED. Poll for logs to actually show up rather than assuming
# they're there the instant the run finishes.
_LOGS_AVAILABLE_TIMEOUT = 15.0


def _create_project(app_server: str) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": "Pi Digit Stats Project", "description": "Integration test project"},
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
                client.read_deployment_by_name(PI_DIGIT_STATS_DEPLOYMENT)
                return
            except ObjectNotFound:
                time.sleep(0.25)
    raise TimeoutError(
        f"Deployment {PI_DIGIT_STATS_DEPLOYMENT} was not registered within {timeout}s"
    )


def _create_run(app_server: str, project_uuid: str, num_pi_digits: int) -> dict:
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={"project_uuid": project_uuid, "num_pi_digits": num_pi_digits},
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
        time.sleep(0.25)
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
    app_server: str, prefect_service: dict[str, str], project_uuid: str, count: int
) -> list[str]:
    _wait_for_deployment_registered(prefect_service)
    run_uuids = []

    for _ in range(count):
        run_uuid = _create_run(app_server, project_uuid, num_pi_digits=100)["uuid"]
        assert _wait_for_terminal_status(app_server, run_uuid) == "COMPLETED"
        run_uuids.append(run_uuid)

    return run_uuids


def test_create_and_run_pi_digit_stats(
    app_server: str, db_connection: psycopg.Connection, prefect_service: dict[str, str]
) -> None:
    # Given a project, and the flow-serving subprocess's deployment registered
    # with the Prefect server
    project_uuid = _create_project(app_server)
    _wait_for_deployment_registered(prefect_service)

    # When a run is created against it, with a small digit count to keep the
    # actual flow execution fast
    body = _create_run(app_server, project_uuid, num_pi_digits=1000)

    # Then it's accepted and returns a run uuid linked to the project
    run_uuid = body["uuid"]
    assert UUID(run_uuid)
    assert body["project_uuid"] == project_uuid

    # And it eventually completes, submitted and executed via a real Prefect
    # server + flow-serving subprocess
    status = _wait_for_terminal_status(app_server, run_uuid)
    assert status == "COMPLETED"

    # And logs contain the printed digit-frequency output (a Counter dict
    # repr) — assert on the shape rather than exact digits/ordering. Logs ship
    # to the Prefect API asynchronously, so poll rather than assuming they're
    # already there the instant the run finishes.
    logs_body = _wait_for_logs(app_server, run_uuid)
    assert logs_body["uuid"] == run_uuid
    assert logs_body["run_status"] == "COMPLETED"
    joined_logs = "\n".join(logs_body["logs"])
    assert re.search(r"'[0-9]':\s*\d+", joined_logs), f"unexpected log output: {joined_logs!r}"

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


def test_run_survives_project_deletion_with_project_id_set_to_null(
    app_server: str, db_connection: psycopg.Connection, prefect_service: dict[str, str]
) -> None:
    # Given a project with a run against it
    project_uuid = _create_project(app_server)
    _wait_for_deployment_registered(prefect_service)
    body = _create_run(app_server, project_uuid, num_pi_digits=1000)
    run_uuid = body["uuid"]

    # When the project is deleted
    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM projects WHERE uuid = %s", (project_uuid,))

    # Then the run row survives, with its project_id set to NULL rather than
    # being cascade-deleted
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT project_id FROM runs WHERE uuid = %s", (run_uuid,))
        run_row = cursor.fetchone()

    assert run_row is not None
    assert run_row[0] is None

    # And the run is still reachable via the API, reporting no project
    response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}")
    assert response.status_code == 200
    assert response.json()["project_uuid"] is None


def test_list_runs_returns_project_runs_with_pagination_and_summary(
    app_server: str, prefect_service: dict[str, str]
) -> None:
    # Given a project with multiple completed runs
    project_uuid = _create_project(app_server)
    run_uuids = _create_completed_runs(app_server, prefect_service, project_uuid, count=3)

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
    app_server: str, prefect_service: dict[str, str]
) -> None:
    # Given a project with completed runs
    project_uuid = _create_project(app_server)
    run_uuids = _create_completed_runs(app_server, prefect_service, project_uuid, count=2)

    # When filtering by completed status
    completed_response = httpx2.get(
        f"{app_server}/v1/runs",
        params={"project_uuid": project_uuid, "status": "COMPLETED", "limit": 10, "offset": 0},
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
        params={"project_uuid": project_uuid, "status": "RUNNING", "limit": 10, "offset": 0},
    )
    assert running_response.status_code == 200
    running_body = running_response.json()
    assert running_body["items"] == []
    assert running_body["total"] == 0
    assert running_body["summary"]["total"] == 2
    assert running_body["summary"]["statuses"] == {"COMPLETED": 2}


def test_get_run_summary_returns_project_counts(
    app_server: str, prefect_service: dict[str, str]
) -> None:
    # Given a project with completed runs
    project_uuid = _create_project(app_server)
    _create_completed_runs(app_server, prefect_service, project_uuid, count=2)

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
