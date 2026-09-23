import { defineStore } from "pinia";

import client from "@/api/client";
import type { ReportSummary, Section } from "@/api/types";

export const useSessionStore = defineStore("session", {
  state: () => ({
    documentId: "" as string,
    sections: [] as Section[],
    warnings: [] as string[],
    reportId: "" as string,
    tokensSummary: "" as string,
    reports: [] as ReportSummary[],
  }),
  actions: {
    setUpload(documentId: string, sections: Section[], warnings: string[]) {
      this.documentId = documentId;
      this.sections = sections;
      this.warnings = warnings;
    },
    setReport(reportId: string) {
      this.reportId = reportId;
    },
    setTokens(tokensSummary: string) {
      this.tokensSummary = tokensSummary;
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
