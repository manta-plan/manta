import { Dialog } from "@base-ui/react/dialog";
import { Select } from "@base-ui/react/select";
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
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { FiCheck, FiChevronDown, FiLoader, FiPlay, FiX } from "react-icons/fi";
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

// Wide enough that a node (about 13rem) never touches its neighbour.
const nodeSpacing = 300;
const nodeTypes = { playbook: PlaybookNodeComponent };

function layoutNodes(playbook: PlaybookSummary | null): PlaybookCanvasNode[] {
  // One node per step, in step order. The canvas shows the step's name; the block it
  // runs is kept as the node's `block` value. A node's id is the step's name, which is
  // what its settings are filed under (and is unique even if a block is used twice).
  return (playbook?.steps ?? []).map((step, index) => ({
    id: step.name,
    type: "playbook",
    position: { x: index * nodeSpacing, y: 40 },
    data: { label: step.name, block: step.block, inactive: false },
  }));
}

export function RunPlaybookDialog({
  error,
  open,
  isSubmitting,
  onOpenChange,
  onSubmit,
}: RunPlaybookDialogProps) {
  const [name, setName] = useState("My First Run");
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

  const selectedPlaybook = availablePlaybooks.find((item) => item.name === playbook) ?? null;

  // Nodes are state, not derived, so React Flow can select and drag them. They are
  // laid out again whenever another playbook is picked.
  const [nodes, setNodes, onNodesChange] = useNodesState<PlaybookCanvasNode>([]);
  const [laidOutPlaybook, setLaidOutPlaybook] = useState<PlaybookSummary | null>(null);

  if (laidOutPlaybook !== selectedPlaybook) {
    setLaidOutPlaybook(selectedPlaybook);
    setNodes(layoutNodes(selectedPlaybook));
  }

  // Connected in step order.
  const edges = useMemo<Edge[]>(
    () =>
      (selectedPlaybook?.steps ?? []).slice(1).map((step, index) => ({
        id: `${selectedPlaybook?.steps[index].name}->${step.name}`,
        source: selectedPlaybook?.steps[index].name ?? "",
        target: step.name,
        markerEnd: { type: MarkerType.ArrowClosed },
      })),
    [selectedPlaybook],
  );

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

  useEffect(() => {
    setNodes((current) =>
      current.map((node) =>
        node.data.inactive === inactiveSteps.has(node.id)
          ? node
          : { ...node, data: { ...node.data, inactive: inactiveSteps.has(node.id) } },
      ),
    );
  }, [inactiveSteps, setNodes]);

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

  const selectedStep = playbookDetail?.steps.find((step) => step.name === selectedNodeId) ?? null;

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

  function handleOpenChange(nextOpen: boolean) {
    if (!isSubmitting) {
      onOpenChange(nextOpen);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (name.trim().length === 0 || playbook === null || playbookDetail === null) {
      setValidationError("Select a playbook before creating a run.");
      return;
    }

    if (stepErrors.size > 0) {
      setValidationError("Fix the highlighted settings first.");
      return;
    }

    setValidationError(null);
    setIssues([]);
    setIsValidating(true);

    try {
      // The backend's own check, so every problem is shown here instead of the
      // run being refused afterwards.
      const result = await validatePlaybookConfig(
        playbook,
        buildConfig(playbookDetail, configValues),
      );

      if (!result.valid) {
        setIssues(result.issues);
        setValidationError("This configuration can't run yet. Fix the following:");
        return;
      }
    } catch (validateError) {
      setValidationError(
        validateError instanceof Error ? validateError.message : "Failed to validate the config.",
      );
      return;
    } finally {
      setIsValidating(false);
    }

    await onSubmit(name.trim(), playbook, buildConfig(playbookDetail, configValues));
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
              {error ? (
                <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                  {error}
                </div>
              ) : null}
              <div className="grid gap-2">
                <label className="text-sm font-semibold" htmlFor="run-name">
                  Name
                </label>
                <input
                  className="border-border bg-surface text-text focus:border-primary focus:ring-primary/20 h-10 rounded-md border px-3 text-sm transition outline-none focus:ring-2"
                  id="run-name"
                  onChange={(event) => setName(event.target.value)}
                  required
                  value={name}
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
                  <Select.Root
                    items={availablePlaybooks.map((item) => ({
                      label: item.name,
                      value: item.name,
                    }))}
                    onValueChange={(value) => {
                      setPlaybook(value);
                      setValidationError(null);
                    }}
                    value={playbook}
                  >
                    <Select.Trigger
                      aria-label="Playbook"
                      className="border-border bg-surface text-text focus-visible:outline-secondary inline-flex h-10 w-full items-center justify-between gap-2 rounded-md border px-3 text-sm transition focus-visible:outline-2 focus-visible:outline-offset-2"
                      id="run-playbook"
                    >
                      <Select.Value placeholder="Select a playbook" />
                      <Select.Icon>
                        <FiChevronDown className="size-4" aria-hidden="true" />
                      </Select.Icon>
                    </Select.Trigger>
                    <Select.Portal>
                      <Select.Positioner
                        alignItemWithTrigger={false}
                        className="z-30 outline-none"
                        sideOffset={6}
                      >
                        <Select.Popup className="border-border bg-surface text-text min-w-[var(--anchor-width)] rounded-md border py-1 shadow-xl outline-none">
                          <Select.List>
                            {availablePlaybooks.map((option) => (
                              <Select.Item
                                className="data-highlighted:bg-surface-alt grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 px-3 py-2 text-sm outline-none"
                                key={option.name}
                                value={option.name}
                              >
                                <Select.ItemIndicator className="text-primary">
                                  <FiCheck className="size-4" aria-hidden="true" />
                                </Select.ItemIndicator>
                                <Select.ItemText className="col-start-2">
                                  {option.name}
                                </Select.ItemText>
                              </Select.Item>
                            ))}
                          </Select.List>
                        </Select.Popup>
                      </Select.Positioner>
                    </Select.Portal>
                  </Select.Root>
                )}
              </div>

              {globalFields.map((field) => {
                const current = getIn(configValues, field.path.split("."));

                return (
                  <div className="grid gap-2" key={field.path}>
                    <label className="text-sm font-semibold" htmlFor={`global.${field.path}`}>
                      {humanize(field.path.split(".").pop() ?? "")}
                    </label>
                    <select
                      className="border-border bg-surface text-text focus:border-primary focus:ring-primary/20 h-10 rounded-md border px-3 text-sm transition outline-none focus:ring-2"
                      id={`global.${field.path}`}
                      onChange={(event) =>
                        setConfigValues((previous) =>
                          setAtPath(
                            previous,
                            field.path,
                            field.options.find((option) => String(option) === event.target.value),
                          ),
                        )
                      }
                      value={current === undefined ? "" : String(current)}
                    >
                      {current === undefined ? <option value="">—</option> : null}
                      {field.options.map((option) => (
                        <option key={String(option)} value={String(option)}>
                          {String(option)}
                        </option>
                      ))}
                    </select>
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
                        key={playbook ?? "none"}
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
                    {inactiveSteps.has(selectedStep.name) && selectedStep.when !== null ? (
                      <p className="mt-1 text-xs text-amber-700">
                        Skipped unless expansion mode is{" "}
                        <span className="font-semibold">{String(selectedStep.when.equals)}.</span>
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
                          : {issue.message}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
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
      } ${data.inactive ? "opacity-50" : ""}`}
    >
      <Handle isConnectable={false} position={Position.Left} type="target" />
      <p className="text-sm font-semibold">{data.label}</p>
      <p className="text-text-secondary mt-1 text-xs">
        {data.inactive ? "Skipped in current mode · click to configure" : "Click to configure"}
      </p>
      <Handle isConnectable={false} position={Position.Right} type="source" />
    </div>
  );
}
