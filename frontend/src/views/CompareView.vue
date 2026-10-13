<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import client from "@/api/client";
import { submitAndPoll, type PollPromise } from "@/api/tasks";
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
const locatingHint = ref("");
const loading = ref(false);
const loadingStage = ref("");
const useLlm = ref(true);
const activeSide = ref<"before" | "after">("before");
const activeId = ref<string | null>(null);
const beforeParagraphs = ref<Array<{ index: number; text: string }>>([]);
const afterParagraphs = ref<Array<{ index: number; text: string }>>([]);
const beforeWorkbench = ref<HTMLElement | null>(null);
const afterWorkbench = ref<HTMLElement | null>(null);
/** 在途对比任务的轮询句柄；卸载时取消，避免回包写进已离开的页面。 */
let pending: PollPromise<CompareResponse> | null = null;

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
    // 复用 store 的报告缓存（历史页/对比页共用同一份列表，避免各拉一次）
    const list = await store.fetchReports();
    reports.value = list;
    beforeId.value =
      (route.query.before as string) || store.reportId || list[0]?.report_id || "";
    // 默认不预选「修改后」报告：留空即走「按示范改写自动生成修改稿并二次审查」这条主线，
    // 否则页面会拿两份既有（均未修改）报告互比，看起来「改了却没变化」。
    // 确需比较两份既有报告时，由用户在下拉框手动选择。
    afterId.value = "";
    await loadPapers(null);
    // 不在进入页面时自动跑对比：生成修改稿要连跑一次完整审查（含模型定向送审与视觉识读），
    // 自动触发会让「打开对比页」变成一次重模型任务，误入即长时间占用。改为由用户点按钮触发。
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
});

watch(afterId, () => {
  if (afterId.value) void loadPapers(null);
});

