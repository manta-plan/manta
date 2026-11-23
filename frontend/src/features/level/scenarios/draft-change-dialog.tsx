import { Segmented } from "../../../components/segmented";
import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import {
  applyChanges,
  describeOp,
  draftScenarioOptions,
  isChangeable,
  loadCtypeAttributes,
  numericValue,
  type DraftChangeOp,
  type DraftChangeTarget,
} from "../../project/lib/draft-scenarios";
import { useInputData, useShownData } from "../../project/lib/record-data";
import { getEntity } from "../../project/lib/record-server/queries";
import { useOpenRecordPageId } from "../../project/lib/use-record-page";
import { useShownDraft } from "../../project/lib/use-shown-draft";
import { useProjectStore } from "../../project/store/project-store";
import { levelOfPageId } from "../level";
import { usePeriods } from "../periods";
import { loadMatches } from "./change-sql";
import { opWords, plural } from "./change-wording";
import { ChangeDialogShell } from "./change-dialog-shell";
import { DEFAULT_CTYPE, levelFilterTarget } from "./level-target";
import { FormSelect } from "../../home/components/form-select";
import { Field, INPUT_CLASS, PRIMARY_BUTTON_CLASS, SECONDARY_BUTTON_CLASS } from "./dialog-parts";

// One change of a draft scenario: an attribute, for one entity or every
// entity of a type (narrowed by carrier and location), set to a value or
// multiplied or added to. Opened from the Scenarios panel and a level page's
// "Change…", prefilled with what it was opened on (else the open level).
// Matches are the entities active in the period shown, as on the pages.

const NEW_DRAFT = "__new__";
const ANY = "__any__";

const OPS: { value: DraftChangeOp; label: string; hint: string }[] = [
  { value: "set", label: "Set", hint: "Replaces the value. A time series becomes this constant." },
  {
    value: "multiply",
    label: "Multiply",
    hint: "1.3 is +30%. A time series is scaled value by value.",
  },
  {
    value: "add",
    label: "Add",
    hint: "Adds to the value, negative to subtract. A time series value by value.",
  },
];

