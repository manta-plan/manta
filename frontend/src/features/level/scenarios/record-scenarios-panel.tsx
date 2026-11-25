// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useState, type ReactNode } from "react";
import {
  LuChevronDown,
  LuChevronRight,
  LuCircleCheck,
  LuGitCommitVertical,
  LuLayers,
  LuPackagePlus,
  LuPencil,
  LuPencilLine,
  LuPlus,
  LuTrash2,
  LuX,
} from "react-icons/lu";
import { SidebarSkeletonBlock } from "../../../components/widget-states";
import { formatRatio } from "../../project/lib/record-format";
import type { Revision } from "../../project/lib/record-server/types";
import { isRunResult, runResultsOf, shortLabel } from "../../project/lib/record-scenarios";
import { skeletonWidth } from "../../project/lib/skeleton";
import { useProjectStore } from "../../project/store/project-store";
import { SidebarEmptyState } from "../../project/components/sidebar-empty-state";
import { ConfirmDialog } from "../../../components/confirm-dialog";
import {
  describeNewEntity,
  describeOp,
  type DraftChange,
  type DraftScenario,
} from "../../project/lib/draft-scenarios";
import { levelPageId, type Level } from "../level";
import type { DraftFigures } from "./change-sql";
import { filterWords, opWords, plural } from "./change-wording";
import { beforeAfter, useDraftFigures } from "./use-draft-figures";
import { useRecordDrafts, useShownDraft } from "../../project/lib/use-shown-draft";
import { useOpenRecordPage } from "../../project/lib/use-record-page";

// What's listed under each scenario: its changes against the scenario it
// starts from (Build), or its run results (Inspect).
type PanelTab = "changes" | "results";

// While the record opens: the base case, a scenario under it, and a few of
// its changes, in the rows' own heights.
function ScenariosSkeleton() {
  const scenario = (labelWidth: string, metaWidth: string) => (
    <div className="flex h-[26px] items-center gap-1.5 px-2">
      <span className="w-3 shrink-0" />
      <SidebarSkeletonBlock className="h-3 w-3 shrink-0 rounded-full" />
      <SidebarSkeletonBlock className="h-2.5" style={{ width: labelWidth }} />
      <SidebarSkeletonBlock className="ml-auto h-2.5 shrink-0" style={{ width: metaWidth }} />
    </div>
  );
  const change = (index: number) => (
    <div key={index} className="flex h-[24px] items-center gap-1.5 pr-2 pl-9">
      <SidebarSkeletonBlock className="h-2.5" style={{ width: skeletonWidth(index + 1) }} />
      <SidebarSkeletonBlock className="ml-auto h-2.5 w-14 shrink-0" />
      <SidebarSkeletonBlock className="h-2.5 w-8 shrink-0" />
    </div>
  );
  return (
    <div role="status" aria-label="Opening the record" className="py-1">
      {scenario("38%", "28px")}
      {scenario("30%", "56px")}
      {[0, 1, 2].map(change)}
    </div>
  );
}

