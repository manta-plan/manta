import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks
from runner.flows import OUTPUT_ARTIFACT_KEY, catalogue_parameter

from manta.entities import Project, Run, User
from manta.services import run_service as run_service_module
from manta.services.errors import AuthorizationError
from manta.services.playbook_service import PlaybookService
from manta.services.results.run_result import DataRecordResult
from manta.services.run_service import RunService
from manta.services.s3_file_storage_service import S3FileStorageService
from manta.services.user_service import UserService

_LIBRARY_PLAYBOOK = "expand"
_BUCKET = "manta"
_RECORD_URL = f"s3://{_BUCKET}/{uuid4()}/store"
_REVISION_UUID = UUID("3de02051-8918-45ab-a61b-980b3da170c4")


class _FakeClientContext:
    """Sync context manager standing in for the client from `get_client(sync_client=True)`."""

    def __init__(self, client) -> None:
        self._client = client

    def __enter__(self):
        return self._client

    def __exit__(self, *_args) -> bool:
        return False


def _patch_get_client(monkeypatch: pytest.MonkeyPatch, client) -> None:
    monkeypatch.setattr(
        run_service_module, "get_client", lambda sync_client=False: _FakeClientContext(client)
    )


def _fake_flow_run(state_type: str, config: dict | None = None):
    # `_flow_run_status` reads `flow_run.state.type.value`, and `_flow_run_config`
    # reads the config back from the parameters Prefect stored on the flow run.
    return SimpleNamespace(
        state=SimpleNamespace(type=SimpleNamespace(value=state_type)),
        parameters={
            "config": config if config is not None else {},
            "record": {"url": _RECORD_URL, "uuid": str(_REVISION_UUID)},
        },
    )


def _library_playbook_service() -> PlaybookService:
    return PlaybookService(playbooks=library_playbooks(), catalogue=library_catalogue())


def _existing_user(user_id: int = 1, username: str = "alice") -> User:
    user = User(
        username=username,
        idp_subject=f"abc-{user_id}",
        idp_source="https://idp.example/realms/manta",
    )
    user.id = user_id
    user.uuid = uuid4()
    user.created_at = datetime.now(UTC)
    return user


def _existing_project(owner_id: int = 1) -> Project:
    project = Project(name="North Sea Wind")
    project.id = 1
    project.uuid = uuid4()
    project.owner_id = owner_id
    project.created_at = datetime.now(UTC)
    return project


def _store_url(project: Project) -> str:
    return f"s3://{_BUCKET}/{project.uuid}/store"


def _dispatching_service(db, mock_s3_client) -> RunService:
    """A RunService that gets as far as dispatching a run: the record's revision exists."""
    return RunService(
        db=db,
        storage=S3FileStorageService(client=mock_s3_client, bucket=_BUCKET),
        playbook_service=_library_playbook_service(),
        user_service=UserService(db),
    )


