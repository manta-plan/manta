# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What the provisioner tells the docker work pool about a block run."""

import pytest

from runner import config, deploy


@pytest.fixture(autouse=True)
def _stack_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "MANTA_DOCKER_NETWORK": "manta-test_default",
        "MANTA_JOB_S3_ENDPOINT": "http://seaweedfs:8333",
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "S3_BUCKET": "manta",
        "MANTA_BLOCK_LOGGERS": "playbook_library",
        "MANTA_BLOCK_SOURCES": "playbook_library",
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

    # Then: on the stack's network, removed when done...
    assert defaults["networks"] == ["manta-test_default"]
    assert defaults["auto_remove"] is True
    # ...images are built locally and never pushed, so a `latest` tag must not
    # send the worker to a registry...
    assert defaults["image_pull_policy"] == "Never"
    # ...and the pool names no image at all: which one a step runs in is a
    # property of the block's environment, supplied per run.
    assert "image" not in defaults


def test_a_block_container_is_told_how_to_report_back_and_where_records_live() -> None:
    # When
    env = _defaults(deploy.docker_job_template())["env"]

    # Then: the flow run reports its own state (no worker can do it for it)...
    assert env["PREFECT_API_URL"] == "http://prefect-server:4200/api"
    # ...persists its result where the orchestrator can read it...
    assert env["PREFECT_RESULTS_DEFAULT_STORAGE_BLOCK"] == config.RESULT_STORAGE_BLOCK
    # ...ships the modelling framework's own logging, which Prefect would
    # otherwise ignore (it captures only its own loggers and what is printed)...
    assert env["PREFECT_LOGGING_EXTRA_LOGGERS"] == "playbook_library"
    # ...knows which block library to import before looking anything up...
    assert env["MANTA_BLOCK_SOURCES"] == "playbook_library"
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
        "MANTA_BLOCK_SOURCES",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_ENDPOINT_URL",
    }


def test_the_playbooks_pool_name_has_dropped_orchestrator_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The pool running run-playbook is named for what it runs, not for an
    # "orchestrator" concept that exists nowhere else in this codebase.
    monkeypatch.delenv("MANTA_PLAYBOOKS_POOL", raising=False)
    assert config.playbooks_pool() == "manta-playbooks"
