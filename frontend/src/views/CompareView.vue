<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import client from "@/api/client";
import type { CompareFinding, CompareResponse, DocumentResponse, ReviewReport, ReportSummary } from "@/api/types";
import PaperPreview from "@/components/PaperPreview.vue";
import SeverityChip from "@/components/SeverityChip.vue";
import { useSessionStore } from "@/stores/session";

const route = useRoute();
const store = useSessionStore();
const reports = ref<ReportSummary[]>([]);
const beforeId = ref("");
const afterId = ref("");
const result = ref<CompareResponse | null>(null);
const error = ref("");
const loading = ref(false);
const loadingStage = ref("");
const useLlm = ref(false);
const activeSide = ref<"before" | "after">("before");
const activeId = ref<string | null>(null);
const beforeParagraphs = ref<Array<{ index: number; text: string }>>([]);
const afterParagraphs = ref<Array<{ index: number; text: string }>>([]);
const revisedReport = ref<ReviewReport | null>(null);

function label(report: ReportSummary): string {
  const counts = report.counts ?? {};
  return `${report.document_name ?? "未命名文档"} · 严重 ${counts.high ?? 0} / 中等 ${counts.mid ?? 0} / 轻微 ${counts.low ?? 0}`;
}

const beforeFindings = computed<CompareFinding[]>(() => result.value?.before_findings ?? []);
const afterFindings = computed<CompareFinding[]>(() => result.value?.after_findings ?? []);

const delta = computed(() => {
  if (!result.value) return null;
  return {
    beforeTotal: result.value.before.total ?? 0,
    afterTotal: result.value.after.total ?? 0,
    beforeHigh: result.value.before.high ?? 0,
    afterHigh: result.value.after.high ?? 0,
    resolved: result.value.resolved_findings.length,
    added: result.value.new_findings.length,
    kept: result.value.kept_findings.length,
  };
});

/** 修改稿中仍需作者本人处理的条目（图表/数据依赖，无法由文字模板代改）。 */
const manualFindings = computed(() => afterFindings.value.filter((item) => item.revision_status === "manual"));

async function documentParagraphs(documentId: string): Promise<Array<{ index: number; text: string }>> {
  if (!documentId) return [];
  try {
    const { data } = await client.get<DocumentResponse>(`/documents/${documentId}`);
    return data.paragraphs.filter((paragraph) => paragraph.text.trim());
  } catch {
    return [];
  }
}

async function loadPapers(report: ReviewReport | null) {
  const beforeMeta = reports.value.find((item) => item.report_id === beforeId.value);
  beforeParagraphs.value = beforeMeta ? await documentParagraphs(beforeMeta.document_id) : [];
  const afterMeta = report
    ? reports.value.find((item) => item.report_id === report.report_id)
    : reports.value.find((item) => item.report_id === afterId.value);
  const afterDocumentId = afterMeta?.document_id ?? (report ? store.documentId : "");
  afterParagraphs.value = await documentParagraphs(afterDocumentId);
}

