import { useState } from "react";
import { useParams } from "wouter";
import { isObject } from "../../../utils/jsonObject";
import { humanize } from "../../../utils/jsonSchema";
import { exactlyOneOf } from "../../playbook-config/exclusiveSettings";
import { useProjectStore } from "../../project/store/project-store";
import { getStepErrors } from "../run-draft";
import { useRunsStore } from "../store/runs-store";
import { useSelectedRun } from "../use-selected-run";
import { PlaybookConfigForm } from "./playbook-config-form";

const noteClassName = "text-surface-400 text-[12px]";

// The settings of one block of the open run, in the right drawer. A draft can be edited here
// (what Start will send); a run that has started shows what it was started with, read-only.
export function RunNodeConfigForm() {
  const { detailId } = useParams<{ detailId?: string }>();
  const stepName = useProjectStore((s) => s.configuringRunNodeId);
  const selected = useSelectedRun(detailId);
  const setDraftStepConfig = useRunsStore((s) => s.setDraftStepConfig);
  // Moves on "Use defaults", so inputs that keep their own text start again.
  const [resetCount, setResetCount] = useState(0);

  const playbookName =
    selected?.kind === "draft"
      ? selected.draft.playbook
      : selected?.kind === "run"
        ? (selected.detail?.playbook ?? selected.run.playbook)
        : null;
  const playbook = useRunsStore((s) =>
    playbookName === null ? undefined : s.playbookDetails[playbookName],
  );
  const playbookError = useRunsStore((s) =>
    playbookName === null ? undefined : s.playbookDetailErrors[playbookName],
  );
  const step = playbook?.steps.find((item) => item.name === stepName);

  if (selected === null || (selected.kind !== "draft" && selected.kind !== "run")) {
    return (
      <div className="text-surface-400 flex flex-1 items-center justify-center p-4 text-center text-[12px]">
        Select a block in the flow to see its settings.
      </div>
    );
  }

  if (playbookError !== undefined) {
    return (
      <div className="p-3 text-[12px] text-red-300" role="alert">
        {playbookError}
      </div>
    );
  }

  if (playbook === undefined) {
    return <div className={`${noteClassName} p-3`}>Loading playbook...</div>;
  }

  if (step === undefined) {
    return (
      <div className="text-surface-400 flex flex-1 items-center justify-center p-4 text-center text-[12px]">
        Select a block in the flow to see its settings.
      </div>
    );
  }

  const draft = selected.kind === "draft" ? selected.draft : null;
  // A run's own record: absent when the backend does not return it.
  const runConfig =
    selected.kind === "run" && selected.detail !== null && isObject(selected.detail.config)
      ? selected.detail.config
      : null;
  const config = draft?.config ?? runConfig;
  const stepValue = config?.[step.name];
  const errors = draft === null ? undefined : getStepErrors(playbook, draft.config).get(step.name);

  return (
    <div className="text-surface-100 flex flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div className="border-surface-600 bg-surface-900 rounded border p-2">
        <div className="text-surface-400 text-[11px] font-medium">
          {step.block ?? "Nested playbook"}
        </div>
        <div className="text-surface-100 mt-1 text-[13px] font-medium">{humanize(step.name)}</div>
        {step.block_summary ? (
          <div className="text-surface-500 mt-1 text-[11px]">{step.block_summary}</div>
        ) : null}
      </div>

      {step.block_config_schema === null ? (
        <p className={noteClassName}>
          This step runs a nested playbook and has no settings of its own.
        </p>
      ) : config === null ? (
        <p className={noteClassName}>
          {selected.kind === "run" && selected.detail === null
            ? "Loading the settings of this run..."
            : "Parameters are not available for this run."}
        </p>
      ) : (
        // A fieldset disables every input in it: a started run's settings only show.
        <fieldset className="min-w-0 border-0 p-0" disabled={draft === null}>
          <PlaybookConfigForm
            defaults={playbook.default_config[step.name]}
            errors={errors}
            exclusive={step.block === null ? undefined : exactlyOneOf[step.block]}
            idPrefix={step.name}
            inputs={step.inputs}
            // A fresh form per step, so inputs with local state don't carry over.
            key={`${step.name}:${resetCount}`}
            onChange={(next) => draft !== null && setDraftStepConfig(draft.id, step.name, next)}
            schema={step.block_config_schema}
            value={isObject(stepValue) ? stepValue : {}}
          />
        </fieldset>
      )}

      <div className="border-surface-600/60 mt-auto flex flex-col gap-2 border-t pt-3">
        {draft === null ? (
          <p className="text-surface-400 text-[11px]">
            This run has already started, so its parameters are read-only.
          </p>
        ) : step.block_config_schema === null ? null : (
          <button
            className="border-surface-600 text-surface-300 hover:bg-surface-700 w-full rounded border px-3 py-1.5 text-[12px] font-medium outline-none disabled:pointer-events-none disabled:opacity-50"
            onClick={() => {
              setDraftStepConfig(
                draft.id,
                step.name,
                structuredClone(playbook.default_config[step.name] ?? {}),
              );
              setResetCount((count) => count + 1);
            }}
            type="button"
          >
            Use defaults
          </button>
        )}
      </div>
    </div>
  );
}
