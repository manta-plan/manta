"""What the provisioner tells the docker work pool about a block run."""

import pytest

from manta_runtime import config, deploy


@pytest.fixture(autouse=True)
def _stack_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "MANTA_EXEC_IMAGE": "manta-exec:test",
        "MANTA_DOCKER_NETWORK": "manta-test_default",
        "MANTA_JOB_S3_ENDPOINT": "http://seaweedfs:8333",
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "manta",
        "MANTA_BLOCK_LOGGERS": "blocks,pypsa",
    }.items():
        monkeypatch.setenv(name, value)


def _defaults(template: dict) -> dict:
    return {
        name: spec["default"]
        for name, spec in template["variables"]["properties"].items()
        if "default" in spec
    }


def test_the_job_template_says_what_a_block_container_is() -> None:
    # When
    defaults = _defaults(deploy.docker_job_template())

    # Then: the execution image, on the stack's network, removed when done.
    assert defaults["image"] == "manta-exec:test"
    assert defaults["networks"] == ["manta-test_default"]
    assert defaults["auto_remove"] is True
    # The image is built locally and never pushed, so a `latest` tag must not
    # send the worker to a registry.
    assert defaults["image_pull_policy"] == "Never"


def test_a_block_container_is_told_how_to_report_back_and_where_records_live() -> None:
    # When
    env = _defaults(deploy.docker_job_template())["env"]

    # Then: the flow run reports its own state (no worker can do it for it)...
    assert env["PREFECT_API_URL"] == "http://prefect-server:4200/api"
    # ...persists its result where the orchestrator can read it...
    assert env["PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK"] == config.RESULT_STORAGE_BLOCK
    # ...ships the modelling framework's own logging, which Prefect would
    # otherwise ignore (it captures only its own loggers and what is printed)...
    assert env["PREFECT_LOGGING_EXTRA_LOGGERS"] == "blocks,pypsa"
    # ...and reaches the object store by service name, not the published host port.
    assert env["AWS_ENDPOINT_URL"] == "http://seaweedfs:8333"
    assert env["AWS_ACCESS_KEY_ID"] == "key"
    assert env["AWS_SECRET_ACCESS_KEY"] == "secret"


def test_a_block_container_is_told_nothing_else() -> None:
    # A container that runs third-party modelling code gets no route to the app
    # database, the identity provider, or anything else this stack holds.
    assert set(_defaults(deploy.docker_job_template())["env"]) == {
        "PREFECT_API_URL",
        "PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK",
        "PREFECT_LOGGING_EXTRA_LOGGERS",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ENDPOINT_URL",
    }
