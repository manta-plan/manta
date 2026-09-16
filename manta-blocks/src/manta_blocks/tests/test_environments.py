# SPDX-FileCopyrightText: 2026 Manta Blocks contributors
#
# SPDX-License-Identifier: MIT

import pytest

from manta_blocks.environments import EnvironmentSpec, current_env
from manta_blocks.tests.fakes import FakeOtherEnv, FakePassthrough


def test_manifest_and_image_are_mutually_exclusive():
    with pytest.raises(ValueError, match="At most one"):
        EnvironmentSpec(name="x", manifest="a.toml", image="ghcr.io/x")


def test_resolved_work_pool_defaults_to_manta_prefixed_name():
    assert EnvironmentSpec(name="pypsa").resolved_work_pool() == "manta-pypsa"


def test_resolved_work_pool_uses_an_explicit_name_when_given():
    spec = EnvironmentSpec(name="pypsa", work_pool="custom-pool")
    assert spec.resolved_work_pool() == "custom-pool"


def test_for_block_reads_the_environment_off_the_block():
    assert EnvironmentSpec.for_block(FakePassthrough) == EnvironmentSpec(name="default")
    assert EnvironmentSpec.for_block(FakeOtherEnv).name == "elsewhere"


def test_current_env_prefers_an_explicit_override(monkeypatch):
    monkeypatch.setenv("MANTA_ENV", "chosen")
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "pixi")
    assert current_env() == "chosen"


def test_current_env_falls_back_to_the_active_pixi_environment(monkeypatch):
    monkeypatch.delenv("MANTA_ENV", raising=False)
    monkeypatch.setenv("PIXI_ENVIRONMENT_NAME", "pixi")
    assert current_env() == "pixi"


def test_current_env_is_default_outside_pixi(monkeypatch):
    monkeypatch.delenv("MANTA_ENV", raising=False)
    monkeypatch.delenv("PIXI_ENVIRONMENT_NAME", raising=False)
    assert current_env() == "default"
