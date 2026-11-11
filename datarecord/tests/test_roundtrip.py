# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Single-layer read path: our DuckDB reader against PyPSA's own.

Notes
-----
- [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
"""

import pandas as pd
import pytest

from datarecord import Workspace
from datarecord.tools.pypsa import PyPSA
from tests.fixtures import export_network


def _has_export_to_parquet() -> bool:
    # Imported lazily, like the rest of this module's PyPSA use, so collecting
    # these tests does not require PyPSA to be installed - collection happens
    # even in an environment that never runs the ac_dc-dependent tests here.
    try:
        import pypsa
    except ImportError:
        return False
    return hasattr(pypsa.Network, "export_to_parquet")


needs_export_to_parquet = pytest.mark.skipif(
    not _has_export_to_parquet(),
    reason="needs PyPSA's own parquet reader/writer, unreleased (https://energy-models.github.io/datarecord/design/tools/)",
)


def assert_networks_equal(got, expected):
    """Compare component frames, which is what the record round-trips."""
    for exp_c in expected.components:
        ctype = exp_c.name
        if exp_c.static.empty:
            continue
        got_c = got.c[ctype]
        pd.testing.assert_index_equal(
            got_c.static.index, exp_c.static.index, check_names=False
        )
        # No junk columns (join artifacts, `deleted`, ...) may leak through.
        assert not set(got_c.static.columns) - set(exp_c.static.columns)
        for col in exp_c.static.columns:
            if col == "obj":
                continue
            pd.testing.assert_series_equal(
                got_c.static[col],
                exp_c.static[col],
                check_dtype=False,
                check_names=False,
            )
        assert set(got_c.dynamic) >= {
            a for a, f in exp_c.dynamic.items() if not f.empty
        }
        for attr, frame in exp_c.dynamic.items():
            if frame.empty:
                continue
            pd.testing.assert_frame_equal(
                got_c.dynamic[attr][frame.columns],
                frame,
                check_dtype=False,
                check_freq=False,
                check_column_type=False,
                check_index_type=False,
            )


@pytest.fixture(scope="module")
def built(tmp_path_factory, ac_dc):
    """`ac_dc` exported and built back once for the module; tests only read it."""
    workspace = Workspace()
    revision = export_network(
        ac_dc, workspace.store(str(tmp_path_factory.mktemp("ac_dc")))
    )
    yield PyPSA.build(revision.record)
    workspace.close()


@needs_export_to_parquet
def test_roundtrip_matches_pypsa_reader(tmp_path, built, ac_dc):
    """Our reader agrees with `import_from_parquet` on the network each produces.

    Not over the same directory: a record blocks writes declares its schema in
    `manifest.json`, which is a different vocabulary from the one
    PyPSA's own reader expects there. So each writer's record is read by its
    own reader and the two networks are compared - which is the property that
    actually matters, and the one a shared directory was only a proxy for.

    Notes
    -----
    - [one schema per record](https://energy-models.github.io/datarecord/design/schema/#one-schema-per-record)
    """
    import pypsa

    plain = str(tmp_path / "pypsa-written")
    ac_dc.export_to_parquet(plain)
    reference = pypsa.Network()
    reference.import_from_parquet(plain)  # type: ignore[attr-defined]

    assert_networks_equal(built, reference)


def test_roundtrip_matches_original(built, ac_dc):
    """Genuine data loss surfaces here even if it is shared with upstream."""
    assert_networks_equal(built, ac_dc)


def test_static_series_split_preserved(built):
    """A static-valued varying attribute stays out of `dynamic`.

    Notes
    -----
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    n = built
    # Only the three wind generators carry a p_max_pu series in ac_dc_meshed.
    assert set(n.c["Generator"].dynamic["p_max_pu"].columns) == {
        "Manchester Wind",
        "Norway Wind",
        "Frankfurt Wind",
    }
    # Links' p_max_pu is static-valued, so it must not appear as a series.
    assert n.c["Link"].dynamic["p_max_pu"].empty
