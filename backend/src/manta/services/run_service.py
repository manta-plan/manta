import json
import logging
from contextlib import suppress
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from playbook.blocks import DataRecord
from playbook.playbooks import BlockStep, NestedPlaybookStep, Playbook, parse_doc, playbook_from_doc

# TODO(post-MVP): a direct dependency on one concrete block library here is an
# MVP corner-cut, not the intended shape — see the TODO on these two
# dependencies in backend/pyproject.toml.
from playbook_library import library_catalogue
from playbook_library.playbooks import library_playbooks
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import (
    ArtifactFilter,
    ArtifactFilterFlowRunId,
    ArtifactFilterKey,
    FlowRunFilter,
    FlowRunFilterParentFlowRunId,
    LogFilter,
    LogFilterFlowRunId,
)
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from prefect.exceptions import ObjectNotFound
from runner.flows import (
    OUTPUT_ARTIFACT_KEY,
    PLAYBOOK_DEPLOYMENT,
    catalogue_parameter,
    parse_catalogue_parameter,
)
from sqlalchemy import desc
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, Run, User
from manta.services.errors import AuthorizationError
from manta.services.playbook_service import PlaybookService
from manta.services.results.run_result import (
    CreateRunResult,
    DataRecordResult,
    GetRunLogsResult,
    GetRunResult,
    GetRunStepsResult,
    GetRunSummaryResult,
    ListRunsResult,
    RunStepResult,
)
from manta.services.s3_file_storage_service import S3FileStorageService
from manta.services.user_service import UserService

logger = logging.getLogger(__name__)


class PrefectUnavailableError(Exception):
    pass


def ensure_prefect_ready() -> None:
    """Called once at app startup (see main.create_app()) — confirms the
    configured Prefect API (PREFECT_API_URL) is actually reachable, the same
    way S3FileStorageService.ensure_bucket_exists() confirms S3 is."""
    with get_client(sync_client=True) as client:
        error = client.api_healthcheck()
    if error is not None:
        raise PrefectUnavailableError(f"Prefect API is not reachable: {error}") from error


def _read_flow_run(flow_run_id: UUID) -> FlowRun:
    with get_client(sync_client=True) as client:
        return client.read_flow_run(flow_run_id)


def _read_flow_runs(flow_run_ids: list[UUID]) -> dict[UUID, FlowRun]:
    with get_client(sync_client=True) as client:
        flow_runs = {}
        for flow_run_id in flow_run_ids:
            flow_runs[flow_run_id] = client.read_flow_run(flow_run_id)
        return flow_runs


def _read_existing_flow_runs(flow_run_ids: list[UUID]) -> dict[UUID, FlowRun]:
    """Like `_read_flow_runs`, but leaves out a flow run Prefect no longer has. For the
    deletion preflight only: an earlier, partly failed delete may have removed some."""
    with get_client(sync_client=True) as client:
        flow_runs = {}
        for flow_run_id in flow_run_ids:
            with suppress(ObjectNotFound):
                flow_runs[flow_run_id] = client.read_flow_run(flow_run_id)
        return flow_runs


def _read_flow_run_logs(flow_run_id: UUID) -> tuple[FlowRun, list[str]]:
    with get_client(sync_client=True) as client:
        flow_run = client.read_flow_run(flow_run_id)
        logs = client.read_logs(
            log_filter=LogFilter(flow_run_id=LogFilterFlowRunId(any_=[flow_run_id]))
        )
        return flow_run, [log.message for log in logs]


def _read_flow_run_with_block_runs(flow_run_id: UUID) -> tuple[FlowRun, list[FlowRun]]:
    """A playbook's flow run, plus the flow run of every block it has dispatched so far.

    Each block runs as a child flow run of its playbook's flow run (see
    runner.flows.PrefectBlockRunner). `parent_flow_run_id` is the filter that finds
    those — not `parent_task_run_id`, which matches something else entirely.
    """
    with get_client(sync_client=True) as client:
        flow_run = client.read_flow_run(flow_run_id)
        block_runs = client.read_flow_runs(
            flow_run_filter=FlowRunFilter(
                parent_flow_run_id=FlowRunFilterParentFlowRunId(any_=[flow_run_id])
            )
        )
        return flow_run, block_runs


def _flow_run_status(flow_run: FlowRun) -> str:
    return flow_run.state.type.value if flow_run.state is not None else "UNKNOWN"


