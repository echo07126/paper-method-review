import { defineStore } from "pinia";

import client from "@/api/client";
import type { ReportSummary, SectionSummary } from "@/api/types";

export const useSessionStore = defineStore("session", {
  state: () => ({
    documentId: "" as string,
    sections: [] as SectionSummary[],
    warnings: [] as string[],
    reportId: "" as string,
    /**
     * 逐报告记录 tokens 摘要。此前是单个全局字符串，打开历史报告时会把
     * 上一次审查（可能是另一篇论文、另一种模型开关）的消耗说明显示在当前报告上。
     */
    tokensSummaryByReport: {} as Record<string, string>,
    reports: [] as ReportSummary[],
  }),
  getters: {
    /** 当前报告对应的 tokens 摘要；无匹配时返回空串（不显示）。 */
    tokensSummary(state): string {
      return state.reportId ? state.tokensSummaryByReport[state.reportId] ?? "" : "";
    },
  },
  actions: {
    setUpload(documentId: string, sections: SectionSummary[], warnings: string[]) {
      this.documentId = documentId;
      this.sections = sections;
      this.warnings = warnings;
    },
    setReport(reportId: string) {
      this.reportId = reportId;
    },
    /** 打开历史报告时同步其所属文档，保证原文预览与报告一致。 */
    setDocument(documentId: string) {
      this.documentId = documentId;
    },
    setTokens(reportId: string, tokensSummary: string) {
      this.tokensSummaryByReport = { ...this.tokensSummaryByReport, [reportId]: tokensSummary };
    },
    setReports(reports: ReportSummary[]) {
      this.reports = reports;
    },
    /** 拉取当前会话的报告历史；失败时静默返回空列表（不阻断主流程）。 */
    async fetchReports(): Promise<ReportSummary[]> {
      try {
        const { data } = await client.get<ReportSummary[]>("/reports");
        this.reports = data;
      } catch {
        this.reports = [];
      }
      return this.reports;
    },
  },
});
