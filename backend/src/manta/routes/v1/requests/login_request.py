# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
