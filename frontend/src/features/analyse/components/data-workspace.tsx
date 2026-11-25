import { useEffect, useState, type ReactNode } from "react";
import { LinesSkeleton, PageSkeleton, TableSkeleton } from "../../../components/widget-states";
import { Link, useLocation, useParams } from "wouter";
import {
  LuCheck,
  LuCircleCheck,
  LuCopy,
  LuInfo,
  LuRotateCcw,
  LuSquareFunction,
  LuTable2,
  LuTriangleAlert,
} from "react-icons/lu";
import { computedPageId, computedReading, computedUses, dataPageOf } from "../lib/data-pages";
import {
  resolveResultSelection,
  useResultSelection,
  writeResultSelectionToUrl,
} from "../lib/inspect-result-selection";
import { projectAnalyseHref } from "../../project/lib/project-route";
import { describeResultSql, loadAttributeTypes, runResultSql } from "../lib/record-result-source";
import {
  VALUE_KINDS,
  checkOutput,
  type BuiltInQuery,
  type OutputColumn,
} from "../lib/result-queries";
import type { InspectResult } from "../lib/result-source";
import {
  ResultCatalogueContext,
  useLoadResultCatalogue,
  useResultCatalogue,
  useResultRead,
} from "../lib/use-result-data";
import { useProjectStore } from "../../project/store/project-store";

// A Data panel page on Analyse: a computed table (what it computes, its SQL,
// its assumptions, its columns, a preview for the shown result and what
// reads it) or a raw table of the result (its columns, row counts, a preview
// and the computed tables built on it). Everything is read-only.

const PREVIEW_ROWS = 100;

function Message({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return (
    <div className="bg-surface-900 flex h-full flex-col items-center justify-center gap-1 px-6 text-center">
      <div className="text-surface-100 text-[13px] font-medium">{title}</div>
      <div className="text-surface-400 max-w-md text-[12px]">{detail}</div>
      {action}
    </div>
  );
}

export function DataWorkspace({ pageId }: { pageId: string }) {
  const catalogueState = useLoadResultCatalogue();
  const page = dataPageOf(pageId);
  const [location] = useLocation();
  const selection = useResultSelection();
  useEffect(() => {
    writeResultSelectionToUrl();
    return () => writeResultSelectionToUrl(true);
  }, [location, selection]);
  if (!page) return <Message title="No such table" detail="Pick one in the Data panel." />;
  if (catalogueState.status === "loading")
    return <PageSkeleton cards={1} label="Loading the table" />;
  if (catalogueState.status === "error") {
    return (
      <Message
        title="Couldn't load the results"
        detail={catalogueState.error}
        action={
          <button
            type="button"
            onClick={catalogueState.retry}
            className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 mt-2 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none"
          >
            <LuRotateCcw size={12} />
            Try again
          </button>
        }
      />
    );
  }
  if (catalogueState.catalogue.results.length === 0)
    return (
      <Message
        title="No results in this record"
        detail="This project's record holds no solved results yet, so there's no data to show."
      />
    );
  return (
    <ResultCatalogueContext.Provider value={catalogueState.catalogue}>
      {page.kind === "computed" ? (
        <ComputedPage key={pageId} query={page.query} />
      ) : (
        <RawPage key={pageId} attribute={page.attribute} />
      )}
    </ResultCatalogueContext.Provider>
  );
}

// ------------------------------------------------------------ Shared parts

function Section({
  title,
  detail,
  action,
  children,
}: {
  title: string;
  detail?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border-surface-600 bg-surface-800 rounded border">
      <div className="border-surface-600 flex min-h-9 items-center gap-2 border-b px-3 py-1.5">
        <h2 className="text-surface-200 text-[11px] font-semibold tracking-wide uppercase">
          {title}
        </h2>
        {detail && (
          <div className="text-surface-400 min-w-0 flex-1 truncate text-[11px]">{detail}</div>
        )}
        {action && <div className="ml-auto flex items-center gap-1">{action}</div>}
      </div>
      <div className="p-3">{children}</div>
    </section>
  );
}

function Header({
  icon: Icon,
  title,
  badge,
  name,
  description,
}: {
  icon: typeof LuTable2;
  title: string;
  badge: string;
  name: string;
  description?: string;
}) {
  return (
    <header className="flex items-start gap-3">
      <Icon size={18} className="text-accent-400 mt-0.5 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1 className="text-surface-50 truncate text-[15px] font-semibold">{title}</h1>
          <span className="border-surface-600 text-surface-400 rounded border px-1.5 py-px text-[10px] font-medium tracking-wide uppercase">
            {badge}
          </span>
          <code className="text-surface-400 truncate font-mono text-[12px]">{name}</code>
        </div>
        {description && (
          <p className="text-surface-300 mt-1 text-[12px] leading-5">{description}</p>
        )}
      </div>
    </header>
  );
}

function useShownResult(): InspectResult {
  const catalogue = useResultCatalogue();
  return resolveResultSelection(catalogue, useResultSelection()).selectedRun;
}

type Load<T> =
  | { status: "loading" }
  | { status: "error"; error: string }
  | { status: "done"; data: T; seconds: number };

/** `read` for the shown result, through the record cache (SWR): read once per result and `key`, with how long it took. */
function useShownRead<T>(read: (result: InspectResult) => Promise<T>, key: string): Load<T> {
  const result = useShownResult();
  const { data, error } = useResultRead("data-page", [result.catalog, key], async () => {
    const started = performance.now();
    const value = await read(result);
    return { value, seconds: (performance.now() - started) / 1000 };
  });
  if (data) return { status: "done", data: data.value, seconds: data.seconds };
  if (error !== undefined)
    return { status: "error", error: error instanceof Error ? error.message : String(error) };
  return { status: "loading" };
}

interface TableData {
  output: OutputColumn[];
  rows: Record<string, unknown>[];
}

const readTable =
  (sql: string) =>
  async (result: InspectResult): Promise<TableData> => {
    const [output, rows] = await Promise.all([
      describeResultSql(result, sql),
      runResultSql<Record<string, unknown>>(
        result,
        `SELECT * FROM (\n${sql}\n) LIMIT ${PREVIEW_ROWS}`,
      ),
    ]);
    return { output, rows };
  };

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number")
    return Math.abs(value) >= 1000 || Number.isInteger(value)
      ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : value.toLocaleString(undefined, { maximumSignificantDigits: 4 });
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("period" in record && "timestep" in record)
      return `${String(record.period)} · ${new Date(Number(record.timestep)).toISOString().slice(0, 16).replace("T", " ")}`;
    if ("entity" in record && "bus" in record)
      return `${String(record.entity)} @ ${String(record.bus)}`;
    return JSON.stringify(value);
  }
  return String(value);
}

