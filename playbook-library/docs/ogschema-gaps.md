<!--
SPDX-FileCopyrightText: 2026 Manta contributors

SPDX-License-Identifier: MIT
-->

# OGSchema gaps found with four sample models

Four PyPSA models convert to an OGSchema record and back to a PyPSA network without loss
of inputs. Three of the rebuilt networks solve to the same objective as the original, and
we compared the fourth as built, without a solve. However, many PyPSA inputs have no
OGSchema field, and several required OGSchema fields have no PyPSA source. The schema also
lacks concepts that a planning model needs.

This page lists each gap, so that we can raise them with the SiennaSchemas maintainers.
It is not a full review of the schema. It covers what four models need.

## What was tested

"OGSchema" is our working name for [SiennaSchemas](https://github.com/Sienna-Platform/SiennaSchemas),
the JSON schemas of the Sienna platform. A record is a datarecord, the parquet-based format
that Manta stores a model in.

| | |
| --- | --- |
| Date | 18 November 2026 |
| Schema | SiennaSchemas 0.5.0, through the pydantic package `power-openapi-models` 0.5.0 |
| PyPSA | 1.4 |
| Converter | `playbook_library.ogschema`, branch `playbook/feat/ogschema-datarecord` |

We converted each model to a record, built a network from the record, and solved both.

| Model | Contains | Snapshots solved | Objective, original and rebuilt |
| --- | --- | --- | --- |
| `pypsa.examples.ac_dc_meshed()` | AC and DC buses, extendable generators, lines and links, a CO2 cap | all 10 | -3,474,256.04 |
| `pypsa.examples.model_energy()` | wind, solar, a battery, hydrogen storage, load shedding | all 2,920 | 8,078,135,675.45 |
| Zambia, from PyPSA-Earth | a fixed fleet, reservoir hydro, imports and exports, 64 buses | the year at 6-hourly steps | 395,806,282,830.15 |

The Zambia values agree to 15 significant figures, and the other two are identical. We did
not solve the Zambia model at hourly steps, which takes longer than five minutes.

The fourth model is the full-resolution model of Belgium from PyPSA-Eur. It has 61 AC
buses, a hydrogen bus at each, 2,770 components, and 8,760 hourly snapshots in each of the
investment periods 2030, 2040 and 2050. We did not solve it. We compared the rebuilt network
with the original as built: the row count and index of each component class, each static
column, each time series over all 26,280 snapshots, the investment periods and all
weightings. Every item is equal, except for the rows of this table.

| Difference | Cells | Largest | Cause |
| --- | --- | --- | --- |
| carrier name on every component, and in the 552 land-use limits | all | names only | the converter derives each carrier name, so 19 carriers become 23 |
| line `type`, `r`, `x` and `b` | 79 lines | 22.9 ohm in `x` | the rebuilt line has the impedance that PyPSA computes from the line type, and no type |
| load `p_set` series | 137,715 | 1e-13 MW | the record stores a peak and a share of the peak |
| one CO2 limit | 1 | 8e-9 t | the record stores the limit for one year |
| colour and display name of the carrier `AC`; the unused carriers `DC` and `nuclear` | 2 | not numeric | the converter drops them |
| row order of generators, links and stores | none | none | order only: the cohorts of one technology come back together |
| bus column `onshore_bus` | none | none | empty in the original, so the record does not keep it |

The original stores an `x` for each line and also a line type, and PyPSA replaces the stored
value with the value from the type when it prepares a solve. For some lines the two differ:
one line stores 7.74 ohm and its type gives 21.85 ohm. After
`n.calculate_dependent_values()` on the original, the two networks agree to 7e-15.

| | PyPSA record | OGSchema record |
| --- | --- | --- |
| convert a network to a record | 0.1 s | 0.9 s |
| write the record to disk | 3.6 s | 3.4 s |
| build a network from the record | 12.5 s | 10.9 s |
| size on disk | 43.5 MB | 30.1 MB |

The OGSchema record is about as fast as the PyPSA record, and it takes 31% less space on
disk. It is smaller because it stores each technology and its series once, not three
times. Each time is from one run on one laptop, so the times are rough.

## How a record stores a value with no field

SiennaSchemas reserves a document-level `ext` map for source data that no field claims.
A record follows it with a naming rule.

| Name | Contains |
| --- | --- |
| `ext__pypsa__<attribute>` | a PyPSA input with no OGSchema field |
| `ext__pypsa__<role>__<attribute>` | the same, for one part of a merged component |
| `ext__pypsa_result__<attribute>` | a PyPSA result |
| `ts__ext__pypsa__<attribute>` | a PyPSA input series with no OGSchema field |
| `cohort__ext__pypsa__<attribute>` | a PyPSA input that differs by build year, over technology and build year |
| `ext__technology_group` | a technology label finer than prime mover and fuel |
| `ext__invented_candidate` | a mark on a technology that the converter invented |

The converter writes an `ext__pypsa__` value only where it differs from the PyPSA default.
So the `ext__` names of a record are the list of its gaps.

## How PyPSA components merge into one type

Some PyPSA components have no OGSchema type of their own, but a group of them does. The
converter merges such a group into the type that has the same meaning. It keeps the PyPSA
names in `ext`, so that it can rebuild the group.

| PyPSA components | OGSchema | Roles in `ext` |
| --- | --- | --- |
| a store, the link that charges it, the link that discharges it, and their bus | one `StorageTechnology` | `bus`, `charge`, `discharge` |
| a load-shedding generator and the load on its bus | one `InterruptiblePowerLoad` | `shedding` |
| a storage unit with an inflow | a `HydroTurbine` and a `HydroReservoir` | none |

A bus can hold several such stores, one for each build year. The converter writes one
`StorageTechnology` for the bus, with the values of each build year under that year.

A record that was not made from PyPSA has no stored names. For a storage technology named
`L`, the converter then builds a store `L`, a bus `L bus`, and the links `L charger` and
`L discharger`.

## Requests for SiennaSchemas

### A named group of components

Two PyPSA carriers can have the same prime mover and fuel. In the PyPSA-Eur model of
Belgium, `solar` and `solar-hsat` are both `PVe`, and the three offshore wind carriers are
all `WS`. The model needs them apart, because each has its own land-use limit.

`prime_mover_type` follows the EIA 923 code list and describes the machine, so more codes
are the wrong fix. No component type has a field for a category or class. We suggest a
supplemental attribute for a named group with a kind:

```json
{"id": 41, "name": "solar-hsat", "kind": "technology"}
```

A component joins a group through `SupplementalAttributeAssociation`, so one component can
be in several groups. For now a record stores the label as `ext__technology_group`. The
tz-oss-interop converter meets the same problem and keeps the PyPSA carrier in a side file.

### Nested membership of buses

A model groups its buses by country, and often by state or region inside a country. The
schema offers three groupings, and none fits.

| Type | Groups per bus | Why it does not fit |
| --- | --- | --- |
| `Area` | one | means a control area, which power flow studies need for themselves |
| `LoadZone` | one | means a zone for price analysis, and requires two peak powers |
| `TradingHub` | many | means a hub where market bids settle, and has no field for its kind |

We think the schema should handle this as topology, with levels that nest, and not only
through a supplemental attribute. For now a record stores the PyPSA `country` column as the
bus property `ext__pypsa__country`.

### A bus for another energy carrier

The schema has AC and DC buses only. A hydrogen bus therefore has no type. The converter
accepts one only as the inside of a storage technology: one store, one link in and one link
out. It refuses a hydrogen demand, a pipeline between two hydrogen buses, and several
stores on one bus that do not differ in build year. The Belgian model has three hydrogen
cohorts on each hydrogen bus, one for each investment period. The converter writes one
`StorageTechnology` for each bus, so an electrolyser built in 2030 can still fill a store
built in 2040. The cost and lifetime of the charger and the discharger are in `ext`.

### Investment periods and vintages

The record holds each technology the way SiennaSchemas holds a multi-year portfolio, with
the build year as a key inside one technology. The converter collapses the three cohorts
of a PyPSA candidate into one technology, and `build` makes one PyPSA component per period
from it. We chose this over one technology per cohort, so that only PyPSA sees cohorts.
A `cohort` dimension over technology and build year lists the years in which each
technology can be built.

| Attribute over `cohort` | Rows in the Belgian record |
| --- | --- |
| `cohort__ext__pypsa__capital_cost` | 1,101 |
| `cohort__ext__pypsa__marginal_cost` | 1,101 |
| `cohort__ext__pypsa__efficiency` | 366, for 122 CCGT and OCGT technologies |
| `cohort__ext__pypsa__charge__` and `discharge__` with `capital_cost` and `marginal_cost`; `charge__efficiency` | 183 each |

The converter writes a value by build year only where the cohorts of a technology differ.
The schema fields of the technology hold the value of the first build year, so a reader
that ignores `ext` still gets a usable technology.

- **A technology has no vintages.** A CCGT built in 2030 keeps an efficiency of 0.58 in
  2040, while a CCGT built in 2040 has 0.59. One SiennaSchemas technology cannot say this,
  so the heat rate holds the 2030 value and the later ones are in `ext`. The same holds for
  the cost of each build year.
- **An investment period is not a component.** A period has a discount weight and a length
  in years. The record has a `period` dimension, and both weights are in `ext`.
- **`MinMaxByKey` does not say what its key is.** `capacity_limits` accepts it, and the
  description calls the key a stringified float. The converter reads the key as the build
  year, and writes it only where the limits differ by build year. The Belgian limits do not
  differ, so its record has none.
- **Results have no build year.** A solved PyPSA network has a capacity and a dispatch for
  each cohort of a technology. The converter refuses to write results for a network with
  cohorts, because no result type is keyed by build year.
- **`CarbonCaps` does not say how many years its limit covers.** The limit is "in the target
  year". PyPSA's limit is for all years of a period, ten in the Belgian model. The converter
  writes the PyPSA limit divided by the years of the period.
- **`MaximumCapacityRequirements` does not say what it counts.** A PyPSA land-use limit
  counts candidate capacity only, at one bus. The requirement has no region of its own, and
  its description does not say whether existing plant counts. The Belgian record attaches
  531 existing generators to candidate technologies, so a reader could count them. Each
  requirement is associated with one whole technology, so the reader must use `target_year`
  and the lifetime to find the cohorts that PyPSA counts.
- **One weather year repeats in each period.** The three periods all use the weather of
  2013, and the record has no mark of the repeat. Several weather years fit as scenarios
  (see [Scenarios](#scenarios)). What remains missing is a link from a period to its
  weather years.

### Investment data

- **Annualised capital cost has no field.** `CapitalCost` is an overnight cost in USD/MW,
  and `TechnologyFinancialData` turns it into an annuity. A PyPSA model often has only the
  annuity, and an annuity cannot be turned back into an overnight cost.
- **`TechnologyFinancialData` requires nine fields.** PyPSA has a source for one of them,
  `discount_rate`, and only where the model sets `overnight_cost`.
- **A technology has no existing capacity.** An extendable PyPSA asset has a `p_nom` that
  already exists. The schema expects a separate operations component, named through
  `ExistingDevices`.
- **`NodalHVDCTransportTechnology` has no flow limits per direction and no impedance.** A
  PyPSA link has `p_min_pu` and `p_max_pu`, and a line between DC buses has a resistance.
- **A `StorageTechnology` has one lifetime and one set of financial data.** Its charge,
  discharge and energy parts each have a capital cost, but they share the lifetime. An
  electrolyser and a cavern do not last equally long.
- **`StorageTechnology` does not say where it counts discharge capacity.** PyPSA sizes a
  link at its input. We store discharge capacity at the grid side, which is the PyPSA value
  times the efficiency.
- **Operations types have no build year, lifetime or capacity bounds.** A fixed PyPSA
  generator can have all of them. The capacity bounds go to `ext`.
- **Build year and retirement year exist only on a technology.** `RetirementPotential` has
  a build year and a planned retirement year for each existing generator, and it attaches
  to a `SupplyTechnology`. An existing fleet with no candidate of its kind has no technology.
  The converter then invents one for each kind of generator, with a capacity limit of 0 and
  the mark `ext__invented_candidate`. It builds no PyPSA component for an invented
  technology. The Zambia record has six.
- **Retirement is a calendar year, and lifetime is a duration.** The converter writes the
  build year plus the lifetime, rounded to whole years. A generator with no build year then
  gets a retirement year such as 25, which is not a calendar year. This is the case for the
  112 wind and solar generators of the Zambia model.
- **`RetirementPotential` covers generators only.** Storage units, links and lines keep
  their build year and lifetime in `ext`.

### Storage and hydro

- **Cyclic storage has no field.** PyPSA's `cyclic_state_of_charge` and `e_cyclic` require
  the final level to equal the first. Neither `StorageTechnology` nor `HydroReservoir` can
  state it.
- **`HydroReservoir` requires fields that an energy model does not have.** These are
  `outflow`, `intake_elevation` and `head_to_volume_factor`.
- **`HydroDispatch` has no efficiency.** A PyPSA run-of-river generator has one.
- **A variable cost cannot change in time on a thermal unit.** In a `FuelCurve` the fuel cost
  and the heat rate can be time series, and `vom_cost` cannot. The converter writes the whole
  marginal cost as the variable cost, so the cost series of 41 Belgian units go to
  `ts__ext__pypsa__marginal_cost`. The efficiency series of 34 units go to the heat rate.
- **Run-of-river hydro fits two types.** `HydroDispatch` is described as hydro without a
  reservoir. `RenewableDispatch` accepts the prime mover `HY` as well, because no type
  restricts its prime movers. We use `HydroDispatch`, and the tz-oss-interop converter reads
  `RenewableDispatch` with `HY` as run-of-river.

### Demand, imports and lines

- **An interruptible load has no size limit of its own.** A PyPSA load-shedding generator
  has a capacity, and it can produce more than the demand on its bus.
- **`Source` requires weekly energy limits and has no rating.** PyPSA has no weekly limit.
- **An AC interconnector modelled as a link has no type.** The converter writes it as a
  `TwoTerminalGenericHVDCLine`, which is a guess from the two AC buses.
- **Standard line types have no field.** The converter writes the resolved resistance,
  reactance and susceptance, and keeps the type name in `ext`. Length, parallel circuits
  and `s_max_pu` have no field either.

### Scenarios

A PyPSA network with scenarios is a two-stage stochastic model: capacities are shared, and
dispatch is optimised for each scenario. Each component and each time series then has a
scenario index, and `n.scenario_weightings` gives each scenario a weight. SiennaSchemas has
the time series type `Scenarios` for this. It holds `scenario_count` series in one array,
and it is a forecast type, with `initial_timestamp`, `horizon`, `interval` and `count`.

The record keeps a series that differs between scenarios as the `ts__` attribute over
`entity`, `snapshot` and `scenario`, with one row set per scenario. As a SiennaSchemas
series it is one `Scenarios` series per component and attribute: `scenario_count` is the
number of scenarios, in the order of the `scenario` dimension, with one window over all
snapshots (`horizon` the whole run, `interval` `PT0S`, `count` 1). A `Scenarios` model with
those values validates against the pydantic package. A series that is the same in every
scenario is stored once, with no scenario.

| PyPSA input | Record | Gap |
| --- | --- | --- |
| scenario names | labels of the `scenario` dimension | `Scenarios` has no names, only a count |
| scenario weights | `scenario__ext__pypsa__weighting_weight` | `Scenarios` has no probabilities or weights |
| a static value that differs between scenarios | refused, with the component and attribute named | a static field cannot vary by scenario |
| a series over all snapshots in each scenario | one window, `count` 1 | `Scenarios` is a forecast type, so a planning series is a single forecast window |

We tested two and three scenarios of the Zambia-like network, with equal and unequal
weights. The solar `p_max_pu` and the inflow of a reservoir differ between scenarios. The
rebuilt networks have the same scenarios, weights, components and series, and they solve to
the same objective as the originals. With investment periods the snapshots are not one
contiguous run, so one window over all of them is untested.

### Other concepts

- **Results have no schema.** Dispatch, optimal capacities and prices go to
  `ext__pypsa_result__` names.
- **A CO2 cap exists only for a portfolio.** `CarbonCaps` belongs to `PortfolioDocument`,
  its unit is million tonnes, and it applies to the entities associated with it. A
  `SystemDocument` has no policy type.
- **Other system-wide limits have no type.** The Zambia model limits the total volume of
  transmission expansion. The converter keeps that constraint in the record's metadata.
- **One model spans two documents.** Loads and the operations devices exist only in
  `SystemDocument`. Technologies and requirements exist only in `PortfolioDocument`. A
  capacity expansion model with a load needs both.
- **A carrier is not a component.** Its colour and display name have no field, so the
  converter drops them. It derives the PyPSA carrier name from the component type, the
  prime mover, the fuel, the storage technology and the technology label.
- **Snapshot weightings have no field.** A time series has a resolution, which covers
  uniform steps only.
- **The storage technology codes are not the EIA codes.** The schema says that `StorageTech`
  follows EIA form 923. The EIA-860 instructions list `ECC`, `FLB`, `PBB`, `LIB`, `MAB`,
  `NIB`, `NAB` and `OTH`. Only `LIB` is also in the schema, and `HGS`, `PTES` and `FLWB`
  appear in neither EIA form.
- **The fuel list has no hydrogen and no general oil.** EIA-860 has the code `H2`. A model
  with a carrier named `oil` must choose distillate or residual fuel oil. Coal has a general
  category, `COAL`, which is the schema's own addition.
- **`GeographicInfo` has no kind.** Each Belgian bus has an onshore and an offshore shape.
  The kind goes to `ext__pypsa__type`. The two country shapes are attached to nothing,
  because a country has no type.
- **A reference does not name its target.** A field such as `bus` or `arc` is an integer
  with a description. Our converter needs a hand-written table of which field points at
  which type.
- **The pydantic package has units only as text.** The schema marks units with `x-unit`,
  and the generated models keep them in the field description alone.

## PyPSA inputs stored in `ext`

Each number is the count of rows that the converter writes for that model.

| PyPSA input | Stored under `ext__pypsa__` as | AC-DC meshed | model-energy | Zambia |
| --- | --- | --- | --- | --- |
| annualised `capital_cost` | `capital_cost` | 17 | 4 | 230 |
| `capital_cost` of the charge and discharge links | `charge__capital_cost`, `discharge__capital_cost` | | 1 each | |
| `p_nom` of extendable generators and links | `p_nom` | 10 | | |
| `s_nom` of extendable lines | `s_nom` | 7 | | |
| `p_min_pu` and `p_max_pu` of extendable links | `p_min_pu`, `p_max_pu` | 4 each | | |
| `r` of lines between DC buses | `r` | 3 | | |
| `country` of buses | `country` | 9 | | 63 |
| cyclic storage flags | `cyclic_state_of_charge`, `e_cyclic` | | 1 each | 8 |
| names of the hydrogen bus and its two links | `bus__name`, `charge__name`, `discharge__name` | | 1 each | |
| name and `p_nom` of a load-shedding generator | `shedding__name`, `shedding__p_nom` | | 1 each | 64 each |
| `sign` of a load-shedding generator | `shedding__sign` | | | 64 |
| snapshot weightings | `weighting_objective`, `_stores`, `_generators` | | 2,920 each | |
| line `type` | `standard_type` | | | 107 |
| line `length`, `s_max_pu`, `i_nom`, `dc`, `underwater_fraction` | the same names | | | 107 each |
| line `num_parallel` | `num_parallel` | | | 71 |
| line `geometry` and `country` | the same names | | | 107 each |
| `p_nom_max` and `p_nom_min` of fixed generators | the same names | | | 120 and 10 |
| generator `weight` and `control` | the same names | | | 115 and 131 |
| `efficiency` of run-of-river generators | `efficiency` | | | 3 |
| bus `lat`, `lon`, `tag_area`, `tag_substation` | the same names | | | 56 each |

The Belgian model has more `ext` names than the other three, so it has its own table.

| PyPSA input of the Belgian model | Stored under `ext__pypsa__` as | Rows |
| --- | --- | --- |
| annualised `capital_cost` of the first build year | `capital_cost` | 1,058 |
| `capital_cost` of the charge and discharge links | `charge__capital_cost`, `discharge__capital_cost` | 61 each |
| `build_year` of the one line built in 2024 | `build_year` | 1 |
| name, lifetime and marginal cost of the hydrogen links | `charge__<attribute>`, `discharge__<attribute>` | 61 each |
| name and columns of the hydrogen bus | `bus__name`; `bus__location`, `bus__country` and five more | 61 each |
| cyclic storage flags | `e_cyclic_per_period`, `cyclic_state_of_charge` | 61 each |
| period weightings | `weighting_objective`, `weighting_years` | 3 each |
| marginal cost series of thermal units | `ts__ext__pypsa__marginal_cost` | 1,077,480 |
| line `b`, `s_nom`, `s_max_pu`, `length`, `num_parallel`, `i_nom`, `standard_type`, `geometry` and three more | the same names | 79 each |
| `asset_status` and `technology_group` of components | the same names | 1,058 and 1,115 |
| `geometry` and `resource_class` of generators | the same names | 538 and 691 |
| `p_nom_min` of fixed generators | `p_nom_min` | 44 |
| bus `country`, `location`, `geometry`, `busmap_all`, `busmap_5` and six more | the same names | 61 each |
| kind of a shape | `type` | 65 |

The PyPSA column `technology_group` of this model contains the PyPSA carrier name. So
`ext__pypsa__technology_group` keeps the original carrier name next to the derived one,
such as `solar-hsat` next to `SupplyTechnology - PVe - hsat`. Our own label
`ext__technology_group` is on 84 components. The record has three invented technologies,
for oil, waste and biomass plant.

## Required fields with no source

The validation runs as DuckDB queries over the record. Every missing value is one of the
nine `financial_data` fields of an investment technology. PyPSA has no source for them.

| Model | Missing values | On |
| --- | --- | --- |
| AC-DC meshed | 153 | 17 technologies |
| model-energy | 36 | 2 `SupplyTechnology` and 2 `StorageTechnology` |
| Zambia | 54 | the 6 invented technologies; nothing in the model is extendable |
| Belgium | 4,590 | 309 `SupplyTechnology`, 122 `StorageTechnology` and 79 `NodalACTransportTechnology` |

The validation does not yet report a required object whose own fields are all optional,
such as the `angle_limits` of a `Line`.

## Required fields filled with a constant

PyPSA has no value for these fields, so the converter writes a fixed one.

| Type | Constant |
| --- | --- |
| `ACBus`, `DCBus` | `number` is the position of the bus; `available` is true |
| `PowerLoad`, `InterruptiblePowerLoad` | `max_reactive_power` 0; `base_power` is the peak load |
| `ThermalStandard` | `status` ONLINE; `reactive_power` 0; `fixed` 0; `fuel_cost` 0 |
| `RenewableDispatch` | `power_factor` 1; `reactive_power` 0 |
| `HydroDispatch`, `HydroTurbine` | `reactive_power` 0; `fixed` 0 |
| `HydroReservoir` | `outflow` 0; `intake_elevation` 0; `head_to_volume_factor` linear with 0 and 1; minimum level 0 |
| `Source` | both weekly energy limits 1e6, the schema default |
| `StorageTechnology` | `fixed`, `start_up` and `shut_down` 0 |
| `SupplyTechnology`, invented | both capacity limits 0; `available` is true |
| `RetirementPotential` | `eligible_generators` is empty; `retirement_cost` is a zero curve |
| `Line` | `active_power_flow` 0; `reactive_power_flow` 0 |
| `TModelHVDCLine` | `l` 0; `c` 0; `base_current` is `s_nom / v_nom` |
| `InterconnectingConverter` | `active_power` 0 |
| `TwoTerminalGenericHVDCLine` | `active_power_flow` 0; the four reactive power limits 0 |
| `EmissionsData` | `pollutant` CO2; `basis` FUEL_INPUT; `energy_unit` GJ; `mass_unit` METRIC_TON |

Every component has `power_units` NATURAL_UNITS and a `base_power` equal to its capacity.

## Where the meaning differs

| PyPSA | OGSchema | Difference |
| --- | --- | --- |
| `marginal_cost`, one cost per MWh of electricity | fuel cost times heat rate, plus a variable cost | the converter writes the whole cost as the variable cost, with a fuel cost of 0 |
| `efficiency` of a thermal generator | heat rate in GJ/MWh | `3.6 / efficiency`, so the value is not bit-exact after a round trip |
| `p_set` series of a load, in MW | a peak and a profile relative to it | the converter stores `max_active_power` and `ts__max_active_power` |
| `p_set` of a generator, which fixes dispatch | `active_power`, an initial operating point | written, but read back from `ext` |
| load-shedding generator | cost of an `InterruptiblePowerLoad` | the value of lost load is `marginal_cost / sign`; the generator can exceed the local demand |
| `import` loads at neighbour buses | `InterruptiblePowerLoad` | the carrier is lost, so imports and demand look the same |
| `export` generators | `Source` | the cost goes on the import offer curve, because the generator injects power |
| a storage unit with `max_hours` | `StorageTechnology` with equal minimum and maximum duration | PyPSA has one `p_nom` for charge and discharge; only the discharge limits are written |
| a store with two links | `StorageTechnology` with no duration limit | the bus can contain nothing else |
| a storage unit with inflow | `HydroTurbine` and `HydroReservoir` in energy units | the level is `p_nom * max_hours`, so `max_hours` is lost where `p_nom` is 0 |
| `build_year` of a fixed generator | an entry in `RetirementPotential.build_year` | PyPSA's default of 0 means no entry |
| `lifetime` of a fixed generator | an entry in `planned_retirement_year` | rounded to whole years; 5 of 123 Zambia lifetimes change, by 0.013 years at most |
| `lifetime` of an extendable generator | `SupplyTechnology.lifetime` | rounded to whole years |
| a fixed generator can never retire early | `eligible_generators` | left empty, because a listed generator may be retired by the model |
| `co2_emissions` per carrier, in t per MWh of fuel | `EmissionsData` per component, in t/GJ | entities of one derived carrier must have the same rate |
| CO2 cap over the whole network | `CarbonCaps` over the associated entities, with a target year | the association is written and not read; the target year is empty |
| `efficiency` of a link | loss curve | `line_loss` is a fraction of capacity; a converter's loss is a function of DC current |
| direction of a link | `bus` and `dc_bus` of a converter | the converter type has no direction, so `ext__pypsa__from_dc` keeps it |
| a line with a standard type | `r`, `x` and `b` of a `Line` | the rebuilt line has no type, and custom line types are dropped |
| `b` and `g` of a line, one total each | a value at each end | halved |
| `v_ang_min` and `v_ang_max`, in degrees, unbounded by default | `angle_limits`, in radians, required | no row for an unbounded limit |
| `x` and `y` of a bus | `GeographicInfo` as a GeoJSON point | the coordinate system is in the record's metadata only |
| CO2 limit of a period, for all its years | `CarbonCaps` with a `target_year` | the limit is divided by the years of the period |
| land-use limit on the candidates of one carrier at one bus | `MaximumCapacityRequirements` with a `target_year` | associated with the whole technology; `target_year` and the lifetime say which cohorts count |
| an existing generator next to candidates of its kind | `ExistingDevices` of the one technology of its kind at its bus | PyPSA does not count it towards the land-use limit of the candidates |
| candidates of one kind built in several periods | one technology with values by build year | the schema fields hold the first build year; later efficiencies and costs are in `ext` |
| a cohort's `p_max_pu` series | one series per technology, from the cohort built first | a later cohort gets it from its build year, and PyPSA's default before |
| `efficiency` series of a thermal generator | heat rate series | the static curve stays next to the series |

## What the converter refuses

The converter raises an error for anything it cannot place. It currently refuses:

- a battery with fixed capacity
- pumped hydro and extendable hydro
- a store that is not part of a storage technology
- a bus that is neither electric nor the inside of a storage technology
- transformers, shunt impedances and processes
- a link with more than two buses, or between two DC buses
- a static value that differs between scenarios
- a shape that is a point
- a capacity limit on a store, or on no extendable asset
- a hydrogen cohort that lacks a link, or that is not extendable
- cohorts of one technology that differ in a text column, or that have a value for one
  build year and none for another
- a cohort series that does not match the series of the cohort built first
- capacity limits that differ by build year on a line or on a link outside a storage
  technology
- results of a solved network with cohorts

Spatial and time aggregation do not work on an OGSchema record yet, because that code reads
the PyPSA names of a record.

## What is not tested yet

- The European sample record has 232,871 components. It would test speed, not the schema.
- No sample has transformers, unit commitment or reserves. Scenarios are tested on a small
  network only, without investment periods.
- We did not solve the Belgian model, and we did not write results to a record with
  investment periods.
