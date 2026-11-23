// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { useMemo, useState, type ReactNode } from "react";
import { LuSearch } from "react-icons/lu";
import { componentKind } from "../component-page";
import { useShownData } from "../../project/lib/record-data";
import { formatValue } from "../../project/lib/record-format";
import { changeKey, getEntity } from "../../project/lib/record-server/queries";
import type { ScenarioChangeValue } from "../../project/lib/record-server/types";
import { useProjectStore } from "../../project/store/project-store";
import { SeriesChip, StatusCell } from "./cells";
import { TableBar } from "./table-bar";
import { loadEntityDims } from "./table-queries";

// One entity's attributes: Attribute, Value, Unit, Source. Its entity
// properties first (asset_status, technology_group, geometry), then its
// inputs (stored, or the default), then on Inspect what the run result made
// of it. Series read as chips that pick them into the chart drawer.

interface AttributeRow {
  key: string;
  attribute: string;
  bus: string | null;
  value: ReactNode;
  unit: string;
  source: "entity dim" | "input" | "default" | "result";
  change?: ScenarioChangeValue;
}

const SOURCE_CLASS: Record<AttributeRow["source"], string> = {
  "entity dim": "text-surface-400",
  input: "text-surface-300",
  default: "text-surface-500 italic",
  result: "text-accent-300",
};

