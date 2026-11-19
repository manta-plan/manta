# SPDX-FileCopyrightText: 2026 Manta contributors
#
# SPDX-License-Identifier: MIT

"""Example networks, typed for an OGSchema record."""

import pypsa

from playbook_library.ogschema.pypsa import Technology, classify

AC_DC_MESHED_CARRIERS = {
    "gas": Technology("ThermalStandard", prime_mover_type="GT", fuel="NATURAL_GAS"),
    "wind": Technology("RenewableDispatch", prime_mover_type="WT"),
}
"""How the generators of PyPSA's AC-DC meshed example are typed, by their PyPSA carrier.

The example names neither a machine nor a fuel grade. `GT`, a gas turbine, is our reading of
its `gas` carrier from an efficiency of 0.35, and `WT`, onshore wind, of its `wind` carrier.
"""

MODEL_ENERGY_CARRIERS = {
    "wind": Technology("RenewableDispatch", prime_mover_type="WT"),
    "solar": Technology("RenewableDispatch", prime_mover_type="PVe"),
    "battery storage": Technology(
        "EnergyReservoirStorage", prime_mover_type="BA", storage_tech="LIB"
    ),
    "hydrogen storage": Technology(
        "EnergyReservoirStorage", prime_mover_type="ES", storage_tech="HGS"
    ),
    "load shedding": Technology("InterruptiblePowerLoad"),
}
"""How the components of PyPSA's model-energy example are typed, by their PyPSA carrier."""

MODEL_ENERGY_BUSES = {"electricity": "ACBus"}
"""The bus carriers of the model-energy example that are electric, with their OGSchema type."""

ZMB_CARRIERS = {
    "onwind": Technology("RenewableDispatch", prime_mover_type="WT"),
    "solar": Technology("RenewableDispatch", prime_mover_type="PVe"),
    "ror": Technology("HydroDispatch", prime_mover_type="HY"),
    "coal": Technology("ThermalStandard", prime_mover_type="ST", fuel="COAL"),
    "oil": Technology("ThermalStandard", prime_mover_type="GT", fuel="DISTILLATE_FUEL_OIL"),
    "biomass": Technology("ThermalStandard", prime_mover_type="ST", fuel="OTHER_BIOMASS_SOLIDS"),
    "hydro": Technology("HydroTurbine", prime_mover_type="HY"),
    "export": Technology("Source"),
    "load shedding": Technology("InterruptiblePowerLoad"),
}
"""How the components of the PyPSA-Earth model of Zambia are typed, by their PyPSA carrier.

The model names no machine and no fuel grade. A steam turbine for `coal` and `biomass`, and
a gas turbine on distillate fuel oil for `oil`, are our reading of those carriers. `COAL` is
the general coal category of SiennaSchemas, for a model that gives no coal rank.
"""

BEL_CARRIERS = {
    "onwind": Technology("RenewableDispatch", prime_mover_type="WT"),
    "solar": Technology("RenewableDispatch", prime_mover_type="PVe"),
    "solar-hsat": Technology("RenewableDispatch", prime_mover_type="PVe", group="hsat"),
    "offwind-ac": Technology("RenewableDispatch", prime_mover_type="WS", group="ac"),
    "offwind-dc": Technology("RenewableDispatch", prime_mover_type="WS", group="dc"),
    "offwind-float": Technology("RenewableDispatch", prime_mover_type="WS", group="float"),
    "CCGT": Technology("ThermalStandard", prime_mover_type="CC", fuel="NATURAL_GAS"),
    "OCGT": Technology("ThermalStandard", prime_mover_type="GT", fuel="NATURAL_GAS"),
    "waste": Technology("ThermalStandard", prime_mover_type="ST", fuel="MUNICIPAL_WASTE"),
    "oil": Technology("ThermalStandard", prime_mover_type="GT", fuel="DISTILLATE_FUEL_OIL"),
    "biomass": Technology("ThermalStandard", prime_mover_type="ST", fuel="OTHER_BIOMASS_SOLIDS"),
    "battery": Technology("EnergyReservoirStorage", prime_mover_type="BA", storage_tech="LIB"),
    "H2": Technology("EnergyReservoirStorage", prime_mover_type="ES", storage_tech="HGS"),
}
"""How the components of the PyPSA-Eur model of Belgium are typed, by their PyPSA carrier.

The prime movers of wind, solar, `CCGT` and `OCGT` follow from the carrier. The model names
no machine for `waste`, `oil` and `biomass`, and no fuel grade for any carrier: a steam
turbine on municipal waste, a gas turbine on distillate fuel oil and a steam turbine on
solid biomass are our reading of them. So are lithium-ion for `battery`, and the groups
that tell tracking solar from fixed and the three kinds of offshore wind apart.
"""


def ac_dc_meshed() -> pypsa.Network:
    """Return PyPSA's AC-DC meshed example, typed for `OGSchema.to_datarecord`."""
    n = pypsa.examples.ac_dc_meshed()
    classify(n, AC_DC_MESHED_CARRIERS)
    return n


def model_energy() -> pypsa.Network:
    """Return PyPSA's model-energy example, typed for `OGSchema.to_datarecord`.

    Its hydrogen bus has no type. It is written with the hydrogen store and the two links
    that charge and discharge it, as one storage technology.
    """
    n = pypsa.examples.model_energy()
    classify(n, MODEL_ENERGY_CARRIERS, MODEL_ENERGY_BUSES)
    return n
