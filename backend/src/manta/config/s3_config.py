import os
from functools import lru_cache

import boto3
from botocore.config import Config
from dotenv import load_dotenv
from mypy_boto3_s3.client import S3Client


def s3_endpoint_url() -> str:
    load_dotenv()
    host = os.environ.get("S3_HOST", "localhost")
    port = os.environ["S3_PORT"]
    return f"http://{host}:{port}"


def s3_bucket_name() -> str:
    load_dotenv()
    return os.environ["S3_BUCKET"]


@lru_cache
def get_s3_client() -> S3Client:
    return boto3.client(
        "s3",
        endpoint_url=s3_endpoint_url(),
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        # SigV4 signing requires a region even against a non-AWS endpoint;
        # SeaweedFS ignores its value. eu-central-1 to match this being an
        # EU project, should this ever point at a real AWS region.
        region_name="eu-central-1",
        # Path-style URLs (http://host:port/bucket/key) instead of
        # virtual-hosted-style (http://bucket.host:port/key), which needs
        # bucket-subdomain DNS that "localhost" doesn't have.
        config=Config(s3={"addressing_style": "path"}),
    )