export function AttributesTable({
  entity,
  inspect,
  results,
  hours,
  changes,
  parentLabel,
}: {
  entity: string;
  inspect: boolean;
  results: Set<string>;
  hours: number;
  changes: Map<string, ScenarioChangeValue> | null;
  parentLabel: string;
}) {
  const manifest = useProjectStore((s) => s.record?.info.manifest);
  const [search, setSearch] = useState("");
  const detail = useShownData("level-table-entity", manifest ? [entity] : null, () =>
    getEntity(entity, manifest!),
  );
  const dims = useShownData("level-table-entity-dims", [entity], () => loadEntityDims(entity));

  const rows = useMemo<AttributeRow[] | null>(() => {
    if (detail.status !== "ready" || !detail.data) return null;
    const { attributes, properties } = detail.data;
    const ctype = String(properties.ctype ?? "");
    const own = dims.status === "ready" ? dims.data : null;
    const list: AttributeRow[] = [
      {
        key: "dim:asset_status",
        attribute: "asset_status",
        bus: null,
        value: <StatusCell status={own?.status ?? null} />,
        unit: "",
        source: "entity dim",
      },
      {
        key: "dim:technology_group",
        attribute: "technology_group",
        bus: null,
        value: own?.technology_group ?? "—",
        unit: "",
        source: "entity dim",
      },
      {
        key: "dim:geometry",
        attribute: "geometry",
        bus: null,
        value: own?.geometry ? (
          <span className="block truncate font-mono text-[11px]" title={own.geometry}>
            {own.geometry}
          </span>
        ) : (
          <span className="text-surface-500">none</span>
        ),
        unit: "",
        source: "entity dim",
      },
    ];
    const resultRows: AttributeRow[] = [];
    for (const attribute of attributes) {
      const isResult = results.has(attribute.name);
      const unit = attribute.spec.unit ?? (attribute.name === "p" ? "MW" : "");
      const value =
        attribute.seriesRows > 0 ? (
          <SeriesChip
            series={{
              entity,
              ctype,
              attribute: attribute.name,
              bus: attribute.bus,
              unit: unit || null,
            }}
            hours={hours}
          />
        ) : (
          formatValue(attribute.value, { dtype: attribute.spec.dtype, unit: null })
        );
      const row: AttributeRow = {
        key: `${attribute.name}\n${attribute.bus ?? ""}`,
        attribute: attribute.name,
        bus: attribute.bus,
        value,
        unit,
        source: isResult ? "result" : attribute.isDefault ? "default" : "input",
        change:
          !isResult && changes
            ? changes.get(changeKey(attribute.name, "entity", entity, attribute.bus))
            : undefined,
      };
      if (isResult) resultRows.push(row);
      else list.push(row);
    }
    // The optimised capacity leads the results.
    const optimised = componentKind(ctype).optimised;
    resultRows.sort(
      (a, b) =>
        Number(b.attribute === optimised) - Number(a.attribute === optimised) ||
        a.attribute.localeCompare(b.attribute),
    );
    return inspect ? [...list, ...resultRows] : list;
  }, [detail, dims, entity, hours, inspect, results, changes]);

  const term = search.trim().toLowerCase();
  const shown = rows?.filter((row) => !term || row.attribute.toLowerCase().includes(term)) ?? [];
  const status =
    detail.status === "error"
      ? `Couldn't load the attributes: ${detail.error}`
      : detail.status === "loading"
        ? "Loading attributes…"
        : detail.data === null
          ? "This entity is not in the shown scenario."
          : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TableBar title="Attributes">
        <div className="border-surface-600 bg-surface-950 focus-within:border-accent-500 flex h-7 w-48 items-center gap-1.5 rounded border px-2">
          <LuSearch size={12} className="text-surface-400 shrink-0" />
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Filter attributes"
            aria-label="Filter attributes"
            className="text-surface-50 placeholder:text-surface-500 min-w-0 flex-1 bg-transparent text-[12px] outline-none"
          />
        </div>
      </TableBar>
      <div
        className={`min-h-0 flex-1 overflow-auto text-[12px] ${detail.status === "ready" && detail.refreshing ? "opacity-70" : ""}`}
      >
        {status ? (
          <div className="text-surface-400 px-3 py-6 text-center">{status}</div>
        ) : (
          <table className="min-w-full border-separate border-spacing-0">
            <thead className="bg-surface-900 text-surface-400 sticky top-0 z-10 text-left">
              <tr>
                <th scope="col" className="border-surface-700 border-b px-3 py-1.5 font-medium">
                  Attribute
                </th>
                <th
                  scope="col"
                  className="border-surface-700 border-b px-3 py-1.5 text-right font-medium"
                >
                  Value
                </th>
                <th scope="col" className="border-surface-700 border-b px-3 py-1.5 font-medium">
                  Unit
                </th>
                <th scope="col" className="border-surface-700 border-b px-3 py-1.5 font-medium">
                  Source
                </th>
              </tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.key} className="text-surface-200 hover:bg-surface-800 h-[27px]">
                  <td className="border-surface-800 text-surface-100 border-b px-3 py-0 font-mono text-[11.5px] whitespace-nowrap">
                    {row.attribute}
                    {row.bus && <span className="text-surface-500 ml-1.5">{row.bus}</span>}
                  </td>
                  <td
                    title={
                      row.change
                        ? `Changed by this scenario; ${parentLabel} has ${row.change.seriesRows > 0 ? `${row.change.seriesRows.toLocaleString()} values changed` : (row.change.before ?? "—")}`
                        : row.source === "default"
                          ? "Default: not set for this entity"
                          : undefined
                    }
                    className={`border-surface-800 max-w-[28rem] border-b px-3 py-0 text-right whitespace-nowrap tabular-nums ${row.change ? "bg-accent-600/15 text-accent-200" : row.source === "default" ? "text-surface-500 italic" : ""}`}
                  >
                    <div className="flex min-w-0 justify-end">{row.value}</div>
                  </td>
                  <td className="border-surface-800 text-surface-300 border-b px-3 py-0 whitespace-nowrap">
                    {row.unit}
                  </td>
                  <td
                    className={`border-surface-800 border-b px-3 py-0 whitespace-nowrap ${SOURCE_CLASS[row.source]}`}
                  >
                    {row.source}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!status && shown.length === 0 && (
          <div className="text-surface-400 px-3 py-6 text-center">
            Nothing matches “{search.trim()}”.
          </div>
        )}
      </div>
      <div className="border-surface-700 text-surface-400 flex h-7 shrink-0 items-center border-t px-3 text-[11px] tabular-nums">
        {rows
          ? shown.length === rows.length
            ? `${rows.length} attributes`
            : `${shown.length} of ${rows.length} attributes`
          : ""}
      </div>
    </div>
  );
}
