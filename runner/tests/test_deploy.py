# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""What the provisioner tells the work pools: what a block run is, and how many
playbook runs go at once."""

import pytest
from prefect.exceptions import ObjectAlreadyExists

from runner import config, deploy


@pytest.fixture(autouse=True)
def _stack_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "MANTA_DOCKER_NETWORK": "manta-test_default",
        "MANTA_JOB_S3_ENDPOINT": "http://seaweedfs:8333",
        "PREFECT_API_URL": "http://prefect-server:4200/api",
        "S3_ACCESS_KEY": "key",
        "S3_SECRET_KEY": "secret",
        "MANTA_BLOCK_LOGGERS": "playbook_library",
        "MANTA_BLOCK_SOURCES": "playbook_library",
    }.items():
        monkeypatch.setenv(name, value)


class _FakePrefectClient:
    """Keeps the work pools the provisioner creates and the updates it sends."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.created: dict = {}
        self.updated: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        return None

    def create_work_pool(self, work_pool) -> None:
        if work_pool.name in self.existing:
            raise ObjectAlreadyExists(http_exc=Exception("409 Conflict"))
        self.created[work_pool.name] = work_pool

    def update_work_pool(self, work_pool_name: str, work_pool) -> None:
        # Only the fields that were set, which is what the real client sends.
        self.updated[work_pool_name] = work_pool.model_dump(exclude_unset=True)


def _prefect_client(
    monkeypatch: pytest.MonkeyPatch, existing: set[str] | None = None
) -> _FakePrefectClient:
    client = _FakePrefectClient(existing)
    monkeypatch.setattr(deploy, "get_client", lambda sync_client: client)
    return client


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


def test_the_limit_on_playbook_runs_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given
    monkeypatch.setenv("MANTA_MAX_CONCURRENT_PLAYBOOK_RUNS", "3")

    # When / Then
    assert config.max_concurrent_playbook_runs() == 3


def test_the_limit_on_playbook_runs_has_a_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.delenv("MANTA_MAX_CONCURRENT_PLAYBOOK_RUNS", raising=False)

    # When / Then
    assert config.max_concurrent_playbook_runs() == 20


def test_a_new_playbooks_pool_is_created_with_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    client = _prefect_client(monkeypatch)

    # When
    deploy.ensure_process_pool("manta-playbooks", concurrency_limit=3)

    # Then
    pool = client.created["manta-playbooks"]
    assert pool.type == "process"
    assert pool.concurrency_limit == 3
    assert client.updated == {}


def test_an_existing_playbooks_pool_gets_the_limit_on_every_deploy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: the pool is there from an earlier deploy, whatever limit it had then.
    client = _prefect_client(monkeypatch, existing={"manta-playbooks"})

    # When
    deploy.ensure_process_pool("manta-playbooks", concurrency_limit=3)

    # Then: the limit is brought up to date, and nothing else about the pool is touched.
    assert client.created == {}
    assert client.updated == {"manta-playbooks": {"concurrency_limit": 3}}


def test_only_the_playbooks_pool_is_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    monkeypatch.setenv("MANTA_BLOCKS_POOL", "manta-blocks")
    monkeypatch.setenv("MANTA_PLAYBOOKS_POOL", "manta-playbooks")
    monkeypatch.setenv("MANTA_MAX_CONCURRENT_PLAYBOOK_RUNS", "3")
    client = _prefect_client(monkeypatch)
    monkeypatch.setattr(deploy, "deploy", lambda flow, name, pool: "deployment-id")

    # When
    deploy.main()

    # Then: a block only ever runs as a step of a playbook run, which holds the slot.
    assert client.created["manta-playbooks"].concurrency_limit == 3
    assert client.created["manta-blocks"].concurrency_limit is None


def test_an_existing_blocks_pool_stays_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given
    client = _prefect_client(monkeypatch, existing={"manta-blocks"})

    # When
    deploy.ensure_docker_pool("manta-blocks", deploy.docker_job_template())

    # Then
    assert "concurrency_limit" not in client.updated["manta-blocks"]
