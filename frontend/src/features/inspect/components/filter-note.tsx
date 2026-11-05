import { LuListFilter } from "react-icons/lu";
import {
  activeDimensions,
  FILTER_DIMENSION_LABELS,
  useInspectFilters,
  type FilterDimension,
} from "../../project/lib/inspect-filters";

// Says how the page's shared filters reach one widget: "Filtered" when it
// applies some of them, and which active ones it can't apply.
export function FilterNote({ filteredBy }: { filteredBy: FilterDimension[] }) {
  const { filters } = useInspectFilters();
  const active = activeDimensions(filters);
  if (active.length === 0) return null;
  const applied = active.filter((dimension) => filteredBy.includes(dimension));
  const ignored = active.filter((dimension) => !filteredBy.includes(dimension));

  return (
    <div className="flex shrink-0 items-center gap-2 text-[10px]">
      {applied.length > 0 && (
        <span className="border-accent-500/50 bg-accent-600/15 text-accent-400 flex items-center gap-1 rounded border px-1.5 py-0.5 font-medium">
          <LuListFilter size={10} />
          Filtered
        </span>
      )}
      {ignored.length > 0 && (
        <span className="text-surface-500">
          Not filtered by{" "}
          {ignored.map((dimension) => FILTER_DIMENSION_LABELS[dimension]).join(" or ")}
        </span>
      )}
    </div>
  );
}
