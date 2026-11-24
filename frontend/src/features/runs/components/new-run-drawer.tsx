import { useEffect, useState, type FormEvent } from "react";
import { FiLoader } from "react-icons/fi";
import { LuHistory, LuPlus, LuX } from "react-icons/lu";
import { useLocation, useParams } from "wouter";
import { humanize } from "../../../utils/jsonSchema";
import type { NewRunDrawerProps } from "../../../utils/playbookTypes";
import { FormSelect } from "../../../components/form-select";
import { getRecordRevisions } from "../../home/lib/record-server";
import { useRecordCatalogue } from "../../home/lib/use-record-catalogue";
import { deriveGlobalFields, getIn, setAtPath } from "../../playbook-config/conditions";
import { projectRunHref } from "../../project/lib/project-route";
import { useProjectStore } from "../../project/store/project-store";
import { listRecordScenarios } from "../list-record-scenarios";
import { useRunsStore } from "../store/runs-store";

const noScenario = "__none__";
const labelClassName = "text-surface-400 text-[11px] font-medium";

// The short form of a new run: what to run, on which data. The blocks and their settings are
// reviewed in the run workspace after "Create Run", which makes a draft there.
export function NewRunDrawer({ open, onOpenChange }: NewRunDrawerProps) {
  // Moves each time the panel is opened, so its form starts again.
  const session = useRunsStore((s) => s.newRunSession);

  return (
    <aside
      aria-hidden={!open}
      aria-label="New run"
      className={`border-surface-600/60 bg-surface-800/70 absolute top-0 left-0 z-20 flex h-full w-72 flex-col border-r backdrop-blur-xl transition-transform duration-200 ease-out ${
        open ? "pointer-events-auto translate-x-0" : "pointer-events-none -translate-x-full"
      }`}
      inert={!open}
    >
      <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
        <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
          <LuHistory size={12} aria-hidden="true" />
          New Run
        </div>
        <button
          aria-label="Close new run drawer"
          className="text-surface-400 hover:text-surface-100 outline-none"
          onClick={() => onOpenChange(false)}
          type="button"
        >
          <LuX size={14} aria-hidden="true" />
        </button>
      </div>
      <NewRunForm key={session} onClose={() => onOpenChange(false)} />
    </aside>
  );
}

