import { LuWorkflow, LuGlobe, LuLock } from "react-icons/lu";
import { INITIAL_PLAYBOOKS } from "../data/playbooks";
import { HomeCardLink, HomeSectionFrame } from "../components/home-primitives";
import { SectionHeader } from "../components/section-header";

export function PlaybooksSection() {
  return (
    <HomeSectionFrame>
      <SectionHeader
        title="Playbooks"
        description="Reusable modeling pipelines that define how a run's stages connect."
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
        {INITIAL_PLAYBOOKS.map((playbook) => (
          <HomeCardLink key={playbook.id} href={`/playbook/${playbook.id}`}>
            <div className="flex items-center justify-between">
              <LuWorkflow size={22} className="text-accent-400" />
              <span className="border-surface-600 bg-surface-700 text-surface-300 flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px]">
                {playbook.visibility === "public" ? <LuGlobe size={10} /> : <LuLock size={10} />}
                {playbook.visibility === "public" ? "Public" : "Private"}
              </span>
            </div>
            <div>
              <div className="text-surface-50 text-[13px] font-medium">{playbook.name}</div>
              <div className="text-surface-400 mt-0.5 text-[11px]">{playbook.description}</div>
            </div>
          </HomeCardLink>
        ))}
      </div>
    </HomeSectionFrame>
  );
}
