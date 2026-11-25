export interface DocumentationHeading {
  depth: 2 | 3;
  id: string;
  label: string;
}

export interface DocumentationDocument {
  id: string;
  title: string;
  description: string;
  sourcePath: string;
  content: string;
  headings: DocumentationHeading[];
}

const DOCUMENT_ORDER = [
  "raw-data-schema",
  "data-transformation",
  "duckdb-project-schema",
  "report-builder",
];

const DOCUMENT_DESCRIPTIONS: Record<string, string> = {
  "raw-data-schema":
    "The datarecord records Manta reads: stores, revisions, layers, dimensions and attributes.",
  "data-transformation": "How the record server opens a record and how the app reads it.",
  "duckdb-project-schema": "The catalogs, schemas and views a record is queried through.",
  "report-builder":
    "Building a paper report from Inspect widgets: templates, layout, themes, undo and PDF export.",
};

const rawDocuments = import.meta.glob("../../docs/**/*.md", {
  eager: true,
  query: "?raw",
  import: "default",
}) as Record<string, string>;

export function slugify(value: string) {
  return (
    value
      .toLowerCase()
      .replace(/[`*_~]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "") || "section"
  );
}

function plainText(value: string) {
  return value
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[`*_~]/g, "")
    .trim();
}

function extractHeadings(content: string): DocumentationHeading[] {
  const occurrences = new Map<string, number>();
  const headings: DocumentationHeading[] = [];
  let inCodeBlock = false;

  for (const line of content.split("\n")) {
    if (line.trimStart().startsWith("```")) {
      inCodeBlock = !inCodeBlock;
      continue;
    }
    if (inCodeBlock) continue;

    const match = line.match(/^(#{2,3})\s+(.+?)\s*#*\s*$/);
    if (!match) continue;
    const label = plainText(match[2]);
    const baseId = slugify(label);
    const count = (occurrences.get(baseId) ?? 0) + 1;
    occurrences.set(baseId, count);
    headings.push({
      depth: match[1].length as 2 | 3,
      id: count === 1 ? baseId : `${baseId}-${count}`,
      label,
    });
  }

  return headings;
}

function titleFromContent(content: string, fallback: string) {
  const heading = content.match(/^#\s+(.+?)\s*$/m)?.[1];
  return heading ? plainText(heading) : fallback;
}

export const DOCUMENTS: DocumentationDocument[] = Object.entries(rawDocuments)
  .map(([sourcePath, content]) => {
    const id = sourcePath.split("/").at(-1)?.replace(/\.md$/, "") ?? sourcePath;
    return {
      id,
      title: titleFromContent(content, id),
      description: DOCUMENT_DESCRIPTIONS[id] ?? "Manta product and data documentation.",
      sourcePath,
      content,
      headings: extractHeadings(content),
    };
  })
  .sort((left, right) => DOCUMENT_ORDER.indexOf(left.id) - DOCUMENT_ORDER.indexOf(right.id));

export function documentationHref(id: string) {
  return `/documentation/${id}`;
}