function NewRunForm({ onClose }: { onClose: () => void }) {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const record = useProjectStore((s) => s.record);
  const playbooks = useRunsStore((s) => s.playbooks);
  const playbooksStatus = useRunsStore((s) => s.playbooksStatus);
  const playbooksError = useRunsStore((s) => s.playbooksError);
  const playbookDetails = useRunsStore((s) => s.playbookDetails);
  const playbookDetailErrors = useRunsStore((s) => s.playbookDetailErrors);
  const loadPlaybooks = useRunsStore((s) => s.loadPlaybooks);
  const loadPlaybookDetail = useRunsStore((s) => s.loadPlaybookDetail);
  const createDraft = useRunsStore((s) => s.createDraft);

  // The panel opens with what the Playbooks by Scenario panel picked, if anything.
  const [scenarioName, setScenarioName] = useState(
    () => useRunsStore.getState().selectedScenario ?? noScenario,
  );
  const [playbook, setPlaybook] = useState<string | null>(
    () => useRunsStore.getState().selectedPlaybook,
  );
  const { catalogue, error: recordsError } = useRecordCatalogue();
  const dataRecords = catalogue?.records ?? [];
  // null until the user picks one: the server's default applies meanwhile.
  const [chosenDataRecord, setChosenDataRecord] = useState<string | null>(null);
  const dataRecordName = chosenDataRecord ?? catalogue?.default ?? dataRecords[0]?.id ?? null;
  const [isResolvingRecord, setIsResolvingRecord] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // The global fields the user changed, by dotted path, on top of the playbook's defaults.
  const [globalEdits, setGlobalEdits] = useState<Record<string, unknown>>({});

  useEffect(() => {
    void loadPlaybooks();
  }, [loadPlaybooks]);

  useEffect(() => {
    if (playbook !== null) {
      void loadPlaybookDetail(playbook);
    }
  }, [playbook, loadPlaybookDetail]);

  const detail = playbook === null ? undefined : playbookDetails[playbook];
  const detailError = playbook === null ? undefined : playbookDetailErrors[playbook];
  const scenarios = record === null ? [] : listRecordScenarios(record.info.revisions);
  // They decide which blocks are active, so they are chosen here, before the blocks are shown.
  const globalFields = detail === undefined ? [] : deriveGlobalFields(detail);
  const config =
    detail === undefined
      ? {}
      : Object.entries(globalEdits).reduce(
          (current, [path, value]) => setAtPath(current, path, value),
          structuredClone(detail.default_config),
        );
  const isLoadingDetail = playbook !== null && detail === undefined && detailError === undefined;
  const blockedReason =
    playbook === null
      ? "Select a playbook to create the run."
      : isLoadingDetail
        ? "Loading the playbook..."
        : detail === undefined
          ? "The playbook could not be loaded."
          : dataRecordName === null
            ? "Select a data record to create the run."
            : null;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (playbook === null || detail === undefined || dataRecordName === null) {
      return;
    }

    setSubmitError(null);
    setIsResolvingRecord(true);
    let revisionUuid: string | undefined;

    try {
      // The run starts from the record's `inputs` revision, which the record server names.
      revisionUuid = (await getRecordRevisions(dataRecordName)).inputs;
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to read the data record.");
      return;
    } finally {
      setIsResolvingRecord(false);
    }

    if (revisionUuid === undefined) {
      setSubmitError(`The data record "${dataRecordName}" has no inputs revision.`);
      return;
    }

    const dataRecord = { name: dataRecordName, revision_uuid: revisionUuid };

    const scenario = scenarios.find((item) => item.name === scenarioName);
    const draft = createDraft({
      projectId,
      playbook,
      dataRecord,
      scenarioId: scenario?.name ?? null,
      scenarioLabel: scenario?.label ?? null,
      config,
    });

    onClose();
    navigate(projectRunHref(projectId, draft.id));
  }

  return (
    <form className="flex min-h-0 flex-1 flex-col" onSubmit={handleSubmit}>
      <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
        <div className="flex flex-col gap-1">
          <span className={labelClassName}>Scenario</span>
          <FormSelect
            ariaLabel="Scenario"
            onValueChange={setScenarioName}
            options={[
              { label: "None (base model)", value: noScenario },
              ...scenarios.map((scenario) => ({ label: scenario.label, value: scenario.name })),
            ]}
            value={scenarioName}
          />
        </div>

        <div className="flex flex-col gap-1">
          <span className={labelClassName}>Playbook</span>
          {playbooksStatus === "loading" || playbooksStatus === "idle" ? (
            <div className="border-surface-600 bg-surface-900 text-surface-400 flex h-8 items-center rounded border px-2 text-[13px]">
              Loading playbooks...
            </div>
          ) : playbooksStatus === "error" ? (
            <div
              className="rounded border border-red-500/40 bg-red-500/10 px-2 py-1.5 text-[12px] text-red-300"
              role="alert"
            >
              {playbooksError}{" "}
              <button
                className="underline outline-none"
                onClick={() => void loadPlaybooks()}
                type="button"
              >
                Retry
              </button>
            </div>
          ) : (
            <FormSelect
              ariaLabel="Playbook"
              onValueChange={(value) => {
                setPlaybook(value);
                setGlobalEdits({});
              }}
              options={playbooks.map((item) => ({ label: item.name, value: item.name }))}
              placeholder="Select a playbook"
              value={playbook}
            />
          )}
          {detailError === undefined ? null : (
            <p className="text-[12px] text-red-300" role="alert">
              {detailError}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1">
          <span className={labelClassName}>Data record</span>
          <FormSelect
            ariaLabel="Data record"
            onValueChange={setChosenDataRecord}
            options={dataRecords.map((item) => ({ label: item.label, value: item.id }))}
            placeholder={
              recordsError
                ? "Can't reach the record server"
                : catalogue
                  ? "No data records available"
                  : "Loading data records..."
            }
            value={dataRecordName}
          />
        </div>

        {globalFields.map((field) => {
          const current = getIn(config, field.path.split("."));
          const label = humanize(field.path.split(".").pop() ?? "");

          return (
            <div className="flex flex-col gap-1" key={field.path}>
              <span className={labelClassName}>{label}</span>
              <FormSelect
                ariaLabel={label}
                onValueChange={(next) =>
                  setGlobalEdits((edits) => ({
                    ...edits,
                    // Keeps the option's own type (a number stays a number).
                    [field.path]: field.options.find((option) => String(option) === next),
                  }))
                }
                options={field.options.map((option) => ({
                  label: String(option),
                  value: String(option),
                }))}
                placeholder="—"
                value={current === undefined ? null : String(current)}
              />
            </div>
          );
        })}

        <div className="border-surface-600 bg-surface-900 rounded border p-2">
          <div className={labelClassName}>Execution</div>
          <div className="text-surface-100 mt-1 text-[12px]">Queued on shared compute pool</div>
          <div className="text-surface-500 mt-1 text-[11px]">
            The run is created as a draft. Review its blocks, then Start it.
          </div>
        </div>
      </div>

      <div className="border-surface-600/60 flex shrink-0 flex-col gap-2 border-t p-3">
        {submitError === null ? null : (
          <p className="text-[12px] text-red-300" role="alert">
            {submitError}
          </p>
        )}
        {blockedReason === null ? null : (
          <p className="text-surface-400 text-[11px]" id="new-run-blocked">
            {blockedReason}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            className="border-surface-600 text-surface-300 hover:bg-surface-700 rounded border px-3 py-1.5 text-[12px] font-medium outline-none"
            onClick={onClose}
            type="button"
          >
            Cancel
          </button>
          <button
            aria-describedby={blockedReason === null ? undefined : "new-run-blocked"}
            className="bg-accent-600 hover:bg-accent-500 flex items-center gap-1.5 rounded px-3 py-1.5 text-[12px] font-medium text-white outline-none disabled:pointer-events-none disabled:opacity-50"
            disabled={blockedReason !== null || isResolvingRecord}
            type="submit"
          >
            {isLoadingDetail || isResolvingRecord ? (
              <FiLoader className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            ) : (
              <LuPlus size={13} aria-hidden="true" />
            )}
            Create Run
          </button>
        </div>
      </div>
    </form>
  );
}
