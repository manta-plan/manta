import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useParams } from "wouter";
import { Menubar } from "@base-ui/react/menubar";
import { Tabs } from "@base-ui/react/tabs";
import { Toolbar } from "@base-ui/react/toolbar";
import {
  LuRuler,
  LuSquare,
  LuBan,
  LuMap,
  LuEarth,
  LuSatellite,
  LuZoomIn,
  LuZoomOut,
  LuCompass,
  LuSearch,
  LuChevronRight,
  LuLayers,
  LuShare2,
  LuSun,
  LuMoon,
  LuMessageSquareText,
  LuNetwork,
  LuGitCommitVertical,
  LuShapes,
} from "react-icons/lu";
import { FaFly } from "react-icons/fa";
import { MenuDropdown, type MenuAction } from "./menu-dropdown";
import { ToolbarIconButton } from "./toolbar-icon-button";
import { ToolbarModeMenu, type ToolbarModeOption } from "./toolbar-mode-menu";
import { ToolbarActionMenu, type ToolbarActionOption } from "./toolbar-action-menu";
import { FeedbackDialog } from "../../home/components/feedback-dialog";
import { AboutDialog } from "./about-dialog";
import { KeyboardShortcutsDialog } from "./keyboard-shortcuts-dialog";
import { useAppStore } from "../../home/store";
import { useProjectStore, type BasemapId, type ToolId } from "../store/project-store";
import {
  getActiveProjectTab,
  projectRunHref,
  projectTabHref,
  type ProjectTab,
} from "../lib/project-route";
import { startModelWorkspaceTour } from "../lib/workspace-tours";
import { zoneLevels } from "../lib/record-geo";
import { selectableScenarios } from "../lib/record-scenarios";
import { NODAL } from "../store/types";
import { MantaLogo } from "../../home/components/manta-logo";
import { RaiIcon } from "./rai-mascot";

// Inspect and Report join once their tabs are built.
const TABS: { id: ProjectTab; label: string }[] = [
  { id: "model", label: "Model" },
  { id: "run", label: "Run" },
];

const MEASURE_OPTIONS: ToolbarModeOption<ToolId>[] = [
  { value: "select", label: "Off", icon: LuBan },
  { value: "measure-distance", label: "Distance", icon: LuRuler },
  { value: "measure-area", label: "Area", icon: LuSquare },
];

const BASEMAP_OPTIONS: ToolbarModeOption<BasemapId>[] = [
  { value: "vector-dark", label: "Dark", icon: LuMoon },
  { value: "vector-light", label: "Light", icon: LuSun },
  { value: "satellite", label: "Satellite", icon: LuSatellite },
];

