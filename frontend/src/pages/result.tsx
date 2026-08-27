import { Button } from "@base-ui/react/button";
import {
  FiArrowLeft,
  FiBarChart2,
  FiCheckCircle,
  FiClock,
  FiCpu,
  FiDownload,
  FiFileText,
  FiRefreshCw,
  FiShare2,
  FiZap,
} from "react-icons/fi";
import { Link } from "wouter";

type ResultPageProps = {
  slug: string;
};

const resultSummary = {
  runId: "RUN-2047",
  title: "Alpine hydro dispatch",
  flow: "Dispatch Optimization",
  status: "Completed",
  started: "Today, 10:00",
  finished: "Today, 10:24",
  duration: "24m 02s",
  owner: "Operations",
  region: "Alpine Europe",
};

const metrics = [
  { label: "Objective value", value: "98.4%", detail: "dispatch target met", icon: FiBarChart2 },
  { label: "Energy balanced", value: "1.82 TWh", detail: "across modeled nodes", icon: FiZap },
  { label: "Solver time", value: "14m 38s", detail: "inside execution window", icon: FiCpu },
  { label: "Warnings", value: "2", detail: "non-blocking constraints", icon: FiFileText },
];

const outputs = [
  {
    name: "Dispatch plan",
    type: "CSV",
    size: "2.4 MB",
    description: "Hourly generation schedule by asset and market zone.",
  },
  {
    name: "Constraint report",
    type: "PDF",
    size: "840 KB",
    description: "Binding constraints and advisory warnings from the solver.",
  },
  {
    name: "Scenario manifest",
    type: "JSON",
    size: "116 KB",
    description: "Input assumptions, model version, and execution parameters.",
  },
];

const timeline = [
  { label: "Run queued", time: "10:00", detail: "Manual trigger from Operations" },
  { label: "Inputs validated", time: "10:01", detail: "42 assets and 8 market zones loaded" },
  { label: "Optimization solved", time: "10:18", detail: "Solver converged within tolerance" },
  { label: "Artifacts published", time: "10:24", detail: "3 result files are ready" },
];

