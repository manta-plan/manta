import re
import time
from uuid import UUID

import httpx2
import psycopg

# The flow-serving subprocess (spawned by create_app()) needs to start up and
# register its deployment with the Prefect server before `POST /runs` can
# submit a run against it. Retry the initial POST with backoff to absorb that
# cold-start race instead of failing the test outright.
_CREATE_RUN_RETRY_TIMEOUT = 60.0
# Then the flow itself needs to actually get scheduled and executed by that
# same subprocess — a genuine cold start, so give this real margin too.
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


def _create_run_with_retry(
    app_server: str,
    project_uuid: str,
    num_pi_digits: int,
    timeout: float = _CREATE_RUN_RETRY_TIMEOUT,
) -> dict:
    deadline = time.monotonic() + timeout
    last_response = None
    while time.monotonic() < deadline:
        last_response = httpx2.post(
            f"{app_server}/v1/runs",
            json={"project_uuid": project_uuid, "num_pi_digits": num_pi_digits},
        )
        if last_response.status_code == 201:
            return last_response.json()
        time.sleep(1.0)
    raise TimeoutError(
        f"POST /v1/runs did not succeed within {timeout}s "
        f"(last response: {last_response.status_code if last_response else None} "
        f"{last_response.text if last_response else None})"
    )


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
        time.sleep(1.0)
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
        time.sleep(1.0)
    raise TimeoutError(
        f"Run {run_uuid} did not have any logs within {timeout}s (last response: {last_body})"
    )


def test_create_and_run_pi_digit_stats(app_server: str, db_connection: psycopg.Connection) -> None:
    # Given a project
    project_uuid = _create_project(app_server)

    # When a run is created against it, with a small digit count to keep the
    # actual flow execution fast
    body = _create_run_with_retry(app_server, project_uuid, num_pi_digits=1000)

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
