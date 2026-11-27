// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { useContext, useMemo, useState } from "react";
import { BUILT_IN_WIDGET_SPECS } from "../lib/built-in-widget-specs";
import { querySql } from "../lib/custom-query";
import { ResultContext, useSharedWidgetState } from "../lib/result-comparison";
import type { CustomItem } from "../lib/widget-sets";
import type { ViewState } from "../../project/store/types";
import { useProjectStore } from "../../project/store/project-store";
import { CustomWidget } from "./custom-widget";

const noop = () => {};

/** A built-in widget: its spec drawn as the custom widget it is, for the result in ResultContext (and beside it the compared one, if any). */
export function BuiltInWidget({
  widgetId,
  resultName,
  comparison = null,
}: {
  widgetId: string;
  resultName: string;
  comparison?: { id: string; label: string } | null;
}) {
  const resultId = useContext(ResultContext);
  const spec = BUILT_IN_WIDGET_SPECS[widgetId];
  // Seeded from the main map; both results' maps share it when comparing.
  const [mapViewState, setMapViewState] = useSharedWidgetState<ViewState>(
    "viewState",
    () => useProjectStore.getState().viewState,
  );
  // The read-only editor's tab (Builder or SQL); nothing else about a built-in changes.
  const [mode, setMode] = useState<CustomItem["mode"]>("builder");
  const item = useMemo<CustomItem>(
    () => ({
      id: widgetId,
      kind: "custom",
      mode,
      sql: querySql(spec.query),
      title: spec.label,
      subtitle: spec.subtitle,
      query: spec.query,
      chart: spec.chart,
      mapViewState,
    }),
    [widgetId, spec, mode, mapViewState],
  );
  const result = useMemo(() => ({ id: resultId, label: resultName }), [resultId, resultName]);
  return (
    <CustomWidget
      item={item}
      builtIn
      onChange={(patch) => {
        if (patch.mapViewState) setMapViewState(patch.mapViewState);
        if (patch.mode) setMode(patch.mode);
      }}
      onDuplicate={noop}
      selectedRun={result}
      comparisonRun={comparison}
      startsEditing={false}
    />
  );
}
