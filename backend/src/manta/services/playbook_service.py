import logging
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from manta_blocks import Catalogue
from manta_playbooks import (
    PlaybookLoadError,
    catalogue_parameter,
    orchestrator_path,
    playbook_from_doc,
)
from manta_playbooks.validation import PlaybookIssue
from manta_playbooks.yaml_io import parse_doc
from prefect.deployments import run_deployment
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.config.playbooks_config import get_catalogue, orchestrator_env
from manta.entities import Playbook, Project, Run
from manta.services.results.playbook_result import (
    CreatePlaybookRunResult,
    GetPlaybookResult,
    GetRunOutputsResult,
    ListPlaybooksResult,
    PlaybookIssueResult,
    PlaybookSummaryResult,
    RunOutputFileResult,
    ValidatePlaybookResult,
)
from manta.services.s3_file_storage_service import (
    S3FileNotFoundError,
    S3FileStorageService,
)

logger = logging.getLogger(__name__)


def run_storage_prefix(run_uuid: UUID) -> str:
    """Where a run's data lives inside its project's prefix.

    The run's input is copied here before anything starts, and blocks write each
    output beside its input, so everything one run touched stays under this prefix —
    which is also what makes "the outputs of a run" a plain listing.
    """
    return f"runs/{run_uuid}/"


def _issue_to_result(issue: PlaybookIssue) -> PlaybookIssueResult:
    return PlaybookIssueResult(
        kind=issue.kind,
        message=issue.message,
        step=issue.step,
        field=".".join(str(part) for part in issue.field) if issue.field else None,
        input=issue.input,
    )


class PlaybookService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        storage: S3FileStorageService = Depends(),
        catalogue: Catalogue = Depends(get_catalogue),
    ) -> None:
        self.db = db
        self.storage = storage
        self.catalogue = catalogue

    def list_playbooks(self) -> ListPlaybooksResult:
        playbooks = self.db.query(Playbook).order_by(Playbook.name).all()
        items = [
            PlaybookSummaryResult(
                uuid=playbook.uuid,
                name=playbook.name,
                description=playbook.description,
                created_at=playbook.created_at,
            )
            for playbook in playbooks
        ]
        return ListPlaybooksResult(items=items, total=len(items))

    def get_playbook(self, playbook_uuid: UUID) -> GetPlaybookResult:
        playbook = self._get_playbook(playbook_uuid)
        return GetPlaybookResult(
            uuid=playbook.uuid,
            name=playbook.name,
            description=playbook.description,
            doc=playbook.doc,
            default_config=playbook.default_config,
            created_at=playbook.created_at,
        )

    def validate_playbook(self, playbook_uuid: UUID, config: dict) -> ValidatePlaybookResult:
        """Everything wrong with running this playbook with `config`.

        Meant to be called by an editor as the user types, so problems are returned
        as data rather than raised.
        """
        playbook = self._get_playbook(playbook_uuid)
        issues = self._issues(playbook, config)
        return ValidatePlaybookResult(
            valid=not issues, issues=[_issue_to_result(issue) for issue in issues]
        )

    def create_run(
        self,
        playbook_uuid: UUID,
        project_uuid: UUID,
        input_key: str,
        config: dict | None,
    ) -> CreatePlaybookRunResult:
        """Start a playbook run: freeze its input, hand it to Prefect, record it.

        The playbook + config combination is validated first, so a run that could
        never work is rejected before anything is copied or started.
        """
        playbook = self._get_playbook(playbook_uuid)
        project = self._get_project(project_uuid)
        run_config = config if config is not None else playbook.default_config

        issues = self._issues(playbook, run_config)
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Playbook {playbook.name!r} cannot run with this config",
                    "issues": [_issue_to_result(issue).model_dump() for issue in issues],
                },
            )

        # The run's uuid is minted before the row exists because the storage prefix
        # and the Prefect parameters both need it.
        run_uuid = uuid4()
        record_key = self._freeze_input(project.uuid, run_uuid, input_key)
        record_url = f"s3://{self.storage.bucket}/{record_key}"

        flow_run = run_deployment(
            orchestrator_path(orchestrator_env()),
            parameters={
                "playbook": playbook.doc,
                "config": run_config,
                "record": {"url": record_url},
                # The orchestrator cannot import the blocks either; the catalogue is
                # how it resolves them. Encoded per run_playbook's contract.
                "catalogue": catalogue_parameter(self.catalogue),
            },
            timeout=0,
        )

        run = Run(
            uuid=run_uuid,
            project_id=project.id,
            prefect_flow_run_id=flow_run.id,
            playbook_id=playbook.id,
            playbook_config=run_config,
            input_key=record_key,
        )
        self.db.add(run)
        try:
            self.db.commit()
        except Exception:
            logger.error(
                f"Failed to persist run for prefect_flow_run_id={flow_run.id} "
                f"(playbook {playbook.uuid}, project {project.uuid}); flow run was "
                f"already started and is now orphaned"
            )
            raise

        logger.info(
            f"Created playbook run {run.uuid} (playbook {playbook.uuid}, "
            f"project {project.uuid}, prefect_flow_run_id={flow_run.id})"
        )

        return CreatePlaybookRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            playbook_uuid=playbook.uuid,
            input_key=record_key,
            created_at=run.created_at,
        )

    def get_run_outputs(self, run_uuid: UUID) -> GetRunOutputsResult:
        """Every file a run has produced so far (its frozen input included)."""
        run = self.db.query(Run).filter(Run.uuid == run_uuid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        project = self.db.query(Project).filter(Project.id == run.project_id).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")
        files = self.storage.list_files(project.uuid, prefix=run_storage_prefix(run.uuid))
        return GetRunOutputsResult(
            uuid=run.uuid,
            items=[
                RunOutputFileResult(
                    key=file.key,
                    size=file.size,
                    last_modified=file.last_modified,
                    url=f"s3://{self.storage.bucket}/{file.key}",
                )
                for file in files
            ],
        )

    def _get_playbook(self, playbook_uuid: UUID) -> Playbook:
        playbook = self.db.query(Playbook).filter(Playbook.uuid == playbook_uuid).one_or_none()
        if playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook_uuid} not found")
        return playbook

    def _get_project(self, project_uuid: UUID) -> Project:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")
        return project

    def _issues(self, playbook: Playbook, config: dict) -> list[PlaybookIssue]:
        """Check a stored playbook document against a config, via the framework."""
        try:
            built = playbook_from_doc(parse_doc(playbook.doc), catalogue=self.catalogue)
        except PlaybookLoadError as e:
            # The document was stored by us, so failing to build it is our data
            # being broken (or the catalogue missing its blocks), not user input.
            logger.error(f"Stored playbook {playbook.uuid} cannot be built: {e}")
            raise HTTPException(
                status_code=500, detail=f"Playbook {playbook.name!r} is not usable: {e}"
            ) from e
        return built.issues(config)

    def _freeze_input(self, project_uuid: UUID, run_uuid: UUID, input_key: str) -> str:
        """Copy the run's input under the run's own prefix, and return the new key."""
        input_filename = PurePosixPath(input_key).name
        dest_filename = f"{run_storage_prefix(run_uuid)}{input_filename}"
        try:
            copied = self.storage.copy_file(
                source_key=input_key, project_uuid=project_uuid, dest_filename=dest_filename
            )
        except S3FileNotFoundError as e:
            raise HTTPException(
                status_code=404, detail=f"Input file {input_key!r} not found"
            ) from e
        return copied.key
