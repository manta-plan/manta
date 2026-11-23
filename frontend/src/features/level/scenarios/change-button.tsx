// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: MIT

import { Toolbar } from "@base-ui/react/toolbar";
import { LuPackagePlus, LuPencil } from "react-icons/lu";
import { ToolbarIconButton } from "../../project/components/toolbar-icon-button";
import { useOpenRecordPageId, useRecordPageTab } from "../../project/lib/use-record-page";
import { useShownDraft } from "../../project/lib/use-shown-draft";
import { useProjectStore } from "../../project/store/project-store";
import { levelOfPageId, type Level } from "../level";
import { levelFilterTarget, useLevelChangeTarget } from "./level-target";

// The open level's actions on Build, in the header's toolbar left of the
// project-wide ones: "Change…" opens the change dialog on the level (its
// entity, or the entities it groups), "Add entity…" the new entity dialog
// with the level's type and carrier. Neither shows on Inspect, nor beside a
// comparison.

export function LevelToolbarActions() {
  const tab = useRecordPageTab();
  const pageId = useOpenRecordPageId();
  const level = levelOfPageId(pageId);
  if (tab !== "build" || !level) return null;
  return (
    <>
      <Toolbar.Group className="flex items-center gap-0.5">
        <AddEntityButton level={level} />
        <ChangeButton level={level} />
      </Toolbar.Group>
      <Toolbar.Separator className="bg-surface-600 mx-1 h-5 w-px" />
    </>
  );
}

function ChangeButton({ level }: { level: Level }) {
  const shownDraft = useShownDraft();
  const openChangeDialog = useProjectStore((s) => s.openChangeDialog);
  const target = useLevelChangeTarget(level);
  return (
    <ToolbarIconButton
      icon={LuPencil}
      label={shownDraft ? `Change… (adds to ${shownDraft.name})` : "Change… (in a draft scenario)"}
      disabled={!target}
      onClick={() => target && openChangeDialog({ draftId: shownDraft?.id, target })}
    />
  );
}

function AddEntityButton({ level }: { level: Level }) {
  const shownDraft = useShownDraft();
  const openEntityDialog = useProjectStore((s) => s.openEntityDialog);
  // An entity level adds a sibling of the same type, once its type is read.
  const target = useLevelChangeTarget(level.kind === "entity" ? level : null);
  const seed = level.kind === "entity" ? target : levelFilterTarget(level);
  const ctype =
    level.kind === "component" || level.kind === "carrier"
      ? level.ctype
      : level.kind === "entity"
        ? seed?.ctype
        : undefined;
  const carrier =
    level.kind === "carrier"
      ? level.carrier
      : level.kind === "entity"
        ? (seed?.carrier ?? null)
        : null;
  const location = seed?.location ?? undefined;
  return (
    <ToolbarIconButton
      icon={LuPackagePlus}
      label={`Add ${ctype ? `a ${ctype}` : "an entity"}… (${shownDraft ? `to ${shownDraft.name}` : "in a draft scenario"})`}
      disabled={level.kind === "entity" && !target}
      onClick={() => openEntityDialog({ draftId: shownDraft?.id, ctype, carrier, location })}
    />
  );
}
