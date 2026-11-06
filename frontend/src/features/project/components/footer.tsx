import { useLocation } from "wouter";
import { LuWifi, LuWifiOff, LuLoaderCircle, LuCloud, LuCircleUser } from "react-icons/lu";
import { useSessionUser } from "../../auth/session";
import { useAppStore } from "../../home/store";
import { useProjectStore } from "../store/project-store";
import { getActiveProjectTab } from "../lib/project-route";

function ConnectionButton() {
  const connectionStatus = useProjectStore((s) => s.connectionStatus);
  const reconnect = useProjectStore((s) => s.reconnect);

  if (connectionStatus === "connecting") {
    return (
      <div className="flex items-center gap-1">
        <LuLoaderCircle size={11} className="animate-spin" />
        <span>Connecting…</span>
      </div>
    );
  }
  const connected = connectionStatus === "connected";
  return (
    <button
      type="button"
      onClick={reconnect}
      title="Reconnect to the record server"
      className={`flex cursor-pointer items-center gap-1 hover:underline ${connected ? "text-ok-500" : "text-danger-500"}`}
    >
      {connected ? <LuWifi size={11} /> : <LuWifiOff size={11} />}
      <span>{connected ? "Connected" : "Disconnected – Reconnect"}</span>
    </button>
  );
}

function formatCoord(v: number) {
  return v.toFixed(5);
}

export function Footer() {
  const [location] = useLocation();
  const activeTab = getActiveProjectTab(location);
  const cursorPosition = useProjectStore((s) => s.cursorPosition);
  const viewState = useProjectStore((s) => s.viewState);
  const statusMessage = useAppStore((s) => s.statusMessage);
  const username = useSessionUser()?.username;

  const mainView = activeTab === "model" ? "map" : "blank";

  return (
    <footer className="border-surface-600 bg-surface-800 text-surface-400 flex h-6 shrink-0 items-center justify-between border-t px-3 text-[11px]">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <LuCloud size={12} />
          <span>{statusMessage}</span>
        </div>
        <span className="text-surface-600">|</span>
        <div className="flex items-center gap-1.5">
          <LuCircleUser size={12} />
          <span>{username}</span>
        </div>
      </div>
      <div className="flex items-center gap-4">
        {mainView === "map" ? (
          <>
            <span>
              Lon/Lat:{" "}
              <span className="text-surface-200 font-mono">
                {cursorPosition
                  ? `${formatCoord(cursorPosition.lng)}, ${formatCoord(cursorPosition.lat)}`
                  : "—"}
              </span>
            </span>
            <span className="text-surface-600">|</span>
            <span>
              Zoom: <span className="text-surface-200 font-mono">{viewState.zoom.toFixed(2)}</span>
            </span>
            <span className="text-surface-600">|</span>
            <span>
              CRS: <span className="text-surface-200 font-mono">EPSG:3857</span>
            </span>
          </>
        ) : null}
        {mainView !== "blank" && <span className="text-surface-600">|</span>}
        <ConnectionButton />
      </div>
    </footer>
  );
}