export function Header() {
  const [location, setLocation] = useLocation();
  const { projectId } = useParams<{ projectId: string }>();
  const activeTab = getActiveProjectTab(location);
  const project = useAppStore((s) => s.projects.find((p) => p.id === projectId));
  const activeTool = useProjectStore((s) => s.activeTool);
  const setActiveTool = useProjectStore((s) => s.setActiveTool);
  const isMeasuring = activeTool === "measure-distance" || activeTool === "measure-area";
  const basemap = useProjectStore((s) => s.basemap);
  const setBasemap = useProjectStore((s) => s.setBasemap);
  const viewState = useProjectStore((s) => s.viewState);
  const setViewState = useProjectStore((s) => s.setViewState);
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const utilityDrawerFlow = useProjectStore((s) => s.utilityDrawerFlow);
  const toggleUtilityDrawer = useProjectStore((s) => s.toggleUtilityDrawer);
  const isMapLayersDrawerOpen = useProjectStore((s) => s.isMapLayersDrawerOpen);
  const toggleMapLayersDrawer = useProjectStore((s) => s.toggleMapLayersDrawer);

  const record = useProjectStore((s) => s.record);
  const resolution = useProjectStore((s) => s.resolution);
  const setResolution = useProjectStore((s) => s.setResolution);
  // Nodal, plus each busmap zone level in the record that groups locations.
  const resolutionOptions = useMemo<ToolbarModeOption<string>[]>(
    () => [
      { value: NODAL, label: "Nodal", icon: LuNetwork },
      ...(record ? zoneLevels(record) : []).map(({ level, zones }) => ({
        value: level,
        label: `Zones (${zones})`,
        icon: LuShapes,
      })),
    ],
    [record],
  );

  // The record's scenarios the page can show; the shown one stays visible here
  // with the sidebar's Scenarios panel collapsed.
  const showScenario = useProjectStore((s) => s.showScenario);
  const switchingScenario = useProjectStore((s) => s.switchingScenario);
  const scenarioOptions = useMemo<ToolbarModeOption<string>[]>(
    () =>
      (record ? selectableScenarios(record.info) : []).map((revision) => ({
        value: revision.name,
        label: revision.label,
        icon: LuGitCommitVertical,
      })),
    [record],
  );

  const zoomBy = (delta: number) =>
    setViewState({ ...viewState, zoom: Math.max(0, viewState.zoom + delta) });
  const resetBearing = () => setViewState({ ...viewState, bearing: 0, pitch: 0 });

  const mapActions: ToolbarActionOption[] = [
    { label: "Zoom In", icon: LuZoomIn, onSelect: () => zoomBy(1) },
    { label: "Zoom Out", icon: LuZoomOut, onSelect: () => zoomBy(-1) },
    { label: "Rotate North", icon: LuCompass, onSelect: resetBearing },
    { label: "Search Location…", icon: LuSearch },
  ];

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isShortcutsDialogOpen, setIsShortcutsDialogOpen] = useState(false);
  const [isAboutDialogOpen, setIsAboutDialogOpen] = useState(false);
  const [isFeedbackDialogOpen, setIsFeedbackDialogOpen] = useState(false);
  const openWelcomeDialog = useProjectStore((s) => s.openWelcomeDialog);

  useEffect(() => {
    const onFullscreenChange = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  const toggleFullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else document.documentElement.requestFullscreen();
  };

  // Map entries only on the Model tab, the one page with a map.
  const viewMenuItems: MenuAction[] = [
    ...(activeTab === "model"
      ? [
          { label: "Map Layers", onSelect: toggleMapLayersDrawer },
          { label: "Zoom In", onSelect: () => zoomBy(1) },
          { label: "Zoom Out", onSelect: () => zoomBy(-1) },
          { label: "Rotate North", onSelect: resetBearing, separatorAfter: true },
        ]
      : []),
    { label: theme === "dark" ? "Light Theme" : "Dark Theme", onSelect: toggleTheme },
    {
      label: isFullscreen ? "Exit Fullscreen" : "Enter Fullscreen",
      shortcut: "F11",
      onSelect: toggleFullscreen,
    },
  ];

  const goToTab = (tab: ProjectTab) =>
    setLocation(tab === "run" ? projectRunHref(projectId) : projectTabHref(projectId, tab));

  // Plain-key shortcuts, listed in KeyboardShortcutsDialog. They stay out of
  // the way of typing, browser chords and any open dialog.
  const shortcutHandler = useRef<(event: KeyboardEvent) => void>(() => {});
  shortcutHandler.current = (event) => {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (document.querySelector('[role="dialog"]')) return;
    const tab = TABS[Number(event.key) - 1];
    if (tab) goToTab(tab.id);
    else if (event.key === "?") setIsShortcutsDialogOpen(true);
    else if (activeTab === "model" && event.key.toLowerCase() === "l") toggleMapLayersDrawer();
    else if (activeTab === "model" && (event.key === "+" || event.key === "=")) zoomBy(1);
    else if (activeTab === "model" && (event.key === "-" || event.key === "_")) zoomBy(-1);
    else return;
    event.preventDefault();
  };
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => shortcutHandler.current(event);
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const menus = [
    { label: "View", items: viewMenuItems },
    {
      label: "Help",
      items: [
        { label: "Welcome…", onSelect: openWelcomeDialog },
        {
          label: "Keyboard Shortcuts",
          shortcut: "?",
          onSelect: () => setIsShortcutsDialogOpen(true),
          separatorAfter: true,
        },
        { label: "Send Feedback…", onSelect: () => setIsFeedbackDialogOpen(true) },
        { label: "About", onSelect: () => setIsAboutDialogOpen(true) },
      ],
    },
  ];

  return (
    <>
      <header className="border-surface-600 bg-surface-800 relative flex h-11 shrink-0 items-center gap-4 border-b px-2">
        {/* Brand + Menubar */}
        <div className="flex shrink-0 items-center gap-3">
          <div className="flex items-center gap-1">
            <Link
              href="/"
              className="hover:bg-surface-700 focus-visible:bg-surface-700 flex h-7 items-center rounded px-2 outline-none"
              title="Manta – back to home"
              aria-label="Manta – back to home"
            >
              <MantaLogo wordmark={false} markHeight={18} />
            </Link>
            <Link
              href="/"
              className="text-surface-200 hover:bg-surface-700 hover:text-surface-50 focus-visible:bg-surface-700 rounded px-1.5 py-1 text-[13px] outline-none"
            >
              Projects
            </Link>
            {project && (
              <>
                <span aria-hidden className="text-surface-500">
                  /
                </span>
                <span
                  className="text-surface-50 max-w-[140px] truncate px-1 text-[13px] font-medium"
                  title={project.name}
                >
                  {project.name}
                </span>
              </>
            )}
          </div>
          <div aria-hidden className="bg-surface-600 h-5 w-px" />
          <Menubar className="flex items-center gap-0.5">
            {menus.map((menu) => (
              <MenuDropdown key={menu.label} label={menu.label} items={menu.items} />
            ))}
          </Menubar>
        </div>

        {/* Center tab control — absolutely positioned so it's centered on the
          full header width regardless of how wide the brand/menubar and
          toolbar regions are, rather than centered within the leftover
          flex space between two unequal-width siblings. */}
        <div className="absolute top-0 left-1/2 flex h-full -translate-x-1/2 items-center">
          <Tabs.Root value={activeTab} className="relative">
            <Tabs.List className="bg-surface-900 relative isolate flex items-center gap-1 rounded-md p-1">
              {TABS.map((tab, index) => (
                <div key={tab.id} className="relative z-10 flex items-center">
                  <Tabs.Tab
                    value={tab.id}
                    onClick={() => goToTab(tab.id)}
                    // aria-selected text is fixed white, not the theme-following
                    // text-surface-50 — the indicator behind it is a constant
                    // brand blue in both themes, so the text color must be too.
                    className="text-surface-300 rounded px-4 py-1 text-[12px] font-medium transition-colors outline-none aria-selected:text-white"
                  >
                    {tab.label}
                  </Tabs.Tab>
                  {index < TABS.length - 1 && (
                    <LuChevronRight
                      aria-hidden
                      size={12}
                      className="text-surface-600 mr-0.5 -ml-1"
                    />
                  )}
                </div>
              ))}
              <Tabs.Indicator className="bg-accent-600 absolute top-1 bottom-1 left-[var(--active-tab-left)] z-0 w-[var(--active-tab-width)] rounded transition-all duration-200" />
            </Tabs.List>
          </Tabs.Root>
        </div>

        {/* Right toolbar */}
        <Toolbar.Root className="ml-auto flex shrink-0 items-center gap-1 pr-1">
          {activeTab === "model" && (
            <>
              <Toolbar.Group className="flex items-center gap-0.5">
                <ToolbarActionMenu label="Map Actions" icon={LuMap} options={mapActions} />
                <ToolbarModeMenu
                  label="Measure Tool"
                  options={MEASURE_OPTIONS}
                  value={activeTool}
                  onChange={setActiveTool}
                  active={isMeasuring}
                  triggerIcon={isMeasuring ? undefined : LuRuler}
                />
                <ToolbarModeMenu
                  label="Basemap"
                  options={BASEMAP_OPTIONS}
                  value={basemap}
                  onChange={setBasemap}
                  triggerIcon={LuEarth}
                />
                {scenarioOptions.length > 0 && (
                  <ToolbarModeMenu
                    label="Scenario"
                    options={scenarioOptions}
                    value={switchingScenario ?? record?.scenario ?? scenarioOptions[0].value}
                    onChange={showScenario}
                    disabled={scenarioOptions.length < 2}
                    disabledHint="the only one in this record"
                  />
                )}
                <ToolbarModeMenu
                  label="Resolution"
                  options={resolutionOptions}
                  value={resolution}
                  onChange={setResolution}
                  disabled={resolutionOptions.length < 2}
                  disabledHint="the only one in this record"
                />
                <ToolbarIconButton
                  icon={LuLayers}
                  label="Map Layers"
                  active={isMapLayersDrawerOpen}
                  onClick={toggleMapLayersDrawer}
                  tourId="map-layers-toggle"
                />
              </Toolbar.Group>

              <Toolbar.Separator className="bg-surface-600 mx-1 h-5 w-px" />
            </>
          )}

          {/* Project-wide actions */}
          <Toolbar.Group className="flex items-center gap-0.5">
            <ToolbarIconButton
              icon={FaFly}
              label="Start tour"
              disabled={activeTab !== "model"}
              onClick={startModelWorkspaceTour}
            />
            <ToolbarIconButton
              icon={theme === "dark" ? LuMoon : LuSun}
              label={theme === "dark" ? "Switch to Light Theme" : "Switch to Dark Theme"}
              onClick={toggleTheme}
            />
            <ToolbarIconButton
              icon={LuMessageSquareText}
              label="Send Feedback"
              onClick={() => setIsFeedbackDialogOpen(true)}
            />
          </Toolbar.Group>

          <Toolbar.Separator className="bg-surface-600 mx-1 h-5 w-px" />

          {/* Right drawer (utility layer) controllers */}
          <Toolbar.Group className="flex items-center gap-0.5">
            <ToolbarIconButton
              icon={LuShare2}
              label="Share"
              active={utilityDrawerFlow === "share"}
              onClick={() => toggleUtilityDrawer("share")}
            />
            <ToolbarIconButton
              icon={RaiIcon}
              label="Ask Rai"
              active={utilityDrawerFlow === "ai-chat"}
              onClick={() => toggleUtilityDrawer("ai-chat")}
            />
          </Toolbar.Group>
        </Toolbar.Root>
      </header>
      <FeedbackDialog open={isFeedbackDialogOpen} onOpenChange={setIsFeedbackDialogOpen} />
      <KeyboardShortcutsDialog
        open={isShortcutsDialogOpen}
        onOpenChange={setIsShortcutsDialogOpen}
      />
      <AboutDialog open={isAboutDialogOpen} onOpenChange={setIsAboutDialogOpen} />
    </>
  );
}
