import {
  LuZap,
  LuLayers,
  LuSlidersHorizontal,
  LuPlay,
  LuChartBar,
  LuMapPinned,
  LuShapes,
  LuWaypoints,
  LuClock3,
  LuNetwork,
  LuChartNoAxesCombined,
} from "react-icons/lu";
import type { IconType } from "react-icons";

export type PlaybookVisibility = "public" | "private";

// How a succeeded run's result can be folded back into the model:
// 'patch' — the result decomposes into field-level diffs against the base
// (e.g. updated generator capacities), so promotion applies it as a
// scenario patch set, same shape as any other scenario mutation.
// 'new-scenario' — the result can't be expressed as a clean diff (it
// restructures the model — different resolution, topology, investment
// periods, etc.), so promotion instead registers a new, independent base
// scenario. This is a property of what the playbook computes, not
// something detected per-run.
export type PlaybookPromotionStrategy = "patch" | "new-scenario";

export interface Playbook {
  id: string;
  name: string;
  description: string;
  visibility: PlaybookVisibility;
  // Whether this playbook has real computation behind it (false/absent for
  // the other playbooks here, which are still browsable but not startable —
  // see NewRunDrawer/RunOverview's runnable filter and ScenariosPanel's
  // playbook list, which shows every playbook but only lets these be
  // selected).
  runnable?: boolean;
  promotionStrategy: PlaybookPromotionStrategy;
}

export const INITIAL_PLAYBOOKS: Playbook[] = [
  {
    id: "playbook-myopic-capacity-expansion",
    name: "Myopic Capacity Expansion",
    description:
      "Single-period capacity expansion pipeline — solves one investment period at a time.",
    visibility: "public",
    runnable: true,
    promotionStrategy: "patch",
  },
  {
    id: "playbook-lt-resource-planning",
    name: "LT Resource Planning",
    description:
      "Multi-period least-cost resource planning pipeline across the full study horizon.",
    visibility: "private",
    runnable: false,
    promotionStrategy: "new-scenario",
  },
  {
    id: "playbook-zoning-generation",
    name: "Zoning Generation",
    description:
      "Generate, assign, and validate a single level of model zones from spatial inputs.",
    visibility: "private",
    runnable: true,
    promotionStrategy: "new-scenario",
  },
  {
    id: "playbook-capacity-expansion-methods",
    name: "Capacity Expansion Methods",
    description:
      "Compare overnight, perfect-foresight, and myopic capacity expansion after temporal and network reduction.",
    visibility: "public",
    runnable: false,
    promotionStrategy: "new-scenario",
  },
];

export type PlaybookStageColor = "blue" | "emerald" | "amber" | "orange" | "violet";

export const PLAYBOOK_STAGE_COLOR_CLASSES: Record<
  PlaybookStageColor,
  { border: string; headerBg: string; text: string }
> = {
  blue: { border: "border-blue-500/40", headerBg: "bg-blue-500/10", text: "text-blue-400" },
  emerald: {
    border: "border-emerald-500/40",
    headerBg: "bg-emerald-500/10",
    text: "text-emerald-400",
  },
  amber: { border: "border-amber-500/40", headerBg: "bg-amber-500/10", text: "text-amber-400" },
  orange: { border: "border-orange-500/40", headerBg: "bg-orange-500/10", text: "text-orange-400" },
  violet: { border: "border-violet-500/40", headerBg: "bg-violet-500/10", text: "text-violet-400" },
};

export interface PlaybookStageNodeData extends Record<string, unknown> {
  category: string;
  icon: IconType;
  color: PlaybookStageColor;
  title: string;
  subtitle: string;
  tags?: string[];
}

export interface PlaybookStageNodeConfig {
  id: string;
  kind?: "stage" | "gateway";
  position: { x: number; y: number };
  data: PlaybookStageNodeData;
}

export interface PlaybookStageEdge {
  id: string;
  source: string;
  target: string;
}

