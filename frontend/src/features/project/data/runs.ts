import {
  getPlaybookFlow,
  PLAYBOOK_STAGE_NODES,
  PLAYBOOK_STAGE_EDGES,
  type PlaybookStageNodeConfig,
  type PlaybookStageEdge,
} from "../../home/data/playbooks";
import type { SolveProgressStage, SolveResultGenerator } from "../lib/solver/dispatch-solver-types";

export type RunStatus = "planned" | "running" | "succeeded" | "failed";

// Populated only for a run against playbook-myopic-capacity-expansion with a
// real DuckDB-backed project open — distinguishes "genuinely solved" runs
// from every other (dummy/simulated) run, which has no realSolve at all.
export interface RunRealSolveState {
  stage: SolveProgressStage;
  detail?: string;
  objectiveCost?: number;
  totalNewCapacityMw?: number;
  expandedGenerators?: SolveResultGenerator[];
  errorMessage?: string;
}

export interface Run {
  id: string;
  name?: string;
  scenarioName: string;
  playbookId?: string;
  playbookName?: string;
  status: RunStatus;
  startedAt: string;
  duration: string | null;
  solverPreset?: string;
  horizon?: string;
  // Per-node parameter overrides for this run's planned flow, keyed by
  // playbook stage id then by that stage's tag name — set via the Planned
  // Flow node click → right drawer config form.
  nodeParams?: Record<string, Record<string, string>>;
  realSolve?: RunRealSolveState;
  // Populated for a real playbook-zoning-generation run — the zone count
  // its clustering actually used, carried into the promoted scenario's
  // zoningParams so the same clustering reproduces on every load (see
  // src/lib/clustering/zonalClustering.ts).
  zoningResult?: { zoneCount: number };
}

// Empty by design — the Run workspace should demo starting from a clean
// slate: create a run from one of the two real playbooks (Myopic Capacity
// Expansion or Zoning Generation) rather than browsing pre-seeded fake ones.
export const INITIAL_RUNS: Run[] = [];

/**
 * How a succeeded run is listed in "Run Result" pickers. Uses the run's
 * own name when it has one, so several runs of one scenario stay distinct.
 */
export function runOutputLabel(run: Run): string {
  return `${run.name ?? run.scenarioName} · ${run.startedAt}`;
}

export type LogLevel = "INFO" | "WARN" | "ERROR";

export interface LogLine {
  time: string;
  level: LogLevel;
  message: string;
}

// Dummy execution trace, varying by status so the log at least reads
// coherently with the run's outcome rather than being one fixed transcript.
export function buildLogLines(run: Run): LogLine[] {
  // Nothing has executed yet for a planned run — no setup trace either,
  // that only starts once Play actually kicks the run off.
  if (run.status === "planned") return [];

  const patchLine =
    run.scenarioName === "Base Scenario"
      ? "No scenario patch set applied (base model)"
      : `Applying scenario patch set: ${run.scenarioName}`;

  if (run.playbookId === "playbook-zoning-generation") {
    return [
      {
        time: "10:32:01",
        level: "INFO",
        message: "Loading node-area geometry and mapped assets...",
      },
      { time: "10:32:03", level: "INFO", message: "Generating contiguous zone candidates..." },
      {
        time: "10:32:08",
        level: "INFO",
        message: "Assigning nodes using within and nearest rules...",
      },
      { time: "10:32:14", level: "INFO", message: "Validating coverage and unassigned nodes..." },
      { time: "10:32:18", level: "INFO", message: "Writing zoning validation output..." },
      { time: "10:32:19", level: "INFO", message: "Zoning generation succeeded in 18s" },
    ];
  }

  const setup: LogLine[] = [
    { time: "10:32:01", level: "INFO", message: "Loading base model (UK Power System Model)..." },
    { time: "10:32:02", level: "INFO", message: patchLine },
    {
      time: "10:32:03",
      level: "INFO",
      message: "Resolving model parameters (Technology costs)...",
    },
    {
      time: "10:32:04",
      level: "INFO",
      message: "Building optimization problem (247,812 variables, 189,203 constraints)",
    },
    {
      time: "10:32:06",
      level: "INFO",
      message: "Starting solver (Solver profile: HiGHS, myopic optimization)",
    },
  ];

  if (run.status === "succeeded") {
    return [
      ...setup,
      { time: "10:32:45", level: "INFO", message: "Solve complete — objective value: 2.184e9 GBP" },
      { time: "10:32:46", level: "INFO", message: "Writing outputs (Capacity mix report)..." },
      { time: "10:32:47", level: "INFO", message: `Run succeeded in ${run.duration}` },
    ];
  }

  if (run.status === "failed") {
    return [
      ...setup,
      {
        time: "10:32:40",
        level: "WARN",
        message: "Solver iteration limit approaching (9,800 / 10,000)",
      },
      {
        time: "10:32:41",
        level: "ERROR",
        message: "Solver returned infeasible — constraint violated: min_capacity[bus=42]",
      },
      { time: "10:32:41", level: "ERROR", message: `Run failed after ${run.duration}` },
    ];
  }

  return [...setup, { time: "10:32:40", level: "INFO", message: "Solving... (elapsed 00:38)" }];
}

// The flow actually executed for a run isn't always the full planned
// pipeline — parameter control can skip stages. A base-model run (no
// scenario patch to apply) skips Scenario Scope entirely, re-linking
// Modeling Capabilities straight to Model Parameters.
export function getExecutedFlow(run: Run): {
  nodes: PlaybookStageNodeConfig[];
  edges: PlaybookStageEdge[];
} {
  if (run.playbookId === "playbook-zoning-generation") return getPlaybookFlow(run.playbookId);
  if (run.scenarioName !== "Base Scenario") {
    return { nodes: PLAYBOOK_STAGE_NODES, edges: PLAYBOOK_STAGE_EDGES };
  }

  const nodes = PLAYBOOK_STAGE_NODES.filter((n) => n.id !== "stage-scenario-scope");
  const edges: PlaybookStageEdge[] = [
    {
      id: "e-capabilities-parameters-skip",
      source: "stage-modeling-capabilities",
      target: "stage-model-parameters",
    },
    ...PLAYBOOK_STAGE_EDGES.filter(
      (e) => e.id === "e-parameters-settings" || e.id === "e-settings-outputs",
    ),
  ];
  return { nodes, edges };
}

// Where a non-succeeded run's log narrative currently sits, referenced by
// stage id rather than raw position — buildLogLines() stops mid "Starting
// solver" (the Run Settings stage) for both failed and running. Looking up
// by id (not index) means this stays correct even when a stage is skipped:
// for a base-model run, Run Settings shifts from index 3 to index 2 once
// Scenario Scope is absent, and this still finds it there.
const CURRENT_STAGE_ID: Partial<Record<RunStatus, string>> = {
  failed: "stage-run-settings",
  running: "stage-run-settings",
};

// Single source of truth for "how far did this run get" — drives both the
// snapshot panel's Blocks Finished stat and which node the executed-flow
// view marks as current, so the two stay consistent with each other.
export function getRunProgress(run: Run): { finished: number; total: number } {
  const { nodes } = getExecutedFlow(run);
  if (run.status === "succeeded") return { finished: nodes.length, total: nodes.length };
  if (run.status === "planned") return { finished: 0, total: nodes.length };

  const currentStageId = CURRENT_STAGE_ID[run.status];
  const currentIndex = currentStageId ? nodes.findIndex((n) => n.id === currentStageId) : -1;
  return { finished: currentIndex === -1 ? nodes.length : currentIndex, total: nodes.length };
}
