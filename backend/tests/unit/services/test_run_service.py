from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from manta.entities import Project, Run
from manta.services import run_service as run_service_module
from manta.services.run_service import RunService


class _FakeClientContext:
    """Async context manager standing in for the Prefect client returned by `get_client()`."""

    def __init__(self, client) -> None:
        self._client = client

    async def __aenter__(self):
        return self._client

    async def __aexit__(self, *_args) -> bool:
        return False


def _patch_get_client(monkeypatch: pytest.MonkeyPatch, client) -> None:
    monkeypatch.setattr(run_service_module, "get_client", lambda: _FakeClientContext(client))


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
    fake_client = MagicMock(read_flow_run=AsyncMock(return_value=_fake_flow_run("COMPLETED")))
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


def test_get_run_logs_returns_logs_and_status_for_a_known_run(
    monkeypatch: pytest.MonkeyPatch,
    mock_db_class,
) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    fake_client = MagicMock(
        read_flow_run=AsyncMock(return_value=_fake_flow_run("RUNNING")),
        read_logs=AsyncMock(
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