export function ResultPage({ slug }: ResultPageProps) {
  return (
    <main className="bg-background text-text min-h-svh">
      <header className="border-border bg-surface border-b">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-4 px-6 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-start gap-4">
            <img
              alt="MANTA Energy"
              className="mt-1 size-8 shrink-0 rounded object-contain"
              src="/manta-icon.svg"
            />
            <div className="border-border min-w-0 border-l pl-4">
              <Link
                className="text-text-secondary hover:text-primary mb-2 inline-flex items-center gap-2 text-sm font-semibold transition"
                href="/"
              >
                <FiArrowLeft className="size-4" aria-hidden="true" />
                Runs
              </Link>
              <h1 className="text-2xl font-semibold tracking-normal">{resultSummary.title}</h1>
              <p className="text-text-secondary mt-1 text-sm">
                Result for {slug} from {resultSummary.flow}.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiShare2 className="size-4" aria-hidden="true" />
              Share
            </Button>
            <Button className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary shadow-primary/20 inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-semibold shadow-lg transition focus-visible:outline-2 focus-visible:outline-offset-2">
              <FiDownload className="size-4" aria-hidden="true" />
              Download
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto grid w-full max-w-7xl gap-6 px-6 py-6">
        <section className="border-border bg-surface rounded-lg border p-4 shadow-sm">
          <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-center">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="bg-accent/20 text-primary inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold">
                  <FiCheckCircle className="size-3.5" aria-hidden="true" />
                  {resultSummary.status}
                </span>
                <span className="text-text-secondary text-sm">{resultSummary.runId}</span>
              </div>
              <p className="text-text-secondary mt-3 max-w-3xl text-sm leading-6">
                Dispatch optimization completed successfully for {resultSummary.region}. Review the
                key metrics, generated artifacts, and execution timeline before using the output in
                downstream planning.
              </p>
            </div>

            <dl className="grid min-w-72 grid-cols-2 gap-3 text-sm">
              <div>
                <dt className="text-text-secondary">Started</dt>
                <dd className="mt-1 font-semibold">{resultSummary.started}</dd>
              </div>
              <div>
                <dt className="text-text-secondary">Duration</dt>
                <dd className="mt-1 font-semibold">{resultSummary.duration}</dd>
              </div>
              <div>
                <dt className="text-text-secondary">Owner</dt>
                <dd className="mt-1 font-semibold">{resultSummary.owner}</dd>
              </div>
              <div>
                <dt className="text-text-secondary">Finished</dt>
                <dd className="mt-1 font-semibold">{resultSummary.finished}</dd>
              </div>
            </dl>
          </div>
        </section>

        <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {metrics.map((metric) => {
            const MetricIcon = metric.icon;

            return (
              <div
                className="border-border bg-surface rounded-lg border px-4 py-3"
                key={metric.label}
              >
                <dt className="text-text-secondary flex items-center gap-2 text-sm font-medium">
                  <MetricIcon className="text-primary size-4" aria-hidden="true" />
                  {metric.label}
                </dt>
                <dd className="text-primary mt-2 text-3xl font-semibold tracking-normal">
                  {metric.value}
                </dd>
                <dd className="text-text-secondary mt-1 text-sm">{metric.detail}</dd>
              </div>
            );
          })}
        </dl>

        <div className="grid gap-6 lg:grid-cols-[1fr_24rem]">
          <section className="border-border bg-surface overflow-hidden rounded-lg border shadow-sm">
            <div className="border-border border-b px-4 py-4">
              <h2 className="text-base font-semibold tracking-normal">Result artifacts</h2>
              <p className="text-text-secondary mt-1 text-sm">
                Files generated by this execution and ready for inspection.
              </p>
            </div>

            <div className="divide-border divide-y">
              {outputs.map((output) => (
                <article
                  className="hover:bg-surface-alt/70 flex flex-col gap-3 px-4 py-4 transition sm:flex-row sm:items-center sm:justify-between"
                  key={output.name}
                >
                  <div className="flex min-w-0 gap-3">
                    <div className="bg-surface-alt text-primary flex size-10 shrink-0 items-center justify-center rounded-md">
                      <FiFileText className="size-5" aria-hidden="true" />
                    </div>
                    <div className="min-w-0">
                      <h3 className="font-semibold">{output.name}</h3>
                      <p className="text-text-secondary mt-1 text-sm">{output.description}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 sm:justify-end">
                    <span className="border-border text-text-secondary rounded-md border px-2 py-1 text-xs font-semibold">
                      {output.type}
                    </span>
                    <span className="text-text-secondary min-w-16 text-sm">{output.size}</span>
                    <Button className="hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex size-8 items-center justify-center rounded-md transition focus-visible:outline-2 focus-visible:outline-offset-2">
                      <FiDownload className="size-4" aria-hidden="true" />
                      <span className="sr-only">Download {output.name}</span>
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <aside className="border-border bg-surface rounded-lg border p-4 shadow-sm">
            <h2 className="text-base font-semibold tracking-normal">Execution timeline</h2>
            <ol className="mt-4 grid gap-4">
              {timeline.map((event, index) => (
                <li className="grid grid-cols-[1.5rem_1fr] gap-3" key={event.label}>
                  <div className="flex flex-col items-center">
                    <span className="bg-accent/20 text-primary flex size-6 items-center justify-center rounded-full">
                      <FiClock className="size-3.5" aria-hidden="true" />
                    </span>
                    {index < timeline.length - 1 ? (
                      <span className="bg-border mt-2 h-full w-px" aria-hidden="true" />
                    ) : null}
                  </div>
                  <div className="pb-1">
                    <div className="flex items-baseline justify-between gap-3">
                      <h3 className="text-sm font-semibold">{event.label}</h3>
                      <span className="text-text-secondary text-xs">{event.time}</span>
                    </div>
                    <p className="text-text-secondary mt-1 text-sm leading-5">{event.detail}</p>
                  </div>
                </li>
              ))}
            </ol>

            <div className="border-border bg-surface-alt mt-5 rounded-lg border p-3">
              <div className="flex items-start gap-3">
                <FiRefreshCw className="text-primary mt-0.5 size-4" aria-hidden="true" />
                <p className="text-text-secondary text-sm leading-5">
                  Result data is static for this first iteration. Live refresh can be wired once the
                  result API is available.
                </p>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
