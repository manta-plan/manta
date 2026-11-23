import { RAMP_GRADIENT } from "./map-layer-store";

// One legend per active colour layer (name, min, ramp, max, unit), or a note
// when the level has nothing to colour.

export interface LegendSpec {
  name: string;
  min: number | null;
  max: number | null;
  unit: string;
  percent: boolean;
  loading: boolean;
  /** Shown instead of the ramp when there are no values. */
  empty: string;
}

function formatValue(value: number, percent: boolean): string {
  if (percent) return `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;
  const abs = Math.abs(value);
  return value.toLocaleString("en", { maximumFractionDigits: abs >= 100 ? 0 : abs >= 10 ? 1 : 2 });
}

export function MapLegend({ spec }: { spec: LegendSpec }) {
  const hasValues = spec.min !== null && spec.max !== null;
  return (
    <div className="border-surface-600 bg-surface-800/95 text-surface-300 pointer-events-auto flex flex-col gap-0.5 rounded border px-2 py-1.5 text-[10px] shadow-lg shadow-black/30">
      <span className="text-surface-100 font-semibold">{spec.name}</span>
      {spec.loading ? (
        <span className="text-surface-500">Loading…</span>
      ) : hasValues ? (
        <>
          <div className="flex items-center gap-1.5 tabular-nums">
            <span>{formatValue(spec.min!, spec.percent)}</span>
            <span className="h-2 w-20 rounded-sm" style={{ backgroundImage: RAMP_GRADIENT }} />
            <span>{formatValue(spec.max!, spec.percent)}</span>
          </div>
          <span className="text-surface-500">{spec.unit}</span>
        </>
      ) : (
        <span className="text-surface-500">{spec.empty}</span>
      )}
    </div>
  );
}