def _flow_run_config(flow_run: FlowRun) -> dict:
    # TODO(post-MVP): a shortcut for the MVP — the config a run was started with is
    # read back from the parameters Prefect stored on its flow run, since Manta
    # doesn't persist it itself. It belongs to the run, not to a playbook, so when
    # the playbook entity is defined (see the TODOs on Run.playbook and
    # CreateRunRequest.config), store it on Run itself and read it from there.
    return flow_run.parameters["config"]


def _flow_run_data_record(flow_run: FlowRun) -> DataRecordResult:
    # TODO(post-MVP): the same shortcut as _flow_run_config. Store the record a run
    # started from on Run itself once data records are tracked in Manta's database.
    return _data_record_result(flow_run.parameters["record"])


def _data_record_result(data: dict) -> DataRecordResult:
    """A record as runner.flows passes it around (DataRecord.to_dict()), for the API."""
    record = DataRecord.from_dict(data)
    return DataRecordResult(store_url=record.url, revision_uuid=record.uuid)


def _flow_run_playbook(flow_run: FlowRun) -> Playbook:
    # TODO(post-MVP): the same shortcut as _flow_run_config — the playbook a run
    # was started with is rebuilt from its flow run's parameters (the document and
    # catalogue it was dispatched with), rather than looked up live in the library
    # by Run.playbook, which may have changed since. Read it from the playbook
    # entity once that exists (see the TODO on Run.playbook).
    parameters = flow_run.parameters
    return playbook_from_doc(
        parse_doc(parameters["playbook"]),
        catalogue=parse_catalogue_parameter(parameters["catalogue"]),
    )


def _read_block_run_outputs(block_runs: list[FlowRun]) -> dict[UUID, DataRecordResult]:
    """The output record each block run published, by block run id. A block run that
    hasn't finished has none yet."""
    # TODO(post-MVP): a run's outputs are only found through the artifacts its block
    # runs publish to Prefect (see runner.flows.run_block). Once data records are
    # tracked in Manta's own database, a run's outputs are stored there instead.
    if not block_runs:
        return {}
    with get_client(sync_client=True) as client:
        artifacts = client.read_artifacts(
            artifact_filter=ArtifactFilter(
                flow_run_id=ArtifactFilterFlowRunId(
                    any_=[block_run.id for block_run in block_runs]
                ),
                key=ArtifactFilterKey(any_=[OUTPUT_ARTIFACT_KEY]),
            )
        )
    outputs = {}
    for artifact in artifacts:
        [row] = json.loads(artifact.data)
        outputs[artifact.flow_run_id] = _data_record_result(row)
    return outputs


def _build_run_step_result(
    step: BlockStep | NestedPlaybookStep,
    active_step_names: set[str],
    block_runs_by_step_name: dict[str, FlowRun],
    outputs: dict[UUID, DataRecordResult],
) -> RunStepResult:
    block = step.block.name if isinstance(step, BlockStep) else None
    block_run = block_runs_by_step_name.get(step.name) if block is not None else None

    if block_run is not None:
        status = _flow_run_status(block_run)
    elif step.name not in active_step_names:
        status = "SKIPPED"
    elif block is None:
        # A nested playbook has no flow run of its own: its blocks run as children
        # of this run under their own step names, so they can't be told apart yet.
        # For the same reason it has no output either.
        status = "UNKNOWN"
    else:
        status = "NOT_STARTED"

    return RunStepResult(
        name=step.name,
        block=block,
        status=status,
        start_time=block_run.start_time if block_run is not None else None,
        end_time=block_run.end_time if block_run is not None else None,
        output=outputs.get(block_run.id) if block_run is not None else None,
        message=block_run.state.message
        if block_run is not None and block_run.state is not None
        else None,
    )


def _normalize_status_filters(status_filters: list[str] | None) -> set[str] | None:
    if status_filters is None:
        return None

    normalized_status_filters = {status_filter.upper() for status_filter in status_filters}
    return normalized_status_filters or None


def _build_run_summary(run_results: list[GetRunResult]) -> GetRunSummaryResult:
    statuses: dict[str, int] = {}

    for run_result in run_results:
        status = run_result.status.upper()
        statuses[status] = statuses.get(status, 0) + 1

    return GetRunSummaryResult(total=len(run_results), statuses=statuses)


