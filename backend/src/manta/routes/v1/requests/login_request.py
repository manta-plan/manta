# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
