import logging
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import (
    FlowRunFilter,
    FlowRunFilterId,
    LogFilter,
    LogFilterFlowRunId,
)
from prefect.client.schemas.objects import FlowRun, TaskRun
from prefect.deployments import run_deployment
from sqlalchemy import desc
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, Run
from manta.services.playbook_service import PlaybookService
from manta.services.results.run_result import (
    CreateRunResult,
    GetRunLogsResult,
    GetRunResult,
    GetRunStepResult,
    GetRunStepsResult,
    GetRunSummaryResult,
    ListRunOutputsResult,
    ListRunsResult,
)
from manta.services.s3_file_storage_service import S3FileStorageService
from manta.workflows.playbook_flows import PLAYBOOK_DEPLOYMENT

logger = logging.getLogger(__name__)

PI_DIGIT_STATS_DEPLOYMENT = "pi-digit-stats/pi-digit-stats"


def _read_flow_run(flow_run_id: UUID) -> FlowRun:
    with get_client(sync_client=True) as client:
        return client.read_flow_run(flow_run_id)


def _read_flow_runs(flow_run_ids: list[UUID]) -> dict[UUID, FlowRun]:
    with get_client(sync_client=True) as client:
        flow_runs = {}
        for flow_run_id in flow_run_ids:
            flow_runs[flow_run_id] = client.read_flow_run(flow_run_id)
        return flow_runs


def _read_flow_run_logs(flow_run_id: UUID) -> tuple[FlowRun, list[str]]:
    with get_client(sync_client=True) as client:
        flow_run = client.read_flow_run(flow_run_id)
        logs = client.read_logs(
            log_filter=LogFilter(flow_run_id=LogFilterFlowRunId(any_=[flow_run_id]))
        )
        return flow_run, [log.message for log in logs]


def _read_flow_run_with_task_runs(flow_run_id: UUID) -> tuple[FlowRun, list[TaskRun]]:
    """The run plus its task runs — a playbook run's steps, in start order.

    Every step of a playbook (nested ones included) executes as one task run of
    the playbook flow run, so this one query is the complete step list.
    """
    with get_client(sync_client=True) as client:
        flow_run = client.read_flow_run(flow_run_id)
        task_runs = client.read_task_runs(
            flow_run_filter=FlowRunFilter(id=FlowRunFilterId(any_=[flow_run_id]))
        )
        return flow_run, sorted(
            task_runs,
            key=lambda task_run: (
                task_run.start_time or task_run.expected_start_time or task_run.created
            ),
        )


