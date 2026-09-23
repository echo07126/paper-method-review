<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import client from "@/api/client";
import type { ReviewCreateResponse } from "@/api/types";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const store = useSessionStore();
const error = ref("");
const loading = ref(false);
const demoteOnFigures = ref(false);
const useLlm = ref(true);

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
    void store.fetchReports();  // 刷新报告历史（不阻塞跳转）
    router.push({ name: "report", params: { id: data.report_id } });
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="card">
    <h2>解析预览</h2>
    <p v-if="store.warnings.length" class="warn">⚠ {{ store.warnings.join("；") }}</p>
    <ul>
      <li v-for="section in store.sections" :key="section.id">
        {{ section.title }}
        <span v-if="section.needs_review" class="review">待确认</span>
      </li>
    </ul>
    <label class="option"><input v-model="useLlm" type="checkbox" /> 启用模型顾问（默认开启；模型建议列为「存疑」，会产生 API token 消耗）</label>
    <label class="option"><input v-model="demoteOnFigures" type="checkbox" /> 图表未解析时保守处理（可能依赖图表的条目列为「存疑」）</label>
    <button class="primary" :disabled="loading || !store.documentId" @click="runReview">
      {{ loading ? "审查中…" : "开始结构化审查 →" }}
    </button>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<style scoped>
.primary { background: var(--accent); color: #fff; border: none; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.warn { color: var(--sev-mid); }
.review { color: var(--sev-mid); font-size: 12px; margin-left: 6px; }
.option { display: block; margin: 10px 0; font-size: 13px; color: var(--ink-2); }
.error { color: var(--sev-high); }
</style>
