<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import client, { API_BASE } from "@/api/client";
import type { ReportSummary } from "@/api/types";
import SeverityChip from "@/components/SeverityChip.vue";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const store = useSessionStore();
const reports = ref<ReportSummary[]>([]);
const loading = ref(true);
const error = ref("");
const keyword = ref("");
const purging = ref(false);
const notice = ref("");

const visible = ref<ReportSummary[]>([]);

function time(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function open(report: ReportSummary) {
  store.setDocument(report.document_id);
  store.setReport(report.report_id);
  router.push({ name: "report", params: { id: report.report_id } });
}

function exportReport(report: ReportSummary) {
  window.open(`${API_BASE}/reports/${report.report_id}/export?format=markdown`, "_blank");
}

function applyFilter() {
  const key = keyword.value.trim().toLowerCase();
  if (!key) {
    visible.value = reports.value;
    return;
  }
  visible.value = reports.value.filter((item) => (item.document_name ?? "").toLowerCase().includes(key));
}

/**
 * 一键删除本会话数据（页面文案承诺的能力，此前只有后端接口、前端无入口）。
 * 后端会一并清掉报告、文档、追问历史、任务记录与临时目录，并让会话 cookie 失效。
 */
async function purgeSession() {
  if (purging.value) return;
  if (!window.confirm("将删除本会话的全部报告、上传原文与中间结果，删除后不可恢复。确定继续？")) return;
  purging.value = true;
  error.value = "";
  notice.value = "";
  try {
    await client.post("/sessions/purge");
    reports.value = [];
    visible.value = [];
    keyword.value = "";
    // 本地状态一并清空，避免报告页/解析页继续引用已删除的 ID
    store.$reset();
    notice.value = "本会话数据已删除：报告、原文与中间结果均已清除。";
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    purging.value = false;
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    // 复用 store 的报告缓存（与对比页共用一份，避免重复拉取）
    const list = await store.fetchReports();
    reports.value = list;
    visible.value = list;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="card">
    <h2>报告历史</h2>
    <p class="muted">
      当前会话（免登录访客）产生的审查报告。报告仅在会话内保留，可一键删除；删除后历史一并清空。
    </p>

    <div class="toolbar">
      <input v-model="keyword" placeholder="按论文名筛选" @input="applyFilter" />
      <button class="primary" @click="router.push({ name: 'compare' })">去做修改对比</button>
      <button class="danger" :disabled="purging" @click="purgeSession">
        {{ purging ? "删除中…" : "一键删除本会话数据" }}
      </button>
    </div>

    <p v-if="notice" class="notice">{{ notice }}</p>

    <p v-if="loading" class="muted">加载中…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <p v-else-if="!visible.length" class="muted">暂无报告：先上传一篇论文完成审查。</p>

    <table v-else class="history">
      <thead>
        <tr>
          <th>论文</th>
          <th>问题分布</th>
          <th>生成时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="report in visible" :key="report.report_id">
          <td class="name">{{ report.document_name ?? "（未命名）" }}</td>
          <td class="counts">
            <SeverityChip severity="high" /> {{ report.counts.high ?? 0 }}
            <SeverityChip severity="mid" /> {{ report.counts.mid ?? 0 }}
            <SeverityChip severity="low" /> {{ report.counts.low ?? 0 }}
            <SeverityChip severity="uncertain" /> {{ report.counts.uncertain ?? 0 }}
          </td>
          <td class="time">{{ time(report.created_at) }}</td>
          <td class="ops">
            <button @click="open(report)">查看</button>
            <button @click="exportReport(report)">导出</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
h2 { margin: 0 0 6px; font-size: 20px; }
.muted { color: var(--ink-2); }
.error { color: var(--sev-high); }
.toolbar { display: flex; gap: 12px; align-items: center; margin: 14px 0; }
.toolbar input { flex: 1; padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; }
.primary { background: var(--accent); color: #fff; border: none; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.danger { background: #fff; color: var(--sev-high); border: 1px solid var(--sev-high); padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.danger:disabled { opacity: 0.55; cursor: not-allowed; }
.notice { color: var(--pass); font-size: 13px; margin: 0 0 12px; }
.history { width: 100%; border-collapse: collapse; font-size: 14px; }
.history th, .history td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: middle; }
.history th { color: var(--ink-3); font-weight: 600; font-size: 12px; }
.name { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.counts { white-space: nowrap; }
.counts :deep(.chip) { margin-right: 4px; }
.time { color: var(--ink-2); font-variant-numeric: tabular-nums; }
.ops button { border: 1px solid var(--line); background: #fff; border-radius: 8px; padding: 5px 12px; margin-right: 8px; cursor: pointer; font-size: 13px; }
.ops button:hover { border-color: var(--accent); color: var(--accent); }
</style>
