import { useEffect, useState } from "react";
import {
  LuChevronDown,
  LuChevronRight,
  LuGitCommitVertical,
  LuLayers,
  LuWorkflow,
} from "react-icons/lu";
import { SidebarEmptyState } from "../../project/components/sidebar-empty-state";
import { useProjectStore } from "../../project/store/project-store";
import { useRunsStore } from "../store/runs-store";
import { listRecordScenarios } from "../list-record-scenarios";
import { useOpenNewRun } from "../use-open-new-run";

// The bottom panel of the Run tab: each scenario of the record, with the playbooks it can run.
// Picking one opens the New Run panel with both chosen.
export function ScenarioPlaybooksPanel() {
  const record = useProjectStore((s) => s.record);
  const playbooks = useRunsStore((s) => s.playbooks);
  const playbooksStatus = useRunsStore((s) => s.playbooksStatus);
  const playbooksError = useRunsStore((s) => s.playbooksError);
  const loadPlaybooks = useRunsStore((s) => s.loadPlaybooks);
  const selectedScenario = useRunsStore((s) => s.selectedScenario);
  const selectedPlaybook = useRunsStore((s) => s.selectedPlaybook);
  const isNewRunDrawerOpen = useProjectStore((s) => s.isNewRunDrawerOpen);
  const openNewRun = useOpenNewRun();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    void loadPlaybooks();
  }, [loadPlaybooks]);

  if (!record) {
    return null;
  }

  const scenarios = listRecordScenarios(record.info.revisions);

  if (scenarios.length === 0) {
    return <SidebarEmptyState icon={LuLayers} text="This record has no scenarios" />;
  }

  const toggle = (name: string) =>
    setExpanded((current) => {
      const next = new Set(current);

      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }

      return next;
    });

  return (
    <div className="h-full overflow-y-auto py-1">
      {scenarios.map((scenario) => {
        const isExpanded = expanded.has(scenario.name);

        return (
          <div key={scenario.name}>
            <div className="text-surface-200 hover:bg-surface-700/60 flex h-[26px] items-center gap-1.5 px-2 text-[12px]">
              <button
                aria-expanded={isExpanded}
                aria-label={`${isExpanded ? "Hide" : "Show"} playbooks of ${scenario.label}`}
                className="text-surface-400 hover:text-surface-100 flex shrink-0 items-center outline-none"
                onClick={() => toggle(scenario.name)}
                type="button"
              >
                {isExpanded ? (
                  <LuChevronDown size={12} aria-hidden="true" />
                ) : (
                  <LuChevronRight size={12} aria-hidden="true" />
                )}
              </button>
              <LuGitCommitVertical
                className="text-accent-400 shrink-0"
                size={13}
                aria-hidden="true"
              />
              <span className="truncate">{scenario.label}</span>
              <span className="text-surface-500 ml-auto shrink-0 text-[11px]">
                {playbooksStatus === "ready" ? `${playbooks.length} playbooks` : ""}
              </span>
            </div>
            {isExpanded ? (
              playbooksStatus === "loading" || playbooksStatus === "idle" ? (
                <div className="text-surface-500 py-0.5 pr-2 pl-9 text-[11px]">
                  Loading playbooks...
                </div>
              ) : playbooksStatus === "error" ? (
                <div className="py-0.5 pr-2 pl-9 text-[11px] text-red-300" role="alert">
                  {playbooksError}{" "}
                  <button
                    className="text-accent-400 underline outline-none"
                    onClick={() => void loadPlaybooks()}
                    type="button"
                  >
                    Retry
                  </button>
                </div>
              ) : playbooks.length === 0 ? (
                <div className="text-surface-500 py-0.5 pr-2 pl-9 text-[11px]">
                  No compatible playbooks yet
                </div>
              ) : (
                playbooks.map((playbook) => {
                  const isSelected =
                    isNewRunDrawerOpen &&
                    selectedScenario === scenario.name &&
                    selectedPlaybook === playbook.name;

                  return (
                    <button
                      aria-pressed={isSelected}
                      className={`focus-visible:bg-surface-700/60 flex h-[24px] w-full items-center gap-1.5 pr-2 pl-9 text-left text-[11px] outline-none ${
                        isSelected
                          ? "bg-accent-600/25 text-surface-100"
                          : "text-surface-400 hover:bg-surface-700/40"
                      }`}
                      key={playbook.name}
                      onClick={() =>
                        openNewRun({ scenario: scenario.name, playbook: playbook.name })
                      }
                      type="button"
                    >
                      <LuWorkflow
                        className="text-accent-400 shrink-0"
                        size={11}
                        aria-hidden="true"
                      />
                      <span className="text-surface-200 truncate">{playbook.name}</span>
                    </button>
                  );
                })
              )
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
