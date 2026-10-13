<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import client, { API_BASE } from "@/api/client";
import type { DocumentResponse, Finding, ReviewReport, Table } from "@/api/types";
import ChatDrawer from "@/components/ChatDrawer.vue";
import FindingList from "@/components/FindingList.vue";
import PaperPreview from "@/components/PaperPreview.vue";
import { useSessionStore } from "@/stores/session";

const route = useRoute();
const router = useRouter();
const store = useSessionStore();
const report = ref<ReviewReport | null>(null);
const paragraphs = ref<Array<{ index: number; text: string }>>([]);
const tables = ref<Table[]>([]);
const activeFinding = ref<Finding | null>(null);
const drawerOpen = ref(false);
const filter = ref<"all" | "problem" | "uncertain" | "pass" | "undetermined" | "gradeA" | "gradeB" | "gradeCD">("all");

const visibleFindings = computed(() => {
  const findings = report.value?.findings ?? [];
  if (filter.value === "undetermined") return findings.filter((item) => item.certainty === "undetermined");
  if (filter.value === "problem") return findings.filter((item) => item.verdict === "problem");
  if (filter.value === "uncertain") return findings.filter((item) => item.verdict === "uncertain");
  if (filter.value === "pass") return findings.filter((item) => item.verdict === "pass");
  if (filter.value === "gradeA") return findings.filter((item) => item.grade === "A");
  if (filter.value === "gradeB") return findings.filter((item) => item.grade === "B");
  if (filter.value === "gradeCD") return findings.filter((item) => item.grade === "C" || item.grade === "D");
  return findings;
});

const topRisk = computed(() => {
  const problems = (report.value?.findings ?? []).filter((item) => item.verdict === "problem");
  const order = { high: 0, mid: 1, low: 2 };
  return [...problems].sort((a, b) => order[a.severity] - order[b.severity])[0] ?? null;
});

/** 质量卡：分级分布取后端汇总，缺省时按逐条 grade 兜底统计（保证老报告也能显示）。 */
const gradeCounts = computed<Record<string, number>>(() => {
  const fallback = (report.value?.findings ?? []).reduce<Record<string, number>>((acc, item) => {
    if (item.grade) acc[item.grade] = (acc[item.grade] ?? 0) + 1;
    return acc;
  }, {});
  return { ...fallback, ...(report.value?.quality?.grades ?? {}) };
});
const avgConfidence = computed(() => (report.value?.quality?.avg_confidence ?? 0).toFixed(2));
const reviewRate = computed(() => {
  const rate = report.value?.quality?.review_rate;
  return rate === undefined ? "—" : `${Math.round(rate * 100)}%`;
});

const loadError = ref("");
const loading = ref(true);
/** 请求序号：/report/A → /report/B 时旧请求可能后到，只允许最新一次的结果落地。 */
let loadSeq = 0;

async function loadReport() {
  const seq = ++loadSeq;
  loadError.value = "";
  loading.value = true;
  report.value = null;
  paragraphs.value = [];
  tables.value = [];
  activeFinding.value = null;
  filter.value = "all";
  const reportId = (route.params.id as string) || store.reportId;
  if (reportId) {
    try {
      const { data } = await client.get<ReviewReport>(`/reports/${reportId}`);
      if (seq !== loadSeq) return;
      report.value = data;
      store.setReport(reportId);
      // 修改稿报告自带 document_id：优先据此加载正文，否则「生成修改稿 → 回到报告」
      // 会把修改稿的结论配在未修改的原稿正文上。
      const targetDocumentId = data.document_id || store.documentId;
      if (targetDocumentId) {
        store.setDocument(targetDocumentId);
        try {
          const { data: document } = await client.get<DocumentResponse>(`/documents/${targetDocumentId}`);
          if (seq !== loadSeq) return;
          paragraphs.value = document.paragraphs.filter((paragraph) => paragraph.text.trim());
          tables.value = document.tables ?? [];
        } catch {
          // 原文不可见时仍可查看报告结论，不阻断主流程
        }
      }
      activeFinding.value = data.findings.find((item) => item.verdict === "problem") ?? null;
    } catch (err) {
      if (seq !== loadSeq) return;
      loadError.value = `${(err as Error).message}（该报告可能已随会话过期被清除，可从「报告历史」选择其他报告）`;
    }
  }
  if (seq === loadSeq) loading.value = false;
}

onMounted(loadReport);
// 组件在 /report/A → /report/B 之间复用时不会重新挂载，必须监听路由参数手动重载。
// 无条件重载：导航到不带参数的 /report 时也应回落到当前会话报告，而不是继续显示上一份。
watch(() => route.params.id, () => void loadReport());

function selectFinding(finding: Finding) {
  activeFinding.value = finding;
}

