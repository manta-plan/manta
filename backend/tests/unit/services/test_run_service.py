import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks
from runner.flows import catalogue_parameter

from manta.entities import Project, Run, User
from manta.services import run_service as run_service_module
from manta.services.errors import AuthorizationError
from manta.services.run_service import RunService

_LIBRARY_PLAYBOOK = "cluster-expand-dispatch"
_RECORD_URL = "s3://bucket/in.nc"


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
        parameters={"config": config if config is not None else {}},
    )


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


def _existing_run(project: Project) -> Run:
    run = Run(project_id=project.id, prefect_flow_run_id=uuid4(), playbook=_LIBRARY_PLAYBOOK)
    run.id = 1
    run.uuid = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def test_create_run_persists_a_run_and_returns_its_dto(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
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
    service = RunService(db=db)

    # When
    result = service.create_run(
        project_uuid=project.uuid,
        playbook=_LIBRARY_PLAYBOOK,
        config=None,
        data_record_url=_RECORD_URL,
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
    # data, an output prefix scoped to this project, and the catalogue encoded
    # as a JSON string (never a dict — see runner.flows.catalogue_parameter).
    library_playbook = library_playbooks()[_LIBRARY_PLAYBOOK]
    assert dispatch.call_args.args[0] == run_service_module.PLAYBOOK_DEPLOYMENT
    parameters = dispatch.call_args.kwargs["parameters"]
    assert parameters["playbook"] == library_playbook.doc.model_dump(mode="json")
    assert parameters["config"] == library_playbook.default_config
    assert parameters["record"] == {"url": _RECORD_URL}
    output_prefix = parameters["output_prefix"]
    assert output_prefix.startswith("s3://")
    assert output_prefix.endswith("/output")
    assert str(project.uuid) in output_prefix
    assert isinstance(parameters["catalogue"], str)
    assert "blocks" in json.loads(parameters["catalogue"])


def test_create_run_uses_an_explicitly_supplied_config_instead_of_the_default(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    dispatch = MagicMock(return_value=SimpleNamespace(id=uuid4()))
    monkeypatch.setattr(run_service_module, "run_deployment", dispatch)
    service = RunService(db=db)
    custom_config = {"globals": {"expansion_mode": "myopic"}}

    # When
    service.create_run(
        project_uuid=project.uuid,
        playbook=_LIBRARY_PLAYBOOK,
        config=custom_config,
        data_record_url=_RECORD_URL,
        user=_existing_user(),
    )

    # Then
    assert dispatch.call_args.kwargs["parameters"]["config"] == custom_config


def test_create_run_logs_orphaned_flow_run_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, caplog: pytest.LogCaptureFixture
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
    service = RunService(db=db)

    # When/Then
    with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            data_record_url=_RECORD_URL,
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
    service = RunService(db=db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=uuid4(),
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            data_record_url=_RECORD_URL,
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
    service = RunService(db=db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            project_uuid=project.uuid,
            playbook="does-not-exist",
            config=None,
            data_record_url=_RECORD_URL,
            user=_existing_user(),
        )
    assert exc_info.value.status_code == 404
    # And no run was ever dispatched for a playbook that doesn't exist.
    dispatch.assert_not_called()


def test_get_run_returns_dto_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    user = _existing_user()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    started_with_config = {"globals": {"expansion_mode": "overnight"}, "cluster": {"n_hours": 6}}
    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=_fake_flow_run("COMPLETED", started_with_config))
    )
    _patch_get_client(monkeypatch, fake_client)
    service = RunService(db=db)

    # When
    result = service.get_run(run_uuid=run.uuid, user=user)

    # Then
    assert result.uuid == run.uuid
    assert result.project_uuid == project.uuid
    assert result.playbook == _LIBRARY_PLAYBOOK
    # The config is whatever the run was dispatched with, read back from Prefect.
    assert result.config == started_with_config
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
    service = RunService(db=db)

    # When
    result = service.get_run(run_uuid=run.uuid, user=user)

    # Then the status is surfaced as-is, not silently coerced to COMPLETED
    assert result.status == "CRASHED"


def test_get_run_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db)

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
    service = RunService(db=db)

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
    service = RunService(db=db)

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
    service = RunService(db=db)

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
    service = RunService(db=db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run_summary(project_uuid=uuid4(), user=_existing_user())
    assert exc_info.value.status_code == 404


def test_list_runs_with_unknown_project_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Project: None})
    service = RunService(db=db)

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
            "catalogue": catalogue_parameter(library_catalogue()),
        },
    )


