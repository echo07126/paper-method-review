export type Severity = "high" | "mid" | "low";
export type Verdict = "pass" | "problem" | "not_applicable" | "uncertain";

export interface Section {
  id: string;
  title: string;
  paragraph_index: number;
  needs_review?: boolean;
}

export interface Anchor {
  paragraph_index: number;
  sentence_index?: number | null;
}

export interface Finding {
  finding_id: string;
  checklist_item_id: string;
  verdict: Verdict;
  severity: Severity;
  headline: string;
  description?: string;
  suggestion?: string;
  anchors: Anchor[];
  evidence_elements?: string[];
  /** 「修改后展示」（可选）：把建议落实为可直接对照的改写示例 */
  suggested_revision?: string;
  provenance?: Record<string, unknown>;
}

export interface ReviewReport {
  report_id: string;
  document_name: string;
  checklist_version: string;
  findings: Finding[];
  counts: Record<string, number>;
  duration_ms: number;
  tokens: Record<string, number>;
  notes: string[];
  figure_references: number;
  demote_on_figures: boolean;
  paper_type: string;
}

export interface UploadResponse {
  document_id: string;
  parser: string;
  sections: Section[];
  paragraph_count: number;
  citation_count: number;
  reference_count: number;
  warnings: string[];
}

export interface SectionSummary {
  title: string;
  paragraph_index: number;
  needs_review?: boolean;
}

export interface ReviewCreateResponse {
  report_id: string;
  counts: Record<string, number>;
  duration_ms: number;
  tokens: Record<string, number>;
  notes: string[];
  figure_references: number;
  demote_on_figures: boolean;
  paper_type: string;
}

export interface ReportSummary {
  report_id: string;
  document_id: string;
  document_name: string | null;
  counts: Record<string, number>;
  created_at: string;
}

export interface Table {
  id: string;
  index: number;
  caption: string;
  rows: Array<Array<string | null>>;
  header_rows: number;
  n_rows: number;
  n_cols: number;
  anchor: Anchor;
}

export interface DocumentResponse {
  document_id: string;
  source_name: string | null;
  sections: Section[];
  paragraphs: Array<{ index: number; text: string }>;
  tables: Table[];
  warnings: string[];
  parser: string | null;
}

export interface CompareFinding {
  checklist_item_id: string;
  headline: string;
  severity: Severity;
  verdict: Verdict;
  anchors: Anchor[];
  description?: string;
  suggestion?: string;
  suggested_revision?: string;
}

export interface CompareResponse {
  before: Record<string, number>;
  after: Record<string, number>;
  resolved: string[];
  new: string[];
  kept: string[];
  before_findings: CompareFinding[];
  after_findings: CompareFinding[];
  resolved_findings: CompareFinding[];
  new_findings: CompareFinding[];
  kept_findings: CompareFinding[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  answer: string;
  source: "llm" | "fallback";
  tokens?: Record<string, number> | null;
  note?: string | null;
  session_id: string;
  history: ChatMessage[];
  truncated: boolean;
  /** finding = 针对某条审查问题；fulltext = 基于全文的自由提问 */
  scope: "finding" | "fulltext";
}