export interface PlaybookFlow {
  nodes: PlaybookStageNodeConfig[];
  edges: PlaybookStageEdge[];
}

// Dummy pipeline for the one playbook above — a linear sequence of stages
// from modeling capability through to output package, mirroring dummy-flow.png.
export const PLAYBOOK_STAGE_NODES: PlaybookStageNodeConfig[] = [
  {
    id: "stage-modeling-capabilities",
    position: { x: 0, y: 0 },
    data: {
      category: "Modeling Capabilities",
      icon: LuZap,
      color: "blue",
      title: "Myopic optimization",
      subtitle: "modeling capability",
      tags: ["planning_period", "investment_vintage"],
    },
  },
  {
    id: "stage-scenario-scope",
    position: { x: 340, y: 0 },
    data: {
      category: "Scenario Scope",
      icon: LuLayers,
      color: "emerald",
      title: "Scenario patch set",
      subtitle: "scenario patches",
      tags: ["scenario"],
    },
  },
  {
    id: "stage-model-parameters",
    position: { x: 680, y: 0 },
    data: {
      category: "Model Parameters",
      icon: LuSlidersHorizontal,
      color: "amber",
      title: "Technology costs",
      subtitle: "model parameter",
    },
  },
  {
    id: "stage-run-settings",
    position: { x: 1020, y: 0 },
    data: {
      category: "Run Settings",
      icon: LuPlay,
      color: "orange",
      title: "Solver profile",
      subtitle: "execution setting",
    },
  },
  {
    id: "stage-outputs",
    position: { x: 1360, y: 0 },
    data: {
      category: "Outputs",
      icon: LuChartBar,
      color: "violet",
      title: "Capacity mix report",
      subtitle: "output package",
    },
  },
];

export const PLAYBOOK_STAGE_EDGES: PlaybookStageEdge[] = [
  {
    id: "e-capabilities-scope",
    source: "stage-modeling-capabilities",
    target: "stage-scenario-scope",
  },
  { id: "e-scope-parameters", source: "stage-scenario-scope", target: "stage-model-parameters" },
  { id: "e-parameters-settings", source: "stage-model-parameters", target: "stage-run-settings" },
  { id: "e-settings-outputs", source: "stage-run-settings", target: "stage-outputs" },
];

export const ZONING_GENERATION_STAGE_NODES: PlaybookStageNodeConfig[] = [
  {
    id: "zoning-spatial-inputs",
    position: { x: 0, y: 0 },
    data: {
      category: "Spatial Inputs",
      icon: LuMapPinned,
      color: "blue",
      title: "Node areas and assets",
      subtitle: "source geometry",
      tags: ["node_areas", "assets"],
    },
  },
  {
    id: "zoning-generation-rules",
    position: { x: 340, y: 0 },
    data: {
      category: "Zoning Rules",
      icon: LuWaypoints,
      color: "emerald",
      title: "Generate zones",
      subtitle: "spatial aggregation",
      tags: ["contiguity", "target_size"],
    },
  },
  {
    id: "zoning-node-assignment",
    position: { x: 680, y: 0 },
    data: {
      category: "Spatial Assignment",
      icon: LuShapes,
      color: "amber",
      title: "Assign nodes to zones",
      subtitle: "within and nearest",
      tags: ["within", "nearest"],
    },
  },
  {
    id: "zoning-validation-output",
    position: { x: 1020, y: 0 },
    data: {
      category: "Outputs",
      icon: LuChartBar,
      color: "violet",
      title: "Zoning validation",
      subtitle: "coverage report",
      tags: ["coverage", "unassigned_nodes"],
    },
  },
];

export const ZONING_GENERATION_STAGE_EDGES: PlaybookStageEdge[] = [
  { id: "zoning-inputs-rules", source: "zoning-spatial-inputs", target: "zoning-generation-rules" },
  {
    id: "zoning-rules-assignment",
    source: "zoning-generation-rules",
    target: "zoning-node-assignment",
  },
  {
    id: "zoning-assignment-validation",
    source: "zoning-node-assignment",
    target: "zoning-validation-output",
  },
];

