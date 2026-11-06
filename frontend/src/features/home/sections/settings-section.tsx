import { LuMoon, LuSun } from "react-icons/lu";
import { useAppStore } from "../store";
import { clearSession, useSessionUser } from "../../auth/session";
import { HomeCard, HomeSectionFrame } from "../components/home-primitives";
import { SectionHeader } from "../components/section-header";

export function SettingsSection() {
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const username = useSessionUser()?.username ?? "";

  return (
    <HomeSectionFrame maxWidthClassName="max-w-2xl">
      <SectionHeader title="Settings" description="Manage your profile and preferences." />

      <HomeCard className="mb-4 p-5">
        <h2 className="text-surface-400 mb-4 text-[11px] font-semibold tracking-wide uppercase">
          Profile
        </h2>
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-surface-400 text-[11px] font-medium">Username</span>
            <input
              readOnly
              value={username}
              className="border-surface-600 bg-surface-900 text-surface-50 focus:border-accent-500 rounded border px-2.5 py-1.5 text-[13px] outline-none"
            />
          </label>
        </div>
      </HomeCard>

      <HomeCard className="mb-4 p-5">
        <h2 className="text-surface-400 mb-4 text-[11px] font-semibold tracking-wide uppercase">
          Preferences
        </h2>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-surface-50 text-[13px] font-medium">Theme</div>
            <div className="text-surface-400 text-[11px]">Choose light or dark mode.</div>
          </div>
          <button
            onClick={toggleTheme}
            className="border-surface-600 text-surface-200 hover:bg-surface-700 flex h-8 items-center gap-1.5 rounded border px-3 text-[12px] font-medium"
          >
            {theme === "dark" ? <LuMoon size={14} /> : <LuSun size={14} />}
            {theme === "dark" ? "Dark" : "Light"}
          </button>
        </div>
      </HomeCard>

      <HomeCard className="p-5">
        <h2 className="text-surface-400 mb-4 text-[11px] font-semibold tracking-wide uppercase">
          Account
        </h2>
        <button
          onClick={clearSession}
          className="border-danger-500/40 text-danger-500 hover:bg-danger-500/10 rounded border px-3 py-1.5 text-[12px] font-medium"
        >
          Sign Out
        </button>
      </HomeCard>
    </HomeSectionFrame>
  );
}