def _existing_run(project: Project) -> Run:
    run = Run(project_id=project.id, prefect_flow_run_id=uuid4(), playbook=_LIBRARY_PLAYBOOK)
    run.id = 1
    run.uuid = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def test_create_run_persists_a_run_and_returns_its_dto(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, mock_s3_client
) -> None:
    # Given
    project = _existing_project()
    user = _existing_user()
    db = mock_db_class(query_results={Project: project})
    flow_run_id = uuid4()
    # `run_deployment` runs synchronously when called from a sync context (see
    # the comment in `RunService.create_run`) — a plain `MagicMock`, not
    # `AsyncMock`, mirrors that real call shape.
    dispatch = MagicMock(return_value=SimpleNamespace(id=flow_run_id))
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    service = _dispatching_service(db, mock_s3_client)

    # When
    result = service.create_run(
        project_uuid=project.uuid,
        playbook=_LIBRARY_PLAYBOOK,
        config=None,
        store_url=_store_url(project),
        revision_uuid=_REVISION_UUID,
        user=user,
    )

    # Then: the run is persisted against the deployment's flow run...
    db.add.assert_called_once()
    db.commit.assert_called_once()
    persisted_run = db.add.call_args.args[0]
    assert isinstance(persisted_run, Run)
    assert persisted_run.project_id == project.id
    assert persisted_run.prefect_flow_run_id == flow_run_id
    assert persisted_run.playbook == _LIBRARY_PLAYBOOK
    assert result.uuid == db.uuid
    assert result.project_uuid == project.uuid
    assert result.playbook == _LIBRARY_PLAYBOOK
    assert result.created_at == db.created_at

    # ...and what actually reaches Prefect is the playbook resolved by name, the
    # library's own default_config (none was supplied), the record as plain
    # data, and the catalogue encoded
    # as a JSON string (never a dict — see runner.flows.catalogue_parameter).
    library_playbook = library_playbooks()[_LIBRARY_PLAYBOOK]
    assert dispatch.call_args.args[0] == run_service_module.PLAYBOOK_DEPLOYMENT
    parameters = dispatch.call_args.kwargs["parameters"]
    assert parameters["playbook"] == library_playbook.doc.model_dump(mode="json")
    assert parameters["config"] == library_playbook.default_config
    assert parameters["record"] == {"url": _store_url(project), "uuid": str(_REVISION_UUID)}
    assert isinstance(parameters["catalogue"], str)
    assert "blocks" in json.loads(parameters["catalogue"])


def test_create_run_uses_an_explicitly_supplied_config_instead_of_the_default(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, mock_s3_client
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    dispatch = MagicMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    service = _dispatching_service(db, mock_s3_client)
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    custom_config = {**default_config, "expansion_overnight": {"period": 2050}}

    # When
    service.create_run(
        project_uuid=project.uuid,
        playbook=_LIBRARY_PLAYBOOK,
        config=custom_config,
        store_url=_store_url(project),
        revision_uuid=_REVISION_UUID,
        user=_existing_user(),
    )

    # Then
    assert dispatch.call_args.kwargs["parameters"]["config"] == custom_config


def test_create_run_logs_orphaned_flow_run_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_class,
    mock_s3_client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Given
    project = _existing_project()
    user = _existing_user()
    db = mock_db_class(query_results={Project: project})
    flow_run_id = uuid4()
    db.commit.side_effect = RuntimeError("connection lost")
    monkeypatch.setattr(
        run_service_module,
        "run_deployment",
        MagicMock(return_value=SimpleNamespace(id=flow_run_id)),
    )
    service = _dispatching_service(db, mock_s3_client)

    # When/Then
    with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            store_url=_store_url(project),
            revision_uuid=_REVISION_UUID,
            user=user,
        )
    assert str(flow_run_id) in caplog.text
    assert str(project.uuid) in caplog.text


def test_create_run_with_unknown_project_raises_404(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    db = mock_db_class(query_results={Project: None})
    monkeypatch.setattr(run_service_module, "run_deployment", MagicMock())
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=uuid4(),
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            store_url=_RECORD_URL,
            revision_uuid=_REVISION_UUID,
            user=_existing_user(),
        )
    assert exc_info.value.status_code == 404


def test_create_run_with_unknown_playbook_raises_404(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    dispatch = MagicMock()
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=project.uuid,
            playbook="does-not-exist",
            config=None,
            store_url=_RECORD_URL,
            revision_uuid=_REVISION_UUID,
            user=_existing_user(),
        )
    assert exc_info.value.status_code == 404
    # And no run was ever dispatched for a playbook that doesn't exist.
    dispatch.assert_not_called()


