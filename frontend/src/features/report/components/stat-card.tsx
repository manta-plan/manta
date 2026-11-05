import { LuTrendingUp, LuTrendingDown } from "react-icons/lu";
import type { StatWidget } from "../../project/data/report-widgets";
import { useProjectStore } from "../../project/store/project-store";

export function StatCard({ widget }: { widget: StatWidget }) {
  const openWidgetConfigDrawer = useProjectStore((s) => s.openWidgetConfigDrawer);
  const TrendIcon = widget.trend?.direction === "up" ? LuTrendingUp : LuTrendingDown;
  const trendColor = widget.trend?.direction === "up" ? "text-ok-500" : "text-danger-500";

  return (
    <div
      onClick={() => openWidgetConfigDrawer(widget.id)}
      className="border-surface-700 bg-surface-800 hover:border-accent-500/60 flex cursor-pointer flex-col gap-1 rounded-lg border p-3 outline-none"
    >
      <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
        {widget.label}
      </div>
      <div className="text-surface-50 text-[20px] font-semibold">{widget.value}</div>
      <div className="text-surface-400 flex items-center gap-1.5 text-[11px]">
        <span>{widget.sublabel}</span>
        {widget.trend && (
          <span className={`flex items-center gap-0.5 font-medium ${trendColor}`}>
            <TrendIcon size={12} />
            {widget.trend.value}
          </span>
        )}
      </div>
    </div>
  );
}
