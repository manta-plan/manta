import json
import time
from dataclasses import dataclass, field
from uuid import uuid4

import httpx2

from manta.services.datarecord_session_launcher import (
    DatarecordSessionInstance,
    DatarecordSessionSpec,
)


@dataclass
class FakeDatarecordSession:
    spec: DatarecordSessionSpec
    registrations: dict[str, dict] = field(default_factory=dict)


class FakeDatarecordSessionLauncher:
    """Stands in for Docker and the session containers: each started instance serves the
    session's internal API in memory, at its endpoint, through `http`."""

    def __init__(self, stores: set[str], start_delay: float = 0.0, healthy: bool = True) -> None:
        self.stores = stores
        self.start_delay = start_delay
        self.healthy = healthy
        self.refusals: dict[str, int] = {}
        self.started: list[DatarecordSessionSpec] = []
        self.running: dict[str, FakeDatarecordSession] = {}
        self.http = httpx2.Client(transport=httpx2.MockTransport(self._handle))

    def start(self, spec: DatarecordSessionSpec) -> DatarecordSessionInstance:
        time.sleep(self.start_delay)
        endpoint = f"datarecord-session-{uuid4()}"
        self.started.append(spec)
        self.running[endpoint] = FakeDatarecordSession(spec)
        return DatarecordSessionInstance(ref=endpoint, endpoint=endpoint)

    def stop(self, ref: str) -> None:
        self.running.pop(ref, None)

    def list(self) -> set[str]:
        return set(self.running)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        session = self.running.get(request.url.host)
        if session is None or not self.healthy:
            raise httpx2.ConnectError(f"{request.url.host} is not running", request=request)
        if request.headers["Authorization"] != f"Bearer {session.spec.api_secret}":
            return httpx2.Response(401, json={"detail": "Invalid API secret"})
        if request.url.path == "/health":
            return httpx2.Response(200, json={"status": "ok"})
        name = request.url.path.removeprefix("/registrations/")
        registered = {"name": name, "prefix": f'manta."{name}"'}
        if request.method == "PUT":
            body = json.loads(request.content)
            if body["store"] in self.refusals:
                status = self.refusals[body["store"]]
                return httpx2.Response(status, json={"detail": f"Store {body['store']} refused"})
            if body["store"] not in self.stores:
                return httpx2.Response(404, json={"detail": f"Store {body['store']} not found"})
            session.registrations[name] = body
            return httpx2.Response(200, json=registered)
        if name not in session.registrations:
            return httpx2.Response(404, json={"detail": f"{name} is not registered"})
        if request.method == "DELETE":
            del session.registrations[name]
            return httpx2.Response(204)
        return httpx2.Response(200, json={**registered, **session.registrations[name]})
