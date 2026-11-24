import asyncio
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx2
from fastapi import Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from manta.config.database_config import get_db_session, get_engine
from manta.config.datarecord_session_config import (
    datarecord_session_max_idle,
    get_datarecord_session_http,
    get_datarecord_session_launcher,
)
from manta.config.s3_config import project_read_credential, s3_bucket_name
from manta.entities import (
    DatarecordSession,
    DatarecordSessionRegistration,
    DatarecordSessionStatus,
    Project,
    User,
)
from manta.services.datarecord_session_launcher import (
    DATARECORD_SESSION_API_PORT,
    DATARECORD_SESSION_QUACK_PORT,
    DatarecordSessionLauncher,
    DatarecordSessionSpec,
)
from manta.services.errors import BackendError
from manta.services.results.datarecord_session_result import (
    DatarecordSessionRegistrationResult,
    OpenDatarecordSessionResult,
    QuackConnectionResult,
    QuackUpstreamResult,
)
from manta.services.user_service import UserService

logger = logging.getLogger(__name__)

QUACK_URI = "/quack"
HEALTH_TIMEOUT = 30.0
HEALTH_INTERVAL = 0.2
_PASSED_THROUGH_STATUS_CODES = (404, 422)
SWEEP_INTERVAL = 60.0
QUACK_TOUCH_INTERVAL = timedelta(minutes=1)
_STARTING_LOCK = 4_172_903_516


