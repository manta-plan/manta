import { Dialog } from "@base-ui/react/dialog";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useNodesState,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { FiLoader, FiPlay, FiX } from "react-icons/fi";
import "@xyflow/react/dist/style.css";
import { getPlaybook, listPlaybooks, validatePlaybookConfig } from "../../playbooks/api";
import type {
  PlaybookCanvasNode,
  PlaybookConfig,
  PlaybookDetail,
  PlaybookIssue,
  PlaybookSummary,
  RunPlaybookDialogProps,
} from "../../../utils/playbookTypes";
import { exampleDataRecords } from "../exampleDataRecords";
import { buildConfig } from "../../playbook-config/buildConfig";
import {
  deriveGlobalFields,
  getIn,
  isStepActive,
  setAtPath,
} from "../../playbook-config/conditions";
import { exactlyOneOf } from "../../playbook-config/exclusiveSettings";
import { validateStep } from "../../playbook-config/validation";
import { humanize } from "../../../utils/jsonSchema";
import { PlaybookConfigForm } from "./playbook-config-form";
import { SelectField } from "./select-field";

// How long an error message stays on screen.
const messageVisibilityMs = 10_000;

function capitalize(message: string): string {
  return message.charAt(0).toUpperCase() + message.slice(1);
}

// Wide enough that a node (about 13rem) never touches its neighbour.
const nodeSpacing = 300;
const nodeTypes = { playbook: PlaybookNodeComponent };

function layoutNodes(steps: PlaybookSummary["steps"]): PlaybookCanvasNode[] {
  // One node per step, in step order. The canvas shows the step's name; the block it
  // runs is kept as the node's `block` value. A node's id is the step's name, which is
  // what its settings are filed under (and is unique even if a block is used twice).
  return steps.map((step, index) => ({
    id: step.name,
    type: "playbook",
    position: { x: index * nodeSpacing, y: 40 },
    data: { label: step.name, block: step.block },
  }));
}