def _flow_run_status(flow_run: FlowRun | TaskRun) -> str:
    return flow_run.state.type.value if flow_run.state is not None else "UNKNOWN"


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
        playbooks: PlaybookService = Depends(),
    ) -> None:
        self.db = db
        self.storage = storage
        self.playbooks = playbooks

    def create_run(self, project_uuid: UUID, num_pi_digits: int) -> CreateRunResult:
        project = self._get_project(project_uuid)

        flow_run = run_deployment(
            PI_DIGIT_STATS_DEPLOYMENT, parameters={"num_digits": num_pi_digits}, timeout=0
        )

        run = Run(project_id=project.id, prefect_flow_run_id=flow_run.id)
        self._persist_run(run, project)

        return CreateRunResult(uuid=run.uuid, project_uuid=project.uuid, created_at=run.created_at)

    def create_playbook_run(
        self, project_uuid: UUID, playbook_name: str, config: dict | None, input_file: str
    ) -> CreateRunResult:
        """Validate and start a playbook run; return once Prefect has accepted it.

        The run's artifacts all live under one prefix in the project's storage —
        `<project>/runs/<run uuid>/` holds a copy of the input (so the run stays
        reproducible even if the original file is later replaced) and every step's
        output, browsable via `get_run_outputs`.
        """
        project = self._get_project(project_uuid)

        doc, default_config = self.playbooks.resolve(playbook_name)
        # No merging: a partial config on top of defaults is easy to get subtly
        # wrong, so a caller either takes the defaults or sends the full config
        # (starting from GET /playbooks/{name}'s default_config).
        run_config = config if config is not None else default_config

        playbook = self.playbooks.build(doc)
        issues = self.playbooks.validate(playbook, run_config)
        if issues:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"Playbook {playbook_name!r} cannot run with this config",
                    "issues": [issue.model_dump() for issue in issues],
                },
            )

        if not self.storage.file_exists(project.uuid, input_file):
            raise HTTPException(
                status_code=404,
                detail=f"Input file {input_file!r} not found in project {project.uuid}",
            )

        run_uuid = uuid4()
        input_key = self.storage.copy_file(
            project.uuid, input_file, f"runs/{run_uuid}/input/{input_file}"
        )
        input_url = f"s3://{self.storage.bucket}/{input_key}"
        output_prefix = f"s3://{self.storage.bucket}/{project.uuid}/runs/{run_uuid}/steps"

        flow_run = run_deployment(
            PLAYBOOK_DEPLOYMENT,
            parameters={
                "playbook": doc.model_dump(mode="json"),
                "config": run_config,
                "record": {"url": input_url},
                "output_prefix": output_prefix,
            },
            flow_run_name=f"run-{run_uuid}",
            timeout=0,
        )

        run = Run(
            uuid=run_uuid,
            project_id=project.id,
            prefect_flow_run_id=flow_run.id,
            playbook_name=playbook_name,
            playbook_doc=doc.model_dump(mode="json"),
            playbook_config=run_config,
            input_url=input_url,
            output_prefix=output_prefix,
        )
        self._persist_run(run, project)

        return CreateRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            created_at=run.created_at,
            playbook_name=playbook_name,
        )

    def list_runs(
        self, project_uuid: UUID, limit: int, offset: int, status_filters: list[str] | None
    ) -> ListRunsResult:
        project = self._get_project(project_uuid)

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

    def get_run_summary(self, project_uuid: UUID) -> GetRunSummaryResult:
        project = self._get_project(project_uuid)

        runs = self._list_project_runs(project.id)
        flow_runs = self._read_project_flow_runs(runs)
        return _build_run_summary(self._build_run_results(project.uuid, runs, flow_runs))

    def get_run(self, run_uuid: UUID) -> GetRunResult:
        run = self._get_run(run_uuid)
        project = self.db.query(Project).filter(Project.id == run.project_id).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")

        flow_run = _read_flow_run(run.prefect_flow_run_id)

        return GetRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            status=_flow_run_status(flow_run),
            created_at=run.created_at,
            playbook_name=run.playbook_name,
        )

    def get_run_logs(self, run_uuid: UUID) -> GetRunLogsResult:
        run = self._get_run(run_uuid)

        flow_run, logs = _read_flow_run_logs(run.prefect_flow_run_id)

        return GetRunLogsResult(uuid=run.uuid, logs=logs, run_status=_flow_run_status(flow_run))

    def get_run_steps(self, run_uuid: UUID) -> GetRunStepsResult:
        """Each step of a playbook run, and how it is doing.

        A step is a task run of the run's flow run, named `<step>[<block>]`. For a
        legacy pi-digit run this lists its computation tasks instead — every kind
        of run reports whatever its flow actually executed.
        """
        run = self._get_run(run_uuid)

        flow_run, task_runs = _read_flow_run_with_task_runs(run.prefect_flow_run_id)

        return GetRunStepsResult(
            uuid=run.uuid,
            run_status=_flow_run_status(flow_run),
            steps=[
                GetRunStepResult(
                    name=task_run.name or str(task_run.id), status=_flow_run_status(task_run)
                )
                for task_run in task_runs
            ],
        )

    def get_run_outputs(self, run_uuid: UUID) -> ListRunOutputsResult:
        """Every file the run produced (plus its input copy), fresh from storage.

        Steps write straight to object storage, so this is live while a run is
        still going: finished steps' outputs appear as they land.
        """
        run = self._get_run(run_uuid)
        if run.output_prefix is None:
            # A legacy pi-digit run: it never had file outputs.
            return ListRunOutputsResult(uuid=run.uuid, items=[])

        project = self.db.query(Project).filter(Project.id == run.project_id).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")

        files = self.storage.list_files(project.uuid, prefix=f"runs/{run.uuid}/")
        return ListRunOutputsResult(uuid=run.uuid, items=files)

    def _get_project(self, project_uuid: UUID) -> Project:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")
        return project

    def _get_run(self, run_uuid: UUID) -> Run:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")
        return run

    def _persist_run(self, run: Run, project: Project) -> None:
        self.db.add(run)
        try:
            self.db.commit()
        except Exception:
            logger.error(
                f"Failed to persist run for prefect_flow_run_id={run.prefect_flow_run_id} "
                f"(project {project.uuid}); flow run was already started and is now orphaned"
            )
            raise

        logger.info(
            f"Created run {run.uuid} for project {project.uuid} "
            f"(prefect_flow_run_id={run.prefect_flow_run_id})"
        )

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
                status=_flow_run_status(flow_runs[run.prefect_flow_run_id]),
                created_at=run.created_at,
                playbook_name=run.playbook_name,
            )
            for run in runs
        ]