class DatarecordSessionService:
    def __init__(
        self,
        db: Session = Depends(get_db_session),
        user_service: UserService = Depends(),
        launcher: DatarecordSessionLauncher = Depends(get_datarecord_session_launcher),
        http: httpx2.Client = Depends(get_datarecord_session_http),
        bucket: str = Depends(s3_bucket_name),
    ) -> None:
        self.db = db
        self.user_service = user_service
        self.launcher = launcher
        self.http = http
        self.bucket = bucket

    def open(self, project_uuid: UUID, user: User) -> OpenDatarecordSessionResult:
        session, skipped = self.ensure_datarecord_session(project_uuid, user)
        result = OpenDatarecordSessionResult(
            status=session.status,
            generation=session.generation,
            quack=QuackConnectionResult(uri=QUACK_URI, token=session.quack_token),
            skipped_registrations=skipped,
        )
        self.db.commit()
        return result

    def quack_upstream(self, project_uuid: UUID, user: User) -> QuackUpstreamResult:
        project = self.user_service.get_owned_project(project_uuid, user)
        session = (
            self.db.query(DatarecordSession)
            .filter_by(
                user_id=user.id, project_id=project.id, status=DatarecordSessionStatus.ACTIVE
            )
            .one_or_none()
        )
        if session is None:
            raise HTTPException(
                status_code=409,
                detail=f"No active datarecord session for project {project_uuid}, "
                f"open it with POST /v1/projects/{project_uuid}/datarecord-session",
            )
        now = datetime.now(UTC)
        unlocked = (
            select(DatarecordSession.id)
            .filter_by(id=session.id)
            .where(DatarecordSession.last_used_at < now - QUACK_TOUCH_INTERVAL)
            .with_for_update(skip_locked=True)
        )
        self.db.execute(
            update(DatarecordSession)
            .where(DatarecordSession.id.in_(unlocked))
            .values(last_used_at=now)
        )
        self.db.commit()
        _, endpoint = _instance(session)
        return QuackUpstreamResult(upstream=f"{endpoint}:{DATARECORD_SESSION_QUACK_PORT}")

    def suspend(self, project_uuid: UUID, user: User) -> None:
        project = self.user_service.get_owned_project(project_uuid, user)
        session = self._locked_session(project, user)
        if session.status == DatarecordSessionStatus.ACTIVE:
            self._stop(session)
            logger.info("Suspended datarecord session %s", session.uuid)
        self.db.commit()

    def put_registration(
        self,
        project_uuid: UUID,
        user: User,
        name: str,
        kind: str,
        store: str,
        revision: UUID,
        packs: list[str],
    ) -> DatarecordSessionRegistrationResult:
        session, _ = self.ensure_datarecord_session(project_uuid, user)
        registration = self._find_registration(session, name)
        if registration is None:
            registration = DatarecordSessionRegistration(
                datarecord_session_id=session.id, name=name
            )
            self.db.add(registration)
        registration.kind = kind
        registration.store = store
        registration.revision_uuid = revision
        registration.packs = packs
        self.db.flush()
        result = DatarecordSessionRegistrationResult.from_registration(
            registration, self._apply(session, registration).json()["prefix"]
        )
        self.db.commit()
        return result

    def get_registration(
        self, project_uuid: UUID, user: User, name: str
    ) -> DatarecordSessionRegistrationResult:
        session, _ = self.ensure_datarecord_session(project_uuid, user)
        registration = self._get_registration(session, name)
        response = self._request(session, "GET", f"/registrations/{name}")
        result = DatarecordSessionRegistrationResult.from_registration(
            registration, response.json()["prefix"]
        )
        self.db.commit()
        return result

    def delete_registration(self, project_uuid: UUID, user: User, name: str) -> None:
        project = self.user_service.get_owned_project(project_uuid, user)
        session = self._locked_session(project, user)
        self.db.delete(self._get_registration(session, name))
        self.db.flush()
        if session.status == DatarecordSessionStatus.ACTIVE and self._is_healthy(session):
            try:
                self._request(session, "DELETE", f"/registrations/{name}")
            except HTTPException as error:
                if error.status_code != 404:
                    raise
        self.db.commit()

    def sweep(self, unused_since: datetime) -> None:
        self._stop_unused(unused_since)
        self._remove_orphans()

    def ensure_datarecord_session(
        self, project_uuid: UUID, user: User
    ) -> tuple[DatarecordSession, list[str]]:
        project = self.user_service.get_owned_project(project_uuid, user)
        session = self._locked_session(project, user)
        if session.status == DatarecordSessionStatus.ACTIVE and not self._is_healthy(session):
            logger.warning("Datarecord session %s does not answer, restarting it", session.uuid)
            self._stop(session)
        skipped: list[str] = []
        while session.status == DatarecordSessionStatus.STOPPED:
            skipped = self._start(session, project, user)
            self.db.commit()
            session = self._locked_session(project, user)
        session.last_used_at = datetime.now(UTC)
        return session, skipped

    def _locked_session(self, project: Project, user: User) -> DatarecordSession:
        query = (
            self.db.query(DatarecordSession)
            .filter_by(user_id=user.id, project_id=project.id)
            .with_for_update()
            .populate_existing()
        )
        session = query.one_or_none()
        if session is not None:
            return session
        new_session = insert(DatarecordSession).values(
            user_id=user.id,
            project_id=project.id,
            status=DatarecordSessionStatus.STOPPED,
            generation=0,
            quack_token=secrets.token_urlsafe(32),
            api_secret=secrets.token_urlsafe(32),
        )
        self.db.execute(
            new_session.on_conflict_do_nothing(index_elements=["user_id", "project_id"])
        )
        return query.one()

    def _stop_unused(self, unused_since: datetime) -> None:
        query = (
            self.db.query(DatarecordSession)
            .filter(
                DatarecordSession.status == DatarecordSessionStatus.ACTIVE,
                DatarecordSession.last_used_at < unused_since,
            )
            .with_for_update(skip_locked=True)
            .populate_existing()
            .limit(1)
        )
        while (session := query.one_or_none()) is not None:
            self._stop(session)
            logger.info(
                "Stopped datarecord session %s, unused since %s",
                session.uuid,
                session.last_used_at,
            )
            self.db.commit()

    def _remove_orphans(self) -> None:
        if not self.db.scalar(select(func.pg_try_advisory_xact_lock(_STARTING_LOCK))):
            logger.info("A session is starting or another sweep runs, leaving orphans for later")
            return
        active = select(DatarecordSession.instance_ref).filter_by(
            status=DatarecordSessionStatus.ACTIVE
        )
        for ref in self.launcher.list() - set(self.db.scalars(active)):
            self.launcher.stop(ref)
            logger.info("Removed orphaned datarecord session container %s", ref)
        self.db.commit()

    def _start(self, session: DatarecordSession, project: Project, user: User) -> list[str]:
        self.db.execute(select(func.pg_advisory_xact_lock_shared(_STARTING_LOCK)))
        spec = DatarecordSessionSpec(
            session_uuid=session.uuid,
            user_uuid=user.uuid,
            project_uuid=project.uuid,
            store_root=f"s3://{self.bucket}/{project.uuid}/",
            s3_credential=project_read_credential(project.uuid),
            quack_token=session.quack_token,
            api_secret=session.api_secret,
        )
        instance = self.launcher.start(spec)
        session.instance_ref = instance.ref
        session.endpoint = instance.endpoint
        try:
            self._wait_until_healthy(session)
            skipped = self._replay(session, project)
        except Exception:
            self.launcher.stop(instance.ref)
            raise
        session.status = DatarecordSessionStatus.ACTIVE
        session.generation += 1
        session.started_at = session.last_used_at = datetime.now(UTC)
        logger.info(
            "Started datarecord session %s (generation %d)", session.uuid, session.generation
        )
        return skipped

    def _stop(self, session: DatarecordSession) -> None:
        ref, _ = _instance(session)
        self.launcher.stop(ref)
        session.status = DatarecordSessionStatus.STOPPED
        session.instance_ref = None
        session.endpoint = None

    def _replay(self, session: DatarecordSession, project: Project) -> list[str]:
        registrations = (
            self.db.query(DatarecordSessionRegistration)
            .filter_by(datarecord_session_id=session.id)
            .order_by(DatarecordSessionRegistration.id)
            .all()
        )
        skipped: list[str] = []
        for registration in registrations:
            try:
                self._apply(session, registration)
            except HTTPException as error:
                logger.warning(
                    "Skipped registration %r of project %s on replay, the session answered %d: %s",
                    registration.name,
                    project.uuid,
                    error.status_code,
                    error.detail,
                )
                skipped.append(registration.name)
        return skipped

    def _is_healthy(self, session: DatarecordSession) -> bool:
        try:
            self._request(session, "GET", "/health")
        except httpx2.TransportError:
            return False
        return True

    def _wait_until_healthy(self, session: DatarecordSession) -> None:
        deadline = time.monotonic() + HEALTH_TIMEOUT
        while not self._is_healthy(session):
            if time.monotonic() > deadline:
                raise BackendError(
                    status_code=503, detail="The datarecord session did not become healthy"
                )
            time.sleep(HEALTH_INTERVAL)

    def _apply(
        self, session: DatarecordSession, registration: DatarecordSessionRegistration
    ) -> httpx2.Response:
        body = {
            "kind": registration.kind,
            "store": registration.store,
            "revision": str(registration.revision_uuid),
            "packs": registration.packs,
        }
        return self._request(session, "PUT", f"/registrations/{registration.name}", json=body)

    def _request(
        self, session: DatarecordSession, method: str, path: str, json: Any = None
    ) -> httpx2.Response:
        _, endpoint = _instance(session)
        response = self.http.request(
            method,
            f"http://{endpoint}:{DATARECORD_SESSION_API_PORT}{path}",
            json=json,
            headers={"Authorization": f"Bearer {session.api_secret}"},
        )
        if response.status_code in _PASSED_THROUGH_STATUS_CODES:
            raise HTTPException(status_code=response.status_code, detail=response.json()["detail"])
        response.raise_for_status()
        return response

    def _find_registration(
        self, session: DatarecordSession, name: str
    ) -> DatarecordSessionRegistration | None:
        return (
            self.db.query(DatarecordSessionRegistration)
            .filter_by(datarecord_session_id=session.id, name=name)
            .one_or_none()
        )

    def _get_registration(
        self, session: DatarecordSession, name: str
    ) -> DatarecordSessionRegistration:
        registration = self._find_registration(session, name)
        if registration is None:
            raise HTTPException(status_code=404, detail=f"Registration {name!r} not found")
        return registration


async def run_datarecord_session_sweeps() -> None:
    while True:
        try:
            await asyncio.to_thread(_sweep_datarecord_sessions)
        except Exception:
            logger.exception("Sweeping datarecord sessions failed")
        await asyncio.sleep(SWEEP_INTERVAL)


def _sweep_datarecord_sessions() -> None:
    with Session(get_engine()) as db:
        service = DatarecordSessionService(
            db,
            UserService(db),
            get_datarecord_session_launcher(),
            get_datarecord_session_http(),
            s3_bucket_name(),
        )
        service.sweep(idle_cutoff())


def idle_cutoff() -> datetime:
    return datetime.now(UTC) - datarecord_session_max_idle() - QUACK_TOUCH_INTERVAL


def _instance(session: DatarecordSession) -> tuple[str, str]:
    if session.instance_ref is None or session.endpoint is None:
        raise BackendError(
            detail=f"Datarecord session {session.uuid} is active without an instance"
        )
    return session.instance_ref, session.endpoint
