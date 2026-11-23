# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The session's internal API: only the backend calls it, with the API secret as bearer token."""

from __future__ import annotations

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from datarecord_session.config import Settings
from datarecord_session.packs import Pack
from datarecord_session.session import (
    NotFoundError,
    Registration,
    RegistrationName,
    Session,
    ViewRegistration,
)


class Registered(BaseModel):
    name: str
    prefix: str


class RegistrationDetail(Registered):
    kind: str
    store: str
    revision: UUID
    packs: list[Pack]
    manifest: dict[str, Any]
    views: dict[str, list[str]]

    @classmethod
    def of(cls, name: str, registration: Registration) -> RegistrationDetail:
        request = registration.request
        return cls(
            name=name,
            prefix=registration.prefix,
            kind=request.kind,
            store=request.store,
            revision=request.revision,
            packs=sorted(request.packs),
            manifest=registration.manifest,
            views=registration.views,
        )


def not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": str(exc)})


def create_app(settings: Settings) -> FastAPI:
    session = Session(settings)
    expected = f"Bearer {settings.api_secret}".encode()

    def require_secret(authorization: Annotated[str, Header()] = "") -> None:
        if not secrets.compare_digest(authorization.encode(), expected):
            raise HTTPException(status_code=401, detail="Invalid API secret")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await session.call(session.start)
        yield
        await session.call(session.stop)

    app = FastAPI(
        title="datarecord session", lifespan=lifespan, dependencies=[Depends(require_secret)]
    )
    app.add_exception_handler(NotFoundError, not_found)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/registrations")
    async def names() -> list[str]:
        return await session.call(session.names)

    @app.put("/registrations/{name}")
    async def register(name: RegistrationName, request: ViewRegistration) -> Registered:
        registration = await session.call(session.register, name, request)
        return Registered(name=name, prefix=registration.prefix)

    @app.get("/registrations/{name}")
    async def get(name: RegistrationName) -> RegistrationDetail:
        return RegistrationDetail.of(name, await session.call(session.get, name))

    @app.delete("/registrations/{name}", status_code=204)
    async def unregister(name: RegistrationName) -> Response:
        await session.call(session.unregister, name)
        return Response(status_code=204)

    return app


def main() -> None:
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port)
