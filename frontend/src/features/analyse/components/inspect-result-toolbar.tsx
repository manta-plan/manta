// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { Toolbar } from "@base-ui/react/toolbar";
import { LuChartColumn, LuCircleOff, LuGitCompareArrows } from "react-icons/lu";
import {
  resolveResultSelection,
  selectComparison,
  selectResult,
  useResultSelection,
} from "../lib/inspect-result-selection";
import { useLoadResultCatalogue } from "../lib/use-result-data";
import { ToolbarModeMenu } from "../../project/components/toolbar-mode-menu";

const NO_COMPARISON = "";

// The Inspect tab's toolbar: which of the record's results every inspection shows, and
// which one it compares with. Hidden until the catalogue has results.
export function InspectResultToolbar({ withComparison = true }: { withComparison?: boolean }) {
  const catalogueState = useLoadResultCatalogue();
  const selection = useResultSelection();
  if (catalogueState.status !== "ready" || catalogueState.catalogue.results.length === 0)
    return null;
  const { results } = catalogueState.catalogue;
  const { selectedRun, comparisonRun } = resolveResultSelection(
    catalogueState.catalogue,
    selection,
  );

  const resultOptions = results.map((run) => ({
    value: run.id,
    label: run.label,
    icon: LuChartColumn,
  }));
  const comparisonOptions = [
    { value: NO_COMPARISON, label: "No comparison", icon: LuCircleOff },
    ...results
      .filter((run) => run.id !== selectedRun.id)
      .map((run) => ({ value: run.id, label: run.label, icon: LuGitCompareArrows })),
  ];

  return (
    <>
      <Toolbar.Group data-tour="result-toolbar" className="flex items-center gap-0.5">
        <ToolbarModeMenu
          label="Result"
          options={resultOptions}
          value={selectedRun.id}
          onChange={selectResult}
          showLabel
          disabled={results.length < 2}
          disabledHint="the only one there is"
        />
        {withComparison && (
          <ToolbarModeMenu
            label="Compare with"
            options={comparisonOptions}
            value={comparisonRun?.id ?? NO_COMPARISON}
            onChange={selectComparison}
            showLabel
            active={comparisonRun !== null}
            disabled={results.length < 2}
            disabledHint="there is no other result"
          />
        )}
      </Toolbar.Group>
      <Toolbar.Separator className="bg-surface-600 mx-1 h-5 w-px" />
    </>
  );
}
