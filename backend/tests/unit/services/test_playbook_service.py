import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from manta_blocks import BlockDescription, BlockDims, Catalogue, EnvironmentSpec

from manta.entities import Playbook, Project, Run
from manta.services import playbook_service as playbook_service_module
from manta.services.playbook_service import PlaybookService, run_storage_prefix
from manta.services.results.s3_file_result import GetS3FileResult, UploadS3FileResult
from manta.services.s3_file_storage_service import S3FileNotFoundError

# A catalogue standing in for the manta-batteries one: enough to resolve, wire, and
# validate the test playbook without any block being importable here — which is
# exactly the backend's situation with the real catalogue.
_CATALOGUE = Catalogue(
    blocks={
        "shrink": BlockDescription(
            name="shrink",
            env="pypsa",
            module="fake_library.shrink:Shrink",
            dims=BlockDims(requires=frozenset({"snapshot"})),
            config_schema={
                "type": "object",
                "properties": {"factor": {"type": "integer"}},
                "additionalProperties": False,
            },
        )
    },
    environments={"pypsa": EnvironmentSpec(name="pypsa")},
)

_DOC = {
    "name": "shrink-once",
    "initial_data": {"dims": ["snapshot"]},
    "steps": [{"name": "shrink", "block": "shrink"}],
}


def _existing_playbook() -> Playbook:
    playbook = Playbook(
        name="shrink-once",
        description="A playbook of one shrink step",
        doc=_DOC,
        default_config={"shrink": {"factor": 2}},
    )
    playbook.id = 7
    playbook.uuid = uuid4()
    playbook.created_at = datetime.now(UTC)
    return playbook


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


def _fake_storage() -> MagicMock:
    storage = MagicMock()
    storage.bucket = "manta"
    storage.copy_file = MagicMock(
        side_effect=lambda source_key, project_uuid, dest_filename: UploadS3FileResult(
            key=f"{project_uuid}/{dest_filename}", size=123
        )
    )
    storage.list_files = MagicMock(return_value=[])
    return storage


def _service(db, storage=None) -> PlaybookService:
    return PlaybookService(db=db, storage=storage or _fake_storage(), catalogue=_CATALOGUE)


def test_list_playbooks_returns_summaries(mock_db_class) -> None:
    # Given
    playbook = _existing_playbook()
    db = mock_db_class(query_results={Playbook: [playbook]})

    # When
    result = _service(db).list_playbooks()

    # Then
    assert result.total == 1
    assert result.items[0].uuid == playbook.uuid
    assert result.items[0].name == "shrink-once"
    assert result.items[0].description == playbook.description


def test_get_playbook_returns_the_full_document(mock_db_class) -> None:
    # Given
    playbook = _existing_playbook()
    db = mock_db_class(query_results={Playbook: playbook})

    # When
    result = _service(db).get_playbook(playbook.uuid)

    # Then
    assert result.uuid == playbook.uuid
    assert result.doc == _DOC
    assert result.default_config == {"shrink": {"factor": 2}}


def test_get_playbook_with_unknown_uuid_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Playbook: None})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _service(db).get_playbook(uuid4())
    assert exc_info.value.status_code == 404


def test_validate_accepts_a_config_the_blocks_accept(mock_db_class) -> None:
    # Given
    playbook = _existing_playbook()
    db = mock_db_class(query_results={Playbook: playbook})

    # When
    result = _service(db).validate_playbook(playbook.uuid, config={"shrink": {"factor": 3}})

    # Then
    assert result.valid
    assert result.issues == []


def test_validate_reports_issues_as_data_not_errors(mock_db_class) -> None:
    # Given
    playbook = _existing_playbook()
    db = mock_db_class(query_results={Playbook: playbook})

    # When — factor has the wrong type, checked against the catalogued JSON schema
    result = _service(db).validate_playbook(playbook.uuid, config={"shrink": {"factor": "lots"}})

    # Then
    assert not result.valid
    assert len(result.issues) == 1
    assert result.issues[0].kind == "config"
    assert result.issues[0].step == "shrink"


def test_validate_with_a_block_missing_from_the_catalogue_raises_500(mock_db_class) -> None:
    # Given — the stored document names a block nothing describes, which is a
    # broken installation rather than a user mistake.
    playbook = _existing_playbook()
    playbook.doc = {
        "name": "shrink-once",
        "initial_data": {"dims": []},
        "steps": [{"name": "mystery", "block": "never_catalogued"}],
    }
    db = mock_db_class(query_results={Playbook: playbook})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _service(db).validate_playbook(playbook.uuid, config={})
    assert exc_info.value.status_code == 500


