import { useRef, useState, type ReactNode } from "react";
import { Menu } from "@base-ui/react/menu";
import { Tooltip } from "@base-ui/react/tooltip";
import type { IconType } from "react-icons";
import {
  LuChartArea,
  LuChartColumn,
  LuChartColumnStacked,
  LuChartLine,
  LuCheck,
  LuChevronDown,
  LuHash,
  LuMap,
  LuPlay,
  LuPlus,
  LuTable2,
  LuX,
} from "react-icons/lu";
import { RESULT_TABLES, resultTable } from "../../project/data/result-tables";
import {
  AGGREGATE_LABELS,
  PLACEHOLDERS,
  PLACEHOLDER_COLUMNS,
  defaultQuery,
  isPlaceholderCondition,
  parseQuerySql,
  querySql,
  tablePlaceholders,
  type Aggregate,
  type CustomQuery,
  type Placeholder,
  type QueryCondition,
} from "../../project/lib/custom-query";
import { useInspectFilters } from "../../project/lib/inspect-filters";
import type { CustomChart, CustomWidgetState } from "../../project/lib/widget-sets";
import { FormSelect } from "../../home/components/form-select";

// The custom widget's editor: a builder for the common shapes, and a SQL
// editor for the same query. The builder writes the SQL as it goes; SQL
// the builder can read switches back to it.

const CHARTS: { id: CustomChart; label: string; icon: IconType }[] = [
  { id: "bar", label: "Bar", icon: LuChartColumn },
  { id: "stacked-bar", label: "Stacked bar", icon: LuChartColumnStacked },
  { id: "line", label: "Line", icon: LuChartLine },
  { id: "area", label: "Stacked area", icon: LuChartArea },
  { id: "table", label: "Table", icon: LuTable2 },
  { id: "number", label: "Single number", icon: LuHash },
  { id: "map", label: "Bus map", icon: LuMap },
];

const PLACEHOLDER_LABELS: Record<Placeholder, string> = {
  buses: "Bus filter",
  snapshots: "Snapshot filter",
  carriers: "Carrier filter",
};

type SortValue = "none" | "value-desc" | "value-asc" | "label-asc" | "label-desc";
const SORT_OPTIONS: { value: SortValue; label: string }[] = [
  { value: "none", label: "Table order" },
  { value: "value-desc", label: "Value, high to low" },
  { value: "value-asc", label: "Value, low to high" },
  { value: "label-asc", label: "Label, A to Z" },
  { value: "label-desc", label: "Label, Z to A" },
];

const NONE = "__none__";
const inputClassName =
  "h-8 w-full rounded border border-surface-600 bg-surface-900 px-2 text-[13px] text-surface-50 outline-none placeholder:text-surface-500 focus-visible:border-accent-500";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-surface-400 text-[10px] font-medium tracking-wide uppercase">
        {label}
      </div>
      {children}
    </div>
  );
}

function IconToggle({
  icon: Icon,
  label,
  active,
  onClick,
}: {
  icon: IconType;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            onClick={onClick}
            aria-pressed={active}
            aria-label={label}
            className={`flex h-7 flex-1 items-center justify-center rounded outline-none ${active ? "bg-accent-600 text-white" : "text-surface-300 hover:bg-surface-700 hover:text-surface-50"}`}
          />
        }
      >
        <Icon size={14} />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8}>
          <Tooltip.Popup className="border-surface-600 bg-surface-950 text-surface-100 rounded border px-2 py-1 text-[11px] shadow-lg">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

