import { LuGitCommitVertical } from "react-icons/lu";
import { RecordScenariosPanel as ScenarioList } from "../../project/components/record-scenarios-panel";
import { recordResults } from "../../project/lib/record-results";
import { shortLabel } from "../../project/lib/record-scenarios";
import { useProjectStore } from "../../project/store/project-store";

export type ScenariosPanelTab = "changes" | "results";

// STUB: replaced by the real port of baby-manta's components/RecordScenariosPanel.tsx
// in phase B (scenario changes with draft rows on Build, results on Inspect).
// Until then: Build lists the scenarios with what they change (the existing
// panel), Inspect lists the record's run results; clicking one shows it.
export function RecordScenariosPanel({
  tab,
}: {
  tab: ScenariosPanelTab;
  /** Draft rows (Build); unused by the stub. */
  withDrafts?: boolean;
}) {
  if (tab === "changes") return <ScenarioList />;
  return <ResultsList />;
}

function ResultsList() {
  const record = useProjectStore((s) => s.record);
  const switching = useProjectStore((s) => s.switchingScenario);
  const showScenario = useProjectStore((s) => s.showScenario);
  if (!record) return null;
  const results = recordResults(record.info);
  if (results.length === 0) {
    return <div className="text-surface-400 p-3 text-[12px]">This record has no run results.</div>;
  }
  const shown = switching ?? record.scenario;
  return (
    <ul className="h-full overflow-y-auto py-1">
      {results.map((result) => {
        const revision = record.info.revisions.find((item) => item.name === result.id);
        return (
          <li key={result.id}>
            <button
              type="button"
              onClick={() => showScenario(result.id)}
              aria-current={shown === result.id}
              className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-[12px] outline-none ${shown === result.id ? "bg-accent-600/20 text-accent-300" : "text-surface-200 hover:bg-surface-700"}`}
            >
              <LuGitCommitVertical size={12} className="shrink-0" />
              <span className="min-w-0 truncate" title={result.label}>
                {revision ? shortLabel(record.info, revision) : result.label}
              </span>
              <span className="text-surface-500 ml-auto shrink-0 truncate text-[11px]">
                {result.scenarioLabel}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
