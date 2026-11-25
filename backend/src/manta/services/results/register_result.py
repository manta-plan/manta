# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RegisterResult(BaseModel):
    uuid: UUID
    username: str
    idp_subject: str
    idp_source: str
    created_at: datetime
