import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx2
import pytest
from testcontainers.compose import DockerCompose

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKER_DIR = REPO_ROOT / "docker"
BACKEND_ENV_FILE = REPO_ROOT / "backend" / ".env"


def _print_logs(label: str, stdout: str, stderr: str) -> None:
    print(f"\n----- {label} logs -----")
    print(stdout)
    if stderr:
        print(f"----- {label} stderr -----\n{stderr}")


@pytest.fixture(scope="session")
def postgres_service() -> Iterator[dict[str, str]]:
    """Boots the same Postgres service dev uses (compose.services.yaml), isolated
    from any locally running dev stack via the compose.test.yaml overlay."""
    with DockerCompose(
        DOCKER_DIR,
        compose_file_name=["compose.services.yaml", "compose.test.yaml"],
        env_file=str(BACKEND_ENV_FILE),
    ) as compose:
        host, port = compose.get_service_host_and_port("postgres", 5432)
        yield {"host": host, "port": str(port)}
        # Fetched before `stop()` removes the container — covers the whole session.
        _print_logs("postgres", *compose.get_logs())


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_until_healthy(base_url: str, process: subprocess.Popen, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"app process exited early with code {process.returncode}")
        try:
            httpx2.get(f"{base_url}/health", timeout=1.0)
            return
        except httpx2.TransportError:
            time.sleep(0.2)
    raise TimeoutError(f"app did not become healthy within {timeout}s")


@pytest.fixture(scope="session")
def app_server(postgres_service: dict[str, str]) -> Iterator[str]:
    """Runs the real app as a host subprocess on a free port, so the integration
    suite exercises an actual HTTP round trip instead of an in-process ASGI call."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "POSTGRES_HOST": postgres_service["host"],
        "POSTGRES_PORT": postgres_service["port"],
    }

    process = subprocess.Popen(  # noqa: S603 — fixed args, no untrusted input
        [
            sys.executable,
            "-m",
            "uvicorn",
            "manta.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
    )
    try:
        _wait_until_healthy(base_url, process)
        yield base_url
    finally:
        process.terminate()
        process.wait(timeout=10)
