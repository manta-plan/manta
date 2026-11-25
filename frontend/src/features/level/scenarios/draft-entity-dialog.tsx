// SPDX-FileCopyrightText: 2026 Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { LuPlus, LuX } from "react-icons/lu";
import {
  describeNewEntity,
  draftScenarioOptions,
  entityExists,
  isChangeable,
  loadBuses,
  loadCtypeAttributes,
  loadCtypeConnections,
} from "../../project/lib/draft-scenarios";
import { useInputData } from "../../project/lib/record-data";
import { useShownDraft } from "../../project/lib/use-shown-draft";
import { useProjectStore } from "../../project/store/project-store";
import { FormSelect } from "../../../components/form-select";
import {
  DialogShell,
  Field,
  INPUT_CLASS,
  PRIMARY_BUTTON_CLASS,
  SECONDARY_BUTTON_CLASS,
} from "./dialog-parts";

// A new entity in a draft scenario: its ctype and carrier, a bus for each of
// the connections that ctype's entities have (chosen by location, then bus),
// and the values it's given; the rest take the manifest's defaults. Opened
// from a draft's row in the Scenarios panel and from a type's page.

const NEW_DRAFT = "__new__";
const NO_CARRIER = "__none__";
// The size attribute a new entity is most likely given first, by what its ctype stores.
const SIZES = ["p_nom", "s_nom", "e_nom"];
// datarecord's connection roles: a bus an entity is attached to, or a branch's ends.
const ROLE_LABELS: Record<string, string> = {
  attached: "Connects at",
  input: "From (input)",
  output: "To (output)",
};

