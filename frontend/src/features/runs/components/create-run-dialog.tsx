import { Dialog } from "@base-ui/react/dialog";
import { Select } from "@base-ui/react/select";
import { Background, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useEffect, useState, type FormEvent } from "react";
import { FiCheck, FiChevronDown, FiPlay, FiX } from "react-icons/fi";
import "@xyflow/react/dist/style.css";
import { getPlaybook, listPlaybooks } from "../../playbooks/api";
import type { PlaybookDetail, PlaybookSummary } from "../../playbooks/types";

type CreateRunDialogProps = {
  error: string | null;
  open: boolean;
  isSubmitting: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (name: string, playbook: string, numPiDigits: number) => Promise<void>;
};

type PlaybookCanvasNode = Node<{ label: string }, "playbook">;

const emptyNodes: PlaybookCanvasNode[] = [];
const emptyEdges: Edge[] = [];
const nodeTypes = { playbook: PlaybookNodeComponent };

function playbookOptionLabel(playbook: PlaybookSummary): string {
  return playbook.status === "coming_soon" ? `${playbook.name} (coming soon)` : playbook.name;
}

export function CreateRunDialog({
  error,
  open,
  isSubmitting,
  onOpenChange,
  onSubmit,
}: CreateRunDialogProps) {
  const [name, setName] = useState("My First Run");
  const [playbook, setPlaybook] = useState("");
  const [availablePlaybooks, setAvailablePlaybooks] = useState<PlaybookSummary[]>([]);
  const [isLoadingPlaybooks, setIsLoadingPlaybooks] = useState(false);
  const [playbooksError, setPlaybooksError] = useState<string | null>(null);
  const [playbookDetail, setPlaybookDetail] = useState<PlaybookDetail | null>(null);
  const [isLoadingCanvas, setIsLoadingCanvas] = useState(false);
  const [canvasError, setCanvasError] = useState<string | null>(null);
  const [nodes, setNodes] = useState<PlaybookCanvasNode[]>(emptyNodes);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [numPiDigits, setNumPiDigits] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const selectedNode = playbookDetail?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const numPiDigitsField =
    selectedNode?.config.find((field) => field.key === "num_pi_digits") ?? null;

  useEffect(() => {
    if (!open) {
      return;
    }

    setAvailablePlaybooks([]);
    setPlaybook("");
    setPlaybooksError(null);
    setIsLoadingPlaybooks(true);

    let cancelled = false;

    listPlaybooks()
      .then((response) => {
        if (cancelled) {
          return;
        }

        setAvailablePlaybooks(response.items);
        const firstAvailable = response.items.find((item) => item.status === "available");
        setPlaybook(firstAvailable?.id ?? "");
      })
      .catch((fetchError) => {
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
    setNodes(emptyNodes);
    setSelectedNodeId(null);
    setPlaybookDetail(null);
    setCanvasError(null);

    if (!open || playbook.length === 0) {
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
        setNodes(
          detail.nodes.map((node, index) => ({
            id: node.id,
            type: "playbook",
            position: { x: 130 + index * 220, y: 80 },
            data: { label: node.label },
          })),
        );
      })
      .catch((fetchError) => {
        if (!cancelled) {
          setCanvasError(
            fetchError instanceof Error ? fetchError.message : "Failed to load playbook canvas.",
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
    setNumPiDigits(numPiDigitsField?.default != null ? String(numPiDigitsField.default) : "");
  }, [selectedNodeId, numPiDigitsField?.default]);

  function handleOpenChange(nextOpen: boolean) {
    if (!isSubmitting) {
      onOpenChange(nextOpen);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (
      name.trim().length === 0 ||
      playbook.length === 0 ||
      selectedNodeId === null ||
      numPiDigitsField === null
    ) {
      setValidationError("Select a playbook and configure its required node.");
      return;
    }

    const parsedNumPiDigits = Number(numPiDigits);
    const minValue = numPiDigitsField.min ?? 1;

    if (!Number.isInteger(parsedNumPiDigits) || parsedNumPiDigits < minValue) {
      setValidationError(
        `Enter a whole number of at least ${minValue} for ${numPiDigitsField.label}.`,
      );
      return;
    }

    setValidationError(null);
    await onSubmit(name.trim(), playbook, parsedNumPiDigits);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="bg-text/40 fixed inset-0 z-20 transition-opacity data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <Dialog.Viewport className="fixed inset-0 z-20 flex items-center justify-center p-4">
          <Dialog.Popup className="border-border bg-surface text-text w-full max-w-lg rounded-lg border p-6 shadow-2xl transition-[opacity,transform] duration-150 outline-none data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
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
                      label: playbookOptionLabel(item),
                      value: item.id,
                      disabled: item.status !== "available",
                    }))}
                    onValueChange={(value) => {
                      if (value !== null) {
                        setPlaybook(value);
                        setValidationError(null);
                      }
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
                                className="data-highlighted:bg-surface-alt grid cursor-default grid-cols-[1rem_1fr] items-center gap-2 px-3 py-2 text-sm outline-none data-disabled:cursor-not-allowed data-disabled:opacity-50"
                                disabled={option.status !== "available"}
                                key={option.id}
                                value={option.id}
                              >
                                <Select.ItemIndicator className="text-primary">
                                  <FiCheck className="size-4" aria-hidden="true" />
                                </Select.ItemIndicator>
                                <Select.ItemText className="col-start-2">
                                  {playbookOptionLabel(option)}
                                </Select.ItemText>
                              </Select.Item>
                            ))}
                          </Select.List>
                        </Select.Popup>
                      </Select.Positioner>
                    </Select.Portal>
                  </Select.Root>
                )}
                <p className="text-text-secondary text-xs">
                  Additional playbooks will become available in a future iteration.
                </p>
              </div>

              <div className="grid gap-2">
                <span className="text-sm font-semibold">Playbook canvas</span>
                <div
                  className="border-border bg-surface-alt relative h-56 overflow-hidden rounded-md border"
                  aria-label="Playbook canvas"
                >
                  {canvasError ? (
                    <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-sm text-red-700">
                      {canvasError}
                    </div>
                  ) : (
                    <>
                      <ReactFlow
                        edges={emptyEdges}
                        fitView={false}
                        nodeTypes={nodeTypes}
                        nodes={nodes}
                        onNodeClick={(_, node) => setSelectedNodeId(node.id)}
                        zoomOnScroll={false}
                      >
                        <Background color="var(--color-border)" gap={18} size={1} />
                      </ReactFlow>
                      {isLoadingCanvas ? (
                        <div className="bg-surface/80 text-text-secondary absolute inset-0 z-10 flex items-center justify-center gap-2 text-sm">
                          <FiPlay className="size-4 animate-pulse" aria-hidden="true" />
                          Loading playbook canvas...
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

              {selectedNode !== null ? (
                <div className="border-border bg-surface-alt grid gap-4 rounded-md border p-4">
                  <div>
                    <h3 className="text-sm font-semibold">{selectedNode.label} configuration</h3>
                    <p className="text-text-secondary mt-1 text-xs">
                      This node is configurable and requires a value before the run can be created.
                    </p>
                  </div>
                  {numPiDigitsField ? (
                    <div className="grid gap-2">
                      <label className="text-sm font-semibold" htmlFor="num-pi-digits">
                        {numPiDigitsField.label}
                      </label>
                      <input
                        className="border-border bg-surface text-text focus:border-primary focus:ring-primary/20 h-10 rounded-md border px-3 text-sm transition outline-none focus:ring-2"
                        id="num-pi-digits"
                        min={numPiDigitsField.min ?? undefined}
                        onChange={(event) => {
                          setNumPiDigits(event.target.value);
                          setValidationError(null);
                        }}
                        required={numPiDigitsField.required}
                        type="number"
                        value={numPiDigits}
                      />
                    </div>
                  ) : null}
                </div>
              ) : null}

              {validationError ? <p className="text-sm text-red-700">{validationError}</p> : null}

              <div className="border-border flex justify-end gap-3 border-t pt-5">
                <Dialog.Close
                  className="border-border bg-surface hover:bg-surface-alt focus-visible:outline-secondary text-primary inline-flex h-10 items-center rounded-md border px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={isSubmitting}
                >
                  Cancel
                </Dialog.Close>
                <button
                  className="bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active focus-visible:outline-secondary inline-flex h-10 items-center gap-2 rounded-md px-4 text-sm font-semibold transition focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-70"
                  disabled={
                    isSubmitting || isLoadingPlaybooks || isLoadingCanvas || selectedNodeId === null
                  }
                  type="submit"
                >
                  <FiPlay
                    className={`size-4 ${isSubmitting ? "animate-pulse" : ""}`}
                    aria-hidden="true"
                  />
                  {isSubmitting ? "Creating..." : "Create run"}
                </button>
              </div>
            </form>
          </Dialog.Popup>
        </Dialog.Viewport>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PlaybookNodeComponent({ data, selected }: NodeProps<PlaybookCanvasNode>) {
  return (
    <div
      className={`border-primary bg-surface min-w-48 rounded-md border-2 px-4 py-3 shadow-sm ${
        selected ? "ring-primary/30 ring-4" : ""
      }`}
    >
      <p className="text-sm font-semibold">{data.label}</p>
      <p className="text-text-secondary mt-1 text-xs">Configurable · Required configuration</p>
    </div>
  );
}
