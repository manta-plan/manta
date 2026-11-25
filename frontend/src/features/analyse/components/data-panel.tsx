import { useMemo, useState, type ReactNode } from "react";
import { SkeletonRows } from "../../../components/widget-states";
import { Link, useParams } from "wouter";
import { LuDatabase, LuSquareFunction, LuTable2 } from "react-icons/lu";
import { computedPageId, rawPageId } from "../lib/data-pages";
import { resolveResultSelection, useResultSelection } from "../lib/inspect-result-selection";
import { projectAnalyseHref } from "../../project/lib/project-route";
import { loadAttributeTypes } from "../lib/record-result-source";
import { recordResults } from "../../project/lib/record-results";
import { BUILT_IN_QUERIES } from "../lib/result-queries";
import { useResultRead } from "../lib/use-result-data";
import { useProjectStore } from "../../project/store/project-store";
import { RecordSearchBox } from "../../level/tree/record-search";

// The Analyse tab's data: the tables we compute from a result (Computed), then
// the result's own tables as the record stores them (Raw), grouped by the
// component types that have them. Raw tables are for browsing; widgets read
// computed ones.

const NO_TYPES = new Map<string, string[]>();

function GroupLabel({ children, action }: { children: string; action?: ReactNode }) {
  return (
    <div className="flex items-center gap-2 px-3 pt-2.5 pb-1">
      <span className="text-surface-500 text-[10px] font-medium tracking-wide uppercase">
        {children}
      </span>
      {action && <span className="ml-auto">{action}</span>}
    </div>
  );
}

function Row({
  pageId,
  icon: Icon,
  name,
  detail,
  indent = false,
}: {
  pageId: string;
  icon: typeof LuDatabase;
  name: string;
  detail?: string;
  indent?: boolean;
}) {
  const { projectId, detailId } = useParams<{ projectId: string; detailId?: string }>();
  const isSelected = detailId === pageId;
  return (
    <Link
      href={projectAnalyseHref(projectId, isSelected ? undefined : pageId)}
      className={`flex w-full items-center gap-2 py-1.5 pr-3 text-left text-[12px] outline-none ${indent ? "pl-6" : "pl-3"} ${isSelected ? "bg-accent-600/25" : "hover:bg-surface-700/60"}`}
    >
      <Icon
        size={13}
        className={`shrink-0 ${isSelected ? "text-accent-400" : "text-surface-400"}`}
      />
      <span
        className={`min-w-0 truncate ${detail ? "text-surface-50 max-w-[55%] shrink-0 font-medium" : "text-surface-100 font-mono text-[11px]"}`}
      >
        {name}
      </span>
      {detail && (
        <>
          <span aria-hidden className="bg-surface-600 h-3 w-px shrink-0" />
          <code className="text-surface-400 min-w-0 truncate font-mono text-[11px]">{detail}</code>
        </>
      )}
    </Link>
  );
}

const matches = (text: string, term: string) =>
  term
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => text.toLowerCase().includes(word));

/** The shown result's attributes by component type: its own results, and with `withInputs` the inputs it was solved from. */
function useRawGroups(withInputs: boolean): { groups: [string, string[]][]; loading: boolean } {
  const info = useProjectStore((s) => s.record?.info ?? null);
  const selection = useResultSelection();
  const results = useMemo(() => (info ? recordResults(info) : []), [info]);
  const result =
    results.length > 0
      ? resolveResultSelection({ results, periods: [], tables: [] }, selection).selectedRun
      : null;
  const revision = info?.revisions.find((item) => item.name === result?.id) ?? null;
  // Which component types have each attribute, through the record cache (SWR); without it, everything groups under Other.
  const typesRead = useResultRead("attribute-types", result ? [result.catalog] : null, () =>
    loadAttributeTypes(result!),
  );
  const types = typesRead.data ?? (typesRead.error !== undefined ? NO_TYPES : null);
  const groups = useMemo(() => {
    if (!revision) return [];
    const own = new Set(revision.results);
    const attributes = withInputs
      ? [...new Set([...revision.results, ...(info?.views.attributes ?? [])])]
      : [...own];
    const byType = new Map<string, string[]>();
    for (const attribute of attributes) {
      const ctypes = types?.get(attribute) ?? [];
      for (const ctype of ctypes.length > 0 ? ctypes : ["Other"])
        byType.set(ctype, [...(byType.get(ctype) ?? []), attribute]);
    }
    return [...byType.entries()]
      .map(([ctype, names]): [string, string[]] => [
        ctype,
        names.sort((a, b) => a.localeCompare(b)),
      ])
      .sort(([a], [b]) => (a === "Other" ? 1 : b === "Other" ? -1 : a.localeCompare(b)));
  }, [revision, info, withInputs, types]);
  return { groups, loading: result !== null && types === null };
}

export function DataPanel({ showSearch }: { showSearch: boolean }) {
  const [term, setTerm] = useState("");
  const [withInputs, setWithInputs] = useState(false);
  // A hidden find box finds nothing.
  const find = showSearch ? term : "";
  const computed = BUILT_IN_QUERIES.filter((query) =>
    matches(`${query.name} ${query.label} ${query.description}`, find),
  );
  const { groups, loading } = useRawGroups(withInputs);
  const raw = groups
    .map(([ctype, names]): [string, string[]] => [
      ctype,
      names.filter((name) => matches(`${name} ${ctype}`, find)),
    ])
    .filter(([, names]) => names.length > 0);

  return (
    <div className="flex h-full flex-col">
      {showSearch && (
        <RecordSearchBox term={term} onChange={setTerm} placeholder="Find a table" autoFocus />
      )}
      <div className="min-h-0 flex-1 overflow-y-auto pb-1">
        {computed.length > 0 && <GroupLabel>Computed</GroupLabel>}
        {computed.map((query) => (
          <Row
            key={query.name}
            pageId={computedPageId(query.name)}
            icon={LuSquareFunction}
            name={query.label}
            detail={query.name}
          />
        ))}
        <GroupLabel
          action={
            <button
              type="button"
              aria-pressed={withInputs}
              onClick={() => setWithInputs((on) => !on)}
              title={
                withInputs
                  ? "Show only what the solve produced"
                  : "Also show the inputs the result was solved from"
              }
              className={`text-[10px] font-medium outline-none ${withInputs ? "text-accent-400" : "text-surface-400 hover:text-surface-100"}`}
            >
              {withInputs ? "With inputs" : "Results only"}
            </button>
          }
        >
          Raw
        </GroupLabel>
        {loading && <SkeletonRows count={6} indent={24} label="Loading the result's tables" />}
        {raw.map(([ctype, names]) => (
          <div key={ctype}>
            <div className="text-surface-300 px-3 pt-1.5 pb-0.5 text-[11px] font-medium">
              {ctype}
            </div>
            {names.map((name) => (
              <Row
                key={`${ctype}/${name}`}
                pageId={rawPageId(name)}
                icon={LuTable2}
                name={name}
                indent
              />
            ))}
          </div>
        ))}
        {find && computed.length === 0 && raw.length === 0 && (
          <div className="text-surface-400 px-3 py-2 text-[12px] leading-5">
            No tables match “{find.trim()}”.
          </div>
        )}
      </div>
    </div>
  );
}
