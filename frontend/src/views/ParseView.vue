<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import client from "@/api/client";
import type { DocumentResponse, ReviewCreateResponse } from "@/api/types";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const store = useSessionStore();
const error = ref("");
const loading = ref(false);
const demoteOnFigures = ref(false);
const useLlm = ref(true);

const paragraphs = ref<Array<{ index: number; text: string }>>([]);
const tables = ref<DocumentResponse["tables"]>([]);
const sourceName = ref("");
const activeSectionIndex = ref<number | null>(null);

const sections = computed(() =>
  [...store.sections].sort((a, b) => a.paragraph_index - b.paragraph_index),
);

/** 章节大纲需展示段落范围；用下一节的起点作为本节的结束边界。 */
function sectionRange(index: number): string {
  const current = sections.value[index];
  const next = sections.value[index + 1];
  const start = current.paragraph_index + 1;
  const end = next ? next.paragraph_index : paragraphs.value.length;
  return end > start ? `P${start}-${end}` : `P${start}`;
}

const needsReview = computed(() => sections.value.filter((section) => section.needs_review).length);

onMounted(async () => {
  if (!store.documentId) return;
  try {
    const { data } = await client.get<DocumentResponse>(`/documents/${store.documentId}`);
    paragraphs.value = data.paragraphs.filter((paragraph) => paragraph.text.trim());
    tables.value = data.tables ?? [];
    sourceName.value = data.source_name ?? "";
    if (sections.value.length) activeSectionIndex.value = 0;
  } catch (err) {
    error.value = (err as Error).message;
  }
});

/** 点击大纲某节，右侧原文滚动到该节起始段落。 */
function locateSection(index: number) {
  activeSectionIndex.value = index;
  const target = sections.value[index];
  if (!target) return;
  const node = document.querySelector<HTMLElement>(`[data-paragraph-index="${target.paragraph_index}"]`);
  node?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function runReview() {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await client.post<ReviewCreateResponse>("/reviews", {
      document_id: store.documentId,
      use_llm: useLlm.value,
      demote_on_figures: demoteOnFigures.value,
    });
    const tokens = data.tokens ?? {};
    store.setTokens(
      useLlm.value
        ? `模型顾问已启用：本次消耗 tokens 输入 ${tokens.input ?? 0} / 输出 ${tokens.output ?? 0}`
        : "本次已手动关闭模型顾问（仅规则判定），tokens 消耗为 0",
    );
    store.setReport(data.report_id);
    void store.fetchReports();
    router.push({ name: "report", params: { id: data.report_id } });
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="parse-view">
    <div class="toolbar">
      <div class="title">解析预览</div>
      <span class="chip pass">章节识别 {{ sections.length }}</span>
      <span v-if="needsReview" class="chip mid">{{ needsReview }} 处待确认</span>
      <span v-else class="chip pass">结构完整</span>
      <div class="toolbar-actions">
        <button class="btn" :disabled="loading" @click="router.push({ name: 'upload' })">重新上传</button>
        <button class="btn primary" :disabled="loading || !store.documentId" @click="runReview">
          {{ loading ? "审查中…" : "开始结构化审查 →" }}
        </button>
      </div>
    </div>

    <p v-if="sourceName" class="tiny source">来源文件：{{ sourceName }}</p>
    <p v-if="store.warnings.length" class="warn">⚠ {{ store.warnings.join("；") }}</p>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="split">
      <div class="card outline">
        <div class="outline-head">章节大纲</div>
        <div
          v-for="(section, index) in sections"
          :key="section.id"
          class="outline-item"
          :class="{ active: activeSectionIndex === index }"
          @click="locateSection(index)"
        >
          <span :class="section.needs_review ? 'warn-dot' : 'ok-dot'" />
          <span class="outline-title">{{ section.title }}</span>
          <span class="tiny range">{{ sectionRange(index) }}</span>
          <span v-if="section.needs_review" class="chip mid mini-chip">待确认</span>
        </div>
        <p v-if="!sections.length" class="tiny empty">未识别到章节，可返回上传页更换文件。</p>
        <div class="outline-tip">💡 点击章节可定位原文；识别不确定的章节会在报告页标注为待确认。</div>
      </div>

      <div class="paper card">
        <template v-for="paragraph in paragraphs" :key="paragraph.index">
          <p :data-paragraph-index="paragraph.index">{{ paragraph.text }}</p>
        </template>
        <template v-for="table in tables" :key="table.id">
          <figure class="table-block" :data-paragraph-index="table.anchor.paragraph_index">
            <figcaption v-if="table.caption">{{ table.caption }}</figcaption>
            <table>
              <thead v-if="table.header_rows > 0">
                <tr>
                  <th v-for="(cell, column) in table.rows[0]" :key="column">{{ cell ?? "" }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, line) in table.rows.slice(table.header_rows)" :key="line">
                  <td v-for="(cell, column) in row" :key="column">{{ cell ?? "" }}</td>
                </tr>
              </tbody>
            </table>
          </figure>
        </template>
        <p v-if="!paragraphs.length" class="tiny empty">原文暂不可见（会话可能已过期，请重新上传）。</p>
      </div>
    </div>

    <div class="card options">
      <label class="option">
        <input v-model="useLlm" type="checkbox" />
        启用模型顾问（默认开启；模型建议列为「存疑」，会产生 API token 消耗）
      </label>
      <label class="option">
        <input v-model="demoteOnFigures" type="checkbox" />
        图表未解析时保守处理（可能依赖图表的条目列为「存疑」）
      </label>
    </div>
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
.chip.pass { background: var(--pass-bg); color: var(--pass); }
.chip.mid { background: var(--sev-mid-bg); color: var(--sev-mid); }
.mini-chip { font-size: 10px; padding: 1px 7px; }
.tiny { color: var(--ink-3); font-size: 12px; }
.source { margin: 0 0 10px; }
.split { display: grid; grid-template-columns: 320px 1fr; gap: 20px; align-items: start; }
.outline { padding: 10px; }
.outline-head { padding: 8px 12px 6px; font-weight: 600; font-size: 13px; }
.outline-item { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 1px solid transparent; border-radius: 10px; cursor: pointer; font-size: 13px; }
.outline-item:hover { background: var(--bg); }
.outline-item.active { background: var(--accent-soft); border-color: var(--accent); color: var(--accent-ink); }
.outline-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.range { flex: none; }
.ok-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--pass); flex: none; }
.warn-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--sev-mid); flex: none; }
.outline-tip { padding: 10px 12px; font-size: 12px; color: var(--ink-3); }
.paper { max-height: 68vh; overflow: auto; padding: 34px 40px; max-width: none; }
.paper p { margin: 10px 0; text-align: justify; }
.table-block { margin: 12px 0; }
.table-block figcaption { font-size: 13px; color: #555; margin-bottom: 4px; }
.table-block table { border-collapse: collapse; font-size: 13px; }
.table-block th, .table-block td { border: 1px solid #d9d9d9; padding: 4px 8px; text-align: left; }
.table-block th { background: #fafafa; }
.options { margin-top: 16px; }
.option { display: block; margin: 8px 0; font-size: 13px; color: var(--ink-2); }
.warn { color: var(--sev-mid); }
.empty { color: var(--ink-3); }
.error { color: var(--sev-high); }
@media (max-width: 980px) {
  .split { grid-template-columns: 1fr; }
  .paper { max-height: none; }
}
</style>