def _fake_block_run(step_name: str, block: str, state_type: str, created: datetime):
    return SimpleNamespace(
        state=SimpleNamespace(type=SimpleNamespace(value=state_type)),
        parameters={"step_name": step_name, "block": block},
        created=created,
        start_time=created,
        end_time=created if state_type == "COMPLETED" else None,
    )


def _patch_flow_runs(monkeypatch: pytest.MonkeyPatch, playbook_flow_run, block_runs) -> MagicMock:
    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=playbook_flow_run),
        read_flow_runs=MagicMock(return_value=block_runs),
    )
    _patch_get_client(monkeypatch, fake_client)
    return fake_client


def test_get_run_steps_reports_every_step_with_its_own_status(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given a run of the library playbook under its default config (overnight
    # expansion), part-way through: cluster done, overnight expansion running
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    started = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    fake_client = _patch_flow_runs(
        monkeypatch,
        _fake_playbook_flow_run("RUNNING", library_playbooks()[_LIBRARY_PLAYBOOK].default_config),
        [
            _fake_block_run("cluster", "cluster_time", "COMPLETED", started),
            _fake_block_run(
                "expansion_overnight", "overnight_capacity_expansion", "RUNNING", started
            ),
        ],
    )
    service = RunService(db=db)

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then every step of the playbook is reported, in playbook order
    assert result.uuid == run.uuid
    assert result.run_status == "RUNNING"
    assert [(step.name, step.block, step.status) for step in result.steps] == [
        ("cluster", "cluster_time", "COMPLETED"),
        ("expansion_overnight", "overnight_capacity_expansion", "RUNNING"),
        # Its `when` is false for this run's config, so it never runs.
        ("expansion_myopic", "myopic_capacity_expansion", "SKIPPED"),
        # It will run, but hasn't been dispatched yet.
        ("dispatch", "rolling_horizon_dispatch", "NOT_STARTED"),
    ]
    assert result.steps[0].start_time == started
    assert result.steps[0].end_time == started
    assert result.steps[3].start_time is None
    assert result.steps[3].end_time is None

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
    service = RunService(db=db)

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then the overnight branch is the one skipped this time
    assert {step.name: step.status for step in result.steps} == {
        "cluster": "NOT_STARTED",
        "expansion_overnight": "SKIPPED",
        "expansion_myopic": "NOT_STARTED",
        "dispatch": "SKIPPED",
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
            _fake_block_run("cluster", "cluster_time", "COMPLETED", second),
            _fake_block_run("cluster", "cluster_time", "FAILED", first),
        ],
    )
    service = RunService(db=db)

    # When
    result = service.get_run_steps(run_uuid=run.uuid, user=_existing_user())

    # Then
    assert result.steps[0].status == "COMPLETED"
    assert result.steps[0].start_time == second


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
    service = RunService(db=db)

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
    service = RunService(db=db)

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
    service = RunService(db=db)

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
    service = RunService(db=db)

    # When
    result = service.get_run_logs(run_uuid=run.uuid, user=user)

    # Then
    assert result.uuid == run.uuid
    assert result.logs == ["line 1", "line 2"]
    assert result.run_status == "RUNNING"


def test_get_run_logs_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db)

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
    service = RunService(db=db)

    # When/Then
    with pytest.raises(AuthorizationError):
        service.create_run(
            project_uuid=project.uuid,
            playbook=_LIBRARY_PLAYBOOK,
            config=None,
            data_record_url=_RECORD_URL,
            user=other_user,
        )


def test_list_runs_rejects_non_owner(mock_db_class) -> None:
    # Given a project owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Project: project})
    service = RunService(db=db)

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
    service = RunService(db=db)

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run_summary(project_uuid=project.uuid, user=other_user)


def test_get_run_rejects_non_owner(mock_db_class) -> None:
    # Given a run whose project is owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    run = _existing_run(project)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Run: run, Project: project})
    service = RunService(db=db)

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run(run_uuid=run.uuid, user=other_user)


def test_get_run_logs_rejects_non_owner(mock_db_class) -> None:
    # Given a run whose project is owned by someone other than the requesting user
    project = _existing_project(owner_id=1)
    run = _existing_run(project)
    other_user = _existing_user(user_id=2, username="mallory")
    db = mock_db_class(query_results={Run: run, Project: project})
    service = RunService(db=db)

    # When/Then
    with pytest.raises(AuthorizationError):
        service.get_run_logs(run_uuid=run.uuid, user=other_user)
