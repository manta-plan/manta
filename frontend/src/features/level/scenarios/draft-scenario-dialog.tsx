import { useEffect, useState } from "react";
import { LuCheck, LuCopy } from "react-icons/lu";
import { toChangeSet } from "../../project/lib/draft-scenarios";
import { useCopyToClipboard } from "../../project/lib/use-copy-to-clipboard";
import { useProjectStore } from "../../project/store/project-store";
import {
  DialogShell,
  Field,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from "./dialog-parts";

// Making a draft scenario (from the scenario the Build tab shows), or
// renaming one. A draft's change set, what the backend will be handed, can
// be copied from here as JSON.

export function DraftScenarioDialog() {
  const dialog = useProjectStore((s) => s.scenarioDialog);
  const close = useProjectStore((s) => s.closeScenarioDialog);
  const record = useProjectStore((s) => s.record);
  const drafts = useProjectStore((s) => s.draftScenarios);
  const createDraft = useProjectStore((s) => s.createDraft);
  const updateDraft = useProjectStore((s) => s.updateDraft);
  const showDraft = useProjectStore((s) => s.showDraft);
  const { copied, copy } = useCopyToClipboard();
  const editing =
    dialog?.mode === "edit" ? (drafts.find((draft) => draft.id === dialog.draftId) ?? null) : null;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  // Seeds once per open.
  useEffect(() => {
    if (!dialog) return;
    setName(editing?.name ?? "");
    setDescription(editing?.description ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dialog]);

  const revisions = record?.info.revisions ?? [];
  const parentName = editing?.parent ?? record?.scenario ?? null;
  const shown = revisions.find((revision) => revision.name === parentName);
  // A run result isn't listed in the Scenarios panel: a draft starts from its scenario.
  const parent =
    shown?.kind === "result" && shown.parent
      ? (revisions.find((revision) => revision.name === shown.parent) ?? shown)
      : shown;
  const taken = drafts.some(
    (draft) =>
      draft.id !== editing?.id &&
      draft.recordId === record?.info.id &&
      draft.name.trim().toLowerCase() === name.trim().toLowerCase(),
  );
  const canSave = Boolean(record && parent && name.trim() && !taken);

  const save = () => {
    if (!canSave || !record || !parent) return;
    if (editing) updateDraft(editing.id, { name, description });
    else
      showDraft(
        createDraft({ recordId: record.info.id, parent: parent.name, name, description }).id,
      );
    close();
  };

  return (
    <DialogShell
      open={dialog !== null}
      onClose={close}
      title={editing ? "Edit scenario" : "New scenario"}
      description={
        <>
          {editing
            ? "A draft"
            : "A draft, kept in this browser until scenarios can be saved to the record,"}{" "}
          starting from <span className="text-surface-200">{parent?.label ?? "—"}</span>.
        </>
      }
      footer={
        <>
          {editing && (
            <button
              type="button"
              onClick={() => copy(JSON.stringify(toChangeSet(editing), null, 2))}
              className={`${SECONDARY_BUTTON_CLASS} flex items-center gap-1.5`}
              title="The change set the backend will be handed, as JSON"
            >
              {copied ? <LuCheck size={13} /> : <LuCopy size={13} />}
              {copied ? "Copied" : "Copy change set"}
            </button>
          )}
          <button type="button" onClick={close} className={`${SECONDARY_BUTTON_CLASS} ml-auto`}>
            Cancel
          </button>
          <button type="button" onClick={save} disabled={!canSave} className={PRIMARY_BUTTON_CLASS}>
            {editing ? "Save" : "Create"}
          </button>
        </>
      }
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
        className="flex flex-col gap-3"
      >
        <Field label="Name" hint={taken ? "Another draft has this name." : undefined}>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="e.g. Offshore wind cost +30%"
            autoFocus
            className={INPUT_CLASS}
          />
        </Field>
        <Field label="Description">
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder="What this scenario explores"
            className={`${INPUT_CLASS} h-auto resize-none py-1.5 leading-5`}
          />
        </Field>
      </form>
    </DialogShell>
  );
}