type ValueRow = { attribute: string; value: string };

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export function DraftEntityDialog() {
  const seed = useProjectStore((s) => s.entityDialog);
  const close = useProjectStore((s) => s.closeEntityDialog);
  const record = useProjectStore((s) => s.record);
  const drafts = useProjectStore((s) => s.draftScenarios);
  const createDraft = useProjectStore((s) => s.createDraft);
  const saveDraftChange = useProjectStore((s) => s.saveDraftChange);
  const removeDraftChange = useProjectStore((s) => s.removeDraftChange);
  const showDraft = useProjectStore((s) => s.showDraft);
  const shownDraft = useShownDraft();

  const [draftId, setDraftId] = useState(NEW_DRAFT);
  const [newName, setNewName] = useState("");
  const [ctype, setCtype] = useState("");
  const [carrier, setCarrier] = useState(NO_CARRIER);
  const [name, setName] = useState("");
  const [isNameTouched, setIsNameTouched] = useState(false);
  const [buses, setBuses] = useState<Record<string, string>>({});
  const [pickedLocations, setPickedLocations] = useState<Record<string, string>>({});
  const [rows, setRows] = useState<ValueRow[]>([]);

  const recordId = record?.info.id ?? "";
  const scenarioKey = record ? `${recordId}\n${record.scenario ?? ""}` : null;
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

  // Seeds once per open.
  useEffect(() => {
    if (!seed) return;
    const change = seed.change;
    setDraftId(seed.draftId ?? shownDraft?.id ?? draftOptions[0]?.id ?? NEW_DRAFT);
    setNewName("");
    setCtype(
      change?.ctype ??
        seed.ctype ??
        record?.entityCounts.find((count) => count.ctype === "Generator")?.ctype ??
        record?.entityCounts[0]?.ctype ??
        "",
    );
    setCarrier((change ? change.carrier : seed.carrier) ?? NO_CARRIER);
    setName(change?.entity ?? "");
    setIsNameTouched(Boolean(change));
    setBuses(change?.buses ?? {});
    setPickedLocations({});
    setRows(
      change
        ? Object.entries(change.values).map(([attribute, value]) => ({
            attribute,
            value: String(value),
          }))
        : [],
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed]);

  const ctypes = useMemo(
    () => [...new Set(record?.entityCounts.map((count) => count.ctype) ?? [])].sort(),
    [record],
  );
  const carriers = useMemo(
    () =>
      (record?.entityCounts ?? [])
        .filter((count) => count.ctype === ctype && count.carrier !== null)
        .map((count) => count.carrier!),
    [record, ctype],
  );
  const carrierLabel = (value: string) => record?.carriers[value]?.niceName || value;
  const shownCarrier = carrier === NO_CARRIER ? null : carrier;

  // How this ctype's entities connect, and every bus to pick from.
  const connections = useInputData(
    "ctype-connections",
    scenarioKey && ctype ? `${scenarioKey}\n${ctype}\n${shownCarrier ?? ""}` : null,
    () => loadCtypeConnections(ctype, shownCarrier),
  );
  const busList = useInputData("buses", scenarioKey, loadBuses);
  const roles = connections.status === "ready" ? connections.data : [];
  // Every bus's location, virtual ones too (an EU-wide CO₂ store's, say).
  const locations = useMemo(
    () =>
      (busList.status === "ready"
        ? [...new Set(busList.data.map((item) => item.location))]
        : (record?.locations ?? []).map((item) => item.location)
      ).sort(),
    [busList, record],
  );
  const busInfo = useMemo(
    () => new Map((busList.status === "ready" ? busList.data : []).map((item) => [item.bus, item])),
    [busList],
  );
  const locationOf = (role: string) =>
    pickedLocations[role] ?? busInfo.get(buses[role] ?? "")?.location ?? seed?.location ?? "";
  const busesAt = (location: string) =>
    busList.status === "ready" ? busList.data.filter((item) => item.location === location) : [];
  // The bus at a location that entities like this one connect to there: the carrier they use most.
  const preferredBus = (location: string, role: string) => {
    const here = busesAt(location);
    const preferred = roles.find((item) => item.role === role)?.busCarriers ?? [];
    for (const busCarrier of preferred) {
      const match = here.find((item) => item.carrier === busCarrier);
      if (match) return match.bus;
    }
    return here.length === 1 ? here[0].bus : "";
  };

  // Fills each connection without a bus with the preferred one where it is.
  useEffect(() => {
    if (roles.length === 0 || busList.status !== "ready") return;
    setBuses((current) => {
      let next = current;
      for (const { role } of roles) {
        if (current[role]) continue;
        const bus = preferredBus(locationOf(role), role);
        if (bus) next = { ...next, [role]: bus };
      }
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roles, busList.status]);

  // A name like the record's own ("BE0 1AC solar new") until one is typed.
  const firstLocation = roles[0] ? locationOf(roles[0].role) : (seed?.location ?? "");
  useEffect(() => {
    if (isNameTouched || !seed) return;
    setName([firstLocation, shownCarrier ?? ctype, "new"].filter(Boolean).join(" "));
  }, [ctype, firstLocation, isNameTouched, seed, shownCarrier]);

  // Values: numbers per entity the ctype stores, inputs only.
  const resultNames = useMemo(
    () => new Set(record?.info.revisions.flatMap((revision) => revision.results) ?? []),
    [record],
  );
  const stored = useInputData(
    "ctype-attributes",
    scenarioKey && ctype ? `${scenarioKey}\n${ctype}` : null,
    () => loadCtypeAttributes(ctype),
  );
  const attributes = useMemo(() => {
    const manifest = record?.info.manifest.attributes ?? {};
    return (stored.status === "ready" ? stored.data : []).filter(
      (attr) => !resultNames.has(attr) && isChangeable(manifest[attr]),
    );
  }, [record, resultNames, stored]);
  // A new entity starts with its size to fill in.
  useEffect(() => {
    if (!seed || seed.change || attributes.length === 0) return;
    setRows((current) =>
      current.length > 0
        ? current
        : SIZES.filter((size) => attributes.includes(size))
            .slice(0, 1)
            .map((attribute) => ({ attribute, value: "" })),
    );
  }, [attributes, seed]);
  const specOf = (attribute: string) => record?.info.manifest.attributes[attribute];

  // The name: given, not the record's already (in the shown scenario), not another new entity's in the draft.
  const trimmed = name.trim();
  const checkedName = useDebounced(trimmed, 300);
  const existing = useInputData(
    "entity-exists",
    scenarioKey && checkedName ? `${scenarioKey}\n${checkedName}` : null,
    () => entityExists(checkedName),
  );
  const targetDraft = drafts.find((draft) => draft.id === draftId);
  const nameIsDraftsAlready = Boolean(
    targetDraft?.changes.some(
      (change) =>
        change.kind === "new-entity" &&
        change.id !== seed?.change?.id &&
        change.entity.toLowerCase() === trimmed.toLowerCase(),
    ),
  );
  const nameIsRecords =
    checkedName === trimmed &&
    existing.status === "ready" &&
    existing.data &&
    trimmed !== seed?.change?.entity;
  const nameProblem = !trimmed
    ? null
    : nameIsRecords
      ? "An entity of this name is in the scenario already."
      : nameIsDraftsAlready
        ? "This draft adds an entity of this name already."
        : null;

  const parsedRows = rows.map((row) => ({
    ...row,
    number: row.value.trim() === "" ? NaN : Number(row.value),
  }));
  const valuesValid = parsedRows.every((row) => row.attribute && Number.isFinite(row.number));
  const busesValid = roles.every(({ role }) => Boolean(buses[role]));
  const isChecking = Boolean(trimmed) && (checkedName !== trimmed || existing.status === "loading");
  const canSave = Boolean(
    record &&
    ctype &&
    trimmed &&
    !nameProblem &&
    !isChecking &&
    connections.status === "ready" &&
    busesValid &&
    valuesValid &&
    (draftId !== NEW_DRAFT || newName.trim()),
  );
  const isEditing = Boolean(seed?.change);

  const save = () => {
    if (!canSave || !record) return;
    const id =
      draftId === NEW_DRAFT
        ? createDraft({ recordId, parent: record.scenario ?? "", name: newName, description: "" })
            .id
        : draftId;
    saveDraftChange(id, {
      id: seed?.change?.id,
      kind: "new-entity",
      entity: trimmed,
      ctype,
      carrier: shownCarrier,
      buses: Object.fromEntries(roles.map(({ role }) => [role, buses[role]])),
      values: Object.fromEntries(parsedRows.map((row) => [row.attribute, row.number])),
    });
    showDraft(id);
    close();
  };

  const preview = (() => {
    if (!ctype || !trimmed) return null;
    const where = describeNewEntity(
      {
        id: "",
        kind: "new-entity",
        entity: trimmed,
        ctype,
        carrier: shownCarrier,
        buses,
        values: {},
      },
      carrierLabel,
      (bus) => busInfo.get(bus)?.location ?? bus,
    );
    const given = parsedRows
      .filter((row) => row.attribute && Number.isFinite(row.number))
      .map(
        (row) =>
          `${row.attribute} ${row.number.toLocaleString()}${specOf(row.attribute)?.unit ? ` ${specOf(row.attribute)!.unit}` : ""}`,
      );
    return `${where}${given.length ? `, with ${given.join(", ")}` : ""}. Other values take their defaults.`;
  })();

  return (
    <DialogShell
      open={seed !== null}
      onClose={close}
      title={isEditing ? "Edit new entity" : "Add an entity"}
      description="It stays in this draft until scenarios can be saved to the record, so the map, tree and pages don't show it yet."
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
            {isEditing ? "Save" : "Add"}
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
            placeholder="e.g. 2 GW more offshore wind"
            className={INPUT_CLASS}
          />
        </Field>
      )}

      <Field label="Type">
        <div className="grid grid-cols-2 gap-1.5">
          <FormSelect
            value={ctype}
            onValueChange={(next) => {
              setCtype(next);
              setCarrier(NO_CARRIER);
              setBuses({});
              setRows([]);
            }}
            ariaLabel="Component type"
            options={ctypes.map((value) => ({ value, label: value }))}
          />
          <FormSelect
            value={carrier}
            onValueChange={(next) => {
              setCarrier(next);
              setBuses({});
            }}
            disabled={carriers.length === 0}
            ariaLabel="Carrier"
            options={[
              { value: NO_CARRIER, label: carriers.length ? "No carrier" : "No carriers" },
              ...carriers.map((value) => ({ value, label: carrierLabel(value) })),
            ]}
          />
        </div>
      </Field>

      <Field label="Name" hint={nameProblem ?? (isChecking ? "Checking the name…" : undefined)}>
        <input
          value={name}
          onChange={(event) => {
            setName(event.target.value);
            setIsNameTouched(true);
          }}
          className={clsx(INPUT_CLASS, nameProblem && "border-danger-500")}
        />
      </Field>

      {connections.status === "loading" && (
        <span className="text-surface-500 text-[11px]">Loading how {ctype} entities connect…</span>
      )}
      {roles.map(({ role }) => {
        const location = locationOf(role);
        const here = busesAt(location);
        return (
          <Field
            key={role}
            label={ROLE_LABELS[role] ?? `Connects at (${role})`}
            hint={
              role === "output"
                ? "One output here; more outputs (a CHP’s heat, say) can’t be added yet."
                : undefined
            }
          >
            <div className="grid grid-cols-2 gap-1.5">
              <FormSelect
                value={location || null}
                onValueChange={(next) => {
                  setPickedLocations((current) => ({ ...current, [role]: next }));
                  setBuses((current) => ({ ...current, [role]: preferredBus(next, role) }));
                }}
                placeholder="Location"
                ariaLabel={`${role} location`}
                options={locations.map((value) => ({ value, label: value }))}
              />
              <FormSelect
                value={buses[role] || null}
                onValueChange={(next) => setBuses((current) => ({ ...current, [role]: next }))}
                disabled={!location}
                placeholder={busList.status === "loading" ? "Loading buses…" : "Bus"}
                ariaLabel={`${role} bus`}
                options={here.map((item) => ({
                  value: item.bus,
                  label: item.carrier ? `${item.bus} (${carrierLabel(item.carrier)})` : item.bus,
                }))}
              />
            </div>
          </Field>
        );
      })}

      <div className="flex flex-col gap-1">
        <span className="text-surface-400 text-[11px] font-medium">Values</span>
        {rows.map((row, index) => {
          const unit = specOf(row.attribute)?.unit;
          const invalid = row.value.trim() !== "" && !Number.isFinite(Number(row.value));
          return (
            <div key={index} className="flex items-center gap-1.5">
              <div className="w-40 shrink-0">
                <FormSelect
                  value={row.attribute || null}
                  onValueChange={(next) =>
                    setRows((current) =>
                      current.map((item, i) => (i === index ? { ...item, attribute: next } : item)),
                    )
                  }
                  placeholder="Attribute"
                  ariaLabel="Attribute"
                  options={attributes
                    .filter(
                      (attr) =>
                        attr === row.attribute || !rows.some((item) => item.attribute === attr),
                    )
                    .map((value) => ({ value, label: value }))}
                />
              </div>
              <input
                value={row.value}
                onChange={(event) =>
                  setRows((current) =>
                    current.map((item, i) =>
                      i === index ? { ...item, value: event.target.value } : item,
                    ),
                  )
                }
                inputMode="decimal"
                placeholder="0"
                aria-label={`${row.attribute || "Attribute"} value`}
                title={specOf(row.attribute)?.description}
                className={clsx(INPUT_CLASS, "min-w-0 flex-1", invalid && "border-danger-500")}
              />
              {unit && <span className="text-surface-400 shrink-0 text-[12px]">{unit}</span>}
              <button
                type="button"
                aria-label="Remove this value"
                onClick={() => setRows((current) => current.filter((_, i) => i !== index))}
                className="text-surface-400 hover:bg-surface-700 hover:text-surface-50 shrink-0 rounded p-1 outline-none"
              >
                <LuX size={13} />
              </button>
            </div>
          );
        })}
        <button
          type="button"
          onClick={() => setRows((current) => [...current, { attribute: "", value: "" }])}
          disabled={attributes.length === 0 || rows.length >= attributes.length}
          className="text-accent-300 hover:bg-surface-700 flex h-7 items-center gap-1 self-start rounded px-1.5 text-[12px] font-medium outline-none disabled:opacity-40"
        >
          <LuPlus size={12} />
          Add a value
        </button>
        <span className="text-surface-500 text-[11px] leading-4">
          {stored.status === "loading"
            ? "Loading its attributes…"
            : "Values not given take the defaults the record declares."}
        </span>
      </div>

      {preview && (
        <div className="border-surface-700 bg-surface-900/60 text-surface-200 rounded border px-3 py-2 text-[12px]">
          {preview}
        </div>
      )}
    </DialogShell>
  );
}