export function RunPlaybookDialog({
  error,
  open,
  isSubmitting,
  onOpenChange,
  onSubmit,
}: RunPlaybookDialogProps) {
  const [dataRecordName, setDataRecordName] = useState(exampleDataRecords[0].name);
  // null until the user picks one.
  const [playbook, setPlaybook] = useState<string | null>(null);
  const [availablePlaybooks, setAvailablePlaybooks] = useState<PlaybookSummary[]>([]);
  const [isLoadingPlaybooks, setIsLoadingPlaybooks] = useState(false);
  const [playbooksError, setPlaybooksError] = useState<string | null>(null);
  const [playbookDetail, setPlaybookDetail] = useState<PlaybookDetail | null>(null);
  const [isLoadingCanvas, setIsLoadingCanvas] = useState(false);
  const [canvasError, setCanvasError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  // The config the run will be created with: the playbook's defaults, as edited.
  const [configValues, setConfigValues] = useState<PlaybookConfig>({});
  const [validationError, setValidationError] = useState<string | null>(null);
  const [issues, setIssues] = useState<PlaybookIssue[]>([]);
  const [isValidating, setIsValidating] = useState(false);
  // Counts submissions; closing the dialog or changing the selection moves it on, so a
  // validation still pending for the earlier selection never creates a run.
  const submitAttempt = useRef(0);
  // The backend's `error` comes from the parent, so hiding it is tracked here.
  const [dismissedError, setDismissedError] = useState<string | null>(null);

  // Messages stay visible for a limited time, then hide.
  useEffect(() => {
    if (validationError === null) {
      return;
    }

    const timer = setTimeout(() => {
      setValidationError(null);
      setIssues([]);
    }, messageVisibilityMs);

    return () => clearTimeout(timer);
  }, [validationError]);

  useEffect(() => {
    if (!error) {
      return;
    }

    const timer = setTimeout(() => setDismissedError(error), messageVisibilityMs);

    return () => clearTimeout(timer);
  }, [error]);

  const selectedPlaybook = availablePlaybooks.find((item) => item.name === playbook) ?? null;

  // A step with a `when` only runs when that setting has the given value (e.g. only
  // the myopic expansion runs when globals.expansion_mode is "myopic").
  const inactiveSteps = useMemo(() => {
    const inactive = new Set<string>();

    for (const step of playbookDetail?.steps ?? []) {
      if (!isStepActive(step, configValues)) {
        inactive.add(step.name);
      }
    }

    return inactive;
  }, [playbookDetail, configValues]);

  // Only the steps that will run are drawn, in step order.
  const visibleSteps = useMemo(
    () => (selectedPlaybook?.steps ?? []).filter((step) => !inactiveSteps.has(step.name)),
    [selectedPlaybook, inactiveSteps],
  );
  const layoutKey = `${playbook ?? ""}:${visibleSteps.map((step) => step.name).join("|")}`;

  // Nodes are state, not derived, so React Flow can select and drag them. They are
  // laid out again whenever another playbook is picked or the visible steps change.
  const [nodes, setNodes, onNodesChange] = useNodesState<PlaybookCanvasNode>([]);
  const [laidOutKey, setLaidOutKey] = useState<string | null>(null);

  if (laidOutKey !== layoutKey) {
    setLaidOutKey(layoutKey);
    setNodes(layoutNodes(visibleSteps));
  }

  // Connected in step order.
  const edges = useMemo<Edge[]>(
    () =>
      visibleSteps.slice(1).map((step, index) => ({
        id: `${visibleSteps[index].name}->${step.name}`,
        source: visibleSteps[index].name,
        target: step.name,
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    [visibleSteps],
  );

  // `globals` has no schema; its settings are the ones the steps' `when`s test.
  const globalFields = useMemo(
    () => (playbookDetail === null ? [] : deriveGlobalFields(playbookDetail)),
    [playbookDetail],
  );

  // Ajv errors for the active steps, so a bad setting is flagged before Create.
  const stepErrors = useMemo(() => {
    const byStep = new Map<string, ReturnType<typeof validateStep>>();

    for (const step of playbookDetail?.steps ?? []) {
      if (!inactiveSteps.has(step.name)) {
        const found = validateStep(step, configValues[step.name] ?? {});

        if (found.length > 0) {
          byStep.set(step.name, found);
        }
      }
    }

    return byStep;
  }, [playbookDetail, configValues, inactiveSteps]);

  const selectedStep =
    playbookDetail?.steps.find(
      (step) => step.name === selectedNodeId && !inactiveSteps.has(step.name),
    ) ?? null;

  useEffect(() => {
    if (!open) {
      return;
    }

    setAvailablePlaybooks([]);
    setPlaybook(null);
    setPlaybooksError(null);
    setIsLoadingPlaybooks(true);

    let cancelled = false;

    listPlaybooks()
      .then((response) => {
        if (cancelled) {
          return;
        }

        setAvailablePlaybooks(response.items);
      })
      .catch((fetchError: unknown) => {
        if (!cancelled) {
          setPlaybooksError(
            fetchError instanceof Error ? fetchError.message : "Failed to load playbooks.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingPlaybooks(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    setSelectedNodeId(null);
    setPlaybookDetail(null);
    setConfigValues({});
    setCanvasError(null);
    setIssues([]);

    if (!open || playbook === null) {
      setIsLoadingCanvas(false);
      return;
    }

    setIsLoadingCanvas(true);

    let cancelled = false;

    getPlaybook(playbook)
      .then((detail) => {
        if (cancelled) {
          return;
        }

        setPlaybookDetail(detail);
        setConfigValues(structuredClone(detail.default_config));
      })
      .catch((fetchError: unknown) => {
        if (!cancelled) {
          setCanvasError(
            fetchError instanceof Error ? fetchError.message : "Failed to load playbook.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingCanvas(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [open, playbook]);

  useEffect(() => {
    submitAttempt.current += 1;
  }, [open, playbook, configValues, dataRecordName]);

  function handleOpenChange(nextOpen: boolean) {
    if (!isSubmitting) {
      onOpenChange(nextOpen);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (playbook === null || playbookDetail === null) {
      setValidationError("Select a playbook before creating a run.");
      return;
    }

    const dataRecord = exampleDataRecords.find((record) => record.name === dataRecordName);

    if (dataRecord === undefined) {
      setValidationError("Select a data record before creating a run.");
      return;
    }

    if (stepErrors.size > 0) {
      setValidationError("Resolve the highlighted settings before creating the run.");
      return;
    }

    setValidationError(null);
    setDismissedError(null);
    setIssues([]);
    setIsValidating(true);
    submitAttempt.current += 1;
    const attempt = submitAttempt.current;

    try {
      // The backend's own check, so every problem is shown here instead of the
      // run being refused afterwards.
      const result = await validatePlaybookConfig(
        playbook,
        buildConfig(playbookDetail, configValues),
      );

      if (attempt !== submitAttempt.current) {
        return;
      }

      if (!result.valid) {
        setIssues(result.issues);
        setValidationError(
          "This configuration cannot be run yet. Please resolve the following issues:",
        );
        return;
      }
    } catch (validateError) {
      if (attempt !== submitAttempt.current) {
        return;
      }

      setValidationError(
        validateError instanceof Error && validateError.message !== ""
          ? capitalize(validateError.message)
          : "Unable to validate the configuration. Please try again.",
      );
      return;
    } finally {
      setIsValidating(false);
    }

    await onSubmit(playbook, buildConfig(playbookDetail, configValues), dataRecord);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="bg-text/40 fixed inset-0 z-20 transition-opacity data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <Dialog.Viewport className="fixed inset-0 z-20 flex items-center justify-center p-4">
          <Dialog.Popup className="border-border bg-surface text-text max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-lg border p-6 shadow-2xl transition-[opacity,transform] duration-150 outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
            <div className="flex items-start justify-between gap-4">
              <div>
                <Dialog.Title className="text-xl font-semibold tracking-normal">
                  Create a new run
                </Dialog.Title>
                <Dialog.Description className="text-text-secondary mt-1 text-sm leading-6">
                  Configure the playbook run before sending it to the execution queue.
                </Dialog.Description>
              </div>
              <Dialog.Close
                aria-label="Close new run dialog"
                className="hover:bg-surface-alt focus-visible:outline-secondary text-text-secondary inline-flex size-8 shrink-0 items-center justify-center rounded-md transition focus-visible:outline-2 focus-visible:outline-offset-2"
              >
                <FiX className="size-4" aria-hidden="true" />
              </Dialog.Close>
            </div>

            <form className="mt-6 grid gap-5" onSubmit={handleSubmit}>
              <div className="grid gap-2">
                <label className="text-sm font-semibold" htmlFor="run-data-record">
                  Data record
                </label>
                <SelectField
                  id="run-data-record"
                  items={exampleDataRecords.map((record) => ({
                    label: record.name,
                    value: record.name,
                  }))}
                  onValueChange={setDataRecordName}
                  value={dataRecordName}
                />
              </div>

              <div className="grid gap-2">
                <label className="text-sm font-semibold" htmlFor="run-playbook">
                  Playbook
                </label>
                {isLoadingPlaybooks ? (
                  <div className="border-border bg-surface-alt text-text-secondary flex h-10 items-center rounded-md border px-3 text-sm">
                    Loading playbooks...
                  </div>
                ) : playbooksError ? (
                  <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                    {playbooksError}
                  </div>
                ) : (
                  <SelectField
                    id="run-playbook"
                    items={availablePlaybooks.map((item) => ({
                      label: item.name,
                      value: item.name,
                    }))}
                    onValueChange={(value) => {
                      setPlaybook(value);
                      setValidationError(null);
                    }}
                    placeholder="Select a playbook"
                    value={playbook}
                  />
                )}
              </div>

              {globalFields.map((field) => {
                const current = getIn(configValues, field.path.split("."));

                return (
                  <div className="grid gap-2" key={field.path}>
                    <label className="text-sm font-semibold" htmlFor={`global.${field.path}`}>
                      {humanize(field.path.split(".").pop() ?? "")}
                    </label>
                    <SelectField
                      id={`global.${field.path}`}
                      items={field.options.map((option) => ({
                        label: String(option),
                        value: String(option),
                      }))}
                      onValueChange={(next) =>
                        setConfigValues((previous) =>
                          setAtPath(
                            previous,
                            field.path,
                            field.options.find((option) => String(option) === next),
                          ),
                        )
                      }
                      placeholder="—"
                      value={current === undefined ? null : String(current)}
                    />
                  </div>
                );
              })}

              <div className="grid gap-2">
                <span className="text-sm font-semibold">Playbook canvas</span>
                <div
                  className="border-border bg-surface-alt relative h-64 overflow-hidden rounded-md border"
                  aria-label="Playbook canvas"
                >
                  {canvasError ? (
                    <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-red-700">
                      {canvasError}
                    </div>
                  ) : (
                    <>
                      {/* Keyed by playbook so the view fits the new nodes. */}
                      <ReactFlow
                        edges={edges}
                        fitView
                        fitViewOptions={{ padding: 0.2 }}
                        key={layoutKey}
                        nodeTypes={nodeTypes}
                        nodes={nodes}
                        nodesConnectable={false}
                        nodesDraggable
                        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                        onNodesChange={onNodesChange}
                        onPaneClick={() => setSelectedNodeId(null)}
                        zoomOnScroll={false}
                      >
                        <Background color="var(--color-border)" gap={18} size={1} />
                        <Controls showInteractive={false} />
                      </ReactFlow>
                      {isLoadingCanvas ? (
                        <div className="bg-surface/80 text-text-secondary absolute inset-0 z-10 flex items-center justify-center gap-2 text-sm">
                          <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
                          Loading playbook...
                        </div>
                      ) : null}
                      {!isLoadingCanvas && nodes.length === 0 ? (
                        <div className="text-text-secondary pointer-events-none absolute inset-0 flex items-center justify-center text-sm">
                          Select a playbook to load its canvas.
                        </div>
                      ) : null}
                    </>
                  )}
                </div>
              </div>

              {selectedStep !== null && selectedStep.block_config_schema !== null ? (
                <div className="border-border bg-surface-alt grid gap-4 rounded-md border p-4">
                  <div>
                    <h3 className="text-sm font-semibold">
                      {humanize(selectedStep.name)} configuration
                    </h3>
                    {selectedStep.block_summary ? (
                      <p className="text-text-secondary mt-1 text-xs">
                        {selectedStep.block_summary}
                      </p>
                    ) : null}
                  </div>
                  <PlaybookConfigForm
                    idPrefix={selectedStep.name}
                    // A fresh form per step, so inputs with local state don't carry over.
                    key={selectedStep.name}
                    onChange={(next) =>
                      setConfigValues((current) => ({ ...current, [selectedStep.name]: next }))
                    }
                    defaults={playbookDetail?.default_config[selectedStep.name]}
                    errors={stepErrors.get(selectedStep.name)}
                    exclusive={
                      selectedStep.block === null ? undefined : exactlyOneOf[selectedStep.block]
                    }
                    inputs={selectedStep.inputs}
                    schema={selectedStep.block_config_schema}
                    value={configValues[selectedStep.name] ?? {}}
                  />
                </div>
              ) : (
                <p className="text-text-secondary text-xs">
                  {selectedStep === null
                    ? "Click a block on the canvas to configure it. Drag blocks to rearrange them."
                    : "This step runs a nested playbook and has no settings of its own."}
                </p>
              )}

              {validationError ? (
                <div className="grid gap-2 text-sm text-red-700">
                  <p>{validationError}</p>
                  {issues.length > 0 ? (
                    <ul className="list-disc pl-5">
                      {issues.map((issue, index) => (
                        <li key={index}>
                          <span className="font-semibold">
                            {[...issue.step_path, ...(issue.config_path ?? [])].join(" › ") ||
                              "playbook"}
                          </span>
                          : {capitalize(issue.message)}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}

              {/* Next to the Create button, so a refused run is seen where it was sent. */}
              {error && error !== dismissedError ? (
                <div
                  className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
                  role="alert"
                >
                  {capitalize(error)}
                </div>
              ) : null}

              {stepErrors.size > 0 ? (
                <p className="text-sm text-red-700" role="alert">
                  Resolve the settings of {[...stepErrors.keys()].map(humanize).join(", ")} before
                  creating the run.
                </p>
              ) : null}

              <div className="border-border flex justify-end gap-3 border-t pt-5">
                <button
                  className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-text-secondary mr-auto inline-flex h-10 items-center rounded-md border px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={playbookDetail === null || isSubmitting}
                  onClick={() =>
                    playbookDetail !== null &&
                    setConfigValues(structuredClone(playbookDetail.default_config))
                  }
                  type="button"
                >
                  Use playbook defaults
                </button>
                <Dialog.Close
                  className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-10 items-center rounded-md border px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={isSubmitting}
                >
                  Cancel
                </Dialog.Close>
                <button
                  className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={
                    isSubmitting ||
                    isValidating ||
                    isLoadingPlaybooks ||
                    isLoadingCanvas ||
                    playbookDetail === null ||
                    stepErrors.size > 0
                  }
                  type="submit"
                >
                  {isSubmitting || isValidating ? (
                    <FiLoader className="h-4 w-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <FiPlay className="h-4 w-4" aria-hidden="true" />
                  )}
                  {isValidating ? "Checking..." : isSubmitting ? "Creating..." : "Create run"}
                </button>
              </div>
            </form>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// Clicking a node selects it (React Flow marks it `selected`), which is what the
// highlight shows; the handles are what draw the connecting edges.
function PlaybookNodeComponent({ data, selected }: NodeProps<PlaybookCanvasNode>) {
  return (
    <div
      className={`min-w-52 cursor-pointer rounded-md border-2 px-4 py-3 shadow-sm transition ${
        selected
          ? "border-primary bg-primary/10 ring-primary/30 ring-4"
          : "border-border bg-surface hover:border-primary"
      }`}
    >
      <Handle isConnectable={false} position={Position.Left} type="target" />
      <p className="text-sm font-semibold">{data.label}</p>
      <p className="text-text-secondary mt-1 text-xs">Click to configure</p>
      <Handle isConnectable={false} position={Position.Right} type="source" />
    </div>
  );
}
