# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""The datarecord schema derived from the SiennaSchemas release that OGSchema follows."""

import pytest

pytest.importorskip("power_openapi_models", reason="the manifest reads the SiennaSchemas models")

from datarecord import AttributeSpec, PropertySpec

from playbook_library.ogschema.manifest import all_types, extended, manifest


@pytest.mark.parametrize(
    ("component_type", "home"),
    [
        ("ACBus", "bus"),
        ("DCBus", "bus"),
        ("Arc", "arc"),
        ("Area", "area"),
        ("LoadZone", "load_zone"),
        ("EmissionsData", "supplemental_attribute"),
        ("GeographicInfo", "supplemental_attribute"),
        ("ThermalStandard", "entity"),
        ("SupplyTechnology", "entity"),
        ("CarbonCaps", "entity"),
    ],
)
def test_each_component_type_has_a_home_dim(component_type, home):
    schema = manifest([component_type])

    assert schema.meta["types"][component_type]["home"] == home
    assert schema.properties[home]["component_type"].one_of == "component_type"


@pytest.mark.parametrize(
    ("component_type", "name", "dtype", "dims"),
    [
        ("ACBus", "bus__base_voltage", "float", {"bus"}),
        ("ThermalStandard", "rating", "float", {"entity"}),
        ("ThermalStandard", "available", "bool", {"entity"}),
        ("SupplyTechnology", "lifetime", "int", {"entity"}),
        ("SupplyTechnology", "capacity_limits__max", "float", {"entity"}),
        ("PowerLoad", "ts__max_active_power", "float", {"entity", "snapshot"}),
        ("EmissionsData", "supplemental_attribute__gwp", "float", {"supplemental_attribute"}),
        (
            "ThermalStandard",
            "ts__operation_cost__variable_operation_cost__value_curve__function_data__proportional_term",
            "float",
            {"entity", "snapshot"},
        ),
        (
            "ThermalStandard",
            "operation_cost__variable_operation_cost__value_curve__function_data__proportional_term",
            "float",
            {"entity"},
        ),
    ],
)
def test_a_number_is_an_attribute_over_its_home_dim(component_type, name, dtype, dims):
    spec = manifest([component_type]).attributes[name]

    assert spec.dtype == dtype
    assert spec.dims == dims


@pytest.mark.parametrize(
    ("component_type", "dim", "name", "one_of"),
    [
        ("ThermalStandard", "entity", "bus", "bus"),
        ("ThermalStandard", "entity", "prime_mover_type", "prime_movers"),
        ("InterconnectingConverter", "entity", "dc_bus", "bus"),
        ("Line", "entity", "arc", "arc"),
        ("Arc", "arc", "from_id", "bus"),
        ("NodalACTransportTechnology", "entity", "start_node", "bus"),
        ("SupplyTechnology", "entity", "power_systems_type", None),
        ("ThermalStandard", "entity", "operation_cost__cost_type", None),
        ("GeographicInfo", "supplemental_attribute", "geo_json", None),
    ],
)
def test_text_is_a_property_that_refers_to_a_dim_where_it_names_a_label(
    component_type, dim, name, one_of
):
    spec = manifest([component_type]).properties[dim][name]

    assert spec.one_of == one_of
    assert spec.dtype == (None if one_of else "str")


@pytest.mark.parametrize(
    ("multi", "over"),
    [
        ("region", {"entity": "entity", "bus": "bus"}),
        ("requirement_association", {"requirement": "entity", "entity": "entity"}),
        (
            "bus_supplemental_attribute",
            {"bus": "bus", "supplemental_attribute": "supplemental_attribute"},
        ),
    ],
)
def test_references_to_many_components_are_multi_dims(multi, over):
    assert manifest(["SupplyTechnology", "ACBus"]).over(multi) == over


def test_a_series_of_a_field_is_declared_for_the_types_that_have_the_field():
    slope = "variable_operation_cost__value_curve__function_data__proportional_term"

    assert f"ts__operation_cost__{slope}" not in manifest(["PowerLoad"]).attributes
    assert f"ts__operation_costs__{slope}" in manifest(["SupplyTechnology"]).attributes


def test_a_snapshot_is_a_timestep_in_a_period_where_the_manifest_has_periods():
    schema = manifest(["PowerLoad"], periods=True)

    assert schema.over("snapshot") == {"period": "period", "timestep": "timestep"}
    assert schema.dimensions["period"].dtype == "int"
    assert schema.dimensions["timestep"].dtype == "datetime"
    assert manifest(["PowerLoad"]).dimensions["snapshot"].dtype == "datetime"
    assert not {"snapshot", "period", "timestep"} & schema.partial


def test_a_field_of_a_union_variant_is_required_of_that_variant_alone():
    required = manifest(["ThermalStandard"]).meta["types"]["ThermalStandard"]["required"]

    assert {"name": "rating", "kind": "attribute", "when": {}} in required
    fixed = {"operation_cost__cost_type": "THERMAL"}
    assert {"name": "operation_cost__fixed", "kind": "attribute", "when": fixed} in required


def test_the_manifest_holds_the_selected_component_types_alone():
    subset = manifest(["PowerLoad", "ACBus"])

    assert subset.dimensions["component_type"].one_of == ("ACBus", "PowerLoad")
    assert "rating" not in subset.attributes
    assert set(subset.attributes) < set(manifest().attributes)
    assert set(manifest().meta["types"]) == set(all_types())


def test_an_unknown_component_type_raises():
    with pytest.raises(ValueError, match="no component type named \\['Windmill'\\]"):
        manifest(["ACBus", "Windmill"])


def test_a_schema_is_extended_by_names_of_a_framework():
    schema = manifest(["PowerLoad"])
    attributes = {
        "ext__pypsa__sign": AttributeSpec(dtype="float", dims={"entity"}),
        "max_active_power": AttributeSpec(dtype="float", dims={"entity", "snapshot"}),
    }
    properties = {"bus": {"ext__pypsa__country": PropertySpec(dtype="str")}}

    wider = extended(schema, attributes, properties, {"pypsa": {"name": "example"}})

    assert wider.attributes["ext__pypsa__sign"].dims == {"entity"}
    assert wider.attributes["max_active_power"].dims == {"entity", "snapshot"}
    assert wider.attributes["max_active_power"].unit == schema.attributes["max_active_power"].unit
    assert wider.properties["bus"]["ext__pypsa__country"].dtype == "str"
    assert wider.meta["pypsa"] == {"name": "example"}
    assert wider.meta["types"] == schema.meta["types"]
