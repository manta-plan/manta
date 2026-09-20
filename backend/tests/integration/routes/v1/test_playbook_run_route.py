import time
from pathlib import Path
from uuid import UUID

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

# The app's flow-serving subprocess (see main.py) registers the run-playbook
# deployment with the Prefect server after startup — a cold start, same as the
# pi-digit-stats flow.
_DEPLOYMENT_REGISTRATION_TIMEOUT = 60.0
# A playbook run spawns one container per step (three steps here) plus the
# orchestrator's own, each polled by Prefect at multi-second intervals, so this
# is dominated by infrastructure latency rather than the (sub-second) solves.
_PLAYBOOK_RUN_COMPLETION_TIMEOUT = 300.0

_RUN_CONFIG = {
    "globals": {"expansion_mode": "overnight"},
    "cluster": {"n_hours": 3},
    "expansion_overnight": {},
    "expansion_myopic": {},
    "dispatch": {"optimize_config": {"horizon": 4}},
}


def _bucket() -> str:
    return dotenv_values(BACKEND_ENV_FILE)["S3_BUCKET"]


def _create_project(app_server: str) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": "Playbook Project", "description": "Playbook integration test"},
    )
    assert response.status_code == 201
    return response.json()["uuid"]


def _upload_input(s3_client: S3Client, project_uuid: str, filename: str) -> None:
    s3_client.upload_file(str(NETWORK_FIXTURE), _bucket(), f"{project_uuid}/{filename}")


def _wait_for_playbook_deployment(
    prefect_service: dict[str, str], timeout: float = _DEPLOYMENT_REGISTRATION_TIMEOUT
) -> None:
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


def _wait_for_terminal_status(
    app_server: str, run_uuid: str, timeout: float = _PLAYBOOK_RUN_COMPLETION_TIMEOUT
) -> str:
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}")
        assert response.status_code == 200
        last_status = response.json()["status"]
        if last_status in ("COMPLETED", "FAILED", "CRASHED", "CANCELLED"):
            return last_status
        time.sleep(2)
    raise TimeoutError(
        f"Run {run_uuid} did not reach a terminal status within {timeout}s "
        f"(last status: {last_status})"
    )


def test_playbooks_are_listed_with_their_default_configs(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/playbooks")

    # Then the built-in playbook is offered, ready to run
    assert response.status_code == 200
    playbooks = {item["name"]: item for item in response.json()["items"]}
    assert "cluster-expand-dispatch" in playbooks
    entry = playbooks["cluster-expand-dispatch"]
    assert [step["name"] for step in entry["doc"]["steps"]] == [
        "cluster",
        "expansion_overnight",
        "expansion_myopic",
        "dispatch",
    ]
    assert entry["default_config"]["globals"]["expansion_mode"] == "overnight"


def test_a_playbook_run_with_an_invalid_config_is_refused_before_starting(
    app_server: str, s3_client: S3Client
) -> None:
    # Given a project with an input file, and a config that switches on the myopic
    # branch even though the playbook's data has no investment periods
    project_uuid = _create_project(app_server)
    _upload_input(s3_client, project_uuid, "network.nc")
    broken_config = {**_RUN_CONFIG, "globals": {"expansion_mode": "myopic"}}

    # When
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={
            "project_uuid": project_uuid,
            "playbook_name": "cluster-expand-dispatch",
            "config": broken_config,
            "input_file": "network.nc",
        },
    )

    # Then the run is refused with the exact problem, and nothing was started
    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert any(
        issue["kind"] == "dims" and "investment_period" in issue["message"] for issue in issues
    )


def test_a_playbook_run_with_a_missing_input_file_is_refused(app_server: str) -> None:
    # Given a project with no such file in its storage
    project_uuid = _create_project(app_server)

    # When
    response = httpx2.post(
        f"{app_server}/v1/runs",
        json={
            "project_uuid": project_uuid,
            "playbook_name": "cluster-expand-dispatch",
            "config": _RUN_CONFIG,
            "input_file": "not-uploaded.nc",
        },
    )

    # Then
    assert response.status_code == 404
    assert "not-uploaded.nc" in response.json()["detail"]


def test_a_playbook_runs_end_to_end_with_a_container_per_block(
    app_server: str,
    s3_client: S3Client,
    db_connection: psycopg.Connection,
    prefect_service: dict[str, str],
) -> None:
    # Given a project whose storage holds the input network, and the playbook
    # deployments registered by the stack's deployer
    project_uuid = _create_project(app_server)
    _upload_input(s3_client, project_uuid, "network.nc")
    _wait_for_playbook_deployment(prefect_service)

    # When a playbook run is created
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
    body = response.json()
    run_uuid = body["uuid"]
    assert UUID(run_uuid)
    assert body["playbook_name"] == "cluster-expand-dispatch"

    # Then it completes, executed by the docker work pool (orchestrator and each
    # block step in their own containers)
    assert _wait_for_terminal_status(app_server, run_uuid) == "COMPLETED"

    # And each step of the playbook reports its own (completed) state; the myopic
    # branch was switched off by the config, so it never ran
    steps_response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}/steps")
    assert steps_response.status_code == 200
    steps = steps_response.json()["steps"]
    assert [step["name"] for step in steps] == [
        "cluster[cluster_time]",
        "expansion_overnight[overnight_capacity_expansion]",
        "dispatch[rolling_horizon_dispatch]",
    ]
    assert {step["status"] for step in steps} == {"COMPLETED"}

    # And the run's outputs are browsable: the input copy plus one file per step
    # that ran, all under the run's own prefix (requirement: users can view each
    # block's outputs)
    outputs_response = httpx2.get(f"{app_server}/v1/runs/{run_uuid}/outputs")
    assert outputs_response.status_code == 200
    outputs = outputs_response.json()["items"]
    run_prefix = f"{project_uuid}/runs/{run_uuid}"
    assert [output["key"] for output in outputs] == [
        f"{run_prefix}/input/network.nc",
        f"{run_prefix}/steps/cluster.nc",
        f"{run_prefix}/steps/dispatch.nc",
        f"{run_prefix}/steps/expansion_overnight.nc",
    ]
    assert all(output["size"] > 0 for output in outputs)

    # And everything needed to reproduce the run is persisted on the Run row
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT playbook_name, playbook_doc, playbook_config, input_url, output_prefix "
            "FROM runs WHERE uuid = %s",
            (run_uuid,),
        )
        run_row = cursor.fetchone()
    assert run_row is not None
    playbook_name, playbook_doc, playbook_config, input_url, output_prefix = run_row
    assert playbook_name == "cluster-expand-dispatch"
    assert playbook_doc["name"] == "cluster-expand-dispatch"
    assert playbook_config == _RUN_CONFIG
    assert input_url == f"s3://{_bucket()}/{run_prefix}/input/network.nc"
    assert output_prefix == f"s3://{_bucket()}/{run_prefix}/steps"
