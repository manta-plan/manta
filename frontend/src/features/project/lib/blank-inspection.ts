import { useProjectStore } from "../store/project-store";
import { defaultQuery } from "./custom-query";
import { newCustomItem, type CustomItem } from "./widget-sets";

/**
 * A custom widget as a blank inspection starts with: supply by carrier.
 * Its map view is seeded from the main Model map, so switching it to a map
 * opens over the area the user was looking at.
 */
export function blankCustomItem(): CustomItem {
  return newCustomItem({
    title: "",
    subtitle: "",
    query: defaultQuery(),
    chart: "bar",
    mapViewState: useProjectStore.getState().viewState,
  });
}
