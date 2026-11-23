from typing import Annotated

from fastapi import Path

from manta.services.datarecord_store_service import STORE_NAME

StoreName = Annotated[str, Path(pattern=STORE_NAME.pattern, max_length=255)]
