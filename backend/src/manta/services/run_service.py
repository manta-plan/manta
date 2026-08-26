import asyncio
import logging
from uuid import UUID

from fastapi import Depends, HTTPException
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import LogFilter, LogFilterFlowRunId
from prefect.client.schemas.objects import FlowRun
from prefect.deployments import run_deployment
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session
from manta.entities import Project, Run
from manta.services.results.run_result import CreateRunResult, GetRunLogsResult, GetRunResult

logger = logging.getLogger(__name__)

PI_DIGIT_STATS_DEPLOYMENT = "pi-digit-stats/pi-digit-stats"


async def _read_flow_run(flow_run_id: UUID) -> FlowRun:
    async with get_client() as client:
        return await client.read_flow_run(flow_run_id)


async def _read_flow_run_logs(flow_run_id: UUID) -> tuple[FlowRun, list[str]]:
    async with get_client() as client:
        flow_run = await client.read_flow_run(flow_run_id)
        logs = await client.read_logs(
            log_filter=LogFilter(flow_run_id=LogFilterFlowRunId(any_=[flow_run_id]))
        )
        return flow_run, [log.message for log in logs]


def _flow_run_status(flow_run: FlowRun) -> str:
    return flow_run.state.type.value if flow_run.state is not None else "UNKNOWN"


class RunService:
    def __init__(self, db: Session = Depends(get_db_session)) -> None:
        self.db = db

    def create_run(self, project_uuid: UUID, num_pi_digits: int) -> CreateRunResult:
        project = self.db.query(Project).filter(Project.uuid == project_uuid).first()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {project_uuid} not found")

        # `run_deployment` is `@async_dispatch`-decorated: called from a sync
        # context (as here — this method runs in FastAPI's threadpool, with no
        # running event loop) it executes synchronously and returns a `FlowRun`
        # directly, not a coroutine — so it must NOT be wrapped in `asyncio.run()`
        # (unlike `_read_flow_run`/`_read_flow_run_logs` below, which are real
        # `async def` coroutine functions and do need it).
        flow_run = run_deployment(
            PI_DIGIT_STATS_DEPLOYMENT, parameters={"num_digits": num_pi_digits}, timeout=0
        )

        run = Run(project_id=project.id, prefect_flow_run_id=flow_run.id)
        self.db.add(run)
        self.db.commit()

        logger.info(
            "Created run %s for project %s (prefect_flow_run_id=%s)",
            run.uuid,
            project.uuid,
            flow_run.id,
        )

        return CreateRunResult(uuid=run.uuid, project_uuid=project.uuid, created_at=run.created_at)

    def get_run(self, run_uuid: UUID) -> GetRunResult:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).first()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        project = self.db.query(Project).filter(Project.id == run.project_id).first()
        if project is None:
            raise HTTPException(status_code=404, detail=f"Project {run.project_id} not found")

        flow_run = asyncio.run(_read_flow_run(run.prefect_flow_run_id))

        return GetRunResult(
            uuid=run.uuid,
            project_uuid=project.uuid,
            status=_flow_run_status(flow_run),
            created_at=run.created_at,
        )

    def get_run_logs(self, run_uuid: UUID) -> GetRunLogsResult:
        run = self.db.query(Run).filter(Run.uuid == run_uuid).first()
        if run is None:
            raise HTTPException(status_code=404, detail=f"Run {run_uuid} not found")

        flow_run, logs = asyncio.run(_read_flow_run_logs(run.prefect_flow_run_id))

        return GetRunLogsResult(logs=logs, run_status=_flow_run_status(flow_run))
