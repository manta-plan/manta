import { Button } from "@base-ui/react/button";
import { Menu } from "@base-ui/react/menu";
import { Select } from "@base-ui/react/select";
import { useState } from "react";
import {
  FiAlertCircle,
  FiCheckCircle,
  FiChevronDown,
  FiCheck,
  FiClock,
  FiExternalLink,
  FiMoreHorizontal,
  FiPlay,
  FiRefreshCw,
  FiSearch,
  FiTrash2,
} from "react-icons/fi";

const statusOptions = [
  { label: "Running", value: "Running" },
  { label: "Completed", value: "Completed" },
  { label: "Failed", value: "Failed" },
  { label: "Queued", value: "Queued" },
] as const;

type RunStatus = (typeof statusOptions)[number]["value"];

const demoRuns = [
  {
    id: "RUN-2048",
    name: "North Sea demand forecast",
    flow: "Demand Forecast",
    status: "Running",
    statusClass: "bg-secondary/10 text-secondary",
    statusIconClassName: "animate-spin",
    icon: FiRefreshCw,
    started: "Today, 11:42",
    duration: "06m 18s",
    trigger: "API",
    owner: "Planning",
  },
  {
    id: "RUN-2047",
    name: "Alpine hydro dispatch",
    flow: "Dispatch Optimization",
    status: "Completed",
    statusClass: "bg-accent/20 text-primary",
    icon: FiCheckCircle,
    started: "Today, 10:00",
    duration: "24m 02s",
    trigger: "Manual",
    owner: "Operations",
  },
  {
    id: "RUN-2046",
    name: "Iberian solar scenario",
    flow: "Scenario Builder",
    status: "Failed",
    statusClass: "bg-red-50 text-red-700",
    icon: FiAlertCircle,
    started: "Today, 09:30",
    duration: "11m 47s",
    trigger: "Manual",
    owner: "Research",
  },
  {
    id: "RUN-2045",
    name: "Grid stability baseline",
    flow: "Network Simulation",
    status: "Queued",
    statusClass: "bg-surface-alt text-text-secondary",
    icon: FiClock,
    started: "Today, 09:15",
    duration: "-",
    trigger: "Retry",
    owner: "Engineering",
  },
];

