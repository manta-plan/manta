import { useProjectStore } from "../../project/store/project-store";
import { useShownDraft } from "../../project/lib/use-shown-draft";

// Which scenario the map, tree and drawers currently show; sits under the
// Record header since it describes the tree below it.
export function ShownScenarioNote() {
  const record = useProjectStore((s) => s.record);
  const switchingScenario = useProjectStore((s) => s.switchingScenario);
  const shownDraft = useShownDraft();
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
      ) : shownDraft ? (
        <>
          Showing: <span className="text-surface-300">{shown.label}</span> ›{" "}
          <span className="text-warn-500">{shownDraft.name}</span> (draft)
        </>
      ) : (
        <>
          Showing: <span className="text-surface-300">{shown.label}</span>
        </>
      )}
    </div>
  );
}
