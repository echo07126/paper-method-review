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

export interface DocumentResponse {
  document_id: string;
  source_name: string | null;
  sections: Section[];
  paragraphs: Array<{ index: number; text: string }>;
  warnings: string[];
  parser: string | null;
}

export interface ChatResponse {
  answer: string;
  source: "llm" | "fallback";
  tokens?: Record<string, number> | null;
  note?: string | null;
}