function askFinding(finding: Finding) {
  activeFinding.value = finding;
  drawerOpen.value = true;
}

/** 去修改对比：带上当前报告，对比页会据此生成修改稿并做二次真实审查。 */
function goCompare() {
  router.push({ name: "compare", query: { before: report.value?.report_id ?? store.reportId } });
}

/** 自由提问：不带 finding，后端据此注入全文并沿用会话记忆 */
function openFreeChat() {
  activeFinding.value = null;
  drawerOpen.value = true;
}

const severityFilters = computed(() => ({
  all: report.value?.findings.length ?? 0,
  problem: (report.value?.findings ?? []).filter((item) => item.verdict === "problem").length,
  high: report.value?.counts.high ?? 0,
  mid: report.value?.counts.mid ?? 0,
  low: report.value?.counts.low ?? 0,
  uncertain: report.value?.counts.uncertain ?? 0,
  pass: report.value?.counts.pass ?? 0,
  undetermined: report.value?.counts.undetermined ?? 0,
  deterministic: report.value?.counts.deterministic ?? 0,
  suspected: report.value?.counts.suspected ?? 0,
}));
</script>

<template>
  <div v-if="report" class="report">
    <div class="toolbar">
      <div class="title">审查报告</div>
      <button class="chip high" :class="{ on: filter === 'problem' }" @click="filter = filter === 'problem' ? 'all' : 'problem'">
        问题 {{ severityFilters.problem }}
      </button>
      <button class="chip mid" @click="filter = filter === 'uncertain' ? 'all' : 'uncertain'">存疑 {{ report.counts.uncertain ?? 0 }}</button>
      <button class="chip low" :class="{ on: filter === 'pass' }" @click="filter = filter === 'pass' ? 'all' : 'pass'">
        通过 {{ report.counts.pass ?? 0 }}
      </button>
      <div class="toolbar-actions">
        <a class="btn" :href="`${API_BASE}/reports/${report.report_id}/export?format=markdown`" target="_blank">导出 Markdown</a>
        <button class="btn" @click="openFreeChat">全文自由提问</button>
        <button class="btn primary" @click="goCompare">去修改对比 →</button>
      </div>
    </div>

    <div class="statrow">
      <div class="stat card">
        <span class="lbl">检出问题</span>
        <span class="num">{{ report.counts.total ?? 0 }}</span>
        <span class="tiny">严重 {{ report.counts.high ?? 0 }} · 中等 {{ report.counts.mid ?? 0 }} · 轻微 {{ report.counts.low ?? 0 }}</span>
      </div>
      <div class="stat card">
        <span class="lbl">Top 风险</span>
        <span class="num risk">{{ topRisk?.headline ?? "无待改问题" }}</span>
        <span class="tiny">{{ topRisk ? `段落 ${topRisk.anchors[0]?.paragraph_index ?? "-"}` : "全部检查通过" }}</span>
      </div>
      <div class="stat card">
        <span class="lbl">已评估条目</span>
        <span class="num">{{ report.counts.assessed ?? 0 }}</span>
        <span class="tiny">确定性 {{ severityFilters.deterministic }} · 疑似 {{ severityFilters.suspected }} · 未判定 {{ severityFilters.undetermined }}</span>
      </div>
      <div class="stat card">
        <span class="lbl">输出质量</span>
        <span class="num">{{ avgConfidence }}</span>
        <span class="tiny">平均置信度（0–1）· 审查率 {{ reviewRate }}</span>
        <span class="tiny">A 高置信 {{ gradeCounts.A ?? 0 }} · B {{ gradeCounts.B ?? 0 }} · C {{ gradeCounts.C ?? 0 }} · D {{ gradeCounts.D ?? 0 }}</span>
      </div>
      <div class="stat card">
        <span class="lbl">审查耗时</span>
        <span class="num">{{ report.duration_ms }} ms</span>
        <span class="tiny">tokens {{ report.tokens.input ?? 0 }} / {{ report.tokens.output ?? 0 }}</span>
      </div>
    </div>

    <p v-if="store.tokensSummary" class="figure-note">ℹ {{ store.tokensSummary }}</p>
    <p v-if="report.paper_type === 'review'" class="figure-note">
      ℹ 识别为综述/理论论文（非实证）：已跳过数据划分、基线、消融、统计检验、可复现性等实证类检查。
    </p>
    <p v-if="report.figure_references" class="figure-note">
      ⚠ 检测到 {{ report.figure_references }} 处图表引用（图/表）：表格内容已结构化解析并纳入审查，图像内部数据未参与规则判定；
      {{ report.demote_on_figures ? "本次已启用保守模式，可能依赖图像证据的条目已列为「存疑」。" : "如统计量仅标在图像内，相关条目可能漏报或误报。" }}
    </p>

    <div class="report-grid">
      <div class="list-col">
        <div class="filters">
          <button :class="{ on: filter === 'all' }" @click="filter = 'all'">全部（{{ severityFilters.all }}）</button>
          <button :class="{ on: filter === 'problem' }" @click="filter = 'problem'">仅问题（{{ severityFilters.problem }}）</button>
          <button :class="{ on: filter === 'uncertain' }" @click="filter = 'uncertain'">仅存疑（{{ severityFilters.uncertain }}）</button>
          <button :class="{ on: filter === 'pass' }" @click="filter = 'pass'">仅通过（{{ severityFilters.pass }}）</button>
          <button :class="{ on: filter === 'undetermined' }" @click="filter = 'undetermined'">未判定（{{ severityFilters.undetermined }}）</button>
          <span class="filter-sep" />
          <button :class="{ on: filter === 'gradeA' }" @click="filter = 'gradeA'">A 高置信（{{ gradeCounts.A ?? 0 }}）</button>
          <button :class="{ on: filter === 'gradeB' }" @click="filter = 'gradeB'">B 中置信（{{ gradeCounts.B ?? 0 }}）</button>
          <button :class="{ on: filter === 'gradeCD' }" @click="filter = 'gradeCD'">C/D 待确认（{{ (gradeCounts.C ?? 0) + (gradeCounts.D ?? 0) }}）</button>
        </div>
        <FindingList
          :findings="visibleFindings"
          :active-id="activeFinding?.finding_id"
          @select="selectFinding"
          @ask="askFinding"
        />
      </div>
      <div class="paper-col">
        <PaperPreview
          :paragraphs="paragraphs"
          :tables="tables"
          :highlight-index="activeFinding?.anchors[0]?.paragraph_index ?? null"
        />
      </div>
    </div>
    <ChatDrawer
      :open="drawerOpen"
      :report-id="report?.report_id ?? store.reportId"
      :finding="activeFinding"
      @close="drawerOpen = false"
    />
  </div>
  <div v-else-if="loading" class="empty">正在加载审查报告…</div>
  <p v-else-if="loadError" class="empty error">{{ loadError }}</p>
  <p v-else class="empty">暂无报告：请先在上传页完成解析与审查。</p>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.toolbar .title { font-size: 17px; font-weight: 700; margin-right: 4px; }
