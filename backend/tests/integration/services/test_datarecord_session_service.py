import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from datarecord_session_fake import FakeDatarecordSessionLauncher
from dotenv import dotenv_values
from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from manta.config.datarecord_session_config import datarecord_session_max_idle
from manta.entities import (
    DatarecordSession,
    DatarecordSessionRegistration,
    DatarecordSessionStatus,
    Project,
    User,
)
from manta.services.datarecord_session_service import DatarecordSessionService, idle_cutoff
from manta.services.user_service import UserService

BUCKET = dotenv_values(Path(__file__).resolve().parents[3] / ".env")["S3_BUCKET"]


@pytest.fixture
def project_and_owner(db_engine: Engine) -> tuple[Project, User]:
    with Session(db_engine, expire_on_commit=False) as db:
        owner = User(username=f"user-{uuid4()}", idp_subject=str(uuid4()), idp_source="test")
        db.add(owner)
        db.flush()
        project = Project(name="Sessions", owner_id=owner.id)
        db.add(project)
        db.commit()
    return project, owner


@contextmanager
def _service(
    db_engine: Engine, launcher: FakeDatarecordSessionLauncher
) -> Iterator[DatarecordSessionService]:
    with Session(db_engine) as db:
        yield DatarecordSessionService(db, UserService(db), launcher, launcher.http, BUCKET)


def _open(
    db_engine: Engine, launcher: FakeDatarecordSessionLauncher, project: Project, user: User
) -> int:
    with _service(db_engine, launcher) as service:
        return service.open(project.uuid, user).generation


def _sweep(db_engine: Engine, launcher: FakeDatarecordSessionLauncher) -> None:
    with _service(db_engine, launcher) as service:
        service.sweep(idle_cutoff())


def _last_used(db_engine: Engine, project: Project, user: User, ago: timedelta) -> None:
    with Session(db_engine) as db:
        db.execute(
            update(DatarecordSession)
            .filter_by(user_id=user.id, project_id=project.id)
            .values(last_used_at=datetime.now(UTC) - ago)
        )
        db.commit()


def _status(db_engine: Engine, project: Project, user: User) -> DatarecordSessionStatus:
    with Session(db_engine) as db:
        query = db.query(DatarecordSession).filter_by(user_id=user.id, project_id=project.id)
        return query.one().status


def _suspended_with_registrations(
    db_engine: Engine, launcher: FakeDatarecordSessionLauncher, project: Project, user: User
) -> None:
    with _service(db_engine, launcher) as service:
        for store in sorted(launcher.stores):
            service.put_registration(project.uuid, user, store, "view", store, uuid4(), [])
        service.suspend(project.uuid, user)


def _registration_names(db_engine: Engine, project: Project, user: User) -> set[str]:
    query = (
        select(DatarecordSessionRegistration.name)
        .join(DatarecordSession)
        .filter_by(user_id=user.id, project_id=project.id)
    )
    with Session(db_engine) as db:
        return set(db.scalars(query))


@pytest.mark.parametrize("status", [404, 422])
def test_replay_skips_a_registration_the_session_refuses(
    db_engine: Engine,
    project_and_owner: tuple[Project, User],
    caplog: pytest.LogCaptureFixture,
    status: int,
) -> None:
    # Given a suspended session with three registrations, two of stores the session refuses
    launcher = FakeDatarecordSessionLauncher(stores={"gone", "kept", "lost"})
    project, owner = project_and_owner
    _suspended_with_registrations(db_engine, launcher, project, owner)
    launcher.refusals.update(gone=status, lost=status)

    # When the session opens again
    with _service(db_engine, launcher) as service:
        result = service.open(project.uuid, owner)

    # Then it starts with the other registration, names and warns about the refused ones,
    # and keeps them
    (instance,) = launcher.running.values()
    assert result.generation == 2
    assert result.skipped_registrations == ["gone", "lost"]
    assert set(instance.registrations) == {"kept"}
    assert f"'gone' of project {project.uuid}" in caplog.text
    assert f"answered {status}: Store gone refused" in caplog.text
    assert _registration_names(db_engine, project, owner) == {"gone", "kept", "lost"}


def test_replay_aborts_the_start_on_another_answer(
    db_engine: Engine, project_and_owner: tuple[Project, User]
) -> None:
    # Given a suspended session with a registration, and a session that fails it
    launcher = FakeDatarecordSessionLauncher(stores={"broken"})
    project, owner = project_and_owner
    _suspended_with_registrations(db_engine, launcher, project, owner)
    launcher.refusals["broken"] = 500

    # When the session opens again
    with _service(db_engine, launcher) as service, pytest.raises(httpx2.HTTPStatusError):
        service.open(project.uuid, owner)

    # Then no instance runs
    assert launcher.running == {}


