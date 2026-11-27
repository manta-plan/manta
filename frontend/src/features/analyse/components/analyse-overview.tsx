// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Menu } from "@base-ui/react/menu";
import type { ReactNode } from "react";
import { useMemo } from "react";
import type { IconType } from "react-icons";
import { GiMagnifyingGlass } from "react-icons/gi";
import {
  LuArrowRight,
  LuChartBar,
  LuChevronDown,
  LuDatabase,
  LuFileText,
  LuGitCompareArrows,
  LuLayoutDashboard,
} from "react-icons/lu";
import { HiOutlineDocumentMagnifyingGlass } from "react-icons/hi2";
import { Link, useLocation, useParams } from "wouter";
import { BUILT_IN_INSPECTIONS } from "../data/inspections";
import { computedPageId } from "../lib/data-pages";
import { selectComparison, selectResult } from "../lib/inspect-result-selection";
import { projectAnalyseHref } from "../../project/lib/project-route";
import { recordResults } from "../../project/lib/record-results";
import { BUILT_IN_QUERIES } from "../lib/result-queries";
import { useLoadResultCatalogue } from "../lib/use-result-data";
import { startAnalyseWorkspaceTour } from "../lib/analyse-tours";
import { useProjectStore } from "../../project/store/project-store";
import { OverviewSectionHeader, OverviewTourButton } from "./workspace-overview-parts";
import { LinesSkeleton } from "../../../components/widget-states";

// The Analyse tab's home: how data, views and reports fit together, with a
// way into each; the results there are to analyse; and the user's own views
// and reports.

const FIRST_VIEW = BUILT_IN_INSPECTIONS[0];

const plural = (count: number, one: string, many: string) =>
  `${count.toLocaleString()} ${count === 1 ? one : many}`;

const actionClassName =
  "flex h-7 items-center gap-1.5 rounded border border-surface-600 bg-surface-800 px-2 text-[12px] font-medium text-surface-200 outline-none hover:border-surface-500 hover:bg-surface-700 hover:text-surface-50 focus-visible:border-accent-500";

function Step({
  icon: Icon,
  iconClassName,
  title,
  description,
  count,
  children,
}: {
  icon: IconType;
  iconClassName: string;
  title: string;
  description: string;
  count: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-44 flex-col px-5 py-4">
      <div className="text-surface-100 flex items-center gap-2 text-[12px] font-medium">
        <Icon size={15} className={iconClassName} />
        {title}
      </div>
      <p className="text-surface-400 mt-2 text-[12px] leading-5">{description}</p>
      <div className="text-surface-200 mt-3 text-[11px] font-medium">{count}</div>
      <div className="mt-auto flex flex-wrap gap-1.5 pt-3">{children}</div>
    </div>
  );
}

const Arrow = () => (
  <div className="text-surface-500 hidden items-center justify-center px-3 lg:flex">
    <LuArrowRight size={15} />
  </div>
);

function HowAnalyseWorks({ resultCount }: { resultCount: number }) {
  const { projectId } = useParams<{ projectId: string }>();
  const views = useProjectStore((s) => s.inspections);
  const reports = useProjectStore((s) => s.reports);
  const openNewInspectionDrawer = useProjectStore((s) => s.openNewInspectionDrawer);
  const openNewReportDrawer = useProjectStore((s) => s.openNewReportDrawer);
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="How Analyse works">
        <div className="flex items-center gap-1">
          <OverviewTourButton onClick={startAnalyseWorkspaceTour} />
        </div>
      </OverviewSectionHeader>
      <div className="divide-surface-700 grid divide-y lg:grid-cols-[1fr_auto_1fr_auto_1fr] lg:divide-x lg:divide-y-0">
        <Step
          icon={LuDatabase}
          iconClassName="text-ok-500"
          title="Data"
          description="Tables computed from each solved result, with their SQL and assumptions, and the result's raw tables beside them."
          count={`${plural(BUILT_IN_QUERIES.length, "computed table", "computed tables")} · ${plural(resultCount, "result", "results")}`}
        >
          <Link
            href={projectAnalyseHref(projectId, computedPageId(BUILT_IN_QUERIES[0].name))}
            className={actionClassName}
          >
            Browse data
          </Link>
        </Step>
        <Arrow />
        <Step
          icon={GiMagnifyingGlass}
          iconClassName="text-accent-400"
          title="Views"
          description="Pages of widgets that chart the data, for the result picked in the toolbar, or two results side by side."
          count={`${BUILT_IN_INSPECTIONS.length} built-in · ${views.length} yours`}
        >
          <Link href={projectAnalyseHref(projectId, FIRST_VIEW.id)} className={actionClassName}>
            Open {FIRST_VIEW.name}
          </Link>
          <button type="button" onClick={openNewInspectionDrawer} className={actionClassName}>
            New view
          </button>
        </Step>
        <Arrow />
        <Step
          icon={LuChartBar}
          iconClassName="text-warn-500"
          title="Reports"
          description="Paper pages of widgets, text and key figures to print or share, each widget on the result you choose."
          count={plural(reports.length, "report", "reports")}
        >
          <button type="button" onClick={() => openNewReportDrawer()} className={actionClassName}>
            New report
          </button>
        </Step>
      </div>
    </section>
  );
}

