<script setup lang="ts">
import { onMounted, ref } from "vue";

import client from "@/api/client";
import type { ReportSummary } from "@/api/types";

interface CompareResult {
  before: Record<string, number>;
  after: Record<string, number>;
  resolved: string[];
  new: string[];
  kept: string[];
}

const reports = ref<ReportSummary[]>([]);
const beforeId = ref("");
const afterId = ref("");
const result = ref<CompareResult | null>(null);
const error = ref("");

function label(report: ReportSummary): string {
  const counts = report.counts ?? {};
  return `${report.document_name} · 严重 ${counts.high ?? 0} / 中等 ${counts.mid ?? 0} / 轻微 ${counts.low ?? 0}`;
}

onMounted(async () => {
  try {
    const { data } = await client.get<ReportSummary[]>("/reports");
    reports.value = data;
    if (data.length >= 2) {
      afterId.value = data[0].report_id;
      beforeId.value = data[1].report_id;
    } else if (data.length === 1) {
      beforeId.value = data[0].report_id;
    }
  } catch (err) {
    error.value = (err as Error).message;
  }
});

async function compare() {
  error.value = "";
  if (!beforeId.value || !afterId.value) {
    error.value = "请先选择初稿与修改稿对应的两份报告。";
    return;
  }
  try {
    const { data } = await client.post<CompareResult>("/compare", {
      before_report_id: beforeId.value,
      after_report_id: afterId.value,
    });
    result.value = data;
  } catch (err) {
    error.value = (err as Error).message;
  }
}
</script>

<template>
  <div class="card">
    <h2>修改前后对比</h2>
    <p class="muted">选择同一篇论文的初稿与修改稿报告，查看问题数量与清单条目变化。</p>
    <div class="row">
      <label>初稿：</label>
      <select v-model="beforeId">
        <option value="">请选择报告</option>
        <option v-for="report in reports" :key="report.report_id" :value="report.report_id">
          {{ label(report) }}
        </option>
      </select>
    </div>
    <div class="row">
      <label>修改稿：</label>
      <select v-model="afterId">
        <option value="">请选择报告</option>
        <option v-for="report in reports" :key="report.report_id" :value="report.report_id">
          {{ label(report) }}
        </option>
      </select>
    </div>
    <button class="primary" @click="compare">开始对比</button>
    <p v-if="error" class="error">{{ error }}</p>
    <div v-if="result" class="result">
      <p>初稿问题：{{ result.before.total ?? 0 }} → 修改稿问题：{{ result.after.total ?? 0 }}</p>
      <p>已解决：{{ result.resolved.join("、") || "无" }}</p>
      <p>仍保留：{{ result.kept.join("、") || "无" }}</p>
      <p>新增：{{ result.new.join("、") || "无" }}</p>
    </div>
  </div>
</template>

<style scoped>
.muted { color: var(--ink-2); }
.row { margin: 10px 0; }
label { display: inline-block; width: 70px; }
select { min-width: 420px; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; }
.primary { margin-top: 8px; background: var(--accent); color: #fff; border: none; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.result { margin-top: 14px; }
.error { color: var(--sev-high); }
</style>