@pytest.mark.parametrize("suspended", [False, True], ids=["new", "suspended"])
def test_parallel_opens_start_one_instance(
    db_engine: Engine, project_and_owner: tuple[Project, User], suspended: bool
) -> None:
    # Given a launcher that is slow to start an instance, and a new or a suspended session
    launcher = FakeDatarecordSessionLauncher(stores=set(), start_delay=0.5)
    project, owner = project_and_owner
    if suspended:
        with _service(db_engine, launcher) as service:
            service.open(project.uuid, owner)
            service.suspend(project.uuid, owner)

    # When eight requests open the session at once
    with ThreadPoolExecutor(max_workers=8) as pool:
        generations = list(pool.map(lambda _: _open(db_engine, launcher, project, owner), range(8)))

    # Then one instance started for them, and every request got it
    assert generations == [1 + suspended] * 8
    assert len(launcher.started) == 1 + suspended
    assert len(launcher.running) == 1


@pytest.mark.parametrize(
    ("unused", "in_use", "status"),
    [
        (timedelta(minutes=2), False, DatarecordSessionStatus.STOPPED),
        (timedelta(seconds=30), False, DatarecordSessionStatus.ACTIVE),
        (timedelta(minutes=-1), False, DatarecordSessionStatus.ACTIVE),
        (timedelta(minutes=2), True, DatarecordSessionStatus.ACTIVE),
    ],
    ids=["expired", "within-touch-interval", "fresh", "expired-in-use"],
)
def test_sweep_stops_a_session_unused_for_longer_than_the_limit(
    db_engine: Engine,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    project_and_owner: tuple[Project, User],
    unused: timedelta,
    in_use: bool,
    status: DatarecordSessionStatus,
) -> None:
    # Given an open session, last used before or after the limit
    launcher = datarecord_session_launcher
    project, owner = project_and_owner
    _open(db_engine, launcher, project, owner)
    _last_used(db_engine, project, owner, datarecord_session_max_idle() + unused)

    # When the sessions are swept, maybe while a request uses the session
    with _service(db_engine, launcher) as request:
        if in_use:
            request.ensure_datarecord_session(project.uuid, owner)
        _sweep(db_engine, launcher)

    # Then only the expired session without a request is stopped
    assert _status(db_engine, project, owner) == status
    assert len(launcher.running) == (status == DatarecordSessionStatus.ACTIVE)


def test_open_after_a_forced_stop_restarts_the_session_with_its_registrations(
    db_engine: Engine,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    project_and_owner: tuple[Project, User],
) -> None:
    # Given a session with a registration, stopped by the sweep after the limit
    launcher = datarecord_session_launcher
    project, owner = project_and_owner
    store = next(iter(launcher.stores))
    with _service(db_engine, launcher) as service:
        service.put_registration(project.uuid, owner, "base", "view", store, uuid4(), [])
    _last_used(db_engine, project, owner, datarecord_session_max_idle() + timedelta(minutes=2))
    _sweep(db_engine, launcher)

    # When the session opens again
    generation = _open(db_engine, launcher, project, owner)

    # Then a new instance of the next generation runs, with the registration replayed
    (instance,) = launcher.running.values()
    assert generation == 2
    assert instance.registrations["base"]["store"] == store


def test_sweep_removes_orphaned_containers_and_keeps_active_ones(
    db_engine: Engine,
    datarecord_session_launcher: FakeDatarecordSessionLauncher,
    project_and_owner: tuple[Project, User],
) -> None:
    # Given an active session and a second, orphaned container of it
    launcher = datarecord_session_launcher
    project, owner = project_and_owner
    _open(db_engine, launcher, project, owner)
    active = set(launcher.running)
    launcher.start(launcher.started[0])

    # When the sessions are swept
    _sweep(db_engine, launcher)

    # Then only the active session's container runs
    assert set(launcher.running) == active


def test_sweep_keeps_the_container_of_a_session_that_is_starting(
    db_engine: Engine, project_and_owner: tuple[Project, User]
) -> None:
    # Given a session whose container runs but is not healthy yet
    launcher = FakeDatarecordSessionLauncher(stores=set(), healthy=False)
    project, owner = project_and_owner
    with ThreadPoolExecutor(max_workers=1) as pool:
        opening = pool.submit(_open, db_engine, launcher, project, owner)
        deadline = time.monotonic() + 5
        while not launcher.running:
            assert time.monotonic() < deadline, "the session container never started"
            time.sleep(0.01)

        # When the sessions are swept, and then the container becomes healthy
        _sweep(db_engine, launcher)
        starting = set(launcher.running)
        launcher.healthy = True

        # Then the container survived the sweep and became the session's instance
        assert opening.result() == 1
    assert set(launcher.running) == starting
    assert len(starting) == 1