onMounted(async () => {
  loading.value = true;
  loadingStage.value = "正在读取报告…";
  try {
    const { data } = await client.get<ReportSummary[]>("/reports");
    reports.value = data;
    store.setReports(data);
    beforeId.value =
      (route.query.before as string) || store.reportId || data[0]?.report_id || "";
    afterId.value = data.find((item) => item.report_id !== beforeId.value)?.report_id ?? "";
    await loadPapers(null);
    await compare();
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
});

watch(afterId, () => {
  if (afterId.value) void loadPapers(null);
});

async function compare() {
  error.value = "";
  if (!beforeId.value) {
    error.value = "请先选择要修改的初稿报告。";
    return;
  }
  loading.value = true;
  loadingStage.value = afterId.value
    ? "正在对比两份报告…"
    : "正在生成修改稿并二次审查（约 1 分钟）…";
  try {
    const { data } = await client.post<CompareResponse>("/compare", {
      before_report_id: beforeId.value,
      after_report_id: afterId.value || null,
      use_llm: afterId.value ? false : useLlm.value,
    });
    result.value = data;
    activeSide.value = "before";
    activeId.value = data.before_findings[0]?.checklist_item_id ?? null;
    revisedReport.value = null;
    if (!afterId.value) {
      const list = await client.get<ReportSummary[]>("/reports");
      reports.value = list.data;
      store.setReports(list.data);
      const generated = list.data.find((item) => item.document_name !== null && item.report_id !== beforeId.value);
      afterId.value = data.after_findings.length || !generated ? afterId.value : generated.report_id;
      const docMeta =
        generated ??
        list.data.find((item) => item.report_id === afterId.value) ??
        null;
      if (docMeta?.report_id) {
        const detail = await client.get<ReviewReport>(`/reports/${docMeta.report_id}`);
        revisedReport.value = detail.data;
      }
      afterParagraphs.value = docMeta ? await documentParagraphs(docMeta.document_id) : [];
    } else {
      revisedReport.value = null;
      await loadPapers(null);
    }
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

async function locate(side: "before" | "after", finding: CompareFinding) {
  activeSide.value = side;
  activeId.value = finding.checklist_item_id;
  await nextTick();
}

function activeAnchor(findings: CompareFinding[]): number | null {
  const current = findings.find((item) => item.checklist_item_id === activeId.value);
  return current?.anchors[0]?.paragraph_index ?? null;
}

function statusLabel(status?: string): string {
  if (status === "rewritten") return "已按示范改写";
  if (status === "manual") return "需作者确认";
  return "未自动改写";
}
</script>

<template>
  <div class="compare-view">
    <div class="toolbar">
      <div class="title">修改前后对比</div>
      <span v-if="delta" class="chip" :class="delta.afterTotal < delta.beforeTotal ? 'pass' : 'mid'">
        修改稿问题 {{ delta.afterTotal }} 项
      </span>
      <div class="toolbar-actions">
        <button class="btn" :disabled="loading" @click="compare">{{ loading ? "处理中…" : "重新对比" }}</button>
        <button class="btn primary" @click="$router.push({ name: 'report', params: { id: afterId || beforeId } })">回到报告</button>
      </div>
    </div>

    <p v-if="!afterId" class="auto-note">
      <label class="auto-option">
        <input v-model="useLlm" type="checkbox" />
        生成修改稿时同时启用模型顾问（会产生 token 消耗；关闭则只用规则引擎复审判定）
      </label>
    </p>

    <div class="selectors">
      <label class="selector">
        <span class="lbl">修改前 · 初稿</span>
        <select v-model="beforeId">
          <option value="">请选择报告</option>
          <option v-for="report in reports" :key="report.report_id" :value="report.report_id">
            {{ label(report) }}
          </option>
        </select>
      </label>
      <label class="selector">
        <span class="lbl">修改后 · 修改稿</span>
        <select v-model="afterId">
          <option value="">默认：按示范改写自动生成并二次审查</option>
          <option v-for="report in reports" :key="report.report_id" :value="report.report_id">
            {{ label(report) }}
          </option>
        </select>
      </label>
    </div>

    <div v-if="loading" class="loading">
      <div class="bar"><i /></div>
      <p>{{ loadingStage }}</p>
    </div>

    <div v-if="delta" class="delta-banner">
      ✔ 修改后问题从 {{ delta.beforeTotal }} 项降至 {{ delta.afterTotal }} 项（严重 {{ delta.beforeHigh }} → {{ delta.afterHigh }}），
      共解决 {{ delta.resolved }} 项、仍保留 {{ delta.kept }} 项、新增 {{ delta.added }} 项 —— 两侧均可点击问题定位到各自原文
    </div>

    <p v-if="manualFindings.length" class="manual-note">
      ⚠ 修改稿中仍有 {{ manualFindings.length }} 项需要作者本人处理：这类结论依赖图表、原始数据或外部材料，
      文字模板无法代改，已如实保留在右侧清单中。
    </p>
    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="result" class="cmp-grid">
      <div class="card cmp-col">
        <div class="head">
          <span class="lbl">修改前 · 初稿</span>
          <span class="chips">
            <span class="chip high">严重 {{ result.before.high ?? 0 }}</span>
            <span class="chip mid">中等 {{ result.before.mid ?? 0 }}</span>
            <span class="chip low">轻微 {{ result.before.low ?? 0 }}</span>
          </span>
        </div>
        <div class="mini-grid">
          <div class="mini-list">
            <div class="cmp-list-head">
              <b>问题清单</b>
              <span class="tiny">{{ beforeFindings.length }} 项 · 点击定位原文</span>
            </div>
            <div class="mini-items">
              <button
                v-for="finding in beforeFindings"
                :key="finding.checklist_item_id"
                class="cmp-f"
                :class="{ active: activeSide === 'before' && activeId === finding.checklist_item_id }"
                @click="locate('before', finding)"
              >
                <SeverityChip :severity="finding.severity" />
                <span class="cmp-f-title">{{ finding.headline }}</span>
                <span class="tiny">段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }}</span>
              </button>
              <p v-if="!beforeFindings.length" class="tiny empty">该稿件无待改问题。</p>
            </div>
          </div>
          <div class="paper-scroll">
            <PaperPreview
              :paragraphs="beforeParagraphs"
              :tables="[]"
              :highlight-index="activeSide === 'before' ? activeAnchor(beforeFindings) : null"
            />
          </div>
        </div>
      </div>

      <div class="card cmp-col">
        <div class="head">
          <span class="lbl">修改后 · 修改稿（二次审查）</span>
          <span class="chips">
            <span class="chip high">严重 {{ result.after.high ?? 0 }}</span>
            <span class="chip mid">中等 {{ result.after.mid ?? 0 }}</span>
            <span class="chip low">轻微 {{ result.after.low ?? 0 }}</span>
          </span>
        </div>
        <div class="mini-grid">
          <div class="mini-list">
            <div class="cmp-list-head">
              <b>问题清单</b>
              <span class="tiny">{{ afterFindings.length }} 项 · 点击定位原文</span>
            </div>
            <div class="mini-items">
              <button
                v-for="finding in afterFindings"
                :key="finding.checklist_item_id"
                class="cmp-f"
                :class="{ active: activeSide === 'after' && activeId === finding.checklist_item_id }"
                @click="locate('after', finding)"
              >
                <SeverityChip :severity="finding.severity" />
                <span class="cmp-f-title">{{ finding.headline }}</span>
                <span class="tiny">段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }}</span>
                <span class="status" :class="finding.revision_status">{{ statusLabel(finding.revision_status) }}</span>
              </button>
              <p v-if="!afterFindings.length" class="tiny empty">二次审查未再发现问题。</p>
            </div>
          </div>
          <div class="paper-scroll">
            <PaperPreview
              :paragraphs="afterParagraphs"
              :tables="[]"
              :highlight-index="activeSide === 'after' ? activeAnchor(afterFindings) : null"
            />
          </div>
        </div>
      </div>
    </div>

    <p v-else-if="!loading && !error" class="tiny empty-state">选择初稿报告后点击「重新对比」，即可生成修改稿并二次审查。</p>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; }
