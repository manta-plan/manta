import { LuDatabase } from "react-icons/lu";
import { useRecordCatalogue } from "../lib/use-record-catalogue";
import type { RecordSummary } from "../lib/record-server";
import { HomeCard, HomeSectionFrame, StatusPill } from "../components/home-primitives";
import { SectionHeader } from "../components/section-header";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

function formatDate(iso: string | null): string {
  return iso
    ? new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      })
    : "—";
}

function RecordRow({ record }: { record: RecordSummary }) {
  return (
    <tr className="border-surface-700 hover:bg-surface-800/60 border-b last:border-0">
      <td className="px-4 py-2.5" title={record.description || undefined}>
        <span className="text-surface-50 flex items-center gap-2">
          <LuDatabase size={14} className="text-accent-400 shrink-0" />
          {record.label}
        </span>
        {record.label !== record.id && (
          <span className="text-surface-500 ml-6 block font-mono text-[11px]">{record.id}</span>
        )}
      </td>
      <td className="text-surface-300 px-4 py-2.5" title={record.revisions.join("\n")}>
        {record.revisions.length}
      </td>
      <td className="text-surface-300 px-4 py-2.5" title={`${record.files.toLocaleString()} files`}>
        {formatBytes(record.size)}
      </td>
      <td className="text-surface-300 px-4 py-2.5">{formatDate(record.modified)}</td>
      <td className="px-4 py-2.5" title={record.error ?? undefined}>
        {record.error ? (
          <span className="text-danger-500 text-[11px]">Failed to open</span>
        ) : record.open ? (
          <StatusPill tone="ok">Open</StatusPill>
        ) : (
          <span title="It opens when a project first uses it, which takes a few seconds">
            <StatusPill>Opens on first use</StatusPill>
          </span>
        )}
      </td>
    </tr>
  );
}

// The records the record server serves: datarecord stores an admin uploads
// to its bucket. A project picks one when it's created.
export function DataCatalogSection() {
  const { catalogue, error } = useRecordCatalogue();

  return (
    <HomeSectionFrame>
      <SectionHeader
        title="Data Catalog"
        description="Data records on the record server, ready to use in a project."
      />

      <HomeCard className="overflow-hidden p-0">
        <table className="w-full text-left text-[12px]">
          <thead>
            <tr className="border-surface-700 bg-surface-800 text-surface-400 border-b text-[11px] tracking-wide uppercase">
              <th className="px-4 py-2 font-medium">Name</th>
              <th className="px-4 py-2 font-medium">Revisions</th>
              <th className="px-4 py-2 font-medium">Size</th>
              <th className="px-4 py-2 font-medium">Modified</th>
              <th className="px-4 py-2 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {catalogue?.records.map((record) => (
              <RecordRow key={record.id} record={record} />
            ))}
            {(!catalogue || catalogue.records.length === 0) && (
              <tr>
                <td
                  colSpan={5}
                  className="text-surface-400 px-4 py-8 text-center"
                  title={error ?? undefined}
                >
                  {error
                    ? "Can't reach the record server."
                    : catalogue
                      ? "No records yet."
                      : "Loading records…"}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </HomeCard>
    </HomeSectionFrame>
  );
}
