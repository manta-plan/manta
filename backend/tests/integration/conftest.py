import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import boto3
import httpx2
import psycopg
import pytest
from botocore.config import Config
from dotenv import dotenv_values
from mypy_boto3_s3.client import S3Client
from testcontainers.compose import DockerCompose

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCKER_DIR = REPO_ROOT / "docker"
BACKEND_ENV_FILE = REPO_ROOT / "backend" / ".env"
DOCKER_ENV_TEST_FILE = REPO_ROOT / "docker" / ".env.test"


def _print_logs(label: str, stdout: str, stderr: str) -> None:
    print(f"\n----- {label} logs -----")
    print(stdout)
    if stderr:
        print(f"----- {label} stderr -----\n{stderr}")


@pytest.fixture(scope="session")
def _docker_services() -> Iterator[DockerCompose]:
    """Boots the same stack dev uses, via compose-test-services.yaml (which
    includes compose-dev-services.yaml wholesale) isolated under its own
    Compose project name and ephemeral host ports (see docker/.env.test).
    Shared by every per-service fixture below so the stack only boots once."""
    with DockerCompose(
        DOCKER_DIR,
        compose_file_name="compose-test-services.yaml",
        env_file=[str(BACKEND_ENV_FILE), str(DOCKER_ENV_TEST_FILE)],
    ) as compose:
        yield compose
        # Fetched before `stop()` removes the containers — covers the whole session.
        _print_logs("docker services", *compose.get_logs())


@pytest.fixture(scope="session")
def postgres_service(_docker_services: DockerCompose) -> dict[str, str]:
    host, port = _docker_services.get_service_host_and_port("postgres", 5432)
    return {"host": host, "port": str(port)}


@pytest.fixture(scope="session")
def seaweedfs_service(_docker_services: DockerCompose) -> dict[str, str]:
    host, port = _docker_services.get_service_host_and_port("seaweedfs", 8333)
    return {"host": host, "port": str(port)}


@pytest.fixture(scope="session")
def db_connection(postgres_service: dict[str, str]) -> Iterator[psycopg.Connection]:
    """A direct connection to the same Postgres the app under test uses, for
    asserting on rows the app is expected to have persisted."""
    env = dotenv_values(BACKEND_ENV_FILE)
    with psycopg.connect(
        host=postgres_service["host"],
        port=postgres_service["port"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        dbname=env["POSTGRES_DB"],
        autocommit=True,
    ) as conn:
        yield conn


@pytest.fixture(scope="session")
def s3_client(seaweedfs_service: dict[str, str]) -> S3Client:
    env = dotenv_values(BACKEND_ENV_FILE)
    return boto3.client(
        "s3",
        endpoint_url=f"http://{seaweedfs_service['host']}:{seaweedfs_service['port']}",
        aws_access_key_id=env["S3_ACCESS_KEY"],
        aws_secret_access_key=env["S3_SECRET_KEY"],
        region_name="eu-central-1",
        config=Config(s3={"addressing_style": "path"}),
    )


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
            httpx2.get(f"{base_url}/v1/health", timeout=1.0)
            return
        except httpx2.TransportError:
            time.sleep(0.2)
    raise TimeoutError(f"app did not become healthy within {timeout}s")


@pytest.fixture(scope="session")
def app_server(
    postgres_service: dict[str, str], seaweedfs_service: dict[str, str]
) -> Iterator[str]:
    """Runs the real app as a host subprocess on a free port, so the integration
    suite exercises an actual HTTP round trip instead of an in-process ASGI call."""
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "POSTGRES_HOST": postgres_service["host"],
        "POSTGRES_PORT": postgres_service["port"],
        "S3_HOST": seaweedfs_service["host"],
        "S3_PORT": seaweedfs_service["port"],
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
