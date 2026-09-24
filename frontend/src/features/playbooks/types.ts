export type PlaybookStatus = "available" | "coming_soon";

export type PlaybookSummary = {
  id: string;
  name: string;
  description: string;
  status: PlaybookStatus;
};

export type PlaybookNodeConfigField = {
  key: string;
  label: string;
  type: "integer";
  required: boolean;
  min: number | null;
  default: number | null;
};

export type PlaybookNode = {
  id: string;
  type: string;
  label: string;
  config: PlaybookNodeConfigField[];
};

export type PlaybookDetail = PlaybookSummary & {
  nodes: PlaybookNode[];
};

export type ListPlaybooksResponse = {
  items: PlaybookSummary[];
};
