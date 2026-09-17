from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from manta.entities import Project, Run
from manta.services import run_service as run_service_module
from manta.services.run_service import RunService


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


def _fake_flow_run(state_type: str):
    # `_flow_run_status` reads `flow_run.state.type.value`.
    return SimpleNamespace(state=SimpleNamespace(type=SimpleNamespace(value=state_type)))


def _existing_project() -> Project:
    project = Project(name="North Sea Wind")
    project.id = 1
    project.uuid = uuid4()
    project.created_at = datetime.now(UTC)
    return project


def _existing_run(project: Project) -> Run:
    run = Run(project_id=project.id, prefect_flow_run_id=uuid4())
    run.id = 1
    run.uuid = uuid4()
    run.created_at = datetime.now(UTC)
    return run


def test_create_run_persists_a_run_and_returns_its_dto(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    flow_run_id = uuid4()
    # `run_deployment` runs synchronously when called from a sync context (see
    # the comment in `RunService.create_run`) — a plain `MagicMock`, not
    # `AsyncMock`, mirrors that real call shape.
    monkeypatch.setattr(
        run_service_module,
        "run_deployment",
        MagicMock(return_value=SimpleNamespace(id=flow_run_id)),
    )
    service = RunService(db=db)

    # When
    result = service.create_run(project_uuid=project.uuid, num_pi_digits=1_000)

    # Then
    db.add.assert_called_once()
    db.commit.assert_called_once()
    persisted_run = db.add.call_args.args[0]
    assert isinstance(persisted_run, Run)
    assert persisted_run.project_id == project.id
    assert persisted_run.prefect_flow_run_id == flow_run_id
    assert result.uuid == db.uuid
    assert result.project_uuid == project.uuid
    assert result.created_at == db.created_at


def test_create_run_logs_orphaned_flow_run_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, caplog: pytest.LogCaptureFixture
) -> None:
    # Given
    project = _existing_project()
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
        service.create_run(project_uuid=project.uuid, num_pi_digits=1_000)
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
        service.create_run(project_uuid=uuid4(), num_pi_digits=1_000)
    assert exc_info.value.status_code == 404


def test_get_run_returns_dto_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    fake_client = MagicMock(read_flow_run=MagicMock(return_value=_fake_flow_run("COMPLETED")))
    _patch_get_client(monkeypatch, fake_client)
    service = RunService(db=db)

    # When
    result = service.get_run(run_uuid=run.uuid)

    # Then
    assert result.uuid == run.uuid
    assert result.project_uuid == project.uuid
    assert result.status == "COMPLETED"
    assert result.created_at == run.created_at


def test_get_run_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})
    service = RunService(db=db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.get_run(run_uuid=uuid4())
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
                first_run.prefect_flow_run_id: _fake_flow_run("COMPLETED"),
                second_run.prefect_flow_run_id: _fake_flow_run("RUNNING"),
            }
        ),
    )
    service = RunService(db=db)

    # When
    result = service.list_runs(project_uuid=project.uuid, limit=10, offset=0, status_filters=None)

    # Then
    assert result.total == 2
    assert result.limit == 10
    assert result.offset == 0
    assert result.summary.total == 2
    assert result.summary.statuses == {"COMPLETED": 1, "RUNNING": 1}
    assert [run.uuid for run in result.items] == [first_run.uuid, second_run.uuid]
    assert [run.project_uuid for run in result.items] == [project.uuid, project.uuid]
    assert [run.status for run in result.items] == ["COMPLETED", "RUNNING"]
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
        project_uuid=project.uuid, limit=10, offset=0, status_filters=["running"]
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
    result = service.get_run_summary(project_uuid=project.uuid)

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
        service.get_run_summary(project_uuid=uuid4())
    assert exc_info.value.status_code == 404


def test_list_runs_with_unknown_project_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Project: None})
    service = RunService(db=db)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.list_runs(project_uuid=uuid4(), limit=10, offset=0, status_filters=None)
    assert exc_info.value.status_code == 404


def test_get_run_logs_returns_logs_and_status_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_class,
) -> None:
    # Given
    project = _existing_project()
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
    result = service.get_run_logs(run_uuid=run.uuid)

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
        service.get_run_logs(run_uuid=uuid4())
    assert exc_info.value.status_code == 404


# --- Playbook runs ---


def _playbook_run_service(db, monkeypatch=None, flow_run_id=None, storage=None) -> RunService:
    from manta.services.playbook_service import PlaybookService

    if storage is None:
        storage = MagicMock()
        storage.bucket = "manta"
        storage.file_exists.return_value = True
        storage.copy_file.side_effect = lambda project_uuid, src, dest: f"{project_uuid}/{dest}"
    if monkeypatch is not None:
        monkeypatch.setattr(
            run_service_module,
            "run_deployment",
            MagicMock(return_value=SimpleNamespace(id=flow_run_id or uuid4())),
        )
    return RunService(db=db, storage=storage, playbooks=PlaybookService())


