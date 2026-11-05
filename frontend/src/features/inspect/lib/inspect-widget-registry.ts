import type { ComponentType } from "react";
import {
  Co2PriceChart,
  EmissionsBySectorChart,
  EmissionsVsCapChart,
  FossilFuelUseChart,
} from "../components/emissions-widgets";
import {
  CoupledDemandChart,
  ElectrolysisChart,
  H2BalanceChart,
  H2PriceMap,
} from "../components/hydrogen-widgets";
import {
  CurtailmentChart,
  DispatchStackChart,
  PriceDurationChart,
  StorageSocChart,
} from "../components/power-dispatch-widgets";
import {
  CapacityExpansionChart,
  CostByCarrierChart,
  CostByComponentChart,
  LcoeVsMarketValueChart,
} from "../components/system-costs-widgets";
import {
  BusPriceMap,
  GeneratorSupplyChart,
  InstalledCapacityChart,
  WithdrawalChart,
} from "../components/system-overview-widgets";
import {
  CongestionHoursChart,
  CrossBorderFlowsChart,
  LineLoadingMap,
  PriceSpreadChart,
} from "../components/transmission-widgets";

export interface PresetWidget {
  label: string;
  component: ComponentType<{ resultName: string }>;
}

export const PRESET_WIDGETS: Record<string, PresetWidget> = {
  "installed-capacity": {
    label: "Installed capacity by component",
    component: InstalledCapacityChart,
  },
  "generator-supply": { label: "Generator supply by carrier", component: GeneratorSupplyChart },
  withdrawal: { label: "Withdrawal by carrier", component: WithdrawalChart },
  "bus-price-map": { label: "Time-averaged bus prices", component: BusPriceMap },
  "cost-by-component": {
    label: "Annualised system cost by component",
    component: CostByComponentChart,
  },
  "cost-by-carrier": { label: "System cost by carrier", component: CostByCarrierChart },
  "lcoe-vs-market-value": {
    label: "Levelised cost vs market value",
    component: LcoeVsMarketValueChart,
  },
  "capacity-expansion": { label: "Capacity expansion", component: CapacityExpansionChart },
  "dispatch-stack": { label: "Dispatch by carrier", component: DispatchStackChart },
  "storage-soc": { label: "Storage state of charge", component: StorageSocChart },
  curtailment: { label: "Curtailment by carrier", component: CurtailmentChart },
  "price-duration": { label: "Price duration curve", component: PriceDurationChart },
  "line-loading-map": { label: "Average line loading", component: LineLoadingMap },
  "congestion-hours": { label: "Congestion hours by corridor", component: CongestionHoursChart },
  "cross-border-flows": { label: "Net cross-border flows", component: CrossBorderFlowsChart },
  "price-spread": { label: "Price spread across congested corridors", component: PriceSpreadChart },
  "emissions-by-sector": { label: "CO2 emissions by sector", component: EmissionsBySectorChart },
  "emissions-vs-cap": { label: "Emissions vs CO2 limit", component: EmissionsVsCapChart },
  "co2-price": { label: "CO2 shadow price", component: Co2PriceChart },
  "fossil-fuel-use": { label: "Fossil fuel use", component: FossilFuelUseChart },
  "h2-balance": { label: "Hydrogen balance", component: H2BalanceChart },
  electrolysis: { label: "Electrolysis by country", component: ElectrolysisChart },
  "h2-price-map": { label: "Time-averaged H2 bus prices", component: H2PriceMap },
  "coupled-demand": {
    label: "Electricity demand from coupled sectors",
    component: CoupledDemandChart,
  },
};
