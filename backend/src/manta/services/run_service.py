import logging
from uuid import UUID

from fastapi import Depends, HTTPException
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from sqlalchemy import desc
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, Run
from manta.services.playbook_service import PlaybookService
from manta.services.results.playbook_result import PlaybookDetailResult
from manta.services.results.run_result import (
    CreateRunResult,
    GetRunLogsResult,
    GetRunResult,
    GetRunSummaryResult,
    ListRunsResult,
)

logger = logging.getLogger(__name__)

PI_DIGIT_STATS_DEPLOYMENT = "pi-digit-stats/pi-digit-stats"

# Only playbooks with an entry here can actually be run — the others in the
# static catalog (see playbook_service.py) are still "coming soon".
_DEPLOYMENT_BY_PLAYBOOK_ID = {
    "pi-digit-statistics": PI_DIGIT_STATS_DEPLOYMENT,
}


def _validate_and_flatten_run_config(
    playbook: PlaybookDetailResult, playbook_config: list[dict[str, int]]
) -> dict[str, int]:
    if len(playbook_config) != len(playbook.nodes):
        raise HTTPException(
            status_code=400,
            detail=f"playbook_config must have exactly {len(playbook.nodes)} entrie(s) for "
            f"playbook {playbook.id}, one per node in order",
        )

    parameters: dict[str, int] = {}

    for node, node_config in zip(playbook.nodes, playbook_config, strict=True):
        config_fields_by_key = {field.key: field for field in node.config}

        unknown_keys = set(node_config) - set(config_fields_by_key)
        if unknown_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown config field(s) for node {node.id}: "
                f"{', '.join(sorted(unknown_keys))}",
            )

        for key, field in config_fields_by_key.items():
            if key not in node_config:
                if field.required:
                    raise HTTPException(
                        status_code=400, detail=f"Missing required config field: {key}"
                    )
                continue

            if field.min is not None and node_config[key] < field.min:
                raise HTTPException(
                    status_code=400, detail=f"Config field {key} must be at least {field.min}"
                )

        parameters.update(node_config)

    return parameters


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


def _flow_run_status(flow_run: FlowRun) -> str:
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
    def __init__(self, db: Session = Depends(get_db_session)) -> None:
        self.db = db
        self.playbooks = PlaybookService()

    def create_run(
        self,
        project_uuid: UUID,
        name: str,
        playbook_id: str,
        playbook_config: list[dict[str, int]],
    ) -> CreateRunResult:
        # `name` is accepted but not persisted — `runs` has no name column yet.
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")

        playbook = self.playbooks.get_playbook(playbook_id)
        deployment_name = _DEPLOYMENT_BY_PLAYBOOK_ID.get(playbook_id)
        if playbook.status != "available" or deployment_name is None:
            raise HTTPException(
                status_code=400, detail=f"Playbook {playbook_id} is not available for runs"
            )
        parameters = _validate_and_flatten_run_config(playbook, playbook_config)

        flow_run = run_deployment(deployment_name, parameters=parameters, timeout=0)

        run = Run(project_id=project.id, prefect_flow_run_id=flow_run.id)
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

        return CreateRunResult(uuid=run.uuid, project_uuid=project.uuid, created_at=run.created_at)

    def list_runs(
        self, project_uuid: UUID, limit: int, offset: int, status_filters: list[str] | None
    ) -> ListRunsResult:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")

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
        project = self.db.query(Project).filter(Project.uuid == project_uuid).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")

        runs = self._list_project_runs(project.id)
        flow_runs = self._read_project_flow_runs(runs)
        return _build_run_summary(self._build_run_results(project.uuid, runs, flow_runs))

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
            )
            for run in runs
        ]

    def get_run(self, run_uuid: UUID) -> GetRunResult:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        project = self.db.query(Project).filter(Project.id == run.project_id).one_or_none()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")

        flow_run = _read_flow_run(run.prefect_flow_run_id)

        return GetRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            status=_flow_run_status(flow_run),
            created_at=run.created_at,
        )

    def get_run_logs(self, run_uuid: UUID) -> GetRunLogsResult:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).one_or_none()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        flow_run, logs = _read_flow_run_logs(run.prefect_flow_run_id)

        return GetRunLogsResult(uuid=run.uuid, logs=logs, run_status=_flow_run_status(flow_run))
