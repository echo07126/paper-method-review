export type Severity = "high" | "mid" | "low";
/** 确定性等级：与 severity 正交，衡量结论的可靠程度 */
export type Certainty = "deterministic" | "suspected" | "undetermined";
/** 输出质量分档：A 高置信 / B 中置信 / C 低置信 / D 待确认 */
export type Grade = "A" | "B" | "C" | "D";
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
  certainty?: Certainty;
  headline: string;
  description?: string;
  suggestion?: string;
  anchors: Anchor[];
  evidence_elements?: string[];
  provenance?: Record<string, unknown>;
  /** 输出质量：0–1 连续置信度与 A/B/C/D 分档 */
  confidence?: number;
  grade?: Grade;
}

/** 质量卡：分级分布、门控分布、平均置信度与审查率 */
export interface ReportQuality {
  grades?: Record<string, number>;
  gate_reasons?: Record<string, number>;
  avg_confidence?: number;
  assessed_items?: number;
  applicable_items?: number;
  review_rate?: number;
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
  quality?: ReportQuality;
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
  quality?: ReportQuality;
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
  certainty?: Certainty;
  verdict: Verdict;
  anchors: Anchor[];
  description?: string;
  suggestion?: string;
  /** rewritten=示范改写已落到修改稿；manual=依赖图表/数据需作者确认；pending=未定位到段落 */
  revision_status?: "rewritten" | "manual" | "pending";
  revision_note?: string;
}

export interface CompareRequest {
  before_report_id: string;
  after_report_id?: string | null;
  use_llm?: boolean;
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

/** 重接口入队响应（HTTP 202）：轮询 poll_url 取任务结果 */
export interface TaskAccepted {
  task_id: string;
  state: string;
  kind: string;
  /** 相对 API 前缀（/api/v1）的轮询路径，如 /tasks/job_xxx */
  poll_url: string;
}

/** 任务状态：succeeded 时 result 为旧同步响应体；failed 时 error 带 code/message */
export interface TaskStatusResponse<T = Record<string, unknown>> {
  task_id: string;
  kind: string;
  state: string;
  result: T | null;
  error: { code: string; message: string } | null;
  created_at: string;
  updated_at: string;
}
