// A component type's page id (Generator, or one carrier of it: Generator ›
// Solar), and what each type shows: its capacity attribute and output.

// ------------------------------------------------------------ Page ids

const PREFIX = "component:";

/** What a page shows: a type, or one carrier of it. */
export interface ComponentPageSubject {
  ctype: string;
  carrier: string | null;
}

/** The page's id where an inspection's would go: /inspect/component:Generator, or component:Generator:solar. */
export function componentPageId(ctype: string, carrier: string | null = null) {
  return `${PREFIX}${ctype}${carrier === null ? "" : `:${encodeURIComponent(carrier)}`}`;
}

const decode = (text: string) => {
  try {
    return decodeURIComponent(text);
  } catch {
    return text;
  }
};

export function componentOfPageId(id: string | null | undefined): ComponentPageSubject | null {
  if (!id?.startsWith(PREFIX)) return null;
  const [ctype, ...carrier] = id.slice(PREFIX.length).split(":");
  return ctype
    ? { ctype: decode(ctype), carrier: carrier.length > 0 ? decode(carrier.join(":")) : null }
    : null;
}

// ------------------------------------------------------------ What each type shows

/** The attribute that sizes a type, and what its result output is called. */
export interface ComponentKind {
  capacity: string | null;
  /** The optimised capacity a result adds. */
  optimised: string | null;
  output: string | null;
  /** How power counts: as stored, only its positive part (a storage unit discharging), or its size (a line's flow either way). */
  outputValue: "signed" | "positive" | "absolute";
}

const KINDS: Record<string, ComponentKind> = {
  Generator: {
    capacity: "p_nom",
    optimised: "p_nom_opt",
    output: "Generation",
    outputValue: "signed",
  },
  StorageUnit: {
    capacity: "p_nom",
    optimised: "p_nom_opt",
    output: "Discharge",
    outputValue: "positive",
  },
  Link: {
    capacity: "p_nom",
    optimised: "p_nom_opt",
    output: "Throughput",
    outputValue: "signed",
  },
  Line: {
    capacity: "s_nom",
    optimised: "s_nom_opt",
    output: "Flow",
    outputValue: "absolute",
  },
  Transformer: {
    capacity: "s_nom",
    optimised: "s_nom_opt",
    output: "Flow",
    outputValue: "absolute",
  },
  Store: {
    capacity: "e_nom",
    optimised: "e_nom_opt",
    output: null,
    outputValue: "signed",
  },
  Load: {
    capacity: null,
    optimised: null,
    output: "Demand",
    outputValue: "signed",
  },
};

export function componentKind(ctype: string): ComponentKind {
  return (
    KINDS[ctype] ?? {
      capacity: null,
      optimised: null,
      output: null,
      outputValue: "signed",
    }
  );
}