export const CAPACITY_EXPANSION_METHODS_STAGE_NODES: PlaybookStageNodeConfig[] = [
  {
    id: "capacity-input-model",
    position: { x: 0, y: 190 },
    data: {
      category: "Inputs",
      icon: LuLayers,
      color: "blue",
      title: "Scenario model",
      subtitle: "model and scenario inputs",
      tags: ["network", "snapshots"],
    },
  },
  {
    id: "capacity-preprocessing-and",
    kind: "gateway",
    position: { x: 320, y: 245 },
    data: {
      category: "Gateway",
      icon: LuWaypoints,
      color: "emerald",
      title: "AND",
      subtitle: "parallel preprocessing",
    },
  },
  {
    id: "capacity-time-aggregation",
    position: { x: 520, y: 0 },
    data: {
      category: "Temporal Reduction",
      icon: LuClock3,
      color: "emerald",
      title: "Time aggregation",
      subtitle: "representative snapshots",
      tags: ["snapshot_clustering"],
    },
  },
  {
    id: "capacity-network-clustering",
    position: { x: 520, y: 340 },
    data: {
      category: "Spatial Reduction",
      icon: LuNetwork,
      color: "emerald",
      title: "Network clustering",
      subtitle: "network reduction",
      tags: ["node_clustering"],
    },
  },
  {
    id: "capacity-method-or",
    kind: "gateway",
    position: { x: 900, y: 245 },
    data: {
      category: "Gateway",
      icon: LuWaypoints,
      color: "amber",
      title: "OR",
      subtitle: "select expansion method",
    },
  },
  {
    id: "capacity-overnight",
    position: { x: 1100, y: 0 },
    data: {
      category: "Capacity Expansion",
      icon: LuZap,
      color: "orange",
      title: "Overnight capacity expansion",
      subtitle: "single investment horizon",
      tags: ["OCE"],
    },
  },
  {
    id: "capacity-perfect-foresight",
    position: { x: 1100, y: 250 },
    data: {
      category: "Capacity Expansion",
      icon: LuChartNoAxesCombined,
      color: "orange",
      title: "Perfect foresight capacity expansion",
      subtitle: "full-horizon optimization",
      tags: ["PCE"],
    },
  },
  {
    id: "capacity-myopic",
    position: { x: 1100, y: 500 },
    data: {
      category: "Capacity Expansion",
      icon: LuZap,
      color: "orange",
      title: "Myopic foresight capacity expansion",
      subtitle: "iterative investment periods",
      tags: ["MCE", "N periods"],
    },
  },
];

export const CAPACITY_EXPANSION_METHODS_STAGE_EDGES: PlaybookStageEdge[] = [
  {
    id: "capacity-input-preprocessing",
    source: "capacity-input-model",
    target: "capacity-preprocessing-and",
  },
  {
    id: "capacity-preprocessing-time",
    source: "capacity-preprocessing-and",
    target: "capacity-time-aggregation",
  },
  {
    id: "capacity-preprocessing-network",
    source: "capacity-preprocessing-and",
    target: "capacity-network-clustering",
  },
  { id: "capacity-time-method", source: "capacity-time-aggregation", target: "capacity-method-or" },
  {
    id: "capacity-network-method",
    source: "capacity-network-clustering",
    target: "capacity-method-or",
  },
  { id: "capacity-method-overnight", source: "capacity-method-or", target: "capacity-overnight" },
  {
    id: "capacity-method-perfect",
    source: "capacity-method-or",
    target: "capacity-perfect-foresight",
  },
  { id: "capacity-method-myopic", source: "capacity-method-or", target: "capacity-myopic" },
];

