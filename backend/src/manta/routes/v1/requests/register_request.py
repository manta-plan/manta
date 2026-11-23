# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username: str
    idp_subject: str
    idp_source: str
