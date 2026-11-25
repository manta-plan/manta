import { useMemo, useState, type ReactNode } from "react";
import { LuChartLine, LuDownload, LuTable, LuX } from "react-icons/lu";
import { useShownData } from "../../project/lib/record-data";
import { useProjectStore } from "../../project/store/project-store";
import { useLevelPage } from "../level-page-context";
import { scopeKey } from "../level-sql";
import { useLevelStore } from "../level-store";
import { pickInfos, type PickInfo } from "./attributes";
import { loadAxis, loadPicked } from "./chart-sql";
import { ChartEmpty, ChartLoading, IconButton } from "./controls";
import { DrawerFrame } from "./drawer-frame";
import { SeriesTable } from "./series-table";
import { SpecChart } from "./spec-chart";
import { distributionOf, downloadCsv, LINE_THRESHOLD, type ChartSpec } from "./spec";

// The series picked in the table: a chip per series, one plot per unit
// (beyond the line threshold, that unit's plot is a distribution and its
// chips hide), the table toggle and a wide CSV.

export function PickedView({
  inspect,
  controls,
  statisticsOn,
}: {
  inspect: boolean;
  controls: ReactNode;
  statisticsOn: boolean;
}) {
  const { scope } = useLevelPage();
  const record = useProjectStore((s) => s.record);
  const picked = useLevelStore((s) => s.pickedSeries);
  const toggle = useLevelStore((s) => s.togglePickedSeries);
  const setPicked = useLevelStore((s) => s.setPickedSeries);
  const [asTable, setAsTable] = useState(false);
  const infos = useMemo(() => pickInfos(picked, record?.info.manifest), [picked, record]);
  // Results aren't in a scenario's catalog: in Build only inputs are read.
  const readable = useMemo(() => infos.filter((info) => inspect || !info.result), [infos, inspect]);

  const data = useShownData(
    "level-chart-picked",
    scope ? [scopeKey(scope), JSON.stringify(readable.map((info) => info.query))] : null,
    async () => {
      const [axis, values] = await Promise.all([
        loadAxis(scope!),
        loadPicked(
          scope!,
          readable.map((info) => info.query),
        ),
      ]);
      return { axis, values };
    },
  );

  const units = [...new Set(readable.map((info) => info.unit))];
  const countOf = (unit: string) => readable.filter((info) => info.unit === unit).length;
  const chips = readable.filter((info) => countOf(info.unit) <= LINE_THRESHOLD);
  const valuesOf = (info: PickInfo) =>
    data.status === "ready" ? (data.data.values[readable.indexOf(info)] ?? []) : [];

  const download = () => {
    if (data.status !== "ready") return;
    downloadCsv(
      readable.length === 1
        ? readable[0].label.replace(" · ", "-")
        : `${readable[0]?.pick.attribute ?? "series"}-picked`,
      data.data.axis.times,
      readable.map((info) => ({ header: `${info.label} [${info.unit}]`, values: valuesOf(info) })),
    );
  };

  const actions = (
    <>
      <IconButton
        label={asTable ? "Show as chart" : "Show as table"}
        pressed={asTable}
        onClick={() => setAsTable(!asTable)}
      >
        {asTable ? <LuChartLine size={13} /> : <LuTable size={13} />}
      </IconButton>
      <IconButton label="Download CSV" onClick={download}>
        <LuDownload size={13} />
      </IconButton>
      <IconButton label="Clear the picked series" onClick={() => setPicked([])}>
        <LuX size={13} />
      </IconButton>
    </>
  );

  let body: ReactNode;
  if (readable.length === 0)
    body = (
      <ChartEmpty
        title={`${picked[0]?.attribute ?? "This"} is a result`}
        detail="Switch to Inspect to see it, or pick an input series."
      />
    );
  else if (data.status === "error")
    body = <ChartEmpty title="The series couldn't be read" detail={data.error} />;
  else if (data.status === "loading") body = <ChartLoading />;
  else if (asTable)
    body = (
      <SeriesTable
        times={data.data.axis.times}
        columns={readable.map((info) => ({
          label: info.label,
          unit: info.unit,
          color: info.color,
          values: valuesOf(info),
        }))}
      />
    );
  else
    body = units.map((unit) => {
      const group = readable.filter((info) => info.unit === unit);
      const many = group.length > LINE_THRESHOLD;
      const spec: ChartSpec = many
        ? {
            kind: "time",
            unit,
            times: data.data.axis.times,
            series: [],
            distribution: distributionOf(group.map(valuesOf)),
          }
        : {
            kind: "time",
            unit,
            times: data.data.axis.times,
            series: group.map((info) => ({
              name: info.label,
              color: info.color,
              values: valuesOf(info),
            })),
          };
      return (
        <div key={unit} className={data.refreshing ? "opacity-60 transition-opacity" : ""}>
          {(units.length > 1 || many) && (
            <div className="text-surface-400 px-3 pt-2 text-[11px]">
              {units.length > 1 && <span className="text-surface-200">{unit}</span>}
              {units.length > 1 && many && " · "}
              {many &&
                `Distribution of ${group.length} series: median line, P25–P75 band (darker) and min–max band (lighter). Unpick series, or clear them with ×, to get back to one line each.`}
            </div>
          )}
          <SpecChart spec={spec} height={units.length > 1 ? 170 : 220} group="level-picked" />
        </div>
      );
    });

  return (
    <DrawerFrame
      mode="attributes"
      statisticsOn={statisticsOn}
      controls={controls}
      actions={actions}
    >
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3 pt-2">
          {chips.map((info) => (
            <span
              key={`${info.pick.entity}\n${info.pick.attribute}\n${info.pick.bus}`}
              className="border-surface-600 bg-surface-800 text-surface-200 flex max-w-full items-center gap-1.5 rounded-full border py-0.5 pr-0.5 pl-2 text-[11px]"
            >
              <span
                className="h-2 w-2 shrink-0 rounded-sm"
                style={{ backgroundColor: info.color }}
              />
              <span className="min-w-0 truncate">
                <span className="font-medium">{info.pick.attribute}</span> ·{" "}
                <span className="font-mono">{info.pick.entity}</span>
              </span>
              <span className="text-surface-500 shrink-0">{info.unit}</span>
              <button
                type="button"
                aria-label={`Remove ${info.label}`}
                title="Remove"
                onClick={() => toggle(info.pick)}
                className="text-surface-400 hover:bg-surface-700 hover:text-surface-100 focus-visible:ring-accent-500 grid h-5 w-5 shrink-0 place-items-center rounded-full outline-none focus-visible:ring-1"
              >
                <LuX size={11} />
              </button>
            </span>
          ))}
        </div>
      )}
      {body}
    </DrawerFrame>
  );
}
