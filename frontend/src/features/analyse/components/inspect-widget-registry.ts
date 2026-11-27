// SPDX-FileCopyrightText: Manta contributors
//
// SPDX-License-Identifier: Apache-2.0

import { createElement, type ComponentType } from "react";
import { BUILT_IN_WIDGET_SPECS } from "../lib/built-in-widget-specs";
import { BuiltInWidget } from "./built-in-widget";

export interface PresetWidget {
  label: string;
  component: ComponentType<{ resultName: string }>;
}

// Every built-in widget, by id: its spec drawn by BuiltInWidget.
export const PRESET_WIDGETS: Record<string, PresetWidget> = Object.fromEntries(
  Object.entries(BUILT_IN_WIDGET_SPECS).map(([widgetId, spec]) => {
    const component = ({ resultName }: { resultName: string }) =>
      createElement(BuiltInWidget, { widgetId, resultName });
    return [widgetId, { label: spec.label, component }];
  }),
);
