# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

import pytest

from datarecord import Workspace


@pytest.fixture
def workspace():
    ws = Workspace()
    yield ws
    ws.close()


@pytest.fixture
def store(workspace, tmp_path):
    return workspace.store(str(tmp_path))


@pytest.fixture(scope="session")
def ac_dc():
    """PyPSA's `ac_dc_meshed`, with its loads renamed off their buses.

    The example names each `Load` after the `Bus` it sits on, which a record
    cannot represent: names are unique across component types,
    and `PyPSA.to_datarecord` rejects such a network rather than renaming it. Renaming here is the test suite standing in for the caller that has
    to reconcile the two vocabularies; `test_tools.py` pins the rejection
    itself.

    Its carriers' own `efficiency` and `marginal_cost` columns are dropped
    for the same reason: one name is one spec record-wide, and PyPSA declares
    both names with a shape no entity column has.

    Notes
    -----
    - [entity is unique across types](https://energy-models.github.io/datarecord/design/format/#entity-is-unique-across-types)
    - [consuming a record](https://energy-models.github.io/datarecord/design/tools/)
    """
    import pypsa

    from tests.fixtures import example, rename_components

    n = example(pypsa.examples.ac_dc_meshed)
    rename_components(n, "Load", " Load")
    n.c.Carrier.static = n.c.Carrier.static.drop(
        columns=["efficiency", "marginal_cost"]
    )
    return n
