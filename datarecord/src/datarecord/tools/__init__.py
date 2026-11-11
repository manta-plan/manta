# SPDX-FileCopyrightText: datarecord contributors
#
# SPDX-License-Identifier: MIT

"""Tool representations of a `Revision`.

A record is tool-agnostic: it resolves to dims, entities and attributes. A
*tool* is one concrete modelling framework that can be built from such a
resolution - PyPSA today, others later. Everything a tool needs to know
about its own framework lives in its module here; nothing in `datarecord`
proper imports a tool, and this package imports none of them either.

Import the tool's own module (`datarecord.tools.pypsa`) to be explicit about
which framework you pull in, and install its extra (`datarecord[pypsa]`) to
get its dependencies.
"""
