import os
from functools import lru_cache

import docker
import httpx2
from dotenv import load_dotenv

from manta.services.datarecord_session_launcher import (
    DatarecordSessionLauncher,
    DockerDatarecordSessionLauncher,
)


def datarecord_session_image() -> str:
    load_dotenv()
    return os.environ["DATARECORD_SESSION_IMAGE"]


def datarecord_session_network() -> str:
    load_dotenv()
    return os.environ["MANTA_DOCKER_NETWORK"]


def datarecord_session_s3_endpoint() -> str:
    load_dotenv()
    return os.environ["MANTA_JOB_S3_ENDPOINT"]


@lru_cache
def get_datarecord_session_launcher() -> DatarecordSessionLauncher:
    return DockerDatarecordSessionLauncher(
        client=docker.from_env(),
        image=datarecord_session_image(),
        network=datarecord_session_network(),
        s3_endpoint=datarecord_session_s3_endpoint(),
    )


@lru_cache
def get_datarecord_session_http() -> httpx2.Client:
    return httpx2.Client(timeout=60)
