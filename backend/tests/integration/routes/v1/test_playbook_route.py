from uuid import UUID

import httpx2
import psycopg
import pytest
from manta_playbooks import ensure_process_pool, run_playbook
from mypy_boto3_s3.client import S3Client
from prefect.settings import PREFECT_API_URL, temporary_settings
from prefect.types.entrypoint import EntrypointType

SEEDED_PLAYBOOK_NAME = "cluster-expand-dispatch"
BUCKET = "manta"  # S3_BUCKET in backend/.env, created by the app at startup

# No worker runs in this stack, so a created run only ever gets as far as Prefect
# accepting it — which is exactly the backend's responsibility boundary. Actually
# executing a playbook needs the worker containers (docker compose --profile
# playbooks) and is exercised outside the test suite for now.


@pytest.fixture(scope="session")
def orchestrator_deployment(prefect_service: dict[str, str]) -> str:
    """Registers the playbook orchestrator deployment the backend submits runs to.

    In the dev stack the playbooks-provision container does this; the test stack has
    no workers, so the deployment is registered here directly against the ephemeral
    Prefect server.
    """
    api_url = f"http://{prefect_service['host']}:{prefect_service['port']}/api"
    with temporary_settings({PREFECT_API_URL: api_url}):
        ensure_process_pool("manta-orchestrator")
        run_playbook.to_deployment(
            name="orchestrator",
            work_pool_name="manta-orchestrator",
            entrypoint_type=EntrypointType.MODULE_PATH,
        ).apply()
    return "run_playbook/orchestrator"


def _create_project(app_server: str) -> str:
    response = httpx2.post(
        f"{app_server}/v1/projects",
        json={"name": "Playbook Project", "description": "Integration test project"},
    )
    assert response.status_code == 201
    return response.json()["uuid"]


def _seeded_playbook_uuid(app_server: str) -> str:
    response = httpx2.get(f"{app_server}/v1/playbooks")
    assert response.status_code == 200
    by_name = {item["name"]: item for item in response.json()["items"]}
    return by_name[SEEDED_PLAYBOOK_NAME]["uuid"]


def _upload_input(s3_client: S3Client, key: str) -> None:
    # Nothing executes without workers, so the bytes never have to be a real
    # network file — the backend only copies them.
    s3_client.put_object(Bucket=BUCKET, Key=key, Body=b"not really a netcdf")


def test_the_example_playbook_is_seeded_and_readable(app_server: str) -> None:
    # When
    listed = httpx2.get(f"{app_server}/v1/playbooks")
    playbook_uuid = _seeded_playbook_uuid(app_server)
    detail = httpx2.get(f"{app_server}/v1/playbooks/{playbook_uuid}")

    # Then
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == SEEDED_PLAYBOOK_NAME
    assert [step["name"] for step in body["doc"]["steps"]] == [
        "cluster",
        "expansion_overnight",
        "expansion_myopic",
        "dispatch",
    ]
    assert body["default_config"]["globals"]["expansion_mode"] == "overnight"


def test_get_playbook_with_unknown_uuid_returns_404(app_server: str) -> None:
    # When
    response = httpx2.get(f"{app_server}/v1/playbooks/{UUID(int=0)}")

    # Then
    assert response.status_code == 404


def test_validate_accepts_the_default_config_and_rejects_a_broken_one(
    app_server: str,
) -> None:
    # Given
    playbook_uuid = _seeded_playbook_uuid(app_server)
    default_config = httpx2.get(f"{app_server}/v1/playbooks/{playbook_uuid}").json()[
        "default_config"
    ]

    # When
    valid = httpx2.post(
        f"{app_server}/v1/playbooks/{playbook_uuid}/validate",
        json={"config": default_config},
    )
    # `n_hours` has the wrong type, and dispatch's input comes from a step that a
    # myopic run switches off — both catchable before anything runs.
    invalid = httpx2.post(
        f"{app_server}/v1/playbooks/{playbook_uuid}/validate",
        json={"config": {**default_config, "cluster": {"n_hours": "three"}}},
    )

    # Then
    assert valid.status_code == 200
    assert valid.json() == {"valid": True, "issues": []}
    assert invalid.status_code == 200
    invalid_body = invalid.json()
    assert not invalid_body["valid"]
    assert any(issue["step"] == "cluster" for issue in invalid_body["issues"])


