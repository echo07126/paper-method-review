<script setup lang="ts">
import type { Finding } from "@/api/types";
import SeverityChip from "@/components/SeverityChip.vue";

defineProps<{ findings: Finding[]; activeId?: string }>();
const emit = defineEmits<{ (event: "select", finding: Finding): void }>();

function chipOf(finding: Finding): "high" | "mid" | "low" | "uncertain" | "pass" {
  if (finding.verdict === "pass") return "pass";
  return finding.verdict === "uncertain" ? "uncertain" : finding.severity;
}
</script>

<template>
  <div class="card finding-list">
    <div class="head">问题清单（{{ findings.length }}）</div>
    <button
      v-for="finding in findings"
      :key="finding.finding_id"
      class="item"
      :class="{ active: finding.finding_id === activeId }"
      @click="emit('select', finding)"
    >
      <SeverityChip :severity="chipOf(finding)" />
      <span class="title">{{ finding.headline }}</span>
      <span class="loc">段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }}</span>
    </button>
    <p v-if="findings.length === 0" class="empty">当前筛选下没有条目。</p>
  </div>
</template>

<style scoped>
.finding-list { padding: 0; overflow: hidden; }
.head { padding: 12px 16px; border-bottom: 1px solid var(--line); font-weight: 600; }
.item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 10px 16px; border: none; border-bottom: 1px solid var(--line); background: transparent; text-align: left; cursor: pointer; }
.item:hover { background: var(--bg); }
.item.active { background: var(--accent-soft); }
.title { flex: 1; font-weight: 500; }
.loc { font-size: 12px; color: var(--ink-3); }
.empty { padding: 16px; color: var(--ink-3); }
</style>
