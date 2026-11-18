import type { Run } from "./runs";

// The inspection flow is fully dummy for the demo: it picks from these
// results instead of the project's runs.
export const DUMMY_RESULT_RUNS: Run[] = [
  {
    id: "result-status-quo-2040",
    name: "Status Quo (SQ) - 2040",
    scenarioName: "Base Scenario",
    status: "succeeded",
    startedAt: "2 hours ago",
    duration: "4m 12s",
  },
  {
    id: "result-high-renewables-2030",
    name: "High Renewables - 2030",
    scenarioName: "High Renewables 2030",
    status: "succeeded",
    startedAt: "1 day ago",
    duration: "3m 58s",
  },
  {
    id: "result-coal-phase-out-2035",
    name: "Coal Phase-Out - 2035",
    scenarioName: "Coal Phase-Out 2035",
    status: "succeeded",
    startedAt: "2 days ago",
    duration: "4m 20s",
  },
  {
    id: "result-net-zero-2050",
    name: "Net Zero - 2050",
    scenarioName: "Net Zero 2050",
    status: "succeeded",
    startedAt: "4 days ago",
    duration: "6m 03s",
  },
  {
    id: "result-delayed-grid-2040",
    name: "Delayed Grid Expansion - 2040",
    scenarioName: "Delayed Grid Expansion",
    status: "succeeded",
    startedAt: "1 week ago",
    duration: "5m 31s",
  },
];

export function runLabel(run: Run) {
  return run.name ?? `${run.scenarioName} result`;
}