def test_create_playbook_run_validates_copies_input_and_dispatches(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    flow_run_id = uuid4()
    service = _playbook_run_service(db, monkeypatch, flow_run_id)

    # When
    result = service.create_playbook_run(
        project_uuid=project.uuid,
        playbook_name="cluster-expand-dispatch",
        config=None,  # falls back to the playbook's default config
        input_file="network.nc",
    )

    # Then: the input was copied into the run's own prefix...
    copy_args = service.storage.copy_file.call_args.args
    assert copy_args[0] == project.uuid
    assert copy_args[1] == "network.nc"
    assert copy_args[2].startswith("runs/") and copy_args[2].endswith("/input/network.nc")

    # ...the deployment got the document, config, input record, and output prefix...
    dispatch = run_service_module.run_deployment.call_args
    assert dispatch.args[0] == run_service_module.PLAYBOOK_DEPLOYMENT
    parameters = dispatch.kwargs["parameters"]
    assert parameters["playbook"]["name"] == "cluster-expand-dispatch"
    assert parameters["config"]["globals"]["expansion_mode"] == "overnight"
    assert parameters["record"]["url"] == f"s3://manta/{project.uuid}/{copy_args[2]}"
    run_prefix = copy_args[2].removesuffix("/input/network.nc")
    assert parameters["output_prefix"] == f"s3://manta/{project.uuid}/{run_prefix}/steps"

    # ...and the run row records everything needed to reproduce it.
    persisted_run = db.add.call_args.args[0]
    assert persisted_run.playbook_name == "cluster-expand-dispatch"
    assert persisted_run.playbook_doc == parameters["playbook"]
    assert persisted_run.playbook_config == parameters["config"]
    assert persisted_run.input_url == parameters["record"]["url"]
    assert persisted_run.output_prefix == parameters["output_prefix"]
    assert persisted_run.prefect_flow_run_id == flow_run_id
    assert result.playbook_name == "cluster-expand-dispatch"


def test_create_playbook_run_refuses_an_invalid_config_before_dispatching(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given: a config whose cluster settings cannot be right (proposal: catch
    # workflow errors early).
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    service = _playbook_run_service(db, monkeypatch)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_playbook_run(
            project_uuid=project.uuid,
            playbook_name="cluster-expand-dispatch",
            config={
                "globals": {"expansion_mode": "overnight"},
                "cluster": {"n_hours": "not-a-number"},
                "expansion_overnight": {},
                "expansion_myopic": {},
                "dispatch": {},
            },
            input_file="network.nc",
        )
    assert exc_info.value.status_code == 422
    issues = exc_info.value.detail["issues"]
    assert issues[0]["step"] == "cluster"
    assert issues[0]["field"] == ["n_hours"]
    # Nothing was copied or started for a run that cannot work.
    run_service_module.run_deployment.assert_not_called()
    service.storage.copy_file.assert_not_called()
    db.add.assert_not_called()


def test_create_playbook_run_with_unknown_playbook_raises_404(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    service = _playbook_run_service(db, monkeypatch)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_playbook_run(
            project_uuid=project.uuid,
            playbook_name="not-a-playbook",
            config=None,
            input_file="network.nc",
        )
    assert exc_info.value.status_code == 404


def test_create_playbook_run_with_missing_input_file_raises_404(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    db = mock_db_class(query_results={Project: project})
    service = _playbook_run_service(db, monkeypatch)
    service.storage.file_exists.return_value = False

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_playbook_run(
            project_uuid=project.uuid,
            playbook_name="cluster-expand-dispatch",
            config=None,
            input_file="gone.nc",
        )
    assert exc_info.value.status_code == 404
    run_service_module.run_deployment.assert_not_called()


def test_get_run_steps_reports_each_child_flow_run(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run})

    def _child(name: str, created: int, state: str):
        return SimpleNamespace(
            name=name,
            id=uuid4(),
            created=created,
            state=SimpleNamespace(type=SimpleNamespace(value=state)),
        )

    fake_client = MagicMock(
        read_flow_run=MagicMock(return_value=_fake_flow_run("RUNNING")),
        read_flow_runs=MagicMock(
            return_value=[
                _child("expansion[overnight_capacity_expansion]", 2, "RUNNING"),
                _child("cluster[cluster_time]", 1, "COMPLETED"),
            ]
        ),
    )
    _patch_get_client(monkeypatch, fake_client)
    service = _playbook_run_service(db)

    # When
    result = service.get_run_steps(run_uuid=run.uuid)

    # Then: steps come back in start order, with their own states.
    assert result.run_status == "RUNNING"
    assert [(step.name, step.status) for step in result.steps] == [
        ("cluster[cluster_time]", "COMPLETED"),
        ("expansion[overnight_capacity_expansion]", "RUNNING"),
    ]


def test_get_run_outputs_lists_the_runs_files_without_transport_records(
    mock_db_class,
) -> None:
    # Given
    from datetime import datetime

    from manta.services.results.s3_file_result import GetS3FileResult

    project = _existing_project()
    run = _existing_run(project)
    run.output_prefix = f"s3://manta/{project.uuid}/runs/{run.uuid}/steps"
    db = mock_db_class(query_results={Run: run, Project: project})
    service = _playbook_run_service(db)

    def _file(key: str) -> GetS3FileResult:
        return GetS3FileResult(key=key, size=1, last_modified=datetime.now(UTC))

    service.storage.list_files.return_value = [
        _file(f"{project.uuid}/runs/{run.uuid}/input/network.nc"),
        _file(f"{project.uuid}/runs/{run.uuid}/steps/cluster.nc"),
        _file(f"{project.uuid}/runs/{run.uuid}/steps/cluster.record.json"),
    ]

    # When
    result = service.get_run_outputs(run_uuid=run.uuid)

    # Then
    service.storage.list_files.assert_called_once_with(project.uuid, prefix=f"runs/{run.uuid}/")
    assert [item.key for item in result.items] == [
        f"{project.uuid}/runs/{run.uuid}/input/network.nc",
        f"{project.uuid}/runs/{run.uuid}/steps/cluster.nc",
    ]


def test_get_run_outputs_for_a_legacy_run_is_empty(mock_db_class) -> None:
    # Given: a run from before playbooks (no output prefix recorded).
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    service = _playbook_run_service(db)

    # When
    result = service.get_run_outputs(run_uuid=run.uuid)

    # Then
    assert result.items == []
    service.storage.list_files.assert_not_called()
