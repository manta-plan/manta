# SPDX-FileCopyrightText: Manta contributors
#
# SPDX-License-Identifier: Apache-2.0

from pydantic import BaseModel


class RefreshTokenRequest(BaseModel):
    refresh_token: str
