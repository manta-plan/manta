import { useMemo } from "react";
import { PageSkeleton } from "./ui";
import { LevelPage } from "./level-page";
import { levelOfPageId } from "./level";
import { recordResults } from "../project/lib/record-results";
import { isRunResult } from "../project/lib/record-scenarios";
import { useRecordPageTab } from "../project/lib/use-record-page";
import { useProjectStore } from "../project/store/project-store";

// The record's pages, on Build and Inspect alike: a level's page (All
// entities, a component, carrier, entity, All locations, a location or bus),
// opened from the record's tree. They read the revision the record shows: a
// scenario's inputs, and on Inspect a result's outputs too. Build shows
// scenarios only. (Comparison pages join here later.)
export function RecordPages({ pageId }: { pageId: string | null }) {
  const record = useProjectStore((s) => s.record);
  const tab = useRecordPageTab();
  const result = useMemo(() => {
    if (tab !== "inspect" || !record) return null;
    const shown = record.info.revisions.find((revision) => revision.name === record.scenario);
    return isRunResult(shown)
      ? (recordResults(record.info).find((item) => item.id === shown!.name) ?? null)
      : null;
  }, [record, tab]);

  if (!record) {
    return (
      <div className="p-4">
        <PageSkeleton label="Opening the record" />
      </div>
    );
  }
  const level = levelOfPageId(pageId);
  if (!level) return null;
  return <LevelPage level={level} stage={tab} result={result} />;
}
