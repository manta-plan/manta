import { Button } from "@base-ui/react/button";
import { Menu } from "@base-ui/react/menu";
import {
  FiAlertCircle,
  FiCheckCircle,
  FiClock,
  FiExternalLink,
  FiFilter,
  FiMoreHorizontal,
  FiPlay,
  FiRefreshCw,
  FiSearch,
  FiTrash2,
  FiZap,
} from "react-icons/fi";

const runStats = [
  { label: "Running", value: "1", tone: "text-secondary", detail: "active simulations" },
  { label: "Completed", value: "1", tone: "text-primary", detail: "ready to inspect" },
  { label: "Failed", value: "1", tone: "text-red-600", detail: "needs review" },
  { label: "Queued", value: "1", tone: "text-text", detail: "waiting for workers" },
];

const runs = [
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
  return (
    <main className="bg-background text-text min-h-svh">
      <header className="border-border bg-surface border-b">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-6 py-5 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="text-text-secondary mb-2 flex items-center gap-2 text-sm font-medium">
              <span className="bg-accent size-2 rounded-full" aria-hidden="true" />
              MANTA Energy
            </div>
            <h1 className="text-2xl font-semibold tracking-normal">Runs</h1>
            <p className="text-text-secondary mt-1 text-sm">
              Monitor recent model executions and operational workflows.
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiRefreshCw className="size-4" aria-hidden="true" />
              Refresh
            </Button>
            <Button className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary shadow-primary/20 inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiPlay className="size-4" aria-hidden="true" />
              New run
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
              <Button className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
                <FiFilter className="size-4" aria-hidden="true" />
                Filter
              </Button>
            </div>
          </div>

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
                {runs.map((run) => {
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
        </section>

        <section className="border-border bg-surface rounded-lg border px-4 py-3">
          <div className="flex items-start gap-3">
            <div className="bg-accent/20 text-primary mt-0.5 flex size-8 items-center justify-center rounded-md">
              <FiZap className="size-4" aria-hidden="true" />
            </div>
            <div>
              <h2 className="text-sm font-semibold">Execution capacity is healthy</h2>
              <p className="text-text-secondary mt-1 text-sm">
                Workers are below threshold and queued runs are expected to start within five
                minutes.
              </p>
            </div>
          </div>
        </section>
      </section>
    </main>
  );
}

const menuItemClass =
  "flex cursor-default items-center gap-2 px-3 py-2 text-sm outline-none select-none data-highlighted:bg-surface-alt";