function ResultsInRecord() {
  const { projectId } = useParams<{ projectId: string }>();
  const [, navigate] = useLocation();
  const info = useProjectStore((s) => s.record?.info ?? null);
  const results = useMemo(() => (info ? recordResults(info) : []), [info]);
  const catalogue = useLoadResultCatalogue();
  const periods = catalogue.status === "ready" ? catalogue.catalogue.periods : [];
  const open = (resultId: string, comparisonId = "") => {
    selectResult(resultId);
    selectComparison(comparisonId);
    navigate(projectAnalyseHref(projectId, FIRST_VIEW.id));
  };
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="Results in this record">
        {periods.length > 0 && (
          <span className="text-surface-400 text-[11px]">
            Investment periods {periods.join(" · ")}
          </span>
        )}
      </OverviewSectionHeader>
      {results.length === 0 ? (
        info ? (
          <div className="text-surface-400 px-5 py-4 text-[12px] leading-5">
            This record holds no solved results yet. Run a scenario on the Run tab to get one.
          </div>
        ) : (
          <div className="px-5 py-3">
            <LinesSkeleton lines={4} label="Opening the record" />
          </div>
        )
      ) : (
        <ul className="divide-surface-700/70 divide-y">
          {results.map((result) => (
            <li key={result.id} className="flex items-center gap-3 px-5 py-2">
              <span className="text-surface-100 min-w-0 flex-1 truncate font-mono text-[12px]">
                {result.label}
              </span>
              <span className="text-surface-400 w-40 shrink-0 truncate text-[12px]">
                {result.scenarioLabel ? `from ${result.scenarioLabel}` : ""}
              </span>
              <button type="button" onClick={() => open(result.id)} className={actionClassName}>
                Open
              </button>
              <Menu.Root>
                <Menu.Trigger
                  className={`${actionClassName} data-[popup-open]:border-accent-500`}
                  disabled={results.length < 2}
                >
                  <LuGitCompareArrows size={12} />
                  Compare with
                  <LuChevronDown size={11} className="text-surface-400" />
                </Menu.Trigger>
                <Menu.Portal>
                  <Menu.Positioner className="z-50 outline-none" sideOffset={4} align="end">
                    <Menu.Popup className="border-surface-600 bg-surface-800 text-surface-100 min-w-48 rounded-md border py-1 text-[12px] shadow-2xl shadow-black/50 outline-none">
                      {results
                        .filter((other) => other.id !== result.id)
                        .map((other) => (
                          <Menu.Item
                            key={other.id}
                            onClick={() => open(result.id, other.id)}
                            className="data-[highlighted]:bg-accent-600 flex cursor-pointer items-center gap-2 px-3 py-1.5 outline-none data-[highlighted]:text-white"
                          >
                            <span className="font-mono">{other.label}</span>
                          </Menu.Item>
                        ))}
                    </Menu.Popup>
                  </Menu.Positioner>
                </Menu.Portal>
              </Menu.Root>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Yours() {
  const { projectId } = useParams<{ projectId: string }>();
  const views = useProjectStore((s) => s.inspections);
  const reports = useProjectStore((s) => s.reports);
  if (views.length === 0 && reports.length === 0) return null;
  const row = (key: string, href: string, icon: IconType, name: string, detail: string) => {
    const Icon = icon;
    return (
      <li key={key}>
        <Link
          href={href}
          className="text-surface-200 hover:bg-surface-800 hover:text-surface-50 flex items-center gap-2 rounded px-2 py-1.5 text-[12px] outline-none"
        >
          <Icon size={14} className="text-surface-400 shrink-0" />
          <span className="min-w-0 flex-1 truncate">{name}</span>
          <span className="text-surface-500 shrink-0 text-[11px]">{detail}</span>
        </Link>
      </li>
    );
  };
  return (
    <section className="border-surface-700 border-b">
      <OverviewSectionHeader title="Yours" />
      <div className="grid gap-4 px-3 py-3 lg:grid-cols-2">
        <div>
          <h3 className="text-surface-400 px-2 pb-1 text-[11px] font-medium">Views</h3>
          {views.length === 0 ? (
            <p className="text-surface-500 px-2 text-[12px]">None yet.</p>
          ) : (
            <ul>
              {views.map((view) =>
                row(
                  view.id,
                  projectAnalyseHref(projectId, view.id),
                  HiOutlineDocumentMagnifyingGlass,
                  view.name,
                  plural(view.items.length, "widget", "widgets"),
                ),
              )}
            </ul>
          )}
        </div>
        <div>
          <h3 className="text-surface-400 px-2 pb-1 text-[11px] font-medium">Reports</h3>
          {reports.length === 0 ? (
            <p className="text-surface-500 px-2 text-[12px]">None yet.</p>
          ) : (
            <ul>
              {reports.map((report) =>
                row(
                  report.id,
                  projectAnalyseHref(projectId, report.id),
                  LuFileText,
                  report.name,
                  `${plural(report.pages.length, "page", "pages")} · ${new Date(report.createdAt).toLocaleDateString()}`,
                ),
              )}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}

export function AnalyseOverview() {
  const info = useProjectStore((s) => s.record?.info ?? null);
  const resultCount = info ? recordResults(info).length : 0;
  return (
    <div data-tour="analyse-home" className="bg-surface-900 flex h-full flex-col overflow-y-auto">
      <header className="border-surface-700 flex h-14 shrink-0 items-center gap-2 border-b px-5">
        <LuLayoutDashboard size={16} className="text-surface-400" />
        <div>
          <h1 className="text-surface-50 text-[14px] font-semibold">Analyse</h1>
          <p className="text-surface-400 mt-0.5 text-[11px]">
            Chart the project's solved results, then lay the charts out as reports.
          </p>
        </div>
      </header>
      <HowAnalyseWorks resultCount={resultCount} />
      <ResultsInRecord />
      <Yours />
    </div>
  );
}
