# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from pydantic import BaseModel


class RefreshTokenRequest(BaseModel):
    refresh_token: str
