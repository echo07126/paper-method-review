"""前端类型与后端 DTO 对齐：补 ReviewCreateResponse / ReportSummary / DocumentResponse / ChatResponse 并替换内联类型。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"

types_path = FRONTEND / "api" / "types.ts"
types_text = types_path.read_text(encoding="utf-8")
extra = '''

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
'''
if "ReviewCreateResponse" not in types_text:
    types_path.write_text(types_text.rstrip() + extra, encoding="utf-8")
    print("types.ts 已补充接口类型")

parse_path = FRONTEND / "views" / "ParseView.vue"
text = parse_path.read_text(encoding="utf-8")
text = text.replace('import client from "@/api/client";', 'import client from "@/api/client";\nimport type { ReviewCreateResponse } from "@/api/types";')
text = text.replace('client.post<{ report_id: string }>("/reviews", {', 'client.post<ReviewCreateResponse>("/reviews", {')
parse_path.write_text(text, encoding="utf-8")

report_path = FRONTEND / "views" / "ReportView.vue"
text = report_path.read_text(encoding="utf-8")
text = text.replace('import type { Finding, ReviewReport } from "@/api/types";', 'import type { ChatResponse, DocumentResponse, Finding, ReviewReport } from "@/api/types";')
text = text.replace('''    const { data } = await client.get<{ paragraphs: Array<{ index: number; text: string }> }>(
      `/documents/${store.documentId}`,
    );''', '''    const { data } = await client.get<DocumentResponse>(`/documents/${store.documentId}`);''')
text = text.replace('client.post<{ answer: string }>(`/reports/${reportId}/chat`, {', 'client.post<ChatResponse>(`/reports/${reportId}/chat`, {')
report_path.write_text(text, encoding="utf-8")

compare_path = FRONTEND / "views" / "CompareView.vue"
text = compare_path.read_text(encoding="utf-8")
text = text.replace('''interface ReportSummary {
  report_id: string;
  document_name: string;
  counts: Record<string, number>;
  created_at: string;
}

''', '')
text = text.replace('import client from "@/api/client";', 'import client from "@/api/client";\nimport type { ReportSummary } from "@/api/types";')
compare_path.write_text(text, encoding="utf-8")
print("views 已改为使用共享类型")
