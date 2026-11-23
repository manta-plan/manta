import os
from functools import lru_cache

from datarecord import S3Credentials, Workspace
from dotenv import load_dotenv

from manta.config.s3_config import s3_bucket_name, s3_endpoint_url


@lru_cache
def get_datarecord_workspace() -> Workspace:
    load_dotenv()
    return Workspace(
        credentials=S3Credentials(
            key_id=os.environ["S3_ACCESS_KEY"],
            secret=os.environ["S3_SECRET_KEY"],
            endpoint=s3_endpoint_url(),
            url_style="path",
        )
    )


def datarecord_root() -> str:
    return f"s3://{s3_bucket_name()}"