def test_create_playbook_run_freezes_input_and_schedules_a_flow_run(
    app_server: str,
    s3_client: S3Client,
    db_connection: psycopg.Connection,
    orchestrator_deployment: str,
) -> None:
    # Given
    project_uuid = _create_project(app_server)
    playbook_uuid = _seeded_playbook_uuid(app_server)
    _upload_input(s3_client, "examples/it-network.nc")

    # When
    response = httpx2.post(
        f"{app_server}/v1/playbooks/{playbook_uuid}/runs",
        json={"project_uuid": project_uuid, "input_key": "examples/it-network.nc"},
    )

    # Then
    assert response.status_code == 201, response.text
    body = response.json()
    run_uuid = body["uuid"]
    assert body["project_uuid"] == project_uuid
    assert body["playbook_uuid"] == playbook_uuid
    assert body["input_key"] == f"{project_uuid}/runs/{run_uuid}/it-network.nc"

    # Then — the input was frozen under the run's prefix in S3
    frozen = s3_client.head_object(Bucket=BUCKET, Key=body["input_key"])
    assert frozen["ContentLength"] > 0

    # Then — the run row records the playbook, its config, and the frozen input
    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT playbook_id, playbook_config, input_key FROM runs WHERE uuid = %s",
            (run_uuid,),
        )
        row = cursor.fetchone()
    assert row is not None
    playbook_id, playbook_config, input_key = row
    assert playbook_id is not None
    assert playbook_config["globals"]["expansion_mode"] == "overnight"
    assert input_key == body["input_key"]

    # Then — Prefect accepted the run (no worker in this stack, so it stays queued)
    status = httpx2.get(f"{app_server}/v1/runs/{run_uuid}").json()["status"]
    assert status in ("SCHEDULED", "PENDING", "LATE", "RUNNING")

    # Then — the run's outputs listing shows the frozen input
    outputs = httpx2.get(f"{app_server}/v1/runs/{run_uuid}/outputs")
    assert outputs.status_code == 200
    assert [item["key"] for item in outputs.json()["items"]] == [body["input_key"]]
    assert outputs.json()["items"][0]["url"] == f"s3://{BUCKET}/{body['input_key']}"


def test_create_playbook_run_with_an_invalid_config_is_rejected(
    app_server: str, s3_client: S3Client, db_connection: psycopg.Connection
) -> None:
    # Given
    project_uuid = _create_project(app_server)
    playbook_uuid = _seeded_playbook_uuid(app_server)
    _upload_input(s3_client, "examples/it-network.nc")
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM runs")
        runs_before = cursor.fetchone()[0]

    # When — n_hours and segments are mutually exclusive only in block code, but a
    # wrong type is catchable from the catalogue schema alone
    response = httpx2.post(
        f"{app_server}/v1/playbooks/{playbook_uuid}/runs",
        json={
            "project_uuid": project_uuid,
            "input_key": "examples/it-network.nc",
            "config": {
                "globals": {"expansion_mode": "overnight"},
                "cluster": {"n_hours": "three"},
            },
        },
    )

    # Then
    assert response.status_code == 422
    assert response.json()["detail"]["issues"]
    with db_connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM runs")
        assert cursor.fetchone()[0] == runs_before


def test_create_playbook_run_with_a_missing_input_returns_404(
    app_server: str,
) -> None:
    # Given
    project_uuid = _create_project(app_server)
    playbook_uuid = _seeded_playbook_uuid(app_server)

    # When
    response = httpx2.post(
        f"{app_server}/v1/playbooks/{playbook_uuid}/runs",
        json={"project_uuid": project_uuid, "input_key": "examples/never-uploaded.nc"},
    )

    # Then
    assert response.status_code == 404
