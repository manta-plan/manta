export type InfrastructureResource =
  | {
      id: "solver-compute";
      kind: "compute";
      title: string;
      status: string;
      statusTone?: "neutral";
      detail: string;
      meta: string;
    }
  | {
      id: "data-storage";
      kind: "storage";
      title: string;
      usedPercent: number;
      detail: string;
      meta: string;
    }
  | {
      id: "runtime-region";
      kind: "region";
      title: string;
      status: string;
      statusTone: "ok";
      detail: string;
      meta: string;
    };

export const INFRASTRUCTURE_RESOURCES: InfrastructureResource[] = [
  {
    id: "solver-compute",
    kind: "compute",
    title: "Solver Compute",
    status: "Idle",
    detail: "4 vCPU · 16 GB RAM",
    meta: "0 active solves",
  },
  {
    id: "data-storage",
    kind: "storage",
    title: "Data Storage",
    usedPercent: 26,
    detail: "128 GB of 500 GB used",
    meta: "5 files in catalog",
  },
  {
    id: "runtime-region",
    kind: "region",
    title: "Region",
    status: "Operational",
    statusTone: "ok",
    detail: "eu-west-2 (London)",
    meta: "99.98% uptime (30d)",
  },
];
