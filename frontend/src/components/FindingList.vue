<script setup lang="ts">
import { ref, watch } from "vue";

import type { Finding } from "@/api/types";
import SeverityChip from "@/components/SeverityChip.vue";

const props = defineProps<{
  findings: Finding[];
  activeId?: string;
  /** 「修改后展示」全局开关：与工具栏共用同一状态 */
  showRevision?: boolean;
}>();
const emit = defineEmits<{
  (event: "select", finding: Finding): void;
  (event: "ask", finding: Finding): void;
}>();

/** 展开态：点击某条即在清单内联展开详情（详情、定位原文、追问都收在这一条里） */
const expanded = ref<string | null>(null);

function chipOf(finding: Finding): "high" | "mid" | "low" | "uncertain" | "pass" {
  if (finding.verdict === "pass") return "pass";
  return finding.verdict === "uncertain" ? "uncertain" : finding.severity;
}

function verdictLabel(finding: Finding): string {
  if (finding.verdict === "pass") return "通过";
  if (finding.verdict === "not_applicable") return "未适用";
  if (finding.verdict === "uncertain") return "存疑";
  return `问题 · ${finding.severity === "high" ? "严重" : finding.severity === "mid" ? "中等" : "轻微"}`;
}

function anchorLabel(finding: Finding): string {
  const anchor = finding.anchors[0];
  if (!anchor) return "未标注位置";
  return `段落 ${anchor.paragraph_index}${anchor.sentence_index ? ` · 句 ${anchor.sentence_index}` : ""}`;
}

function toggle(finding: Finding) {
  expanded.value = expanded.value === finding.finding_id ? null : finding.finding_id;
  emit("select", finding);
}

watch(
  () => props.activeId,
  (id) => {
    if (id) expanded.value = id;
  },
  { immediate: true },
);
</script>

<template>
  <div class="card finding-list">
    <div class="list-head">
      <b>问题清单（点击展开）</b>
      <span class="tiny">{{ findings.length }} 项</span>
    </div>

    <div class="list-body">
      <div
        v-for="finding in findings"
        :key="finding.finding_id"
        class="finding"
        :class="{ active: finding.finding_id === activeId, open: expanded === finding.finding_id }"
      >
        <button class="f-summary" type="button" @click="toggle(finding)">
          <div class="f-top">
            <SeverityChip :severity="chipOf(finding)" />
            <span class="f-title">{{ finding.headline }}</span>
            <span class="f-arrow">{{ expanded === finding.finding_id ? "▾" : "▸" }}</span>
          </div>
          <div class="f-meta">
            <span>📍 {{ anchorLabel(finding) }}</span>
            <span>判定：{{ verdictLabel(finding) }}</span>
          </div>
        </button>

        <div v-if="expanded === finding.finding_id" class="f-detail">
          <p v-if="finding.description" class="f-desc">{{ finding.description }}</p>

          <div class="f-block">
            <span class="f-label">修改建议</span>
            <p>{{ finding.suggestion || "（本条未给出具体建议）" }}</p>
          </div>

          <div v-if="showRevision" class="f-block revision">
            <span class="f-label">修改后（示范）</span>
            <p>{{ finding.suggested_revision || "（本条暂无示范改写，可点击「追问这条」获取针对性表述）" }}</p>
          </div>

          <div class="f-actions">
            <button type="button" @click.stop="emit('select', finding)">定位原文</button>
            <button type="button" class="ask" @click.stop="emit('ask', finding)">追问这条</button>
          </div>
        </div>
      </div>
      <p v-if="findings.length === 0" class="empty">当前筛选下没有条目。</p>
    </div>
  </div>
</template>

<style scoped>
.finding-list { padding: 0; overflow: hidden; display: flex; flex-direction: column; }
.list-head { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--line); }
.list-head b { font-size: 13.5px; }
.list-body { flex: 1; min-height: 0; overflow: auto; }
.finding { border-bottom: 1px solid var(--line); transition: background 0.12s; }
.finding:last-child { border-bottom: none; }
.finding:hover { background: var(--bg); }
.finding.active { box-shadow: inset 3px 0 0 var(--accent); }
.finding.open { background: var(--accent-soft); }
.f-summary { display: block; width: 100%; padding: 12px 16px; border: none; background: transparent; text-align: left; cursor: pointer; font: inherit; }
.f-top { display: flex; align-items: center; gap: 8px; }
.f-title { flex: 1; font-weight: 600; font-size: 13.5px; }
.f-arrow { color: var(--ink-3); font-size: 12px; }
.f-meta { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 4px; font-size: 11.5px; color: var(--ink-3); }
.f-detail { padding: 0 16px 12px; }
.f-desc { margin: 4px 0 8px; font-size: 13px; color: var(--ink-2); }
.f-block { border-left: 3px solid var(--line); padding: 5px 10px; margin: 8px 0; font-size: 13px; }
.f-block.revision { border-left-color: var(--accent); background: rgba(255, 255, 255, 0.7); border-radius: 0 8px 8px 0; }
.f-block p { margin: 2px 0 0; white-space: pre-wrap; }
.f-label { font-size: 11.5px; color: var(--ink-3); }
.f-actions { display: flex; gap: 8px; margin-top: 10px; }
.f-actions button { font-size: 12px; padding: 4px 10px; border-radius: 8px; border: 1px solid var(--line); background: #fff; cursor: pointer; }
.f-actions .ask { color: var(--accent); border-color: var(--accent); }
.tiny { font-size: 11.5px; color: var(--ink-3); }
.empty { padding: 16px; color: var(--ink-3); }
</style>
