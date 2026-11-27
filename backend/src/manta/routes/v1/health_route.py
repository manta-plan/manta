# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}
