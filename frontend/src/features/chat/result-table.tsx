import { ROW_LIMIT, type SqlResult } from "./run-sql";

// The rows of a query the model wrote, as a small table inside a chat reply.
// At most ROW_LIMIT rows, so nothing is virtualised.

const NUMBER = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 4 });

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return NUMBER.format(value);
  if (value instanceof Date) return value.toISOString().replace("T", " ").slice(0, 16);
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function ResultTable({ result }: { result: SqlResult }) {
  if (result.rows.length === 0) {
    return <div className="text-surface-400 py-1">The query returned no rows.</div>;
  }

  const cell = "border-b border-surface-700/60 px-2 py-0.5 whitespace-nowrap";
  return (
    <div>
      <div className="border-surface-600 bg-surface-900/60 max-h-64 overflow-auto rounded border">
        <table className="w-full border-collapse text-[11px]">
          <thead className="bg-surface-800 text-surface-300 sticky top-0 text-left">
            <tr>
              {result.columns.map((column) => (
                <th key={column} className="border-surface-600 border-b px-2 py-1 font-medium">
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, index) => (
              <tr key={index} className="text-surface-200">
                {result.columns.map((column) => (
                  <td
                    key={column}
                    className={`${cell} ${typeof row[column] === "number" ? "text-right tabular-nums" : ""}`}
                  >
                    {cellText(row[column])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="text-surface-400 pt-0.5 text-[10px]">
        {result.truncated
          ? `The first ${ROW_LIMIT} rows`
          : `${result.rows.length} ${result.rows.length === 1 ? "row" : "rows"}`}
      </div>
    </div>
  );
}
