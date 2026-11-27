# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The four inputs a session starts from, and where it listens, read from the environment.

`DATARECORD_SESSION_STORE_ROOT` is the project's folder, `s3://<bucket>/<project_uuid>/`,
or a local path. An `s3://` root needs the S3 credential in `DATARECORD_SESSION_S3_*`;
the session never reads the `AWS_*` variables.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from datarecord import S3Credentials

PREFIX = "DATARECORD_SESSION_"


def _credentials(env: Mapping[str, str]) -> S3Credentials:
    return S3Credentials(
        key_id=env[f"{PREFIX}S3_KEY_ID"],
        secret=env[f"{PREFIX}S3_SECRET"],
        session_token=env.get(f"{PREFIX}S3_SESSION_TOKEN") or None,
        endpoint=env[f"{PREFIX}S3_ENDPOINT"],
        region=env[f"{PREFIX}S3_REGION"],
        url_style="path",
    )


@dataclass(frozen=True)
class Settings:
    store_root: str
    credentials: S3Credentials | None
    quack_token: str
    api_secret: str
    quack_host: str = "0.0.0.0"  # noqa: S104
    quack_port: int = 9494
    api_host: str = "0.0.0.0"  # noqa: S104
    api_port: int = 8080

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        root = env[f"{PREFIX}STORE_ROOT"]
        return cls(
            store_root=root,
            credentials=_credentials(env) if root.startswith("s3://") else None,
            quack_token=env[f"{PREFIX}QUACK_TOKEN"],
            api_secret=env[f"{PREFIX}API_SECRET"],
            quack_host=env.get(f"{PREFIX}QUACK_HOST", cls.quack_host),
            quack_port=int(env.get(f"{PREFIX}QUACK_PORT", cls.quack_port)),
            api_host=env.get(f"{PREFIX}API_HOST", cls.api_host),
            api_port=int(env.get(f"{PREFIX}API_PORT", cls.api_port)),
        )

    def store_uri(self, store: str) -> str:
        return f"{self.store_root.rstrip('/')}/{store}"
