// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { LuBoxes, LuCircleDot, LuMapPin, LuSearch, LuX } from "react-icons/lu";
import { useProjectStore } from "../../project/store/project-store";
import { entityLabel } from "../../project/lib/record-format";
import { useShownData } from "../../project/lib/record-data";
import { useOpenRecordPage, useOpenRecordPageId } from "../../project/lib/use-record-page";
import { levelPageId, type Level } from "../level";
import { SEARCH_ENTITIES, SEARCH_LOCATIONS, searchEntities, treeCounts } from "./tree-queries";
import { SkeletonRows } from "../../../components/widget-states";

// How long typing pauses before the server is asked.
const DEBOUNCE_MS = 200;

export function RecordSearchBox({
  term,
  onChange,
  placeholder = "Find an entity, carrier or location",
  autoFocus,
}: {
  term: string;
  onChange: (term: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  return (
    <div className="border-surface-700 shrink-0 border-b px-2 py-1.5">
      <div className="border-surface-600 bg-surface-900 focus-within:border-accent-500 flex h-7 items-center gap-1.5 rounded border px-2">
        <LuSearch size={12} className="text-surface-400 shrink-0" />
        <input
          type="search"
          value={term}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => event.key === "Escape" && onChange("")}
          placeholder={placeholder}
          aria-label={placeholder}
          autoFocus={autoFocus}
          className="text-surface-50 placeholder:text-surface-500 min-w-0 flex-1 bg-transparent text-[12px] outline-none [&::-webkit-search-cancel-button]:hidden"
        />
        {term && (
          <button
            type="button"
            onClick={() => onChange("")}
            aria-label="Clear"
            className="text-surface-400 hover:text-surface-100 shrink-0 outline-none"
          >
            <LuX size={12} />
          </button>
        )}
      </div>
    </div>
  );
}

function Group({
  title,
  count,
  children,
}: {
  title: string;
  count: number | string;
  children: ReactNode;
}) {
  return (
    <section>
      <h3 className="text-surface-500 px-3 pt-2 pb-1 text-[10px] font-semibold tracking-wide uppercase">
        {title}
        <span className="ml-1 font-normal tabular-nums">{count}</span>
      </h3>
      {children}
    </section>
  );
}

/** A result: a click opens its level; the open level's row is marked. */
function ResultRow({
  level,
  name,
  detail,
  title,
  color,
  icon: Icon = LuCircleDot,
}: {
  level: Level;
  name: string;
  detail?: string;
  title: string;
  color?: string | null;
  icon?: typeof LuCircleDot;
}) {
  const openRecordPage = useOpenRecordPage();
  const openPageId = useOpenRecordPageId();
  const pageId = levelPageId(level);
  const isOpen = pageId === openPageId;
  return (
    <button
      type="button"
      onClick={() => openRecordPage(pageId)}
      title={title}
      className={`focus-visible:bg-surface-700 flex h-[24px] w-full cursor-pointer items-center gap-1.5 px-3 text-left text-[12px] outline-none ${isOpen ? "bg-accent-600/25 text-surface-50" : "text-surface-200 hover:bg-surface-700/60"}`}
    >
      {color ? (
        <span
          className="h-2.5 w-2.5 shrink-0 rounded-full border border-black/20"
          style={{ backgroundColor: color }}
        />
      ) : (
        <Icon size={13} className="text-accent-400 shrink-0" />
      )}
      <span className="min-w-0 flex-1 truncate">{name}</span>
      {detail && (
        <span className="text-surface-500 ml-auto shrink-0 truncate text-[10px] tabular-nums">
          {detail}
        </span>
      )}
    </button>
  );
}

/** Whether every word of the term is in one of the texts (case aside). */
function holdsEvery(term: string, ...texts: (string | null | undefined)[]): boolean {
  const haystack = texts.filter(Boolean).join(" ").toLowerCase();
  return term
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(word));
}

