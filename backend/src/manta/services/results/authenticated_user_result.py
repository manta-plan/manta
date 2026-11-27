# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthenticatedUserResult(BaseModel):
    # Ownership checks compare against this object, so no service may alter it.
    model_config = ConfigDict(frozen=True)

    # The database key, for services to match against foreign keys. Excluded from
    # serialisation so it can never reach a client; `uuid` is the public identifier.
    id: int = Field(exclude=True)
    uuid: UUID
    username: str
