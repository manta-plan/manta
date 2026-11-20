import { LuDatabase, LuFolder } from "react-icons/lu";
import type { ComponentType } from "react";
import type { IconType } from "react-icons";
import { ProjectsSection } from "./sections/projects-section";
import { DataCatalogSection } from "./sections/data-catalog-section";

export type HomeRouteId = "projects" | "data";

export interface HomeRouteDefinition {
  id: HomeRouteId;
  path: string;
  label: string;
  icon: IconType;
  Component: ComponentType;
}

export const HOME_ROUTES: HomeRouteDefinition[] = [
  { id: "projects", path: "/", label: "Projects", icon: LuFolder, Component: ProjectsSection },
  {
    id: "data",
    path: "/data",
    label: "Data Catalog",
    icon: LuDatabase,
    Component: DataCatalogSection,
  },
];

export function getHomeRoute(path: string) {
  return HOME_ROUTES.find((route) => route.path === path) ?? HOME_ROUTES[0];
}