export function DraftChangeDialog() {
  const seed = useProjectStore((s) => s.changeDialog);
  const close = useProjectStore((s) => s.closeChangeDialog);
  const record = useProjectStore((s) => s.record);
  const drafts = useProjectStore((s) => s.draftScenarios);
  const createDraft = useProjectStore((s) => s.createDraft);
  const saveDraftChange = useProjectStore((s) => s.saveDraftChange);
  const removeDraftChange = useProjectStore((s) => s.removeDraftChange);
  const showDraft = useProjectStore((s) => s.showDraft);
  const shownDraft = useShownDraft();
  const openPageId = useOpenRecordPageId();
  const { period } = usePeriods();

  const [draftId, setDraftId] = useState(NEW_DRAFT);
  const [newName, setNewName] = useState("");
  const [mode, setMode] = useState<"entity" | "filter">("filter");
  const [ctype, setCtype] = useState("");
  const [carrier, setCarrier] = useState(ANY);
  const [location, setLocation] = useState(ANY);
  const [attribute, setAttribute] = useState("");
  const [op, setOp] = useState<DraftChangeOp>("multiply");
  const [value, setValue] = useState("");

  const recordId = record?.info.id ?? "";
  // The drafts it can go to: those of the scenario shown (and the one it's in, when editing).
  const scenarioField = useMemo(
    () =>
      draftScenarioOptions(drafts, {
        recordId,
        revisions: record?.info.revisions ?? [],
        shown: record?.scenario ?? null,
        keepId: seed?.draftId,
        newValue: NEW_DRAFT,
      }),
    [drafts, record, recordId, seed],
  );
  const draftOptions = scenarioField.usable;
  const seedEntity =
    seed?.change?.target.kind === "entity"
      ? seed.change.target
      : seed?.target?.kind === "entity"
        ? seed.target
        : null;
  const ctypes = useMemo(
    () => [...new Set(record?.entityCounts.map((count) => count.ctype) ?? [])].sort(),
    [record],
  );

  // Seeds once per open: from the change or target it's opened with, else the open level.
  useEffect(() => {
    if (!seed) return;
    const level = levelOfPageId(openPageId);
    const target = seed.change?.target ?? seed.target ?? (level ? levelFilterTarget(level) : null);
    const fallbackCtype = ctypes.includes(DEFAULT_CTYPE) ? DEFAULT_CTYPE : (ctypes[0] ?? "");
    setDraftId(seed.draftId ?? shownDraft?.id ?? draftOptions[0]?.id ?? NEW_DRAFT);
    setNewName("");
    setMode(target?.kind ?? "filter");
    setCtype(target && ctypes.includes(target.ctype) ? target.ctype : fallbackCtype);
    setCarrier(target?.carrier ?? ANY);
    setLocation(target?.location ?? ANY);
    setAttribute(seed.change?.attribute ?? seed.attribute ?? "");
    setOp(seed.change?.op ?? (seed.attribute ? "set" : "multiply"));
    setValue(seed.change ? String(seed.change.value) : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  const carriers = useMemo(
    () =>
      (record?.entityCounts ?? []).filter(
        (count) => count.ctype === ctype && count.carrier !== null,
      ),
    [record, ctype],
  );
  // "<id> · <region>": the region is the location's first zone, where the record has zones.
  const locations = useMemo(() => {
    const regionOf = new Map<string, string>();
    for (const zone of record?.zones ?? [])
      if (!regionOf.has(zone.location)) regionOf.set(zone.location, zone.zone);
    return (record?.locations ?? [])
      .map((item) => item.location)
      .sort()
      .map((name) => ({
        value: name,
        label: regionOf.has(name) ? `${name} · ${regionOf.get(name)}` : name,
      }));
  }, [record]);
  const carrierLabel = (name: string) => record?.carriers[name]?.niceName || name;

  const filter: Extract<DraftChangeTarget, { kind: "filter" }> | null = ctype
    ? {
        kind: "filter",
        ctype,
        carrier: carrier === ANY ? null : carrier,
        location: location === ANY ? null : location,
      }
    : null;
  const target: DraftChangeTarget | null = mode === "entity" && seedEntity ? seedEntity : filter;
  const isFilter = target?.kind === "filter";

  // The filter's matches in the period shown, and the numeric or series attributes they store.
  const matches = useShownData(
    "change-matches",
    seed && isFilter && filter && period
      ? [filter.ctype, filter.carrier, filter.location, period]
      : null,
    () => loadMatches(filter!, period!),
  );
  const matchData = matches.status === "ready" ? matches.data : null;

  // One entity: the attributes its type stores, and its value before and after.
  const resultNames = useMemo(
    () => new Set(record?.info.revisions.flatMap((revision) => revision.results) ?? []),
    [record],
  );
  const ctypeStored = useInputData(
    "ctype-attributes",
    record && seed && !isFilter && target
      ? `${recordId}\n${record.scenario ?? ""}\n${target.ctype}`
      : null,
    () => loadCtypeAttributes(target!.ctype),
  );
  const detail = useInputData(
    "entity-detail",
    record && seed && !isFilter && seedEntity
      ? `${recordId}\n${record.scenario ?? ""}\n${seedEntity.entity}`
      : null,
    () => getEntity(seedEntity!.entity, record!.info.manifest),
  );

  const attributes = useMemo(() => {
    const manifest = record?.info.manifest.attributes ?? {};
    const names = new Set(
      isFilter
        ? (matchData?.attributes.map((item) => item.attribute) ?? [])
        : ctypeStored.status === "ready"
          ? ctypeStored.data
          : [],
    );
    if (attribute) names.add(attribute);
    return [...names]
      .filter((name) => !resultNames.has(name) && isChangeable(manifest[name]))
      .sort();
  }, [attribute, ctypeStored, isFilter, matchData, record, resultNames]);
  const spec = attribute ? record?.info.manifest.attributes[attribute] : undefined;
  const unit = spec?.unit ?? undefined;
  const current =
    detail.status === "ready"
      ? detail.data?.attributes.find((item) => item.name === attribute && item.bus === null)
      : undefined;
  const number = value.trim() === "" ? NaN : Number(value);
  const valid = Number.isFinite(number);

  const preview = (() => {
    if (!attribute || !valid) return "Choose an attribute and enter a value to see what changes.";
    if (isFilter) {
      if (!matchData) return "Counting the matching entities…";
      const series =
        matchData.attributes.find((item) => item.attribute === attribute)?.withSeries ?? 0;
      const seriesNote =
        series > 0
          ? ` (${series.toLocaleString()} with a time series, ${op === "set" ? "replaced by a constant" : "changed value by value"})`
          : "";
      return `${attribute}: ${opWords(op, number, unit)} for ${plural(matchData.matching, "entity", "entities")}${seriesNote}, counted in ${period}.`;
    }
    const change = describeOp(op, number, unit);
    if (detail.status === "loading") return `${attribute}: ${change}`;
    if (current && current.seriesRows > 0)
      return `${attribute}: ${op === "set" ? `${change}, replacing its time series (${current.seriesRows.toLocaleString()} values)` : `${change}, each of its ${current.seriesRows.toLocaleString()} values over time`}`;
    const before = numericValue(current);
    const after = applyChanges(before, [{ op, value: number }]);
    const show = (n: number | null) =>
      n === null
        ? "—"
        : `${n.toLocaleString(undefined, { maximumFractionDigits: 4 })}${unit ? ` ${unit}` : ""}`;
    return `${attribute}: ${show(before)}${current?.isDefault ? " (default)" : ""} → ${show(after)}`;
  })();

  const isEditing = Boolean(seed?.change);
  const canSave = Boolean(
    record && target && attribute && valid && (draftId !== NEW_DRAFT || newName.trim()),
  );

  const save = () => {
    if (!canSave || !record || !target) return;
    const id =
      draftId === NEW_DRAFT
        ? createDraft({ recordId, parent: record.scenario ?? "", name: newName, description: "" })
            .id
        : draftId;
    saveDraftChange(id, {
      id: seed?.change?.id,
      kind: "attribute",
      attribute,
      target,
      op,
      value: number,
    });
    showDraft(id);
    close();
  };

  return (
    <ChangeDialogShell
      open={seed !== null}
      onClose={close}
      title={isEditing ? "Edit change" : "Add a change"}
      description="The change is added to a draft scenario, kept in this browser until scenarios can be saved to the record."
      footer={
        <>
          {isEditing && seed?.draftId && seed.change && (
            <button
              type="button"
              onClick={() => {
                removeDraftChange(seed.draftId!, seed.change!.id);
                close();
              }}
              className="text-danger-400 hover:bg-danger-500/10 h-8 rounded px-3 text-[12px] font-medium outline-none"
            >
              Remove
            </button>
          )}
          <button type="button" onClick={close} className={`${SECONDARY_BUTTON_CLASS} ml-auto`}>
            Cancel
          </button>
          <button type="button" onClick={save} disabled={!canSave} className={PRIMARY_BUTTON_CLASS}>
            {isEditing ? "Save" : "Add change"}
          </button>
        </>
      }
    >
      {!isEditing && (
        <Field label="Scenario" hint={scenarioField.hint}>
          <FormSelect
            value={draftId}
            onValueChange={setDraftId}
            ariaLabel="Scenario"
            options={scenarioField.options}
          />
        </Field>
      )}
      {!isEditing && draftId === NEW_DRAFT && (
        <Field label="New scenario's name">
          <input
            value={newName}
            onChange={(event) => setNewName(event.target.value)}
            placeholder="e.g. Offshore wind cost +30%"
            className={INPUT_CLASS}
          />
        </Field>
      )}

      <Field
        label="Applies to"
        hint={
          isFilter
            ? matchData
              ? `${plural(matchData.matching, "matching entity", "matching entities")}${period ? ` in ${period}` : ""}`
              : matches.status === "error"
                ? "Couldn't count the matching entities."
                : "Counting…"
            : undefined
        }
      >
        {seedEntity && (
          <Segmented
            equal
            ariaLabel="Applies to"
            value={mode}
            onChange={setMode}
            options={[
              { value: "entity", label: "This entity" },
              { value: "filter", label: "Matching entities" },
            ]}
          />
        )}
        {mode === "entity" && seedEntity ? (
          <div
            className="border-surface-700 bg-surface-900/60 text-surface-100 truncate rounded border px-2 py-1.5 text-[12px]"
            title={seedEntity.entity}
          >
            {seedEntity.entity}
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-1.5">
            <FormSelect
              value={ctype}
              onValueChange={(next) => {
                setCtype(next);
                setCarrier(ANY);
              }}
              ariaLabel="Component type"
              options={ctypes.map((name) => ({ value: name, label: name }))}
            />
            <FormSelect
              value={carrier}
              onValueChange={setCarrier}
              ariaLabel="Carrier"
              options={[
                { value: ANY, label: "Any carrier" },
                ...carriers.map((count) => ({
                  value: count.carrier!,
                  label: carrierLabel(count.carrier!),
                })),
              ]}
            />
            <FormSelect
              value={location}
              onValueChange={setLocation}
              ariaLabel="Location"
              options={[{ value: ANY, label: "Anywhere" }, ...locations]}
            />
          </div>
        )}
      </Field>

      <Field
        label="Attribute"
        hint={
          spec
            ? `${spec.description}${unit ? ` (${unit})` : ""}`
            : (isFilter ? matches.status === "loading" : ctypeStored.status === "loading")
              ? "Loading the attributes…"
              : isFilter && matchData && attributes.length === 0
                ? "The matching entities store no numeric attribute."
                : undefined
        }
      >
        <FormSelect
          value={attribute || null}
          onValueChange={setAttribute}
          placeholder="Choose an attribute"
          ariaLabel="Attribute"
          options={attributes.map((name) => ({ value: name, label: name }))}
        />
      </Field>

      <Field label="Change" hint={OPS.find((item) => item.value === op)?.hint}>
        <div className="flex gap-1.5">
          <Segmented
            ariaLabel="Operation"
            value={op}
            onChange={setOp}
            options={OPS.map((item) => ({ value: item.value, label: item.label }))}
            className="shrink-0"
          />
          <input
            value={value}
            onChange={(event) => setValue(event.target.value)}
            inputMode="decimal"
            placeholder={op === "multiply" ? "1.3" : "0"}
            aria-label="Value"
            className={clsx(INPUT_CLASS, value.trim() !== "" && !valid && "border-danger-500")}
          />
          {op !== "multiply" && unit && (
            <span className="text-surface-400 self-center text-[12px] whitespace-nowrap">
              {unit}
            </span>
          )}
        </div>
      </Field>

      <div
        aria-live="polite"
        className="border-surface-700 bg-surface-900/60 text-surface-200 rounded border px-3 py-2 text-[12px]"
      >
        {preview}
      </div>
    </ChangeDialogShell>
  );
}
