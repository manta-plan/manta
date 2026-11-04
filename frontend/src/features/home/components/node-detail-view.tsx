import { LuEye } from "react-icons/lu";
import type { PlaybookStageNodeConfig } from "../data/playbooks";

// Read-only on purpose: a playbook only defines which parameters a stage
// takes. Their values are set on a run's detail page, before it starts.
export function NodeDetailView({ node }: { node: PlaybookStageNodeConfig | undefined }) {
  if (!node) {
    return (
      <div className="text-surface-400 flex flex-1 items-center justify-center p-4 text-center text-[12px]">
        Select a node on the canvas to see its details.
      </div>
    );
  }

  const { data } = node;

  return (
    <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-3">
      <div className="border-accent-500/30 bg-accent-600/10 text-surface-300 flex gap-2 rounded border px-2.5 py-2 text-[11px] leading-4">
        <LuEye size={13} className="text-accent-400 mt-px shrink-0" />
        <p>
          <span className="text-surface-100 font-medium">Preview only.</span> Parameter values are
          set on a run's detail page, before the run starts.
        </p>
      </div>

      <PreviewField label="Label" value={data.title} />
      <PreviewField label="Type" value={data.subtitle} />

      {data.tags && data.tags.length > 0 && (
        <>
          <div className="text-surface-400 mt-1 text-[11px] font-semibold tracking-wide uppercase">
            Parameters
          </div>
          {data.tags.map((tag) => (
            <PreviewField key={tag} label={tag} value="Set per run" mono muted />
          ))}
        </>
      )}
    </div>
  );
}

function PreviewField({
  label,
  value,
  mono,
  muted,
}: {
  label: string;
  value: string;
  mono?: boolean;
  muted?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className={`text-surface-400 text-[11px] font-medium ${mono ? "font-mono" : ""}`}>
        {label}
      </span>
      <div
        className={`border-surface-600 rounded border border-dashed px-2.5 py-1.5 text-[13px] ${muted ? "text-surface-500 italic" : "text-surface-200"}`}
      >
        {value}
      </div>
    </div>
  );
}
