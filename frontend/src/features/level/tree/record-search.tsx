// STUB: replaced by the real port of baby-manta's components/RecordSearch.tsx.
export function RecordSearchBox({
  term,
  onChange,
  placeholder = "Find an entity, carrier or location",
}: {
  term: string;
  onChange: (term: string) => void;
  placeholder?: string;
}) {
  return (
    <input
      value={term}
      onChange={(event) => onChange(event.target.value)}
      placeholder={placeholder}
      aria-label="Search the record"
      className="border-surface-600 bg-surface-900 text-surface-100 m-2 h-7 rounded border px-2 text-[12px]"
    />
  );
}

export function RecordSearchResults(_props: { term: string; period: string }) {
  return <div className="text-surface-400 p-3 text-[12px]">Search results not ported yet</div>;
}
