# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel


class LoginResult(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 It's not a password
    expires_in: int
    refresh_token: str
    refresh_expires_in: int