// The record's scenarios, read-only. Clicking one shows it: the tree, drawers
// and map follow. Under each, by tab: what it changes against the scenario it
// starts from, or its run results (each one shown on click, like a scenario).
export function RecordScenariosPanel({
  tab: activeTab,
  withDrafts = false,
}: {
  tab: PanelTab;
  withDrafts?: boolean;
}) {
  const record = useProjectStore((s) => s.record);
  const drafts = useRecordDrafts();
  const shownDraft = useShownDraft();
  const shownChange = useProjectStore((s) => s.scenarioChange);
  const openScenarioChange = useProjectStore((s) => s.openScenarioChange);
  const showScenario = useProjectStore((s) => s.showScenario);
  const switchingScenario = useProjectStore((s) => s.switchingScenario);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const recordStatus = useProjectStore((s) => s.recordStatus);
  const recordError = useProjectStore((s) => s.recordError);
  const reconnect = useProjectStore((s) => s.reconnect);

  if (!record) {
    if (recordStatus !== "error") return <ScenariosSkeleton />;
    return (
      <div
        className="text-surface-400 flex h-full items-center justify-center px-4 text-center text-[12px]"
        title={recordError ?? undefined}
      >
        <span>
          Can't reach the record server.{" "}
          <button
            type="button"
            onClick={reconnect}
            className="text-accent-400 cursor-pointer font-medium hover:underline"
          >
            Retry
          </button>
        </span>
      </div>
    );
  }
  const info = record.info;
  const revisions = info.revisions;
  const byName = new Map(revisions.map((revision) => [revision.name, revision]));
  const shown = byName.get(record.scenario ?? "");
  // Parents first, so a scenario follows the one it starts from.
  const depth = (revision: Revision): number =>
    revision.parent ? 1 + depth(byName.get(revision.parent) ?? { ...revision, parent: null }) : 0;
  const scenarios = revisions
    .filter((revision) => revision.kind === "scenario")
    .sort((a, b) => depth(a) - depth(b));
  if (scenarios.length === 0)
    return <SidebarEmptyState icon={LuLayers} text="This record has no scenarios" />;

  const toggle = (key: string) =>
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {scenarios.map((scenario) => {
          const changes = record.scenarioChanges.filter(
            (change) => change.scenario === scenario.name,
          );
          const runResults = runResultsOf(info, scenario.name);
          const childCount = activeTab === "changes" ? changes.length : runResults.length;
          const key = `${activeTab}:${scenario.name}`;
          const isOpen = childCount > 0 && !collapsed.has(key);
          const parent = scenario.parent ? byName.get(scenario.parent) : undefined;
          const isShown = scenario.name === record.scenario && !shownDraft;
          const ownDrafts = withDrafts
            ? drafts.filter((draft) => draft.parent === scenario.name)
            : [];
          const canShow = Boolean(scenario.catalog);
          // One of its run results is shown, but not listed here: say which.
          const hiddenRunResult =
            isRunResult(shown) &&
            shown?.parent === scenario.name &&
            !(activeTab === "results" && isOpen)
              ? shown
              : undefined;
          const meta =
            scenario.name === switchingScenario
              ? "Loading…"
              : hiddenRunResult
                ? `› ${shortLabel(info, hiddenRunResult)}`
                : activeTab === "results"
                  ? plural(runResults.length, "result", "results")
                  : parent
                    ? plural(changes.length, "change", "changes")
                    : "Base";
          return (
            <div key={scenario.name}>
              <div
                onClick={() =>
                  canShow ? showScenario(scenario.name) : childCount > 0 && toggle(key)
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
                className={`group flex h-[26px] cursor-pointer items-center gap-1.5 px-2 text-[12px] ${
                  isShown
                    ? "bg-accent-600/25 text-surface-50"
                    : hiddenRunResult
                      ? "bg-accent-600/10 text-surface-100"
                      : "text-surface-200 hover:bg-surface-700/60"
                }`}
              >
                <button
                  type="button"
                  aria-label={isOpen ? "Collapse" : "Expand"}
                  disabled={childCount === 0}
                  onClick={(event) => {
                    event.stopPropagation();
                    toggle(key);
                  }}
                  className="text-surface-400 hover:text-surface-100 flex w-3 shrink-0 justify-center outline-none"
                >
                  {childCount > 0 &&
                    (isOpen ? <LuChevronDown size={12} /> : <LuChevronRight size={12} />)}
                </button>
                <LuGitCommitVertical size={13} className="text-accent-400 shrink-0" />
                <span className="truncate">{scenario.label}</span>
                <span
                  className={`ml-auto shrink-0 truncate text-[11px] ${hiddenRunResult ? "text-accent-300" : "text-surface-500"}`}
                >
                  {meta}
                </span>
              </div>
              {isOpen &&
                activeTab === "changes" &&
                changes.map((change) => {
                  const spec = info.manifest.attributes[change.attribute];
                  const isSelected =
                    shownChange?.scenario === scenario.name &&
                    shownChange.attribute === change.attribute;
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
                      className={`flex h-[24px] cursor-pointer items-center gap-1.5 pr-2 pl-9 text-[11px] ${
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
              {isOpen &&
                activeTab === "results" &&
                runResults.map((runResult) => {
                  const isShownResult = runResult.name === record.scenario;
                  return (
                    <div
                      key={runResult.name}
                      onClick={() => showScenario(runResult.name)}
                      title={[
                        runResult.label,
                        runResult.description,
                        !isShownResult && "Click to show it",
                      ]
                        .filter(Boolean)
                        .join("\n")}
                      className={`flex h-[24px] cursor-pointer items-center gap-1.5 pr-2 pl-9 text-[12px] ${
                        isShownResult
                          ? "bg-accent-600/25 text-surface-50"
                          : "text-surface-200 hover:bg-surface-700/60"
                      }`}
                    >
                      <LuCircleCheck size={12} className="text-ok-500 shrink-0" />
                      <span className="truncate">{shortLabel(info, runResult)}</span>
                      <span className="text-surface-500 ml-auto shrink-0 text-[11px]">
                        {runResult.name === switchingScenario
                          ? runResult.open
                            ? "Loading…"
                            : "Opening…"
                          : plural(
                              runResult.results.length,
                              "result attribute",
                              "result attributes",
                            )}
                      </span>
                    </div>
                  );
                })}
              {ownDrafts.map((draft) => (
                <DraftRows
                  key={draft.id}
                  draft={draft}
                  isShown={draft.id === shownDraft?.id}
                  carrierLabel={(carrier) => record.carriers[carrier]?.niceName || carrier}
                />
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// A draft scenario under the one it starts from: its row (click to show it,
// with its actions on hover) and its changes, in the order they apply.
function DraftRows({
  draft,
  isShown,
  carrierLabel,
}: {
  draft: DraftScenario;
  isShown: boolean;
  carrierLabel: (carrier: string) => string;
}) {
  const showDraft = useProjectStore((s) => s.showDraft);
  const deleteDraft = useProjectStore((s) => s.deleteDraft);
  const openScenarioDialog = useProjectStore((s) => s.openScenarioDialog);
  const openChangeDialog = useProjectStore((s) => s.openChangeDialog);
  const openEntityDialog = useProjectStore((s) => s.openEntityDialog);
  const [isOpen, setIsOpen] = useState(true);
  const [isDeleting, setIsDeleting] = useState(false);
  const figures = useDraftFigures(draft);
  const count = draft.changes.length;
  const action = (label: string, Icon: typeof LuPlus, onClick: () => void) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="text-surface-400 hover:bg-surface-600 hover:text-surface-50 focus-visible:text-surface-50 rounded p-0.5 outline-none"
    >
      <Icon size={12} />
    </button>
  );
  return (
    <>
      <div
        onClick={() => showDraft(draft.id)}
        title={[draft.description, "A draft, kept in this browser", !isShown && "Click to show it"]
          .filter(Boolean)
          .join("\n")}
        className={`group flex h-[26px] cursor-pointer items-center gap-1.5 pr-2 pl-5 text-[12px] ${isShown ? "bg-accent-600/25 text-surface-50" : "text-surface-200 hover:bg-surface-700/60"}`}
      >
        <button
          type="button"
          aria-label={isOpen ? "Collapse" : "Expand"}
          disabled={count === 0}
          onClick={(event) => {
            event.stopPropagation();
            setIsOpen((open) => !open);
          }}
          className="text-surface-400 hover:text-surface-100 flex w-3 shrink-0 justify-center outline-none"
        >
          {count > 0 && (isOpen ? <LuChevronDown size={12} /> : <LuChevronRight size={12} />)}
        </button>
        <LuPencilLine size={12} className="text-warn-500 shrink-0" />
        <span className="truncate">{draft.name}</span>
        <span className="border-warn-500/40 text-warn-500 shrink-0 rounded border px-1 text-[9px] font-semibold tracking-wide uppercase">
          Draft
        </span>
        <span className="text-surface-500 ml-auto shrink-0 text-[11px] group-focus-within:hidden group-hover:hidden">
          {plural(count, "change", "changes")}
        </span>
        <span className="ml-auto hidden shrink-0 items-center gap-0.5 group-focus-within:flex group-hover:flex">
          {action("Add a change", LuPlus, () => openChangeDialog({ draftId: draft.id }))}
          {action("Add an entity", LuPackagePlus, () => openEntityDialog({ draftId: draft.id }))}
          {action("Rename or describe", LuPencil, () =>
            openScenarioDialog({ mode: "edit", draftId: draft.id }),
          )}
          {action("Delete the draft", LuTrash2, () => setIsDeleting(true))}
        </span>
      </div>
      {isOpen &&
        draft.changes.map((change, index) => (
          <DraftChangeRow
            key={change.id}
            draft={draft}
            change={change}
            index={index}
            figures={figures}
            carrierLabel={carrierLabel}
          />
        ))}
      <ConfirmDialog
        open={isDeleting}
        onOpenChange={setIsDeleting}
        title={`Delete “${draft.name}”?`}
        description={`Its ${plural(count, "change", "changes")} go with it. The draft is only in this browser, so this can't be undone.`}
        confirmLabel="Delete"
        onConfirm={() => {
          deleteDraft(draft.id);
          setIsDeleting(false);
        }}
      />
    </>
  );
}

// One change of a draft: "~ <id> <attr> <old> → <new>" for one entity, a
// group row "Generator Solar · capital_cost multiply by 1.3 · 296 entities"
// for a filter, "+ <id> added" for a new entity. A click shows the draft and
// opens what the change is about (a new entity, not in the scenario yet,
// opens its dialog); the pencil edits it, the × removes it.
function DraftChangeRow({
  draft,
  change,
  index,
  figures,
  carrierLabel,
}: {
  draft: DraftScenario;
  change: DraftChange;
  index: number;
  figures: DraftFigures | null;
  carrierLabel: (carrier: string) => string;
}) {
  const showDraft = useProjectStore((s) => s.showDraft);
  const record = useProjectStore((s) => s.record);
  const shownDraft = useShownDraft();
  const openChangeDialog = useProjectStore((s) => s.openChangeDialog);
  const openEntityDialog = useProjectStore((s) => s.openEntityDialog);
  const removeDraftChange = useProjectStore((s) => s.removeDraftChange);
  const openRecordPage = useOpenRecordPage();
  const unit =
    change.kind === "attribute"
      ? (record?.info.manifest.attributes[change.attribute]?.unit ?? undefined)
      : undefined;
  const edit = () =>
    change.kind === "new-entity"
      ? openEntityDialog({ draftId: draft.id, change })
      : openChangeDialog({ draftId: draft.id, change });
  const open = () => {
    if (change.kind === "new-entity") return edit();
    if (shownDraft?.id !== draft.id) showDraft(draft.id);
    const { target } = change;
    const level: Level =
      target.kind === "entity"
        ? { kind: "entity", entity: target.entity }
        : target.carrier
          ? { kind: "carrier", ctype: target.ctype, carrier: target.carrier }
          : { kind: "component", ctype: target.ctype };
    openRecordPage(levelPageId(level));
  };

  let body: ReactNode;
  let what: string;
  if (change.kind === "new-entity") {
    what = `New ${change.ctype} “${change.entity}”\n${describeNewEntity(change, carrierLabel)}`;
    body = (
      <>
        <span className="text-ok-500 shrink-0 font-mono">+</span>
        <span className="min-w-0 truncate font-mono">{change.entity}</span>
        <span className="text-surface-500 ml-auto shrink-0">added</span>
      </>
    );
  } else if (change.target.kind === "entity") {
    const values = beforeAfter(draft, change, figures, describeOp(change.op, change.value));
    what = `${change.target.entity}\n${change.attribute}: ${opWords(change.op, change.value, unit)}${values ? `\n${values.before} → ${values.after}` : ""}`;
    body = (
      <>
        <span className="text-warn-500 shrink-0 font-mono">~</span>
        <span className="min-w-0 truncate font-mono">{change.target.entity}</span>
        <span className="text-surface-400 shrink-0 font-mono">{change.attribute}</span>
        <span className="text-warn-500 ml-auto shrink-0 tabular-nums">
          {values ? `${values.before} → ${values.after}` : describeOp(change.op, change.value)}
        </span>
      </>
    );
  } else {
    const matched = figures?.matches[change.id];
    const group = `${filterWords(change.target, carrierLabel)} · ${change.attribute} ${opWords(change.op, change.value, unit)}`;
    what = `${group}${matched === undefined ? "" : `\n${plural(matched, "entity", "entities")} in the period shown`}`;
    body = (
      <>
        <span className="text-warn-500 shrink-0 font-mono">~</span>
        <span className="min-w-0 truncate">{group}</span>
        {matched !== undefined && (
          <span className="text-surface-500 ml-auto shrink-0 tabular-nums">
            {plural(matched, "entity", "entities")}
          </span>
        )}
      </>
    );
  }

  const action = (label: string, Icon: typeof LuX, onClick: () => void) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={(event) => {
        event.stopPropagation();
        onClick();
      }}
      className="text-surface-500 hover:bg-surface-600 hover:text-surface-50 focus-visible:text-surface-50 shrink-0 rounded p-0.5 outline-none"
    >
      <Icon size={11} />
    </button>
  );
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={open}
      onKeyDown={(event) => {
        if (event.key === "Enter" && event.target === event.currentTarget) open();
      }}
      title={`${index + 1}. ${what}`}
      className="text-surface-300 hover:bg-surface-700/60 focus-visible:bg-surface-700/60 flex h-[24px] cursor-pointer items-center gap-1.5 pr-1 pl-11 text-[11px] outline-none"
    >
      {body}
      <span
        className={`flex shrink-0 items-center ${change.kind === "attribute" && change.target.kind === "filter" && figures?.matches[change.id] === undefined ? "ml-auto" : ""}`}
      >
        {action("Edit the change", LuPencil, edit)}
        {action("Remove the change", LuX, () => removeDraftChange(draft.id, change.id))}
      </span>
    </div>
  );
}