export function HomePage() {
  const [runs, setRuns] = useState<typeof demoRuns>([]);
  const [isLoadingRuns, setIsLoadingRuns] = useState(false);
  const [isRefreshingRuns, setIsRefreshingRuns] = useState(false);
  const [selectedStatuses, setSelectedStatuses] = useState<RunStatus[]>([]);
  const hasRuns = runs.length > 0;
  const filteredRuns =
    selectedStatuses.length > 0
      ? runs.filter((run) => selectedStatuses.includes(run.status as RunStatus))
      : runs;
  const selectedStatusLabel =
    selectedStatuses.length > 0 ? `${selectedStatuses.length} selected` : "All statuses";

  const runStats = [
    {
      label: "Running",
      value: String(runs.filter((run) => run.status === "Running").length),
      tone: "text-secondary",
      detail: hasRuns ? "active simulations" : "no active runs",
    },
    {
      label: "Completed",
      value: String(runs.filter((run) => run.status === "Completed").length),
      tone: "text-primary",
      detail: hasRuns ? "ready to inspect" : "no results yet",
    },
    {
      label: "Failed",
      value: String(runs.filter((run) => run.status === "Failed").length),
      tone: "text-red-600",
      detail: hasRuns ? "needs review" : "clear",
    },
    {
      label: "Queued",
      value: String(runs.filter((run) => run.status === "Queued").length),
      tone: "text-text",
      detail: hasRuns ? "waiting for workers" : "empty queue",
    },
  ];

  function handleNewRun() {
    setIsLoadingRuns(true);

    window.setTimeout(() => {
      setRuns(demoRuns);
      setIsLoadingRuns(false);
    }, 1000);
  }

  function handleRefreshRuns() {
    setIsRefreshingRuns(true);

    window.setTimeout(() => {
      setRuns((currentRuns) => (currentRuns.length > 0 ? [...currentRuns] : currentRuns));
      setIsRefreshingRuns(false);
    }, 1000);
  }

  return (
    <main className="bg-background text-text min-h-svh">
      <header className="border-border bg-surface border-b">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-3 px-6 py-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-4">
            <img
              alt="MANTA Energy"
              className="size-8 shrink-0 rounded object-contain"
              src="/manta-icon.svg"
            />
            <div className="border-border min-w-0 border-l pl-4">
              <h1 className="text-xl font-semibold tracking-normal">Runs</h1>
              <p className="text-text-secondary mt-0.5 truncate text-sm">
                Monitor recent executions and operational workflows.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
              disabled={isRefreshingRuns}
              onClick={handleRefreshRuns}
            >
              <FiRefreshCw
                className={`size-4 ${isRefreshingRuns ? "animate-spin" : ""}`}
                aria-hidden="true"
              />
              {isRefreshingRuns ? "Refreshing..." : "Refresh"}
            </Button>
            <Button
              className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary shadow-primary/20 inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
              disabled={isLoadingRuns}
              onClick={handleNewRun}
            >
              {isLoadingRuns ? (
                <FiRefreshCw className="size-4 animate-spin" aria-hidden="true" />
              ) : (
                <FiPlay className="size-4" aria-hidden="true" />
              )}
              {isLoadingRuns ? "Starting..." : "New run"}
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-7xl gap-6 px-6 py-6">
        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {runStats.map((stat) => (
            <div className="border-border bg-surface rounded-lg border px-4 py-3" key={stat.label}>
              <dt className="text-text-secondary text-sm font-medium">{stat.label}</dt>
              <dd className={`mt-2 text-3xl font-semibold tracking-normal ${stat.tone}`}>
                {stat.value}
              </dd>
              <dd className="text-text-secondary mt-1 text-sm">{stat.detail}</dd>
            </div>
          ))}
        </dl>

        <section className="border-border bg-surface overflow-hidden rounded-lg border shadow-sm">
          <div className="border-border flex flex-col gap-3 border-b px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="text-base font-semibold tracking-normal">Recent runs</h2>
              <p className="text-text-secondary mt-1 text-sm">
                Latest execution activity across active MANTA workflows.
              </p>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <label className="border-border bg-surface-alt text-text-secondary flex h-10 min-w-64 items-center gap-2 rounded-md border px-3 text-sm">
                <FiSearch className="size-4" aria-hidden="true" />
                <span className="sr-only">Search runs</span>
                <input
                  className="placeholder:text-muted text-text min-w-0 flex-1 bg-transparent outline-none"
                  placeholder="Search runs"
                  type="search"
                />
              </label>
              <Select.Root<RunStatus, true>
                items={statusOptions}
                multiple
                value={selectedStatuses}
                onValueChange={setSelectedStatuses}
              >
                <Select.Trigger className="border-border bg-surface hover:bg-surface-alt data-[popup-open]:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-10 min-w-40 items-center justify-between gap-2 rounded-md border px-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
                  <span>{selectedStatusLabel}</span>
                  <Select.Icon>
                    <FiChevronDown className="size-4" aria-hidden="true" />
                  </Select.Icon>
                </Select.Trigger>
                <Select.Portal>
                  <Select.Positioner align="end" className="z-10 outline-none" sideOffset={6}>
                    <Select.Popup className="border-border bg-surface text-text shadow-primary/10 min-w-[var(--anchor-width)] rounded-md border py-1 shadow-xl transition-[opacity,scale] duration-100 ease-out outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
                      <Select.List className="max-h-72 overflow-y-auto py-1">
                        {statusOptions.map((status) => (
                          <Select.Item
                            className={selectItemClass}
                            key={status.value}
                            value={status.value}
                          >
                            <Select.ItemIndicator className="text-primary">
                              <FiCheck className="size-4" aria-hidden="true" />
                            </Select.ItemIndicator>
                            <Select.ItemText>{status.label}</Select.ItemText>
                          </Select.Item>
                        ))}
                      </Select.List>
                    </Select.Popup>
                  </Select.Positioner>
                </Select.Portal>
              </Select.Root>
            </div>
          </div>

          {hasRuns ? (
            filteredRuns.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[880px] border-collapse text-left text-sm">
                  <thead className="bg-surface-alt text-text-secondary">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Run</th>
                      <th className="px-4 py-3 font-semibold">Status</th>
                      <th className="px-4 py-3 font-semibold">Started</th>
                      <th className="px-4 py-3 font-semibold">Duration</th>
                      <th className="px-4 py-3 font-semibold">Trigger</th>
                      <th className="px-4 py-3 font-semibold">Owner</th>
                      <th className="px-4 py-3 text-right font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-border divide-y">
                    {filteredRuns.map((run) => {
                      const StatusIcon = run.icon;

                      return (
                        <tr className="hover:bg-surface-alt/70 transition" key={run.id}>
                          <td className="px-4 py-4">
                            <div className="text-text font-semibold">{run.name}</div>
                            <div className="text-text-secondary mt-1 flex items-center gap-2">
                              <span>{run.id}</span>
                              <span aria-hidden="true">/</span>
                              <span>{run.flow}</span>
                            </div>
                          </td>
                          <td className="px-4 py-4">
                            <span
                              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${run.statusClass}`}
                            >
                              <StatusIcon
                                className={`size-3.5 ${run.statusIconClassName ?? ""}`}
                                aria-hidden="true"
                              />
                              {run.status}
                            </span>
                          </td>
                          <td className="text-text-secondary px-4 py-4">{run.started}</td>
                          <td className="text-text-secondary px-4 py-4">{run.duration}</td>
                          <td className="text-text-secondary px-4 py-4">{run.trigger}</td>
                          <td className="text-text-secondary px-4 py-4">{run.owner}</td>
                          <td className="px-4 py-4 text-right">
                            <Menu.Root>
                              <Menu.Trigger
                                aria-label={`Open actions for ${run.name}`}
                                className="hover:bg-surface-alt data-[popup-open]:bg-surface-alt focus-visible:outline-secondary text-text-secondary inline-flex size-8 items-center justify-center rounded-md transition focus-visible:outline-2 focus-visible:outline-offset-2"
                              >
                                <FiMoreHorizontal className="size-4" aria-hidden="true" />
                              </Menu.Trigger>
                              <Menu.Portal>
                                <Menu.Positioner
                                  align="end"
                                  className="z-10 outline-none"
                                  sideOffset={6}
                                >
                                  <Menu.Popup className="border-border bg-surface text-text shadow-primary/10 min-w-40 rounded-md border py-1 shadow-xl transition-[opacity,scale] duration-100 ease-out outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
                                    <Menu.Item className={menuItemClass}>
                                      <FiExternalLink className="size-4" aria-hidden="true" />
                                      View result
                                    </Menu.Item>
                                    <Menu.Item className={`${menuItemClass} text-red-700`}>
                                      <FiTrash2 className="size-4" aria-hidden="true" />
                                      Remove
                                    </Menu.Item>
                                  </Menu.Popup>
                                </Menu.Positioner>
                              </Menu.Portal>
                            </Menu.Root>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="grid min-h-72 place-items-center px-6 py-12 text-center">
                <div className="max-w-sm">
                  <div className="bg-surface-alt text-primary mx-auto mb-4 flex size-12 items-center justify-center rounded-lg">
                    <FiSearch className="size-5" aria-hidden="true" />
                  </div>
                  <h3 className="text-lg font-semibold tracking-normal">No matching runs</h3>
                  <p className="text-text-secondary mt-2 text-sm leading-6">
                    Adjust the status filter to bring more executions back into view.
                  </p>
                </div>
              </div>
            )
          ) : (
            <div className="grid min-h-72 place-items-center px-6 py-12 text-center">
              <div className="max-w-sm">
                <div className="bg-surface-alt text-primary mx-auto mb-4 flex size-12 items-center justify-center rounded-lg">
                  {isLoadingRuns ? (
                    <FiRefreshCw className="size-5 animate-spin" aria-hidden="true" />
                  ) : (
                    <FiPlay className="size-5" aria-hidden="true" />
                  )}
                </div>
                <h3 className="text-lg font-semibold tracking-normal">
                  {isLoadingRuns ? "Starting demo run" : "No runs yet"}
                </h3>
                <p className="text-text-secondary mt-2 text-sm leading-6">
                  {isLoadingRuns
                    ? "Preparing sample executions for the workspace."
                    : "Create a run to populate this workspace with execution activity."}
                </p>
              </div>
            </div>
          )}
        </section>
      </section>
    </main>
  );
}

const menuItemClass =
  "flex cursor-default items-center gap-2 px-3 py-2 text-sm outline-none select-none data-highlighted:bg-surface-alt";

const selectItemClass =
  "grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 px-3 py-2 text-sm outline-none select-none data-highlighted:bg-surface-alt";
