<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute } from "vue-router";

import client from "@/api/client";
import type { ChatResponse, DocumentResponse, Finding, ReviewReport } from "@/api/types";
import ChatDrawer from "@/components/ChatDrawer.vue";
import FindingList from "@/components/FindingList.vue";
import PaperPreview from "@/components/PaperPreview.vue";
import { useSessionStore } from "@/stores/session";

const route = useRoute();
const store = useSessionStore();
const report = ref<ReviewReport | null>(null);
const paragraphs = ref<Array<{ index: number; text: string }>>([]);
const activeFinding = ref<Finding | null>(null);
const drawerOpen = ref(false);
const answer = ref("");
const filter = ref<"all" | "problem" | "uncertain" | "pass">("all");

const visibleFindings = computed(() => {
  const findings = report.value?.findings ?? [];
  if (filter.value === "problem") return findings.filter((item) => item.verdict === "problem");
  if (filter.value === "uncertain") return findings.filter((item) => item.verdict === "uncertain");
  if (filter.value === "pass") return findings.filter((item) => item.verdict === "pass");
  return findings;
});

const loadError = ref("");

onMounted(async () => {
  loadError.value = "";
  const reportId = (route.params.id as string) || store.reportId;
  if (reportId) {
    try {
      const { data } = await client.get<ReviewReport>(`/reports/${reportId}`);
      report.value = data;
      store.setReport(reportId);
    } catch (err) {
      loadError.value = `${(err as Error).message}（该报告可能已随会话过期被清除，可从「报告历史」选择其他报告）`;
    }
  }
  if (store.documentId) {
    try {
      const { data } = await client.get<DocumentResponse>(`/documents/${store.documentId}`);
      paragraphs.value = data.paragraphs.filter((paragraph) => paragraph.text.trim());
    } catch {
      // 原文不可见时仍可查看报告结论，不阻断主流程
    }
  }
});

async function askFinding(finding: Finding) {
  activeFinding.value = finding;
  drawerOpen.value = true;
  answer.value = "正在获取解答…";
  const reportId = report.value?.report_id ?? store.reportId;
  try {
    const { data } = await client.post<ChatResponse>(`/reports/${reportId}/chat`, {
      question: "这条问题该怎么改？",
      finding_id: finding.finding_id,
    });
    answer.value = data.answer;
  } catch (err) {
    answer.value = (err as Error).message;
  }
}
</script>

<template>
  <div v-if="report" class="report">
    <div class="toolbar">
      <b>审查报告</b>
      <span class="counts">
        严重 {{ report.counts.high ?? 0 }} / 中等 {{ report.counts.mid ?? 0 }} / 轻微 {{ report.counts.low ?? 0 }}
        / 存疑 {{ report.counts.uncertain ?? 0 }} / 通过 {{ report.counts.pass ?? 0 }}
      </span>
      <a :href="`/api/v1/reports/${report.report_id}/export?format=markdown`" target="_blank">导出 Markdown</a>
    </div>
    <p v-if="store.tokensSummary" class="figure-note">ℹ {{ store.tokensSummary }}</p>
    <p v-if="report.paper_type === 'review'" class="figure-note">
      ℹ 识别为综述/理论论文（非实证）：已跳过数据划分、基线、消融、统计检验、可复现性等实证类检查。
    </p>
    <p v-if="report.figure_references" class="figure-note">
      ⚠ 检测到 {{ report.figure_references }} 处图表引用（图/表）：图表内部数据未解析；
      {{ report.demote_on_figures ? "本次已启用保守模式，可能依赖图表的条目已列为「存疑」。" : "如统计量仅标在图内，相关条目可能漏报或误报。" }}
    </p>
    <div class="filters">
      <button :class="{ on: filter === 'all' }" @click="filter = 'all'">全部（{{ report.findings.length }}）</button>
      <button :class="{ on: filter === 'problem' }" @click="filter = 'problem'">仅问题（{{ report.counts.total ?? 0 }}）</button>
      <button :class="{ on: filter === 'uncertain' }" @click="filter = 'uncertain'">仅存疑（{{ report.counts.uncertain ?? 0 }}）</button>
      <button :class="{ on: filter === 'pass' }" @click="filter = 'pass'">仅通过（{{ report.counts.pass ?? 0 }}）</button>
    </div>
    <div class="grid">
      <FindingList
        :findings="visibleFindings"
        :active-id="activeFinding?.finding_id"
        @select="activeFinding = $event; answer = ''"
      />
      <PaperPreview :paragraphs="paragraphs" :highlight-index="activeFinding?.anchors[0]?.paragraph_index ?? null" />
    </div>
    <button class="ask" :disabled="!activeFinding" @click="activeFinding && askFinding(activeFinding)">
      追问这条
    </button>
  </div>
  <p v-else-if="loadError" class="empty error">{{ loadError }}</p>
  <p v-else class="empty">暂无报告：请先在上传页完成解析与审查。</p>
  <ChatDrawer
    :open="drawerOpen"
    :question="activeFinding ? activeFinding.headline : ''"
    :answer="answer"
    @close="drawerOpen = false"
  />
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }
.counts { color: var(--ink-2); }
.figure-note { background: var(--sev-mid-bg); color: var(--sev-mid); border-radius: 10px; padding: 8px 12px; font-size: 13px; }
.filters { display: flex; gap: 8px; margin-bottom: 12px; }
.filters button { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 5px 14px; cursor: pointer; font-size: 13px; }
.filters button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.grid { display: grid; grid-template-columns: 380px 1fr; gap: 16px; align-items: start; }
.ask { margin-top: 12px; }
.empty { color: var(--ink-3); }
</style>