def test_create_run_refuses_a_config_with_issues_before_minting_or_dispatching_a_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given the library's config switched to its myopic branch, whose expansion needs
    # a period dimension the playbook's data does not have
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    dispatch = MagicMock()
    mint_run_uuid = MagicMock(side_effect=uuid4)
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    monkeypatch.setattr(run_service_module, "uuid4", mint_run_uuid)
    service = RunService(
        db=db, playbook_service=_library_playbook_service(), user_service=UserService(db)
    )
    default_config = library_playbooks()[_LIBRARY_PLAYBOOK].default_config
    myopic_config = {**default_config, "globals": {"expansion_mode": "myopic"}}

    # When
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=myopic_config,
            store_url=_RECORD_URL,
            revision_uuid=_REVISION_UUID,
            user=_existing_user(),
        )

    # Then it is refused with every issue, each pointing at the step it is about...
    assert exc_info.value.status_code == 422
    detail = exc_info.value.detail
    assert detail["message"] == f"Playbook {_LIBRARY_PLAYBOOK!r} cannot run with this config"
    [issue] = detail["issues"]
    assert issue["kind"] == "dims"
    assert issue["step_path"] == ["expansion_myopic"]
    assert issue["config_path"] is None
    assert "'period'" in issue["message"]
    # ...and no run was minted, dispatched or persisted.
    mint_run_uuid.assert_not_called()
    dispatch.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "store_url",
    [
        f"s3://{_BUCKET}/{uuid4()}/store",
        "s3://other-bucket/{project_uuid}/store",
        "file:///{project_uuid}/store",
    ],
    ids=["other_project", "other_bucket", "not_s3"],
)
def test_create_run_rejects_a_store_outside_the_projects_storage(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, mock_s3_client, store_url: str
) -> None:
    # Given
    project = _existing_project()
    dispatch = MagicMock()
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    service = _dispatching_service(mock_db_class(query_results={Project: project}), mock_s3_client)

    # When/Then
    with pytest.raises(AuthorizationError):
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            store_url=store_url.format(project_uuid=project.uuid),
            revision_uuid=_REVISION_UUID,
            user=_existing_user(),
        )
    mock_s3_client.head_object.assert_not_called()
    dispatch.assert_not_called()


def test_create_run_with_unknown_revision_raises_404(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, mock_s3_client
) -> None:
    # Given a store in the project's storage that has no such revision
    project = _existing_project()
    dispatch = MagicMock()
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
    )
    service = _dispatching_service(mock_db_class(query_results={Project: project}), mock_s3_client)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            store_url=_store_url(project),
            revision_uuid=_REVISION_UUID,
            user=_existing_user(),
        )
    assert exc_info.value.status_code == 404
    mock_s3_client.head_object.assert_called_once_with(
        Bucket=_BUCKET, Key=f"{project.uuid}/store/layers/{_REVISION_UUID}/manifest.json"
    )
    dispatch.assert_not_called()


def test_get_run_returns_dto_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    user = _existing_user()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    started_with_config = {
        "globals": {"expansion_mode": "overnight"},
        "expansion_overnight": {"period": 2050},
    }
    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=_fake_flow_run("COMPLETED", started_with_config))
    )
    _patch_get_client(monkeypatch, fake_client)
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run(run_uuid=run.uuid, user=user)

    # Then
    assert result.uuid == run.uuid
    assert result.project_uuid == project.uuid
    assert result.playbook == _LIBRARY_PLAYBOOK
    # The config is whatever the run was dispatched with, read back from Prefect.
    assert result.config == started_with_config
    assert result.data_record == DataRecordResult(
        store_url=_RECORD_URL, revision_uuid=_REVISION_UUID
    )
    assert result.status == "COMPLETED"
    assert result.created_at == run.created_at