// 切换初稿时同步刷新左侧原文，并清掉上一份初稿生成的修改稿选择，避免错配
watch(beforeId, () => {
  if (!beforeId.value) return;
  if (afterId.value) afterId.value = "";
  void loadPapers(null);
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
    : "已提交修改稿生成任务（约 1–3 分钟，本页自动轮询结果）…";
  // 记录提交前已有的报告 id：二次审查会新建报告，据此识别新生成的那份
  const knownIds = new Set(reports.value.map((item) => item.report_id));
  // 记录提交时的初稿选择：任务跑完可能已过 1–3 分钟，期间用户若换了初稿，
  // 结果就属于另一份稿件，直接丢弃而不是把它画到当前选择上。
  const submittedBefore = beforeId.value;
  const submittedAfter = afterId.value;
  try {
    // 对比为后台任务：POST 立即返回 task_id，前端轮询 /tasks/{id} 取结果，不再挂长连接。
    pending = submitAndPoll<CompareResponse>(
      "/compare",
      {
        before_report_id: submittedBefore,
        after_report_id: submittedAfter || null,
        use_llm: submittedAfter ? false : useLlm.value,
      },
      {
        // 把服务端真实阶段回显到进度条文案：等待 1–3 分钟时用户能看到任务确实在推进
        onState: (state) => {
          if (state === "queued") {
            loadingStage.value = "任务已入队，等待执行…";
          } else if (state === "running") {
            loadingStage.value = submittedAfter
              ? "正在对比两份报告…"
              : "正在生成修改稿并做二次审查（约 1–3 分钟）…";
          }
        },
      },
    );
    const data = await pending;
    if (beforeId.value !== submittedBefore) {
      error.value = "对比结果已忽略：任务执行期间「修改前」报告被切换，请重新对比。";
      return;
    }
    result.value = data;
    activeSide.value = "before";
    activeId.value = data.before_findings[0]?.checklist_item_id ?? null;
    if (!submittedAfter) {
      const list = await store.fetchReports();
      reports.value = list;
      // 认「提交前不存在的那份报告」为新生成结果，避免多份历史时误选旧报告
      const generated = list.find((item) => !knownIds.has(item.report_id)) ?? null;
      if (generated) {
        afterId.value = generated.report_id;
        // 修改稿有自己的 document_id：不同步到 store 的话，「回到报告」会把
        // 修改稿的结论并排显示在未修改的原稿正文上。
        const revisedDocumentId = data.document_id ?? generated.document_id;
        if (revisedDocumentId) store.setDocument(revisedDocumentId);
        afterParagraphs.value = await documentParagraphs(revisedDocumentId);
      }
    } else {
      await loadPapers(null);
    }
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    pending = null;
    loading.value = false;
  }
}

onUnmounted(() => {
  pending?.cancel();
  pending = null;
});

async function locate(side: "before" | "after", finding: CompareFinding) {
  activeSide.value = side;
  activeId.value = finding.checklist_item_id;
  await nextTick();
  // 两栏原文都在页面上直接展开，定位即「把目标段落滚到视口中间」。
  const anchor = finding.anchors[0]?.paragraph_index ?? null;
  const scope = side === "before" ? beforeWorkbench.value : afterWorkbench.value;
  if (!scope) return;
  if (anchor === null) {
    locatingHint.value = "该条问题未给出原文段落锚点，无法自动定位。";
    return;
  }
  const node = scope.querySelector<HTMLElement>(`[data-paragraph-index="${anchor}"]`);
  if (!node) {
    locatingHint.value = `修改稿的段落 ${anchor} 暂不可见（可能已随会话过期被清除）。`;
    return;
  }
  locatingHint.value = "";
  const offset = node.getBoundingClientRect().top - scope.getBoundingClientRect().top;
  window.scrollTo({ top: window.scrollY + offset - 120, behavior: "smooth" });
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
        <button class="btn primary" :disabled="loading" @click="compare">
          {{ loading ? "处理中…" : result ? "重新对比" : "生成修改稿并对比" }}
        </button>
        <button class="btn" @click="$router.push({ name: 'report', params: { id: afterId || beforeId } })">回到报告</button>
      </div>
    </div>

    <p v-if="!afterId" class="auto-note">
      <label class="auto-option">
        <input v-model="useLlm" type="checkbox" />
        用模型结合全文生成补写（每条附原文出处，无依据不写；关闭则退回清单规范句式）
      </label>
    </p>

    <div class="selectors">
      <label class="selector">
        <span class="lbl">修改前 · 初稿</span>
        <select v-model="beforeId" :disabled="loading">
          <option value="">请选择报告</option>
          <option v-for="report in reports" :key="report.report_id" :value="report.report_id">
            {{ label(report) }}
          </option>
        </select>
      </label>
      <label class="selector">
        <span class="lbl">修改后 · 修改稿</span>
        <select v-model="afterId" :disabled="loading">
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
    <p v-if="locatingHint" class="hint">{{ locatingHint }}</p>

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
        <div class="cmp-list">
          <div v-for="(finding, index) in beforeFindings" :key="`${finding.checklist_item_id}-${index}`" class="cmp-row">
            <button
              class="cmp-f"
              :class="{ active: activeSide === 'before' && activeId === finding.checklist_item_id }"
              @click="locate('before', finding)"
            >
              <SeverityChip :severity="finding.severity" />
              <span class="cmp-f-title">{{ finding.headline }}</span>
              <span class="tiny">段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }} · 点击定位原文</span>
            </button>
          </div>
          <p v-if="!beforeFindings.length" class="tiny empty">该稿件无待改问题。</p>
        </div>
        <div ref="beforeWorkbench" class="workbench">
          <PaperPreview
            :paragraphs="beforeParagraphs"
            :tables="[]"
            :highlight-index="activeSide === 'before' ? activeAnchor(beforeFindings) : null"
            :external-scroll="true"
            min-height="52vh"
          />
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
        <div class="cmp-list">
          <div v-for="(finding, index) in afterFindings" :key="`${finding.checklist_item_id}-${index}`" class="cmp-row">
            <button
              class="cmp-f"
              :class="{ active: activeSide === 'after' && activeId === finding.checklist_item_id }"
              @click="locate('after', finding)"
            >
              <span class="cmp-f-head">
                <SeverityChip :severity="finding.severity" />
                <span class="status" :class="finding.revision_status" :title="finding.revision_note || ''">
                  {{ statusLabel(finding.revision_status) }}
                </span>
              </span>
              <span class="cmp-f-title">{{ finding.headline }}</span>
              <span class="tiny">段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }} · 点击定位原文</span>
            </button>
          </div>
          <p v-if="!afterFindings.length" class="tiny empty">二次审查未再发现问题。</p>
        </div>
        <div ref="afterWorkbench" class="workbench">
          <PaperPreview
            :paragraphs="afterParagraphs"
            :tables="[]"
            :highlight-index="activeSide === 'after' ? activeAnchor(afterFindings) : null"
            :external-scroll="true"
            min-height="52vh"
          />
        </div>
      </div>
    </div>

    <p v-else-if="!loading && !error" class="tiny empty-state">
      确认左侧初稿报告后，点右上角「生成修改稿并对比」：系统会现场补写修改稿并对修改稿做一次真实二次审查（作为后台任务提交，本页自动轮询结果，约 1–3 分钟；想秒级出结果可取消勾选上面的模型选框）。
    </p>
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
.cmp-list { display: flex; flex-direction: column; max-height: 260px; overflow: auto; border-bottom: 1px solid var(--line); }
.cmp-row { border-bottom: 1px solid var(--line); }
.cmp-f { display: flex; flex-direction: column; gap: 4px; width: 100%; text-align: left; padding: 10px 14px; border: none; background: transparent; cursor: pointer; font: inherit; font-size: 12.5px; }
.cmp-f:hover { background: var(--bg); }
.cmp-f.active { background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); }
.cmp-f-head { display: flex; align-items: center; gap: 6px; }
.cmp-f-title { font-weight: 600; font-size: 13px; }
.status { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: var(--bg); color: var(--ink-3); }
.status.rewritten { background: var(--pass-bg); color: var(--pass); }
.status.manual { background: var(--sev-mid-bg); color: var(--sev-mid); }
.status.pending { background: var(--sev-low-bg); color: var(--sev-low); }
.workbench { padding: 10px 12px 14px; }
.workbench :deep(.paper) { border: none; box-shadow: none; border-radius: 0; max-height: none; padding: 18px 22px; }
.workbench :deep(.hl) { scroll-margin-top: 90px; }
.tiny { color: var(--ink-3); font-size: 12px; }
.empty { padding: 12px; }
.empty-state { margin-top: 12px; }
.error { color: var(--sev-high); }
.hint { color: var(--sev-mid); font-size: 12.5px; margin: 0 0 12px; }
@media (max-width: 1100px) {
  .cmp-grid { grid-template-columns: 1fr; }
  .selectors { grid-template-columns: 1fr; }
}
</style>
