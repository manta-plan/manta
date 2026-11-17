# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

import importlib.metadata
import warnings

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError as e:  # pragma: no cover
    warnings.warn(f"Could not determine version of {__name__}\n{e!s}", stacklevel=2)
    __version__ = "unknown"

from datarecord.layered.record import Record
from datarecord.layered.revision import Revision
from datarecord.mutable import WorkingRecord
from datarecord.record import (
    Flags,
    Frames,
    LazyFrames,
    RecordLike,
)
from datarecord.schema import (
    AttributeSpec,
    Dimension,
    Group,
    PropertySpec,
    Schema,
    Trait,
)
from datarecord.store import Store, Workspace

__all__ = [
    "AttributeSpec",
    "Dimension",
    "Flags",
    "Frames",
    "Group",
    "LazyFrames",
    "PropertySpec",
    "Record",
    "RecordLike",
    "Revision",
    "Schema",
    "Store",
    "Trait",
    "WorkingRecord",
    "Workspace",
]