def test_get_run_returns_dto_with_non_completed_status(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run whose flow is in a non-COMPLETED terminal state
    project = _existing_project()
    user = _existing_user()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    fake_client = MagicMock(read_flow_run=MagicMock(return_value=_fake_flow_run("CRASHED")))
    _patch_get_client(monkeypatch, fake_client)
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run(run_uuid=run.uuid, user=user)

    # Then the status is surfaced as-is, not silently coerced to COMPLETED
    assert result.status == "CRASHED"


def test_get_run_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run(run_uuid=uuid4(), user=_existing_user())
    assert exc_info.value.status_code == 404


def test_list_runs_returns_project_runs_with_prefect_statuses(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    first_run = _existing_run(project)
    second_run = _existing_run(project)
    second_run.id = 2
    second_run.uuid = uuid4()
    second_run.prefect_flow_run_id = uuid4()
    db = mock_db_class(query_results={Project: project, Run: [first_run, second_run]})
    monkeypatch.setattr(
        run_service_module,
        "_read_flow_runs",
        MagicMock(
            return_value={
                first_run.prefect_flow_run_id: _fake_flow_run("COMPLETED", {"cluster": {}}),
                second_run.prefect_flow_run_id: _fake_flow_run("RUNNING", {"dispatch": {}}),
            }
        ),
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.list_runs(
        project_uuid=project.uuid,
        limit=10,
        offset=0,
        status_filters=None,
        user=_existing_user(),
    )

    # Then
    assert result.total == 2
    assert result.limit == 10
    assert result.offset == 0
    assert result.summary.total == 2
    assert result.summary.statuses == {"COMPLETED": 1, "RUNNING": 1}
    assert [run.uuid for run in result.items] == [first_run.uuid, second_run.uuid]
    assert [run.project_uuid for run in result.items] == [project.uuid, project.uuid]
    assert [run.playbook for run in result.items] == [_LIBRARY_PLAYBOOK, _LIBRARY_PLAYBOOK]
    assert [run.status for run in result.items] == ["COMPLETED", "RUNNING"]
    assert [run.config for run in result.items] == [{"cluster": {}}, {"dispatch": {}}]
    assert [run.created_at for run in result.items] == [first_run.created_at, second_run.created_at]


def test_list_runs_filters_project_runs_by_status(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    completed_run = _existing_run(project)
    running_run = _existing_run(project)
    running_run.id = 2
    running_run.uuid = uuid4()
    running_run.prefect_flow_run_id = uuid4()
    db = mock_db_class(query_results={Project: project, Run: [completed_run, running_run]})
    monkeypatch.setattr(
        run_service_module,
        "_read_flow_runs",
        MagicMock(
            return_value={
                completed_run.prefect_flow_run_id: _fake_flow_run("COMPLETED"),
                running_run.prefect_flow_run_id: _fake_flow_run("RUNNING"),
            }
        ),
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.list_runs(
        project_uuid=project.uuid,
        limit=10,
        offset=0,
        status_filters=["running"],
        user=_existing_user(),
    )

    # Then
    assert result.total == 1
    assert result.summary.total == 2
    assert result.summary.statuses == {"COMPLETED": 1, "RUNNING": 1}
    assert [run.uuid for run in result.items] == [running_run.uuid]
    assert [run.status for run in result.items] == ["RUNNING"]


def test_get_run_summary_returns_project_status_counts(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    running_run = _existing_run(project)
    completed_run = _existing_run(project)
    completed_run.id = 2
    completed_run.uuid = uuid4()
    completed_run.prefect_flow_run_id = uuid4()
    failed_run = _existing_run(project)
    failed_run.id = 3
    failed_run.uuid = uuid4()
    failed_run.prefect_flow_run_id = uuid4()
    queued_run = _existing_run(project)
    queued_run.id = 4
    queued_run.uuid = uuid4()
    queued_run.prefect_flow_run_id = uuid4()
    unknown_run = _existing_run(project)
    unknown_run.id = 5
    unknown_run.uuid = uuid4()
    unknown_run.prefect_flow_run_id = uuid4()
    db = mock_db_class(
        query_results={
            Project: project,
            Run: [running_run, completed_run, failed_run, queued_run, unknown_run],
        }
    )
    monkeypatch.setattr(
        run_service_module,
        "_read_flow_runs",
        MagicMock(
            return_value={
                running_run.prefect_flow_run_id: _fake_flow_run("RUNNING"),
                completed_run.prefect_flow_run_id: _fake_flow_run("COMPLETED"),
                failed_run.prefect_flow_run_id: _fake_flow_run("CRASHED"),
                queued_run.prefect_flow_run_id: _fake_flow_run("SCHEDULED"),
                unknown_run.prefect_flow_run_id: _fake_flow_run("LATE"),
            }
        ),
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_summary(project_uuid=project.uuid, user=_existing_user())

    # Then
    assert result.total == 5
    assert result.statuses == {
        "RUNNING": 1,
        "COMPLETED": 1,
        "CRASHED": 1,
        "SCHEDULED": 1,
        "LATE": 1,
    }


def test_get_run_summary_with_unknown_project_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Project: None})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run_summary(project_uuid=uuid4(), user=_existing_user())
    assert exc_info.value.status_code == 404


def test_list_runs_with_unknown_project_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Project: None})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.list_runs(
            project_uuid=uuid4(), limit=10, offset=0, status_filters=None, user=_existing_user()
        )
    assert exc_info.value.status_code == 404


def _fake_playbook_flow_run(state_type: str, config: dict, playbook_doc: dict | None = None):
    """The playbook's own flow run, carrying the parameters it was dispatched with."""
    if playbook_doc is None:
        playbook_doc = library_playbooks()[_LIBRARY_PLAYBOOK].doc.model_dump(mode="json")
    return SimpleNamespace(
        id=uuid4(),
        state=SimpleNamespace(type=SimpleNamespace(value=state_type)),
        parameters={
            "playbook": playbook_doc,
            "config": config,
            "record": {"url": _RECORD_URL, "uuid": str(_REVISION_UUID)},
            "catalogue": catalogue_parameter(library_catalogue()),
        },
    )


def _fake_block_run(
    step_name: str, block: str, state_type: str, created: datetime, message: str | None = None
):
    return SimpleNamespace(
        id=uuid4(),
        state=SimpleNamespace(type=SimpleNamespace(value=state_type), message=message),
        parameters={"step_name": step_name, "block": block},
        created=created,
        start_time=created,
        end_time=created if state_type == "COMPLETED" else None,
    )


def _fake_output_artifact(block_run, record: dict):
    """The table artifact a block run publishes its output record as (see
    runner.flows.run_block)."""
    return SimpleNamespace(flow_run_id=block_run.id, data=json.dumps([record]))


def _patch_flow_runs(
    monkeypatch: pytest.MonkeyPatch, playbook_flow_run, block_runs, artifacts=()
) -> MagicMock:
    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=playbook_flow_run),
        read_flow_runs=MagicMock(return_value=block_runs),
        read_artifacts=MagicMock(return_value=list(artifacts)),
    )
    _patch_get_client(monkeypatch, fake_client)
    return fake_client


def test_get_run_steps_reports_every_step_with_its_own_status(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run of the library playbook under its default config (overnight
    # expansion), part-way through: overnight expansion running
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    started = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    fake_client = _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("RUNNING", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        [
            _fake_block_run(
                "expansion_overnight", "overnight_capacity_expansion", "RUNNING", started
            ),
        ],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then every step of the playbook is reported, in playbook order
    assert result.uuid == run.uuid
    assert result.run_status == "RUNNING"
    assert [(step.name, step.block, step.status) for step in result.steps] == [
        ("expansion_overnight", "overnight_capacity_expansion", "RUNNING"),
        # Their `when` is false for this run's config, so they never run.
        ("expansion_myopic", "myopic_capacity_expansion", "SKIPPED"),
        ("expansion_perfect", "perfect_capacity_expansion", "SKIPPED"),
    ]
    assert result.steps[0].start_time == started
    assert result.steps[0].end_time is None
    assert result.steps[1].start_time is None
    assert result.steps[1].end_time is None

    # And the block runs were looked up as children of the playbook's flow run
    flow_run_filter = fake_client.read_flow_runs.call_args.kwargs["flow_run_filter"]
    assert flow_run_filter.parent_flow_run_id.any_ == [run.prefect_flow_run_id]


def test_get_run_steps_decides_skipped_steps_from_the_runs_own_config(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run started in myopic mode, with nothing dispatched yet
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("PENDING", {"globals": {"expansion_mode": "myopic"}}),
        [],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then the overnight branch is the one skipped this time
    assert {step.name: step.status for step in result.steps} == {
        "expansion_overnight": "SKIPPED",
        "expansion_myopic": "NOT_STARTED",
        "expansion_perfect": "SKIPPED",
    }


def test_get_run_steps_reports_the_latest_block_run_of_a_step_run_twice(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a step with two block runs, e.g. after the playbook run was retried
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    first = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    second = datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("RUNNING", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        # Deliberately newest first, so list order can't be what decides it.
        [
            _fake_block_run(
                "expansion_overnight", "overnight_capacity_expansion", "COMPLETED", second
            ),
            _fake_block_run("expansion_overnight", "overnight_capacity_expansion", "FAILED", first),
        ],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then
    assert result.steps[0].status == "COMPLETED"
    assert result.steps[0].start_time == second


def test_get_run_steps_reports_the_output_record_each_block_run_published(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run whose overnight expansion has completed, writing a new revision
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    block_run = _fake_block_run(
        "expansion_overnight",
        "overnight_capacity_expansion",
        "COMPLETED",
        datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )
    output_uuid = uuid4()
    fake_client = _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("COMPLETED", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        [block_run],
        [_fake_output_artifact(block_run, {"url": _store_url(project), "uuid": str(output_uuid)})],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then the completed step reports its record, and the steps that never ran none
    outputs = {step.name: step.output for step in result.steps}
    assert outputs.pop("expansion_overnight") == DataRecordResult(
        store_url=_store_url(project), revision_uuid=output_uuid
    )
    assert set(outputs.values()) == {None}
    # ...read in one call, for the run's own block runs' output artifacts only
    artifact_filter = fake_client.read_artifacts.call_args.kwargs["artifact_filter"]
    assert artifact_filter.flow_run_id.any_ == [block_run.id]
    assert artifact_filter.key.any_ == [OUTPUT_ARTIFACT_KEY]


def test_get_run_steps_reads_no_artifacts_before_any_block_has_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run with nothing dispatched yet
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    fake_client = _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("PENDING", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        [],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then
    assert {step.output for step in result.steps} == {None}
    fake_client.read_artifacts.assert_not_called()


def test_get_run_steps_reports_why_a_step_failed(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run whose overnight expansion failed to solve
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    message = "Flow run encountered an exception: SolveError: solver status infeasible"
    _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("FAILED", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        [
            _fake_block_run(
                "expansion_overnight",
                "overnight_capacity_expansion",
                "FAILED",
                datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
                message=message,
            ),
        ],
    )
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then the failed step carries the block's own error, the others nothing
    assert [step.message for step in result.steps] == [message, None, None]


def test_get_run_steps_reports_a_nested_playbook_step_as_unknown(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run of a playbook with a step that runs another playbook
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    playbook_doc = {
        "name": "outer",
        "steps": [
            {"name": "cluster", "block": "cluster_time"},
            {
                "name": "inner",
                "playbook": {
                    "name": "inner",
                    "steps": [{"name": "dispatch", "block": "rolling_horizon_dispatch"}],
                },
            },
        ],
    }
    _patch_flow_runs(monkeypatch, _fake_playbook_flow_run("RUNNING", {}, playbook_doc), [])
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then the nested step is listed without a block, and without a status it
    # can't actually know
    assert [(step.name, step.block, step.status) for step in result.steps] == [
        ("cluster", "cluster_time", "NOT_STARTED"),
        ("inner", None, "UNKNOWN"),
    ]


def test_get_run_steps_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run_steps(run_uuid=uuid4(), user=_existing_user())
    assert exc_info.value.status_code == 404


def test_get_run_steps_rejects_non_owner(mock_db_class) -> None:
    # Given a run whose project is owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    run = _existing_run(project)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Run: run, Project: project})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run_steps(run_uuid=run.uuid, user=other_user)


def test_get_run_logs_returns_logs_and_status_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_class,
) -> None:
    # Given
    project = _existing_project()
    user = _existing_user()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=_fake_flow_run("RUNNING")),
        read_logs=MagicMock(
            return_value=[SimpleNamespace(message="line 1"), SimpleNamespace(message="line 2")]
        ),
    )
    _patch_get_client(monkeypatch, fake_client)
    service = RunService(db=db, user_service=UserService(db))

    # When
    result = service.get_run_logs(run_uuid=run.uuid, user=user)

    # Then
    assert result.uuid == run.uuid
    assert result.logs == ["line 1", "line 2"]
    assert result.run_status == "RUNNING"


def test_get_run_logs_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run_logs(run_uuid=uuid4(), user=_existing_user())
    assert exc_info.value.status_code == 404


def test_create_run_rejects_non_owner(monkeypatch: pytest.MonkeyPatch, mock_db_class) -> None:
    # Given a project owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Project: project})
    monkeypatch.setattr(run_service_module, "run_deployment", MagicMock())
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            store_url=_RECORD_URL,
            revision_uuid=_REVISION_UUID,
            user=other_user,
        )


def test_list_runs_rejects_non_owner(mock_db_class) -> None:
    # Given a project owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Project: project})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.list_runs(
            project_uuid=project.uuid, limit=10, offset=0, status_filters=None, user=other_user
        )


def test_get_run_summary_rejects_non_owner(mock_db_class) -> None:
    # Given a project owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Project: project})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run_summary(project_uuid=project.uuid, user=other_user)


def test_get_run_rejects_non_owner(mock_db_class) -> None:
    # Given a run whose project is owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    run = _existing_run(project)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Run: run, Project: project})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run(run_uuid=run.uuid, user=other_user)


def test_get_run_logs_rejects_non_owner(mock_db_class) -> None:
    # Given a run whose project is owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    run = _existing_run(project)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Run: run, Project: project})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run_logs(run_uuid=run.uuid, user=other_user)


def test_delete_flow_runs_deletes_block_runs_then_the_playbook_run(
    monkeypatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    block_a, block_b = uuid4(), uuid4()
    client = MagicMock()
    client.read_flow_runs.return_value = [SimpleNamespace(id=block_a), SimpleNamespace(id=block_b)]
    _patch_get_client(monkeypatch, client)
    db = mock_db_class(query_results={Run: [run]})
    service = RunService(db=db, user_service=UserService(db))

    # When
    service.delete_flow_runs(project, _existing_user())

    # Then
    deleted = [call.args[0] for call in client.delete_flow_run.call_args_list]
    assert deleted == [block_a, block_b, run.prefect_flow_run_id]


def test_delete_flow_runs_skips_flow_runs_that_are_already_gone(monkeypatch, mock_db_class) -> None:
    # Given
    project = _existing_project()
    first, second = _existing_run(project), _existing_run(project)
    client = MagicMock()
    client.read_flow_runs.return_value = []
    client.delete_flow_run.side_effect = [run_service_module.ObjectNotFound(Exception()), None]
    _patch_get_client(monkeypatch, client)
    db = mock_db_class(query_results={Run: [first, second]})
    service = RunService(db=db, user_service=UserService(db))

    # When
    service.delete_flow_runs(project, _existing_user())

    # Then
    assert [call.args[0] for call in client.delete_flow_run.call_args_list] == [
        first.prefect_flow_run_id,
        second.prefect_flow_run_id,
    ]


def test_delete_flow_runs_rejects_non_owner(monkeypatch) -> None:
    # Given a project owned by someone other than the requesting user
    client = MagicMock()
    _patch_get_client(monkeypatch, client)

    # When/Then nothing is touched in Prefect
    with pytest.raises(AuthorizationError):
        RunService(db=MagicMock(), user_service=UserService(MagicMock())).delete_flow_runs(
            _existing_project(owner_id=1), _existing_user(user_id=2)
        )
    client.delete_flow_run.assert_not_called()


def _flow_run_in_state(is_final: bool | None):
    state = None if is_final is None else SimpleNamespace(is_final=lambda: is_final)
    return SimpleNamespace(state=state)


@pytest.mark.parametrize("is_final", [None, False], ids=["unknown_state", "not_final"])
def test_ensure_no_active_runs_rejects_an_active_run(monkeypatch, mock_db_class, is_final) -> None:
    # Given
    project = _existing_project()
    done, active = _existing_run(project), _existing_run(project)
    flow_runs = {
        done.prefect_flow_run_id: _flow_run_in_state(True),
        active.prefect_flow_run_id: _flow_run_in_state(is_final),
    }
    monkeypatch.setattr(run_service_module, "_read_existing_flow_runs", lambda ids: flow_runs)
    db = mock_db_class(query_results={Run: [done, active]})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.ensure_no_active_runs(project, _existing_user())
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Only projects without active runs can be deleted"


def test_ensure_no_active_runs_accepts_finished_runs(monkeypatch, mock_db_class) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    flow_runs = {run.prefect_flow_run_id: _flow_run_in_state(True)}
    monkeypatch.setattr(run_service_module, "_read_existing_flow_runs", lambda ids: flow_runs)
    db = mock_db_class(query_results={Run: [run]})
    service = RunService(db=db, user_service=UserService(db))

    # When/Then
    service.ensure_no_active_runs(project, _existing_user())


def _ensure_no_active_runs_with(monkeypatch, mock_db_class, flow_run_reads: dict):
    """Runs the preflight for a project with one run per key of `flow_run_reads`; each value
    is what reading that run's flow run from Prefect gives (a flow run, or an exception)."""
    project = _existing_project()
    runs = [_existing_run(project) for _ in flow_run_reads]
    outcomes = {
        run.prefect_flow_run_id: outcome
        for run, outcome in zip(runs, flow_run_reads.values(), strict=True)
    }

    def read_flow_run(flow_run_id):
        outcome = outcomes[flow_run_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = MagicMock()
    client.read_flow_run.side_effect = read_flow_run
    _patch_get_client(monkeypatch, client)
    db = mock_db_class(query_results={Run: runs})
    RunService(db=db, user_service=UserService(db)).ensure_no_active_runs(project, _existing_user())


def _not_found() -> Exception:
    return run_service_module.ObjectNotFound(Exception())


def test_ensure_no_active_runs_skips_flow_runs_prefect_no_longer_has(
    monkeypatch, mock_db_class
) -> None:
    # When/Then a retried delete is not blocked by flow runs its earlier attempt removed
    _ensure_no_active_runs_with(
        monkeypatch, mock_db_class, {"gone": _not_found(), "done": _flow_run_in_state(True)}
    )


def test_ensure_no_active_runs_still_rejects_an_active_run_next_to_a_missing_one(
    monkeypatch, mock_db_class
) -> None:
    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _ensure_no_active_runs_with(
            monkeypatch,
            mock_db_class,
            {"gone": _not_found(), "active": _flow_run_in_state(False)},
        )
    assert exc_info.value.status_code == 409


def test_ensure_no_active_runs_rejects_a_run_with_an_unknown_state(
    monkeypatch, mock_db_class
) -> None:
    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _ensure_no_active_runs_with(
            monkeypatch, mock_db_class, {"unknown": _flow_run_in_state(None)}
        )
    assert exc_info.value.status_code == 409


def test_ensure_no_active_runs_propagates_other_prefect_errors(monkeypatch, mock_db_class) -> None:
    # When/Then an outage is not mistaken for "nothing active"
    with pytest.raises(RuntimeError, match="prefect down"):
        _ensure_no_active_runs_with(
            monkeypatch, mock_db_class, {"broken": RuntimeError("prefect down")}
        )


def test_ensure_no_active_runs_rejects_non_owner() -> None:
    # When/Then
    with pytest.raises(AuthorizationError):
        RunService(db=MagicMock(), user_service=UserService(MagicMock())).ensure_no_active_runs(
            _existing_project(owner_id=1), _existing_user(user_id=2)
        )
