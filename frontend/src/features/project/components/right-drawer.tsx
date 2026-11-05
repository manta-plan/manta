import clsx from "clsx";
import type { IconType } from "react-icons";
import {
  LuX,
  LuShare2,
  LuCopy,
  LuMail,
  LuLink,
  LuGlobe,
  LuLock,
  LuDownload,
  LuLayers,
} from "react-icons/lu";
import { useProjectStore, type UtilityDrawerFlow } from "../store/project-store";
import { AiChatView } from "./ai-chat-view";
import { MapLayersPanel } from "./map-layers-panel";
import { RaiAnimated } from "./rai-mascot";

// Rai idles once each time the drawer opens.
const RaiTitleIcon = () => <RaiAnimated motion="idle" size={18} />;

const UTILITY_META: Record<UtilityDrawerFlow, { title: string; icon: IconType }> = {
  "ai-chat": { title: "Rai", icon: RaiTitleIcon },
  share: { title: "Share", icon: LuShare2 },
};

function SharePanel() {
  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-3">
      <section className="flex flex-col gap-2">
        <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
          Project Link
        </div>
        <div className="border-surface-600 bg-surface-900 flex items-center gap-2 rounded border px-2 py-1.5">
          <LuLink size={13} className="text-surface-400 shrink-0" />
          <span className="text-surface-200 min-w-0 flex-1 truncate text-[12px]">
            manta.app/projects/belgium-base-model
          </span>
          <button
            className="text-surface-400 hover:bg-surface-700 hover:text-surface-100 rounded p-1 outline-none"
            aria-label="Copy project link"
          >
            <LuCopy size={13} />
          </button>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
          Access
        </div>
        <div className="grid grid-cols-2 gap-2">
          <button className="border-accent-500 bg-accent-600/15 flex h-16 flex-col items-start justify-between rounded border p-2 text-left outline-none">
            <LuLock size={14} className="text-accent-300" />
            <span className="text-surface-100 text-[12px] font-medium">Private</span>
          </button>
          <button className="border-surface-600 bg-surface-900 hover:border-surface-500 flex h-16 flex-col items-start justify-between rounded border p-2 text-left outline-none">
            <LuGlobe size={14} className="text-surface-400" />
            <span className="text-surface-200 text-[12px] font-medium">Workspace</span>
          </button>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
          Invite
        </div>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder="name@company.com"
            className="border-surface-600 bg-surface-900 text-surface-100 placeholder:text-surface-500 focus:border-accent-500 h-8 min-w-0 flex-1 rounded border px-2 text-[12px] outline-none"
          />
          <button className="bg-accent-600 hover:bg-accent-500 flex h-8 items-center gap-1.5 rounded px-2.5 text-[12px] font-medium text-white outline-none">
            <LuMail size={13} />
            Invite
          </button>
        </div>
      </section>

      <section className="flex flex-col gap-2">
        <div className="text-surface-400 text-[11px] font-semibold tracking-wide uppercase">
          Export
        </div>
        <button className="border-surface-600 bg-surface-900 text-surface-200 hover:border-surface-500 hover:text-surface-100 flex h-8 items-center justify-between rounded border px-2 text-[12px] outline-none">
          <span>Download share snapshot</span>
          <LuDownload size={13} />
        </button>
      </section>

      <p className="border-surface-600/70 bg-surface-900/70 text-surface-400 mt-auto rounded border p-2 text-[11px] leading-4">
        Sharing controls are dummy for now. The layout is ready for project links, workspace access,
        invites, and snapshot export.
      </p>
    </div>
  );
}

export function RightDrawer() {
  const utilityDrawerFlow = useProjectStore((s) => s.utilityDrawerFlow);
  const closeUtilityDrawer = useProjectStore((s) => s.closeUtilityDrawer);
  const isMapLayersDrawerOpen = useProjectStore((s) => s.isMapLayersDrawerOpen);
  const toggleMapLayersDrawer = useProjectStore((s) => s.toggleMapLayersDrawer);

  const isUtilityOpen = utilityDrawerFlow !== null;
  const utilityMeta = utilityDrawerFlow ? UTILITY_META[utilityDrawerFlow] : null;
  const UtilityIcon = utilityMeta?.icon;

  return (
    <>
      {/* Layer 2 (detail): page-specific panels. Only the map layers for now;
          the widget and run node config forms arrive with their tabs. Stacks
          just inside layer 1 when it's open, otherwise hugs the right edge. */}
      <aside
        className={clsx(
          "absolute top-0 z-20 flex h-full w-72 flex-col border-l border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-all duration-200 ease-out",
          isUtilityOpen ? "right-72" : "right-0",
          isMapLayersDrawerOpen
            ? "translate-x-0 pointer-events-auto"
            : "translate-x-full pointer-events-none",
        )}
      >
        <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
          <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
            <LuLayers size={12} />
            Layers
          </div>
          <button
            onClick={toggleMapLayersDrawer}
            className="text-surface-400 hover:text-surface-100 outline-none"
          >
            <LuX size={14} />
          </button>
        </div>
        {isMapLayersDrawerOpen && <MapLayersPanel />}
      </aside>

      {/* Layer 1 (utility): AI chat, share. Always anchored to the true
          right edge, independent of whether the detail layer is open. */}
      <aside
        className={clsx(
          "absolute top-0 right-0 z-20 flex h-full w-72 flex-col border-l border-surface-600/60 bg-surface-800/70 backdrop-blur-xl transition-transform duration-200 ease-out",
          isUtilityOpen
            ? "translate-x-0 pointer-events-auto"
            : "translate-x-full pointer-events-none",
        )}
      >
        <div className="border-surface-600/60 flex h-8 shrink-0 items-center justify-between border-b px-3">
          <div className="text-surface-200 flex items-center gap-1.5 text-[11px] font-semibold tracking-wide uppercase">
            {UtilityIcon && <UtilityIcon size={12} />}
            {utilityMeta?.title ?? ""}
          </div>
          <button
            onClick={closeUtilityDrawer}
            className="text-surface-400 hover:text-surface-100 outline-none"
          >
            <LuX size={14} />
          </button>
        </div>
        <div className="flex flex-1 flex-col overflow-hidden">
          {utilityDrawerFlow === "ai-chat" ? (
            <AiChatView />
          ) : utilityDrawerFlow === "share" ? (
            <SharePanel />
          ) : (
            <div className="text-surface-400 flex flex-1 items-center justify-center p-4 text-center text-[12px]">
              {utilityMeta && `${utilityMeta.title} will appear here.`}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