def test_create_run_freezes_input_starts_the_orchestrator_and_persists(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    playbook = _existing_playbook()
    project = _existing_project()
    db = mock_db_class(query_results={Playbook: playbook, Project: project})
    storage = _fake_storage()
    flow_run_id = uuid4()
    run_deployment = MagicMock(return_value=SimpleNamespace(id=flow_run_id))
    monkeypatch.setattr(playbook_service_module, "run_deployment", run_deployment)
    service = _service(db, storage)

    # When
    result = service.create_run(
        playbook_uuid=playbook.uuid,
        project_uuid=project.uuid,
        input_key="examples/network-tiny.nc",
        config=None,
    )

    # Then — the input was copied under the run's own prefix
    copy_kwargs = storage.copy_file.call_args.kwargs
    assert copy_kwargs["source_key"] == "examples/network-tiny.nc"
    assert copy_kwargs["project_uuid"] == project.uuid
    assert copy_kwargs["dest_filename"] == f"{run_storage_prefix(result.uuid)}network-tiny.nc"

    # Then — the orchestrator deployment was started with the document, the default
    # config, the frozen record, and the catalogue
    deployment_name = run_deployment.call_args.args[0]
    parameters = run_deployment.call_args.kwargs["parameters"]
    assert deployment_name == "run_playbook/orchestrator"
    assert parameters["playbook"] == _DOC
    assert parameters["config"] == playbook.default_config
    assert parameters["record"] == {"url": f"s3://manta/{result.input_key}"}
    # The catalogue crosses as an opaque JSON string — Prefect must not walk into
    # its schemas' `$ref`s (see run_playbook's docstring).
    assert isinstance(parameters["catalogue"], str)
    assert json.loads(parameters["catalogue"])["blocks"].keys() == {"shrink"}

    # Then — the run row records what ran
    persisted_run = db.add.call_args.args[0]
    assert isinstance(persisted_run, Run)
    assert persisted_run.uuid == result.uuid
    assert persisted_run.project_id == project.id
    assert persisted_run.prefect_flow_run_id == flow_run_id
    assert persisted_run.playbook_id == playbook.id
    assert persisted_run.playbook_config == playbook.default_config
    assert persisted_run.input_key == result.input_key
    assert result.playbook_uuid == playbook.uuid
    assert result.project_uuid == project.uuid


def test_create_run_with_an_invalid_config_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    playbook = _existing_playbook()
    project = _existing_project()
    db = mock_db_class(query_results={Playbook: playbook, Project: project})
    storage = _fake_storage()
    run_deployment = MagicMock()
    monkeypatch.setattr(playbook_service_module, "run_deployment", run_deployment)
    service = _service(db, storage)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            playbook_uuid=playbook.uuid,
            project_uuid=project.uuid,
            input_key="examples/network-tiny.nc",
            config={"shrink": {"factor": "lots"}},
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["issues"]
    storage.copy_file.assert_not_called()
    run_deployment.assert_not_called()
    db.add.assert_not_called()


def test_create_run_with_unknown_playbook_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Playbook: None})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _service(db).create_run(
            playbook_uuid=uuid4(), project_uuid=uuid4(), input_key="x.nc", config=None
        )
    assert exc_info.value.status_code == 404


def test_create_run_with_unknown_project_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Playbook: _existing_playbook(), Project: None})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _service(db).create_run(
            playbook_uuid=uuid4(), project_uuid=uuid4(), input_key="x.nc", config=None
        )
    assert exc_info.value.status_code == 404


def test_create_run_with_a_missing_input_file_raises_404_and_starts_nothing(
    monkeypatch: pytest.MonkeyPatch, mock_db_class
) -> None:
    # Given
    playbook = _existing_playbook()
    project = _existing_project()
    db = mock_db_class(query_results={Playbook: playbook, Project: project})
    storage = _fake_storage()
    storage.copy_file.side_effect = S3FileNotFoundError("no such key")
    run_deployment = MagicMock()
    monkeypatch.setattr(playbook_service_module, "run_deployment", run_deployment)
    service = _service(db, storage)

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        service.create_run(
            playbook_uuid=playbook.uuid,
            project_uuid=project.uuid,
            input_key="examples/gone.nc",
            config=None,
        )
    assert exc_info.value.status_code == 404
    run_deployment.assert_not_called()
    db.add.assert_not_called()


def test_create_run_logs_orphaned_flow_run_when_commit_fails(
    monkeypatch: pytest.MonkeyPatch, mock_db_class, caplog: pytest.LogCaptureFixture
) -> None:
    # Given
    playbook = _existing_playbook()
    project = _existing_project()
    db = mock_db_class(query_results={Playbook: playbook, Project: project})
    db.commit.side_effect = RuntimeError("connection lost")
    flow_run_id = uuid4()
    monkeypatch.setattr(
        playbook_service_module,
        "run_deployment",
        MagicMock(return_value=SimpleNamespace(id=flow_run_id)),
    )
    service = _service(db)

    # When/Then
    with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
        service.create_run(
            playbook_uuid=playbook.uuid,
            project_uuid=project.uuid,
            input_key="examples/network-tiny.nc",
            config=None,
        )
    assert str(flow_run_id) in caplog.text
    assert str(playbook.uuid) in caplog.text


def test_get_run_outputs_lists_the_files_under_the_runs_prefix(mock_db_class) -> None:
    # Given
    project = _existing_project()
    run = _existing_run(project)
    db = mock_db_class(query_results={Run: run, Project: project})
    storage = _fake_storage()
    output_key = f"{project.uuid}/runs/{run.uuid}/network-tiny-cluster_time.nc"
    storage.list_files.return_value = [
        GetS3FileResult(key=output_key, size=456, last_modified=datetime.now(UTC))
    ]
    service = _service(db, storage)

    # When
    result = service.get_run_outputs(run.uuid)

    # Then
    storage.list_files.assert_called_once_with(project.uuid, prefix=f"runs/{run.uuid}/")
    assert result.uuid == run.uuid
    assert [item.key for item in result.items] == [output_key]
    assert result.items[0].url == f"s3://manta/{output_key}"


def test_get_run_outputs_with_unknown_run_raises_404(mock_db_class) -> None:
    # Given
    db = mock_db_class(query_results={Run: None})

    # When/Then
    with pytest.raises(HTTPException) as exc_info:
        _service(db).get_run_outputs(uuid4())
    assert exc_info.value.status_code == 404