// What the search finds in the shown scenario and period, in place of the
// tree, in this order: component types, carrier groups (by id or name),
// locations, entities. A click opens the level.
export function RecordSearchResults({ term, period }: { term: string; period: string }) {
  const record = useProjectStore((s) => s.record);
  // The term once typing pauses; a term searched before shows at once.
  const [settled, setSettled] = useState(term.trim());
  useEffect(() => {
    const timer = setTimeout(() => setSettled(term.trim()), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [term]);
  // The tree's own read (same key): cached by the time a search is typed.
  const countsState = useShownData("tree-counts", [period], () => treeCounts(period));
  const counts = useMemo(
    () => (countsState.status === "ready" ? countsState.data : []),
    [countsState],
  );
  const state = useShownData("tree-search", settled ? [period, settled] : null, () =>
    searchEntities(period, settled),
  );

  // Types and groups from the tree's counts, locations from the record: no server trip.
  const { types, groups, locations } = useMemo(() => {
    const totals = new Map<string, number>();
    for (const item of counts)
      totals.set(item.ctype, (totals.get(item.ctype) ?? 0) + item.entities);
    return {
      types: settled
        ? [...totals]
            .filter(([ctype]) => holdsEvery(settled, ctype))
            .sort(([a], [b]) => a.localeCompare(b))
        : [],
      groups: settled
        ? counts.flatMap(({ ctype, carrier, entities }) =>
            carrier !== null && holdsEvery(settled, carrier, record?.carriers[carrier]?.niceName)
              ? [{ ctype, carrier, entities }]
              : [],
          )
        : [],
      locations: settled
        ? (record?.locations ?? [])
            .map((item) => item.location)
            .filter((location) => holdsEvery(settled, location))
            .sort()
        : [],
    };
  }, [counts, record, settled]);

  if (!record) return null;
  const entities = state.status === "ready" ? state.data : [];
  const nothing =
    state.status === "ready" &&
    entities.length === 0 &&
    types.length === 0 &&
    groups.length === 0 &&
    locations.length === 0;
  if (nothing)
    return (
      <div className="text-surface-400 px-3 py-2 text-[12px]">Nothing matches “{settled}”.</div>
    );

  return (
    <div className="h-full overflow-y-auto pb-1">
      {types.length > 0 && (
        <Group title="Component types" count={types.length}>
          {types.map(([ctype, total]) => (
            <ResultRow
              key={ctype}
              level={{ kind: "component", ctype }}
              name={ctype}
              detail={total.toLocaleString()}
              title={ctype}
              icon={LuBoxes}
            />
          ))}
        </Group>
      )}
      {groups.length > 0 && (
        <Group title="Carriers" count={groups.length}>
          {groups.map(({ ctype, carrier, entities: total }) => {
            const known = record.carriers[carrier];
            return (
              <ResultRow
                key={`${ctype}:${carrier}`}
                level={{ kind: "carrier", ctype, carrier }}
                name={`${known?.niceName || carrier} · ${ctype}`}
                detail={total.toLocaleString()}
                title={carrier}
                color={known?.color}
              />
            );
          })}
        </Group>
      )}
      {locations.length > 0 && (
        <Group
          title="Locations"
          count={
            locations.length > SEARCH_LOCATIONS
              ? `first ${SEARCH_LOCATIONS} of ${locations.length}`
              : locations.length
          }
        >
          {locations.slice(0, SEARCH_LOCATIONS).map((location) => (
            <ResultRow
              key={location}
              level={{ kind: "location", location }}
              name={location}
              title={location}
              icon={LuMapPin}
            />
          ))}
        </Group>
      )}
      {state.status === "error" && (
        <div className="text-danger-500 px-3 py-2 text-[12px]">{state.error}</div>
      )}
      {state.status === "loading" && <SkeletonRows count={4} label="Searching" />}
      {entities.length > 0 && (
        <Group
          title="Entities"
          count={entities.length > SEARCH_ENTITIES ? `first ${SEARCH_ENTITIES}` : entities.length}
        >
          {entities.slice(0, SEARCH_ENTITIES).map((entity) => {
            const carrier = entity.carrier ? record.carriers[entity.carrier] : undefined;
            return (
              <ResultRow
                key={entity.entity}
                level={{ kind: "entity", entity: entity.entity }}
                name={entityLabel(entity.entity, entity.location)}
                detail={[entity.ctype, carrier?.niceName || entity.carrier]
                  .filter(Boolean)
                  .join(" · ")}
                title={entity.entity}
                color={carrier?.color}
              />
            );
          })}
        </Group>
      )}
      {entities.length > SEARCH_ENTITIES && (
        <div className="text-surface-500 px-3 pt-2 text-[11px]">
          Type more to narrow the entities down.
        </div>
      )}
    </div>
  );
}