export const PLAYBOOK_FLOWS: Record<string, PlaybookFlow> = {
  "playbook-myopic-capacity-expansion": {
    nodes: PLAYBOOK_STAGE_NODES,
    edges: PLAYBOOK_STAGE_EDGES,
  },
  "playbook-lt-resource-planning": { nodes: PLAYBOOK_STAGE_NODES, edges: PLAYBOOK_STAGE_EDGES },
  "playbook-zoning-generation": {
    nodes: ZONING_GENERATION_STAGE_NODES,
    edges: ZONING_GENERATION_STAGE_EDGES,
  },
  "playbook-capacity-expansion-methods": {
    nodes: CAPACITY_EXPANSION_METHODS_STAGE_NODES,
    edges: CAPACITY_EXPANSION_METHODS_STAGE_EDGES,
  },
};

export function getPlaybookFlow(playbookId: string | undefined): PlaybookFlow {
  return PLAYBOOK_FLOWS[playbookId ?? ""] ?? PLAYBOOK_FLOWS["playbook-myopic-capacity-expansion"];
}

// Block palette shown on the playbook detail page. These are the current
// model-engineering building blocks, grouped by their workflow purpose.
export interface PlaybookBlockTemplate {
  id: string;
  title: string;
  subtitle: string;
}

export interface PlaybookBlockCategory {
  id: string;
  label: string;
  icon: IconType;
  color: PlaybookStageColor;
  blocks: PlaybookBlockTemplate[];
}

export const PLAYBOOK_BLOCK_CATEGORIES: PlaybookBlockCategory[] = [
  {
    id: "tractability",
    label: "Tractability",
    icon: LuSlidersHorizontal,
    color: "blue",
    blocks: [
      { id: "time-clustering", title: "Time clustering", subtitle: "temporal reduction" },
      { id: "network-clustering", title: "Network clustering", subtitle: "spatial reduction" },
      { id: "asset-grouping", title: "Asset grouping", subtitle: "asset reduction" },
    ],
  },
  {
    id: "scenario-building",
    label: "Scenario Building",
    icon: LuLayers,
    color: "emerald",
    blocks: [
      {
        id: "random-sampling-scenario-generation",
        title: "Random sampling scenario generation",
        subtitle: "scenario sampling",
      },
      { id: "scenario-clustering", title: "Scenario clustering", subtitle: "scenario reduction" },
    ],
  },
  {
    id: "optimisation",
    label: "Optimisation",
    icon: LuZap,
    color: "amber",
    blocks: [
      {
        id: "overnight-capacity-expansion",
        title: "Overnight capacity expansion",
        subtitle: "capacity expansion",
      },
      {
        id: "myopic-foresight-capacity-expansion",
        title: "Myopic foresight capacity expansion",
        subtitle: "capacity expansion",
      },
      {
        id: "perfect-foresight-capacity-expansion",
        title: "Perfect foresight capacity expansion",
        subtitle: "capacity expansion",
      },
      { id: "rolling-horizon-dispatch", title: "Rolling horizon dispatch", subtitle: "dispatch" },
      {
        id: "perfect-foresight-dispatch",
        title: "Perfect foresight dispatch",
        subtitle: "dispatch",
      },
      {
        id: "two-stage-stochastic-capacity-expansion",
        title: "Two-stage stochastic capacity expansion",
        subtitle: "stochastic capacity expansion",
      },
      {
        id: "multi-stage-stochastic-dispatch",
        title: "Multi-stage stochastic dispatch",
        subtitle: "stochastic dispatch",
      },
      {
        id: "maintenance-scheduling-dispatch",
        title: "Maintenance scheduling dispatch",
        subtitle: "dispatch",
      },
    ],
  },
];

// Drag-and-drop payload from the block palette onto the playbook canvas.
export const PLAYBOOK_BLOCK_DRAG_TYPE = "application/x-manta-playbook-block";

export function findPlaybookBlock(categoryId: string, blockId: string) {
  const category = PLAYBOOK_BLOCK_CATEGORIES.find((c) => c.id === categoryId);
  const block = category?.blocks.find((b) => b.id === blockId);
  return category && block ? { category, block } : undefined;
}