class RunService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        storage: S3FileStorageService = Depends(),
        playbook_service: PlaybookService = Depends(),
        user_service: UserService = Depends(),
    ) -> None:
        self.db = db
        self.storage = storage
        self.playbook_service = playbook_service
        self.user_service = user_service

    def create_run(
        self,
        project_uuid: UUID,
        playbook: str,
        config: dict | None,
        store_url: str,
        revision_uuid: UUID,
        user: User,
    ) -> CreateRunResult:
        project = self.user_service.get_owned_project(project_uuid, user)

        library_playbook = library_playbooks().get(playbook)
        if library_playbook is None:
            raise HTTPException(status_code=404, detail=f"Playbook {playbook!r} not found")
        run_config = config if config is not None else library_playbook.default_config

        # Before a run is minted or anything is dispatched, so a config that cannot
        # work is refused here with every reason, rather than failing minutes later
        # inside a block's container.
        self.playbook_service.raise_for_config_issues(playbook, run_config)
        self._raise_for_record_issues(project, store_url, revision_uuid)

        run_uuid = uuid4()

        flow_run = run_deployment(
            PLAYBOOK_DEPLOYMENT,
            parameters={
                "playbook": library_playbook.doc.model_dump(mode="json"),
                "config": run_config,
                "record": {"url": store_url, "uuid": str(revision_uuid)},
                "catalogue": catalogue_parameter(library_catalogue()),
            },
            timeout=0,
        )

        run = Run(
            uuid=run_uuid,
            project_id=project.id,
            prefect_flow_run_id=flow_run.id,
            playbook=playbook,
        )
        self.db.add(run)
        try:
            self.db.commit()
        except Exception:
            logger.error(
                f"Failed to persist run for prefect_flow_run_id={flow_run.id} "
                f"(project {project.uuid}); flow run was already started and is now orphaned"
            )
            raise

        logger.info(
            f"Created run {run.uuid} for project {project.uuid} (prefect_flow_run_id={flow_run.id})"
        )

        return CreateRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            playbook=run.playbook,
            created_at=run.created_at,
        )

    def _raise_for_record_issues(
        self, project: Project, store_url: str, revision_uuid: UUID
    ) -> None:
        # The run writes its revisions into this store, so it must be the project's own.
        url = urlparse(store_url)
        project_prefix = f"/{project.uuid}/"
        if (
            url.scheme != "s3"
            or url.netloc != self.storage.bucket
            or not url.path.startswith(project_prefix)
        ):
            raise AuthorizationError(detail="data record store is not in the project's storage")

        store = url.path.removeprefix(project_prefix).rstrip("/")
        if not self.storage.file_exists(
            project.uuid, f"{store}/layers/{revision_uuid}/manifest.json"
        ):
            raise HTTPException(
                status_code=404,
                detail=f"Revision {revision_uuid} not found in {store_url!r}",
            )

    def list_runs(
        self,
        project_uuid: UUID,
        limit: int,
        offset: int,
        status_filters: list[str] | None,
        user: User,
    ) -> ListRunsResult:
        project = self.user_service.get_owned_project(project_uuid, user)

        runs = self._list_project_runs(project.id)
        flow_runs = self._read_project_flow_runs(runs)
        normalized_status_filters = _normalize_status_filters(status_filters)
        run_results = self._build_run_results(project.uuid, runs, flow_runs)
        filtered_run_results = [
            run_result
            for run_result in run_results
            if normalized_status_filters is None
            or run_result.status.upper() in normalized_status_filters
        ]
        paginated_run_results = filtered_run_results[offset : offset + limit]

        return ListRunsResult(
            items=paginated_run_results,
            total=len(filtered_run_results),
            limit=limit,
            offset=offset,
            summary=_build_run_summary(run_results),
        )

    def get_run_summary(self, project_uuid: UUID, user: User) -> GetRunSummaryResult:
        project = self.user_service.get_owned_project(project_uuid, user)

        runs = self._list_project_runs(project.id)
        flow_runs = self._read_project_flow_runs(runs)
        return _build_run_summary(self._build_run_results(project.uuid, runs, flow_runs))

    def ensure_no_active_runs(self, project: Project, user: User) -> None:
        """Raises a 409 if any run of the project has not reached a final Prefect state.
        A run in flight would write to S3 again after the project's cleanup. A run whose
        state is unknown counts as active. A flow run Prefect no longer has is skipped, so a
        delete retried after a partial failure is not blocked by its own earlier cleanup."""
        self.user_service.ensure_project_owner(project, user)

        runs = self._list_project_runs(project.id)
        flow_runs = _read_existing_flow_runs([run.prefect_flow_run_id for run in runs])
        if any(
            flow_run.state is None or not flow_run.state.is_final()
            for flow_run in flow_runs.values()
        ):
            raise HTTPException(
                status_code=409,
                detail="Only projects without active runs can be deleted",
            )

    def delete_flow_runs(self, project: Project, user: User) -> None:
        """Deletes the Prefect flow run of each of the project's runs, together with the
        block flow runs dispatched under it. A flow run that is already gone is skipped,
        so a retry after a partial failure picks up where it stopped."""
        self.user_service.ensure_project_owner(project, user)

        flow_run_ids = [run.prefect_flow_run_id for run in self._list_project_runs(project.id)]
        with get_client(sync_client=True) as client:
            for flow_run_id in flow_run_ids:
                block_runs = client.read_flow_runs(
                    flow_run_filter=FlowRunFilter(
                        parent_flow_run_id=FlowRunFilterParentFlowRunId(any_=[flow_run_id])
                    )
                )
                for doomed_id in [*(block_run.id for block_run in block_runs), flow_run_id]:
                    with suppress(ObjectNotFound):
                        client.delete_flow_run(doomed_id)

    def _list_project_runs(self, project_id: int) -> list[Run]:
        return (
            self.db.query(Run)
            .filter(Run.project_id == project_id)
            .order_by(desc(Run.created_at))
            .all()
        )

    def _read_project_flow_runs(self, runs: list[Run]) -> dict[UUID, FlowRun]:
        return _read_flow_runs([run.prefect_flow_run_id for run in runs])

    def _build_run_results(
        self, project_uuid: UUID, runs: list[Run], flow_runs: dict[UUID, FlowRun]
    ) -> list[GetRunResult]:
        return [
            GetRunResult(
                uuid=run.uuid,
                project_uuid=project_uuid,
                playbook=run.playbook,
                config=_flow_run_config(flow_runs[run.prefect_flow_run_id]),
                data_record=_flow_run_data_record(flow_runs[run.prefect_flow_run_id]),
                status=_flow_run_status(flow_runs[run.prefect_flow_run_id]),
                created_at=run.created_at,
            )
            for run in runs
        ]

    def _get_run_with_project(self, run_uuid: UUID, user: User) -> tuple[Run, Project]:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        project = self.db.query(Project).filter(Project.id == run.project_id).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")
        self.user_service.ensure_project_owner(project, user)

        return run, project

    def get_run(self, run_uuid: UUID, user: User) -> GetRunResult:
        run, project = self._get_run_with_project(run_uuid, user)
        flow_run = _read_flow_run(run.prefect_flow_run_id)

        return GetRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            playbook=run.playbook,
            config=_flow_run_config(flow_run),
            data_record=_flow_run_data_record(flow_run),
            status=_flow_run_status(flow_run),
            created_at=run.created_at,
        )

    def get_run_steps(self, run_uuid: UUID, user: User) -> GetRunStepsResult:
        run, _ = self._get_run_with_project(run_uuid, user)
        flow_run, block_runs = _read_flow_run_with_block_runs(run.prefect_flow_run_id)
        playbook = _flow_run_playbook(flow_run)
        active_step_names = {
            step.name for step in playbook.active(_flow_run_config(flow_run)).steps
        }
        # Matched by the step name each block run was dispatched with. Should a step
        # ever have more than one (the playbook run was retried), the latest wins.
        block_runs_by_step_name = {
            block_run.parameters["step_name"]: block_run
            for block_run in sorted(block_runs, key=lambda block_run: block_run.created)
        }
        outputs = _read_block_run_outputs(list(block_runs_by_step_name.values()))

        return GetRunStepsResult(
            uuid=run.uuid,
            steps=[
                _build_run_step_result(step, active_step_names, block_runs_by_step_name, outputs)
                for step in playbook.steps
            ],
            run_status=_flow_run_status(flow_run),
        )

    def get_run_logs(self, run_uuid: UUID, user: User) -> GetRunLogsResult:
        run, _ = self._get_run_with_project(run_uuid, user)
        flow_run, logs = _read_flow_run_logs(run.prefect_flow_run_id)

        return GetRunLogsResult(uuid=run.uuid, logs=logs, run_status=_flow_run_status(flow_run))
