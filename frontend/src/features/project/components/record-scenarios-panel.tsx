import { useState } from "react";
import { LuChevronDown, LuChevronRight, LuGitCommitVertical, LuLayers } from "react-icons/lu";
import { useProjectStore } from "../store/project-store";
import { formatRatio } from "../lib/record-format";
import type { Revision } from "../lib/record-server/types";
import { selectableScenarios } from "../lib/record-scenarios";
import { SidebarEmptyState } from "./sidebar-empty-state";

// Which scenario the map, tree and drawers currently show; sits under the
// Record header since it describes the tree below it.
export function ShownScenarioNote() {
  const record = useProjectStore((s) => s.record);
  const switchingScenario = useProjectStore((s) => s.switchingScenario);
  if (!record) return null;
  const shown = record.info.revisions.find((revision) => revision.name === record.scenario);
  const switching = record.info.revisions.find((revision) => revision.name === switchingScenario);
  if (!shown) return null;
  return (
    <div
      className="border-surface-700 text-surface-500 shrink-0 truncate border-b px-3 py-1 text-[11px]"
      title="What the map, tree and drawers show"
    >
      {switching ? (
        <>
          Loading <span className="text-surface-300">{switching.label}</span>…
        </>
      ) : (
        <>
          Showing: <span className="text-surface-300">{shown.label}</span>
        </>
      )}
    </div>
  );
}

// The record's scenarios and what each one changes, read-only. Clicking one
// shows it: the tree, drawers and map follow. Run results are left out.
export function RecordScenariosPanel() {
  const record = useProjectStore((s) => s.record);
  const tableDrawer = useProjectStore((s) => s.tableDrawer);
  const openScenarioChange = useProjectStore((s) => s.openScenarioChange);
  const showScenario = useProjectStore((s) => s.showScenario);
  const switchingScenario = useProjectStore((s) => s.switchingScenario);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  if (!record) return null;
  const revisions = record.info.revisions;
  const byName = new Map(revisions.map((revision) => [revision.name, revision]));
  // Parents first, so a scenario follows the one it starts from.
  const depth = (revision: Revision): number =>
    revision.parent ? 1 + depth(byName.get(revision.parent) ?? { ...revision, parent: null }) : 0;
  const scenarios = revisions
    .filter((revision) => revision.kind === "scenario")
    .sort((a, b) => depth(a) - depth(b));
  if (scenarios.length === 0)
    return <SidebarEmptyState icon={LuLayers} text="This record has no scenarios" />;

  const selectable = new Set(selectableScenarios(record.info).map((revision) => revision.name));
  const toggle = (name: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {scenarios.map((scenario) => {
          const changes = record.scenarioChanges.filter(
            (change) => change.scenario === scenario.name,
          );
          const parent = scenario.parent ? byName.get(scenario.parent) : undefined;
          const isOpen = changes.length > 0 && !collapsed.has(scenario.name);
          const isShown = scenario.name === record.scenario;
          const canShow = selectable.has(scenario.name);
          return (
            <div key={scenario.name}>
              <div
                onClick={() =>
                  canShow
                    ? showScenario(scenario.name)
                    : changes.length > 0 && toggle(scenario.name)
                }
                title={
                  [
                    scenario.description,
                    parent && `Starts from ${parent.label}`,
                    canShow && !isShown && "Click to show it",
                  ]
                    .filter(Boolean)
                    .join("\n") || undefined
                }
                className={`flex h-[26px] cursor-default items-center gap-1.5 px-2 text-[12px] ${
                  isShown
                    ? "bg-accent-600/25 text-surface-50"
                    : "text-surface-200 hover:bg-surface-700/60"
                }`}
              >
                <button
                  type="button"
                  aria-label={isOpen ? "Hide its changes" : "Show its changes"}
                  disabled={changes.length === 0}
                  onClick={(event) => {
                    event.stopPropagation();
                    toggle(scenario.name);
                  }}
                  className="text-surface-400 hover:text-surface-100 flex w-3 shrink-0 justify-center outline-none"
                >
                  {changes.length > 0 &&
                    (isOpen ? <LuChevronDown size={12} /> : <LuChevronRight size={12} />)}
                </button>
                <LuGitCommitVertical size={13} className="text-accent-400 shrink-0" />
                <span className="truncate">{scenario.label}</span>
                <span className="text-surface-500 ml-auto shrink-0 text-[11px]">
                  {scenario.name === switchingScenario
                    ? "Loading…"
                    : parent
                      ? `${changes.length} ${changes.length === 1 ? "change" : "changes"}`
                      : "Base"}
                </span>
              </div>
              {isOpen &&
                changes.map((change) => {
                  const spec = record.info.manifest.attributes[change.attribute];
                  const isSelected =
                    tableDrawer?.kind === "scenario-change" &&
                    tableDrawer.scenario === scenario.name &&
                    tableDrawer.attribute === change.attribute;
                  const noun =
                    change.dim === "bus"
                      ? change.subjects === 1
                        ? "bus"
                        : "buses"
                      : change.subjects === 1
                        ? "entity"
                        : "entities";
                  return (
                    <div
                      key={change.attribute}
                      onClick={() => openScenarioChange(scenario.name, change.attribute)}
                      title={spec?.description}
                      className={`flex h-[24px] cursor-default items-center gap-1.5 pr-2 pl-9 text-[11px] ${
                        isSelected
                          ? "bg-accent-600/25 text-surface-50"
                          : "text-surface-300 hover:bg-surface-700/60"
                      }`}
                    >
                      <span className="truncate font-mono">{change.attribute}</span>
                      <span className="text-surface-500 ml-auto shrink-0">
                        {change.subjects} {noun}
                        {change.seriesRows > 0 && " · series"}
                      </span>
                      <span className="text-accent-300 w-10 shrink-0 text-right tabular-nums">
                        {formatRatio(change.ratio)}
                      </span>
                    </div>
                  );
                })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
