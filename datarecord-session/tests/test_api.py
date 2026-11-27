# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The internal API: the API secret, and registrations of the kind `view`."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from conftest import STORE, Endpoints, Register, Revisions


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
@pytest.mark.parametrize("path", ["/health", "/registrations"])
def test_every_route_needs_the_api_secret(
    endpoints: Endpoints, headers: dict[str, str], path: str
) -> None:
    assert httpx.get(endpoints.api + path, headers=headers).status_code == 401


def test_health(api: httpx.Client) -> None:
    assert api.get("/health").json() == {"status": "ok"}


def test_put_is_idempotent(api: httpx.Client, register: Register, revisions: Revisions) -> None:
    first = register("twice", revisions.base)
    second = register("twice", revisions.base)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"name": "twice", "prefix": 'manta."twice"'}
    assert api.get("/registrations").json() == ["twice"]


def test_put_of_another_revision_replaces_the_registration(
    api: httpx.Client, register: Register, revisions: Revisions
) -> None:
    register("moved", revisions.root).raise_for_status()
    register("moved", revisions.base).raise_for_status()

    detail = api.get("/registrations/moved").json()
    assert detail["revision"] == revisions.base
    assert detail["manifest"]["id"] == revisions.base


def test_get_lists_the_views(api: httpx.Client, registered: str, revisions: Revisions) -> None:
    detail = api.get("/registrations/base").json()

    assert detail["prefix"] == registered
    assert (detail["kind"], detail["store"], detail["packs"]) == ("view", STORE, ["pypsa-eur"])
    assert detail["manifest"]["parent"] == revisions.root
    views = detail["views"]
    assert views["attributes"] == [
        "busmap_1",
        "efficiency",
        "p_max_pu",
        "p_nom",
        "p_nom_extendable",
    ]
    assert views["static"] == ["static_float", "static_int", "static_bool", "static_str"]
    assert "bus_location" in views["pypsa-eur"]


def test_delete_unregisters(api: httpx.Client, register: Register, revisions: Revisions) -> None:
    register("gone", revisions.base).raise_for_status()

    assert api.delete("/registrations/gone").status_code == 204
    assert api.get("/registrations/gone").status_code == 404
    assert api.delete("/registrations/gone").status_code == 404
    assert api.get("/registrations").json() == []


@pytest.mark.parametrize(
    ("name", "overrides"),
    [
        ("r", {"store": "../other-project"}),
        ("r", {"store": "europe/layers"}),
        ("r", {"store": ".."}),
        ("r", {"kind": "diff"}),
        ("r", {"packs": ["unknown"]}),
        ("r", {"revision": "not-a-uuid"}),
        ("Upper", {}),
        ("a.b", {}),
        ("_fold", {}),
        ("main", {}),
    ],
)
def test_put_refuses_bad_input(
    register: Register, revisions: Revisions, name: str, overrides: dict[str, Any]
) -> None:
    response = register(name, revisions.base, **overrides)

    assert response.status_code == 422


@pytest.mark.parametrize("store", [STORE, "absent"])
def test_put_of_an_unknown_revision_is_not_found(
    api: httpx.Client, register: Register, store: str
) -> None:
    response = register("r", str(uuid4()), store=store)

    assert response.status_code == 404
    assert api.get("/registrations").json() == []