function Preview({ load }: { load: Load<TableData> }) {
  if (load.status === "loading") return <TableSkeleton label="Running on the server" />;
  if (load.status === "error")
    return (
      <div className="border-danger-500/40 bg-danger-500/10 text-danger-500 flex gap-1.5 rounded border p-2 font-mono text-[12px] leading-5 whitespace-pre-wrap">
        <LuTriangleAlert size={13} className="mt-1 shrink-0" />
        {load.error}
      </div>
    );
  if (load.data.rows.length === 0)
    return <div className="text-surface-400 text-[12px]">No rows for this result.</div>;
  const columns = load.data.output.map((column) => column.name);
  return (
    <div className="border-surface-700 max-h-96 overflow-auto rounded border">
      <table className="w-full text-[12px] tabular-nums">
        <thead className="bg-surface-800 sticky top-0">
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                className="border-surface-600 text-surface-300 border-b px-2 py-1 text-left font-mono font-medium"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {load.data.rows.map((row, index) => (
            <tr key={index} className="border-surface-700/60 border-b last:border-0">
              {columns.map((column) => (
                <td
                  key={column}
                  className={`px-2 py-0.5 whitespace-nowrap ${typeof row[column] === "number" ? "text-surface-100 text-right" : "text-surface-200"}`}
                >
                  {formatCell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Columns({
  load,
  notes,
}: {
  load: Load<TableData>;
  notes?: (output: OutputColumn[]) => ReactNode;
}) {
  if (load.status === "loading") return <LinesSkeleton lines={5} label="Reading the columns" />;
  if (load.status !== "done")
    return <div className="text-surface-400 text-[12px]">Unavailable.</div>;
  return (
    <div className="flex flex-col gap-2">
      <table className="w-full text-[12px]">
        <tbody>
          {load.data.output.map((column) => (
            <tr key={column.name} className="border-surface-700 border-b last:border-0">
              <td className="text-surface-100 py-1 pr-2 font-mono">{column.name}</td>
              <td
                title={column.type}
                className="text-surface-400 py-1 text-right font-mono text-[11px]"
              >
                {column.type.length > 28 ? `${column.type.slice(0, 28)}…` : column.type}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {notes?.(load.data.output)}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() =>
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        })
      }
      className="border-surface-600 bg-surface-800 text-surface-200 hover:bg-surface-700 hover:text-surface-50 focus-visible:border-accent-500 flex h-7 items-center gap-1.5 rounded border px-2 text-[12px] font-medium outline-none"
    >
      {copied ? <LuCheck size={12} className="text-ok-500" /> : <LuCopy size={12} />}
      {copied ? "Copied" : "Copy SQL"}
    </button>
  );
}

function LinkList({ items }: { items: { href: string; label: string; detail?: string }[] }) {
  return (
    <ul className="flex flex-col gap-1">
      {items.map((item) => (
        <li key={item.href}>
          <Link
            href={item.href}
            className="text-surface-200 hover:bg-surface-700 hover:text-surface-50 flex items-center justify-between gap-2 rounded px-1.5 py-1 text-[12px] outline-none"
          >
            <span className="truncate">{item.label}</span>
            {item.detail && (
              <span className="text-surface-400 shrink-0 text-[11px]">{item.detail}</span>
            )}
          </Link>
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------ Computed

function ComputedPage({ query }: { query: BuiltInQuery }) {
  const { projectId } = useParams<{ projectId: string }>();
  const result = useShownResult();
  const load = useShownRead(readTable(query.sql), `computed:${query.name}`);
  const views = useProjectStore((s) => s.inspections);
  const reports = useProjectStore((s) => s.reports);
  const uses = computedUses(query.name, views, reports);
  const kind = VALUE_KINDS.find((item) => item.id === query.kind);
  return (
    <div className="bg-surface-900 h-full overflow-y-auto">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 p-4">
        <Header
          icon={LuSquareFunction}
          title={query.label}
          badge="Computed"
          name={query.name}
          description={query.description}
        />
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex min-w-0 flex-col gap-3">
            <Section
              title="SQL"
              detail="Computed by Manta from the result's raw tables, each time a widget asks."
              action={<CopyButton text={query.sql} />}
            >
              <pre className="border-surface-600 bg-surface-900 text-surface-200 max-h-[32rem] overflow-auto rounded border p-2 font-mono text-[12px] leading-5 whitespace-pre select-text">
                {query.sql}
              </pre>
              <p className="text-surface-500 mt-1.5 text-[11px] leading-4">
                Plain record names (<code className="font-mono">attributes.p</code>,{" "}
                <code className="font-mono">dims.snapshot</code>) read the result shown in the
                toolbar.
              </p>
            </Section>
            <Section
              title="Preview"
              detail={
                load.status === "done"
                  ? `First ${load.data.rows.length} rows for ${result.label} · ${load.seconds.toFixed(1)} s`
                  : `For ${result.label}`
              }
            >
              <Preview load={load} />
            </Section>
          </div>
          <div className="flex min-w-0 flex-col gap-3">
            <Section title="How it's computed">
              <dl className="grid grid-cols-[6rem_1fr] gap-x-2 gap-y-1 text-[12px]">
                <dt className="text-surface-400">Value</dt>
                <dd className="text-surface-100">
                  {query.valueLabel} [{query.unit}]
                </dd>
                <dt className="text-surface-400">Adds up as</dt>
                <dd className="text-surface-100" title={kind?.detail}>
                  {kind?.label}
                </dd>
              </dl>
              <div className="text-surface-400 mt-3 text-[11px] font-semibold tracking-wide uppercase">
                Assumptions
              </div>
              <ul className="mt-1 flex flex-col gap-1.5">
                {query.assumptions.map((assumption) => (
                  <li
                    key={assumption}
                    className="text-surface-200 flex gap-1.5 text-[12px] leading-5"
                  >
                    <LuInfo size={12} className="text-surface-500 mt-1 shrink-0" />
                    {assumption}
                  </li>
                ))}
              </ul>
            </Section>
            <Section title="Columns">
              <Columns
                load={load}
                notes={(output) =>
                  checkOutput(output, query.kind).notes.map((note) => (
                    <div key={note} className="text-surface-300 flex gap-1.5 text-[12px] leading-5">
                      <LuCircleCheck size={12} className="text-ok-500 mt-1 shrink-0" />
                      {note}
                    </div>
                  ))
                }
              />
            </Section>
            <Section
              title="Used by"
              detail={
                uses.length === 0
                  ? "No widget reads it yet"
                  : `${uses.reduce((sum, use) => sum + use.widgets, 0)} widget(s)`
              }
            >
              {uses.length === 0 ? (
                <div className="text-surface-400 text-[12px] leading-5">
                  Add a custom widget to a view and pick this table.
                </div>
              ) : (
                <LinkList
                  items={uses.map((use) => ({
                    href: projectAnalyseHref(projectId, use.id),
                    label: use.name,
                    detail: `${use.widgets} in ${use.kind}`,
                  }))}
                />
              )}
            </Section>
          </div>
        </div>
      </div>
    </div>
  );
}

// ------------------------------------------------------------ Raw

interface RawCounts {
  rows: number;
  series: number;
}

function RawPage({ attribute }: { attribute: string }) {
  const { projectId } = useParams<{ projectId: string }>();
  const result = useShownResult();
  const info = useProjectStore((s) => s.record?.info ?? null);
  const view = `attributes."${attribute.replaceAll('"', '""')}"`;
  const load = useShownRead(readTable(`SELECT * FROM ${view}`), `raw:${attribute}`);
  const counts = useShownRead(async (shown) => {
    const [row] = await runResultSql<{ rows: number; series: number }>(
      shown,
      `SELECT count(*) AS rows, count(*) FILTER (WHERE snapshot IS NOT NULL) AS series FROM ${view}`,
    ).catch(() =>
      runResultSql<{ rows: number; series: number }>(
        shown,
        `SELECT count(*) AS rows, 0 AS series FROM ${view}`,
      ),
    );
    return { rows: Number(row.rows), series: Number(row.series) } satisfies RawCounts;
  }, `raw-counts:${attribute}`);
  // The same read as the Data panel's grouping, so it's usually cached already.
  const typesRead = useResultRead("attribute-types", [result.catalog], () =>
    loadAttributeTypes(result),
  );
  const ctypes = typesRead.data?.get(attribute) ?? [];
  const isResult =
    info?.revisions.find((item) => item.name === result.id)?.results.includes(attribute) ?? false;
  const readers = computedReading(attribute);
  return (
    <div className="bg-surface-900 h-full overflow-y-auto">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 p-4">
        <Header
          icon={LuTable2}
          title={attribute}
          badge="Raw"
          name={`attributes.${attribute}`}
          description={`${isResult ? "Produced by the solve" : "An input the result was solved from"}, as the record stores it${ctypes.length > 0 ? `, for ${ctypes.join(", ")}` : ""}. Browse-only: widgets read computed tables.`}
        />
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="flex min-w-0 flex-col gap-3">
            <Section
              title="Preview"
              detail={
                load.status === "done"
                  ? `First ${load.data.rows.length} rows for ${result.label} · ${load.seconds.toFixed(1)} s`
                  : `For ${result.label}`
              }
              action={<CopyButton text={`SELECT * FROM attributes.${attribute}`} />}
            >
              <Preview load={load} />
            </Section>
          </div>
          <div className="flex min-w-0 flex-col gap-3">
            <Section title="Rows">
              {counts.status === "done" ? (
                <dl className="grid grid-cols-[8rem_1fr] gap-x-2 gap-y-1 text-[12px]">
                  <dt className="text-surface-400">In all</dt>
                  <dd className="text-surface-100 text-right tabular-nums">
                    {counts.data.rows.toLocaleString()}
                  </dd>
                  <dt className="text-surface-400">Per snapshot</dt>
                  <dd className="text-surface-100 text-right tabular-nums">
                    {counts.data.series.toLocaleString()}
                  </dd>
                  <dt className="text-surface-400">Constant</dt>
                  <dd className="text-surface-100 text-right tabular-nums">
                    {(counts.data.rows - counts.data.series).toLocaleString()}
                  </dd>
                </dl>
              ) : counts.status === "loading" ? (
                <LinesSkeleton lines={3} label="Counting" />
              ) : (
                <div className="text-surface-400 text-[12px]">Unavailable.</div>
              )}
            </Section>
            <Section title="Columns">
              <Columns load={load} />
            </Section>
            <Section
              title="Computed from it"
              detail={readers.length === 0 ? "No computed table reads it" : undefined}
            >
              {readers.length === 0 ? (
                <div className="text-surface-400 text-[12px] leading-5">
                  It's in the record, but no computed table uses it yet.
                </div>
              ) : (
                <LinkList
                  items={readers.map((query) => ({
                    href: projectAnalyseHref(projectId, computedPageId(query.name)),
                    label: query.label,
                    detail: query.name,
                  }))}
                />
              )}
            </Section>
          </div>
        </div>
      </div>
    </div>
  );
}
