from pathlib import Path
from uuid import uuid4

import docker
import pytest
from dotenv import dotenv_values
from testcontainers.compose import DockerCompose

from manta.config.s3_config import S3Credential
from manta.services.datarecord_session_launcher import (
    DatarecordSessionSpec,
    DockerDatarecordSessionLauncher,
)

NETWORK = dotenv_values(Path(__file__).resolve().parents[4] / "docker" / ".env.test")[
    "MANTA_DOCKER_NETWORK"
]


@pytest.mark.parametrize("exited", [False, True], ids=["running", "exited"])
def test_docker_launcher_starts_a_labelled_container_on_the_network_and_removes_it(
    docker_services: DockerCompose, exited: bool
) -> None:
    # Given a launcher on the test stack's network, with an image the stack already has
    client = docker.from_env()
    launcher = DockerDatarecordSessionLauncher(
        client, image="postgres:17-alpine", network=NETWORK, s3_endpoint="http://seaweedfs:8333"
    )
    secret = str(uuid4())
    spec = DatarecordSessionSpec(
        session_uuid=uuid4(),
        user_uuid=uuid4(),
        project_uuid=uuid4(),
        store_root="s3://manta/project/",
        s3_credential=S3Credential(key_id="key", secret=secret),
        quack_token=secret,
        api_secret=secret,
    )

    # When an instance starts
    instance = launcher.start(spec)
    container = client.containers.get(instance.ref)

    # Then it is a container named after its endpoint, on the network, labelled and configured
    assert container.name == instance.endpoint
    assert container.attrs["HostConfig"]["NetworkMode"] == NETWORK
    assert container.labels["manta.datarecord-session.session"] == str(spec.session_uuid)
    assert "DATARECORD_SESSION_STORE_ROOT=s3://manta/project/" in container.attrs["Config"]["Env"]

    # When it runs on, or exits
    if exited:
        container.stop(timeout=0)

    # Then it is listed
    assert instance.ref in launcher.list()

    # When it stops, twice
    launcher.stop(instance.ref)
    launcher.stop(instance.ref)

    # Then it is gone
    assert instance.ref not in launcher.list()
