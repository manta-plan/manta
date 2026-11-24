import logging
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from docker import DockerClient
from docker.errors import NotFound

from manta.config.s3_config import S3_REGION, S3Credential

logger = logging.getLogger(__name__)

DATARECORD_SESSION_API_PORT = 8080
DATARECORD_SESSION_QUACK_PORT = 9494
DATARECORD_SESSION_LABEL = "manta.datarecord-session"


@dataclass(frozen=True)
class DatarecordSessionSpec:
    session_uuid: UUID
    user_uuid: UUID
    project_uuid: UUID
    store_root: str
    s3_credential: S3Credential
    quack_token: str
    api_secret: str


@dataclass(frozen=True)
class DatarecordSessionInstance:
    ref: str
    endpoint: str


class DatarecordSessionLauncher(Protocol):
    def start(self, spec: DatarecordSessionSpec) -> DatarecordSessionInstance: ...

    def stop(self, ref: str) -> None: ...


class DockerDatarecordSessionLauncher:
    def __init__(self, client: DockerClient, image: str, network: str, s3_endpoint: str) -> None:
        self.client = client
        self.image = image
        self.network = network
        self.s3_endpoint = s3_endpoint

    def start(self, spec: DatarecordSessionSpec) -> DatarecordSessionInstance:
        name = f"datarecord-session-{uuid4()}"
        container = self.client.containers.run(
            self.image,
            name=name,
            detach=True,
            network=self.network,
            labels=_labels(spec),
            environment=self._environment(spec),
        )
        logger.info("Started datarecord session %s as container %s", spec.session_uuid, name)
        return DatarecordSessionInstance(ref=container.id, endpoint=name)

    def stop(self, ref: str) -> None:
        try:
            self.client.containers.get(ref).remove(force=True)
        except NotFound:
            logger.info("Datarecord session container %s is already gone", ref)
            return
        logger.info("Removed datarecord session container %s", ref)

    def _environment(self, spec: DatarecordSessionSpec) -> dict[str, str]:
        return {
            "DATARECORD_SESSION_STORE_ROOT": spec.store_root,
            "DATARECORD_SESSION_S3_KEY_ID": spec.s3_credential.key_id,
            "DATARECORD_SESSION_S3_SECRET": spec.s3_credential.secret,
            "DATARECORD_SESSION_S3_ENDPOINT": self.s3_endpoint,
            "DATARECORD_SESSION_S3_REGION": S3_REGION,
            "DATARECORD_SESSION_QUACK_TOKEN": spec.quack_token,
            "DATARECORD_SESSION_API_SECRET": spec.api_secret,
        }


def _labels(spec: DatarecordSessionSpec) -> dict[str, str]:
    return {
        f"{DATARECORD_SESSION_LABEL}.session": str(spec.session_uuid),
        f"{DATARECORD_SESSION_LABEL}.user": str(spec.user_uuid),
        f"{DATARECORD_SESSION_LABEL}.project": str(spec.project_uuid),
    }
