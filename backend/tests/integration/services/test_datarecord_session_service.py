from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import httpx2
import pytest
from datarecord_session_fake import FakeDatarecordSessionLauncher
from dotenv import dotenv_values
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from manta.entities import (
    DatarecordSession,
    DatarecordSessionRegistration,
    Project,
    User,
)
from manta.services.datarecord_session_service import DatarecordSessionService
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

    def open_session(_: int) -> int:
        with _service(db_engine, launcher) as service:
            return service.open(project.uuid, owner).generation

    # When eight requests open the session at once
    with ThreadPoolExecutor(max_workers=8) as pool:
        generations = list(pool.map(open_session, range(8)))

    # Then one instance started for them, and every request got it
    assert generations == [1 + suspended] * 8
    assert len(launcher.started) == 1 + suspended
    assert len(launcher.running) == 1
