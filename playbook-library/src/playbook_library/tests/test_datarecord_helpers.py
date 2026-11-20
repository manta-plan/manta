# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

from uuid import UUID

import pytest

pytest.importorskip("pypsa", reason="the stored test network needs PyPSA installed")

from playbook.blocks.core import DataRecord, DataRecordError

from playbook_library.datarecord_helpers import revision

pytestmark = pytest.mark.pypsa


def test_revision_returns_the_revision_a_record_points_at(single_period_record):
    _, rev = revision(single_period_record)
    assert rev.id == single_period_record.uuid


@pytest.mark.parametrize(
    ("url_suffix", "uuid"),
    [("missing-store", None), ("", UUID(int=0))],
    ids=["missing-store", "missing-revision"],
)
def test_a_record_pointing_at_nothing_raises_a_datarecord_error(
    single_period_record, url_suffix, uuid
):
    record = DataRecord(
        url=single_period_record.url + url_suffix, uuid=uuid or single_period_record.uuid
    )
    with pytest.raises(DataRecordError, match="No revision"):
        revision(record)