// Picks the labels a literal condition keeps.
function ValuesMenu({
  values,
  options,
  onChange,
}: {
  values: string[];
  options: string[];
  onChange: (values: string[]) => void;
}) {
  const summary =
    values.length === 0
      ? "Pick values"
      : values.length <= 2
        ? values.join(", ")
        : `${values.length} values`;
  return (
    <Menu.Root>
      <Menu.Trigger className="border-surface-600 bg-surface-900 text-surface-100 focus-visible:border-accent-500 flex h-8 min-w-0 flex-1 items-center gap-1 rounded border px-2 text-left text-[12px] outline-none">
        <span
          className={`min-w-0 flex-1 truncate ${values.length === 0 ? "text-surface-500" : ""}`}
        >
          {summary}
        </span>
        <LuChevronDown size={13} className="text-surface-400 shrink-0" />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="start">
          <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 max-h-72 min-w-48 overflow-y-auto rounded-md border py-1 text-[12px] shadow-2xl shadow-black/50 outline-none">
            {options.map((option) => (
              <Menu.CheckboxItem
                key={option}
                checked={values.includes(option)}
                onCheckedChange={(checked) =>
                  onChange(
                    checked ? [...values, option] : values.filter((value) => value !== option),
                  )
                }
                closeOnClick={false}
                className="data-[highlighted]:bg-surface-700 flex cursor-default items-center gap-2 px-3 py-1.5 outline-none"
              >
                <span className="border-surface-500 flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border">
                  <Menu.CheckboxItemIndicator>
                    <LuCheck size={11} />
                  </Menu.CheckboxItemIndicator>
                </span>
                <span className="min-w-0 flex-1 truncate">{option}</span>
              </Menu.CheckboxItem>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

function sortValue(query: CustomQuery): SortValue {
  return query.orderBy ? (`${query.orderBy.by}-${query.orderBy.direction}` as SortValue) : "none";
}

function Builder({
  state,
  onQueryChange,
  onChartChange,
}: {
  state: CustomWidgetState;
  onQueryChange: (query: CustomQuery, chart?: CustomChart) => void;
  onChartChange: (chart: CustomChart) => void;
}) {
  const { allBuses } = useInspectFilters();
  const { query } = state;
  const table = resultTable(query.table) ?? RESULT_TABLES[0];
  const [x = null, series = null] = query.groupBy;
  const update = (patch: Partial<CustomQuery>) => onQueryChange({ ...query, ...patch });
  const columnOptions = table.columns.map((column) => ({ value: column, label: column }));
  const placeholders = tablePlaceholders(table);
  const literalConditions = query.where
    .map((condition, index) => ({ condition, index }))
    .filter(({ condition }) => !isPlaceholderCondition(condition)) as {
    condition: { column: string; values: string[] };
    index: number;
  }[];
  const literalColumns = table.columns.filter((column) => column !== "snapshot");
  const labelsOf = (column: string) =>
    column === "bus"
      ? allBuses
      : [
          ...new Set(
            table.rows
              .map((row) => row.labels[column])
              .filter((label): label is string => label !== undefined),
          ),
        ];

  const setGroupBy = (nextX: string | null, nextSeries: string | null) =>
    update({
      groupBy: [nextX, nextX ? nextSeries : null].filter(
        (column): column is string => column !== null,
      ),
    });
  const setWhere = (where: QueryCondition[]) => update({ where });
  const togglePlaceholder = (placeholder: Placeholder, on: boolean) =>
    setWhere(
      on
        ? [...query.where, { column: PLACEHOLDER_COLUMNS[placeholder], placeholder }]
        : query.where.filter(
            (condition) =>
              !(isPlaceholderCondition(condition) && condition.placeholder === placeholder),
          ),
    );

  // Some charts fix the query's shape: a number has no axis, a map has buses.
  const pickChart = (chart: CustomChart) => {
    if (chart === "number")
      onQueryChange({ ...query, groupBy: [], orderBy: null, limit: null }, chart);
    else if (chart === "map") onQueryChange({ ...query, groupBy: ["bus"] }, chart);
    else if (!x)
      onQueryChange(
        {
          ...query,
          groupBy: [
            table.columns.find((column) => column !== "snapshot" && column !== "bus") ??
              table.columns[0],
          ],
        },
        chart,
      );
    else onChartChange(chart);
  };

  return (
    <div className="flex flex-col gap-3">
      <Field label="Result table">
        <FormSelect
          value={table.name}
          onValueChange={(name) => {
            // A new table starts over from its defaults, keeping the chart's shape.
            const next = defaultQuery(name);
            const hasBus = resultTable(name)?.columns.includes("bus") ?? false;
            if (state.chart === "map" && hasBus) onQueryChange({ ...next, groupBy: ["bus"] });
            else if (state.chart === "number") onQueryChange({ ...next, groupBy: [] });
            else onQueryChange(next, state.chart === "map" ? "bar" : undefined);
          }}
          options={RESULT_TABLES.map((item) => ({
            value: item.name,
            label: `${item.label} [${item.unit}]`,
          }))}
          ariaLabel="Result table"
        />
        <div className="text-surface-500 text-[11px] leading-4">{table.description}</div>
      </Field>
      <Field label="Chart">
        <div className="border-surface-600 bg-surface-900 flex items-center gap-0.5 rounded border p-0.5">
          {CHARTS.map((chart) => (
            <IconToggle
              key={chart.id}
              icon={chart.icon}
              label={chart.label}
              active={state.chart === chart.id}
              onClick={() => pickChart(chart.id)}
            />
          ))}
        </div>
      </Field>
      <Field label="Value">
        <FormSelect
          value={query.aggregate}
          onValueChange={(aggregate) => update({ aggregate: aggregate as Aggregate })}
          options={Object.entries(AGGREGATE_LABELS).map(([value, label]) => ({
            value,
            label: `${label} of ${table.valueLabel.toLowerCase()}`,
          }))}
          ariaLabel="Aggregate"
        />
      </Field>
      <div className="grid grid-cols-2 gap-2">
        <Field label="X axis">
          <FormSelect
            value={x ?? NONE}
            onValueChange={(value) =>
              setGroupBy(value === NONE ? null : value, value === series ? null : series)
            }
            options={[{ value: NONE, label: "None" }, ...columnOptions]}
            disabled={state.chart === "number" || state.chart === "map"}
            ariaLabel="X axis"
          />
        </Field>
        <Field label="Split by">
          <FormSelect
            value={series ?? NONE}
            onValueChange={(value) => setGroupBy(x, value === NONE ? null : value)}
            options={[
              { value: NONE, label: "None" },
              ...columnOptions.filter((option) => option.value !== x),
            ]}
            disabled={!x || state.chart === "map"}
            ariaLabel="Split by"
          />
        </Field>
      </div>
      {placeholders.length > 0 && (
        <Field label="Follows the page's">
          <div className="flex flex-col gap-1">
            {placeholders.map((placeholder) => (
              <label
                key={placeholder}
                className="text-surface-200 flex items-center gap-2 text-[12px]"
              >
                <input
                  type="checkbox"
                  checked={query.where.some(
                    (condition) =>
                      isPlaceholderCondition(condition) && condition.placeholder === placeholder,
                  )}
                  onChange={(event) => togglePlaceholder(placeholder, event.target.checked)}
                  className="accent-accent-500"
                />
                {PLACEHOLDER_LABELS[placeholder]}
                <code className="text-surface-500 ml-auto font-mono text-[10px]">{`{{${placeholder}}}`}</code>
              </label>
            ))}
          </div>
        </Field>
      )}
      <Field label="Only include">
        <div className="flex flex-col gap-1.5">
          {literalConditions.map(({ condition, index }) => (
            <div key={index} className="flex items-center gap-1.5">
              <div className="w-24 shrink-0">
                <FormSelect
                  value={condition.column}
                  onValueChange={(column) =>
                    setWhere(
                      query.where.map((item, itemIndex) =>
                        itemIndex === index ? { column, values: [] } : item,
                      ),
                    )
                  }
                  options={literalColumns.map((column) => ({ value: column, label: column }))}
                  ariaLabel="Condition column"
                />
              </div>
              <ValuesMenu
                values={condition.values}
                options={labelsOf(condition.column)}
                onChange={(values) =>
                  setWhere(
                    query.where.map((item, itemIndex) =>
                      itemIndex === index ? { column: condition.column, values } : item,
                    ),
                  )
                }
              />
              <button
                type="button"
                onClick={() => setWhere(query.where.filter((_, itemIndex) => itemIndex !== index))}
                aria-label="Remove condition"
                className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 shrink-0 items-center justify-center rounded outline-none"
              >
                <LuX size={13} />
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              setWhere([
                ...query.where,
                { column: literalColumns[literalColumns.length - 1], values: [] },
              ])
            }
            className="text-surface-300 hover:bg-surface-700 hover:text-surface-50 flex h-7 items-center gap-1 self-start rounded px-1.5 text-[12px] outline-none"
          >
            <LuPlus size={13} />
            Add condition
          </button>
        </div>
      </Field>
      <div className="grid grid-cols-[1fr_5rem] gap-2">
        <Field label="Sort">
          <FormSelect
            value={sortValue(query)}
            onValueChange={(value) => {
              const [by, direction] = value.split("-") as ["value" | "label", "asc" | "desc"];
              update({ orderBy: value === "none" ? null : { by, direction } });
            }}
            options={SORT_OPTIONS}
            disabled={!x}
            ariaLabel="Sort"
          />
        </Field>
        <Field label="Top">
          <input
            type="number"
            min={1}
            value={query.limit ?? ""}
            placeholder="All"
            disabled={!x}
            onChange={(event) =>
              update({
                limit:
                  event.target.value === ""
                    ? null
                    : Math.max(1, Math.round(Number(event.target.value))),
              })
            }
            className={`${inputClassName} disabled:opacity-50`}
            aria-label="Keep the first N labels"
          />
        </Field>
      </div>
    </div>
  );
}

function SqlEditor({
  state,
  onRun,
}: {
  state: CustomWidgetState;
  onRun: (sql: string, query: CustomQuery) => void;
}) {
  const [draft, setDraft] = useState(state.sql);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isChanged = draft !== state.sql;

  const run = () => {
    const parsed = parseQuerySql(draft);
    if (!parsed.ok) return setError(parsed.error);
    setError(null);
    onRun(draft, parsed.query);
  };

  const insert = (text: string) => {
    const textarea = textareaRef.current;
    if (!textarea) return setDraft((current) => current + text);
    const { selectionStart, selectionEnd } = textarea;
    setDraft((current) => current.slice(0, selectionStart) + text + current.slice(selectionEnd));
    requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(selectionStart + text.length, selectionStart + text.length);
    });
  };

  return (
    <div className="flex flex-col gap-2">
      <textarea
        ref={textareaRef}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            run();
          }
        }}
        spellCheck={false}
        rows={10}
        aria-label="SQL query"
        className="border-surface-600 bg-surface-950 text-surface-100 focus-visible:border-accent-500 w-full resize-y rounded border p-2 font-mono text-[12px] leading-5 outline-none"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={run}
          className={`flex h-7 items-center gap-1.5 rounded px-2.5 text-[12px] font-medium outline-none ${isChanged ? "bg-accent-600 hover:bg-accent-500 text-white" : "border-surface-600 text-surface-200 hover:bg-surface-700 border"}`}
        >
          <LuPlay size={12} />
          Run
        </button>
        <span className="text-surface-500 text-[11px]">⌘↵</span>
        {isChanged && <span className="text-surface-400 ml-auto text-[11px]">Not run yet</span>}
      </div>
      {error && (
        <div className="border-danger-500/50 bg-danger-500/10 text-danger-400 rounded border px-2 py-1.5 text-[11px] leading-4">
          {error}
        </div>
      )}
      <Field label="Page filters">
        <div className="flex flex-wrap gap-1">
          {PLACEHOLDERS.map((placeholder) => (
            <button
              key={placeholder}
              type="button"
              onClick={() => insert(`{{${placeholder}}}`)}
              title={`Insert: ${PLACEHOLDER_COLUMNS[placeholder]} IN {{${placeholder}}} follows the page's ${PLACEHOLDER_COLUMNS[placeholder]} filter`}
              className="border-surface-600 text-surface-300 hover:border-accent-500 hover:text-surface-50 rounded border px-1.5 py-0.5 font-mono text-[11px] outline-none"
            >
              {`{{${placeholder}}}`}
            </button>
          ))}
        </div>
        <div className="text-surface-500 text-[11px] leading-4">
          <code className="font-mono">bus IN {"{{buses}}"}</code> keeps the page's buses, or all of
          them with no bus filter.
        </div>
      </Field>
      <details className="text-surface-400 text-[11px]">
        <summary className="hover:text-surface-200 cursor-pointer text-[10px] font-medium tracking-wide uppercase outline-none">
          Tables
        </summary>
        <div className="mt-1.5 flex flex-col gap-1.5">
          {RESULT_TABLES.map((table) => (
            <div key={table.name}>
              <button
                type="button"
                onClick={() => insert(table.name)}
                className="text-surface-200 hover:text-accent-400 font-mono outline-none"
              >
                {table.name}
              </button>
              <span className="text-surface-500"> · {table.unit}</span>
              <div className="text-surface-500 font-mono text-[10px]">
                {[...table.columns, "value"].join(", ")}
              </div>
            </div>
          ))}
        </div>
      </details>
      <div className="text-surface-500 text-[11px] leading-4">
        Preview on dummy result tables. Reads one aggregate of value, grouped by up to two columns;
        full DuckDB SQL comes with the wiring.
      </div>
    </div>
  );
}

export function CustomWidgetEditor({
  state,
  onChange,
  onClose,
}: {
  state: CustomWidgetState;
  onChange: (patch: Partial<CustomWidgetState>) => void;
  onClose: () => void;
}) {
  const [modeError, setModeError] = useState<string | null>(null);
  // Every builder change rewrites the SQL, so the SQL tab opens on what's drawn.
  const changeQuery = (query: CustomQuery, chart?: CustomChart) =>
    onChange({ query, sql: querySql(query), ...(chart ? { chart } : {}) });

  const switchMode = (mode: CustomWidgetState["mode"]) => {
    if (mode === state.mode) return;
    if (mode === "sql") {
      setModeError(null);
      return onChange({ mode });
    }
    // Back to the builder only with SQL it can read; it then takes over the SQL.
    const parsed = parseQuerySql(state.sql);
    if (!parsed.ok) return setModeError(`The builder can't read this SQL: ${parsed.error}`);
    setModeError(null);
    onChange({ mode, query: parsed.query, sql: querySql(parsed.query) });
  };

  return (
    <aside className="border-surface-700 mr-3 flex w-80 shrink-0 flex-col border-r pt-2 pr-3">
      <div className="flex shrink-0 items-center gap-2 pb-2">
        <div
          role="tablist"
          aria-label="Editor"
          className="border-surface-600 bg-surface-900 flex flex-1 items-center rounded border p-0.5"
        >
          {(["builder", "sql"] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              role="tab"
              aria-selected={state.mode === mode}
              onClick={() => switchMode(mode)}
              className={`flex h-6 flex-1 items-center justify-center rounded text-[11px] font-medium outline-none ${state.mode === mode ? "bg-surface-700 text-surface-50" : "text-surface-400 hover:text-surface-100"}`}
            >
              {mode === "builder" ? "Builder" : "SQL"}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close editor"
          className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 flex h-6 w-6 items-center justify-center rounded outline-none"
        >
          <LuX size={14} />
        </button>
      </div>
      {modeError && (
        <div className="border-danger-500/50 bg-danger-500/10 text-danger-400 mb-2 rounded border px-2 py-1.5 text-[11px] leading-4">
          {modeError}
        </div>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 pb-2">
        <div className="mb-3 flex flex-col gap-2">
          <Field label="Title">
            <input
              value={state.title}
              onChange={(event) => onChange({ title: event.target.value })}
              placeholder="From the query"
              className={inputClassName}
            />
          </Field>
          <Field label="Subtitle">
            <input
              value={state.subtitle}
              onChange={(event) => onChange({ subtitle: event.target.value })}
              placeholder="From the query"
              className={inputClassName}
            />
          </Field>
        </div>
        {state.mode === "builder" ? (
          <Builder
            state={state}
            onQueryChange={changeQuery}
            onChartChange={(chart) => onChange({ chart })}
          />
        ) : (
          <>
            <Field label="Chart">
              <div className="border-surface-600 bg-surface-900 mb-3 flex items-center gap-0.5 rounded border p-0.5">
                {CHARTS.map((chart) => (
                  <IconToggle
                    key={chart.id}
                    icon={chart.icon}
                    label={chart.label}
                    active={state.chart === chart.id}
                    onClick={() => onChange({ chart: chart.id })}
                  />
                ))}
              </div>
            </Field>
            <SqlEditor state={state} onRun={(sql, query) => onChange({ sql, query })} />
          </>
        )}
      </div>
    </aside>
  );
}