.toolbar-actions { margin-left: auto; display: flex; gap: 8px; }
.btn { border: 1px solid var(--line); background: #fff; border-radius: 10px; padding: 8px 16px; font-size: 13px; color: var(--ink); text-decoration: none; cursor: pointer; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.chip { display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; background: var(--bg); color: var(--ink-2); cursor: pointer; border: none; }
.chip.high { background: var(--sev-high-bg); color: var(--sev-high); }
.chip.mid { background: var(--sev-mid-bg); color: var(--sev-mid); }
.chip.low { background: var(--sev-low-bg); color: var(--sev-low); }
.chip.pass { background: var(--pass-bg); color: var(--pass); }
.chip.on { outline: 2px solid var(--accent); outline-offset: 1px; }
.statrow { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.stat { flex: 1; min-width: 140px; padding: 12px 16px; display: flex; flex-direction: column; gap: 2px; }
.stat .num { font-size: 24px; font-weight: 700; line-height: 1.25; }
.stat .num.risk { font-size: 14px; font-weight: 600; color: var(--sev-high); padding-top: 6px; }
.stat .lbl { font-size: 12px; color: var(--ink-2); }
.tiny { font-size: 11.5px; color: var(--ink-3); }
.figure-note { background: var(--sev-mid-bg); color: var(--sev-mid); border-radius: 10px; padding: 8px 12px; font-size: 13px; }
.filters { display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.filters button { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 4px 12px; cursor: pointer; font-size: 12.5px; color: var(--ink-2); }
.filters button.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.filter-sep { width: 1px; align-self: stretch; background: var(--line); margin: 2px; }
.report-grid { display: grid; grid-template-columns: 400px 1fr; gap: 20px; align-items: start; }
.list-col { display: flex; flex-direction: column; min-height: 0; }
.paper-col { position: sticky; top: 70px; }
.empty { color: var(--ink-3); }
.error { color: var(--sev-high); }
@media (max-width: 980px) {
  .report-grid { grid-template-columns: 1fr; }
  .paper-col { position: static; }
}
@media (min-height: 820px) {
  .report-grid { height: calc(100vh - 300px); min-height: 430px; }
  .list-col, .paper-col { height: 100%; min-height: 0; }
  .list-col :deep(.finding-list) { height: 100%; min-height: 0; }
  .paper-col :deep(.paper) { max-height: 100%; }
}
</style>