.toolbar .title { font-size: 17px; font-weight: 700; }
.toolbar-actions { margin-left: auto; display: flex; gap: 8px; }
.btn { border: 1px solid #d4d8e3; background: #fff; color: var(--ink); padding: 9px 18px; border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.chip { display: inline-flex; align-items: center; font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; background: var(--bg); color: var(--ink-2); }
.chip.high { background: var(--sev-high-bg); color: var(--sev-high); }
.chip.mid { background: var(--sev-mid-bg); color: var(--sev-mid); }
.chip.low { background: var(--sev-low-bg); color: var(--sev-low); }
.chip.pass { background: var(--pass-bg); color: var(--pass); }
.selectors { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 16px; }
.selector { display: flex; flex-direction: column; gap: 6px; }
.selector .lbl { font-size: 12px; color: var(--ink-2); font-weight: 600; }
.selector select { padding: 9px 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; font-size: 13px; }
.auto-note { margin: 0 0 14px; }
.auto-option { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink-2); }
.loading { margin-bottom: 16px; }
.loading .bar { height: 8px; background: var(--bg); border-radius: 99px; overflow: hidden; }
.loading .bar i { display: block; height: 100%; width: 40%; background: var(--accent); border-radius: 99px; animation: slide 1.2s ease-in-out infinite; }
@keyframes slide { 0% { margin-left: -40%; } 100% { margin-left: 100%; } }
.loading p { margin: 8px 0 0; font-size: 13px; color: var(--ink-2); }
.delta-banner { display: flex; gap: 14px; align-items: center; background: var(--pass-bg); color: var(--pass); border: 1px solid var(--pass); padding: 12px 18px; border-radius: 12px; margin-bottom: 14px; font-weight: 600; font-size: 13.5px; }
.manual-note { background: var(--sev-mid-bg); color: var(--sev-mid); border-radius: 10px; padding: 10px 14px; font-size: 13px; margin: 0 0 14px; }
.cmp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: stretch; }
.cmp-col { display: flex; flex-direction: column; padding: 0; overflow: hidden; }
.cmp-col .head { display: flex; justify-content: space-between; align-items: center; gap: 6px; padding: 12px 16px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.cmp-col .head .lbl { font-size: 13.5px; font-weight: 600; }
.chips { display: flex; gap: 6px; flex-wrap: wrap; }
.mini-grid { display: grid; grid-template-columns: 230px 1fr; flex: 1; min-height: 0; }
.mini-list { display: flex; flex-direction: column; min-height: 0; border-right: 1px solid var(--line); }
.cmp-list-head { padding: 9px 12px; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; align-items: center; font-size: 12.5px; }
.mini-items { flex: 1; overflow: auto; }
.cmp-f { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; width: 100%; text-align: left; padding: 9px 12px; border: none; border-bottom: 1px solid var(--line); background: transparent; cursor: pointer; font: inherit; font-size: 12.5px; }
.cmp-f:hover { background: var(--bg); }
.cmp-f.active { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.cmp-f-title { flex: 1 1 100%; font-weight: 500; }
.status { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: var(--bg); color: var(--ink-3); }
.status.rewritten { background: var(--pass-bg); color: var(--pass); }
.status.manual { background: var(--sev-mid-bg); color: var(--sev-mid); }
.paper-scroll { min-height: 0; overflow: hidden; }
.paper-scroll :deep(.paper) { max-height: 58vh; border: none; box-shadow: none; border-radius: 0; }
.tiny { color: var(--ink-3); font-size: 12px; }
.empty { padding: 12px; }
.empty-state { margin-top: 12px; }
.error { color: var(--sev-high); }
@media (max-width: 1100px) {
  .cmp-grid { grid-template-columns: 1fr; }
  .selectors { grid-template-columns: 1fr; }
}
</style>
