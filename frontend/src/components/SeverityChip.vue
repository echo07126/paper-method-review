<script setup lang="ts">
import type { Severity } from "@/api/types";

const props = defineProps<{ severity: Severity | "uncertain" | "pass" }>();
const labels: Record<string, string> = { high: "严重", mid: "中等", low: "轻微", uncertain: "存疑", pass: "通过" };
</script>

<template>
  <span class="chip" :class="props.severity">{{ labels[props.severity] }}</span>
</template>

<style scoped>
.chip { display: inline-flex; padding: 2px 10px; border-radius: 999px; font-size: 12px; font-weight: 600; }
.chip.high { background: var(--sev-high-bg); color: var(--sev-high); }
.chip.mid { background: var(--sev-mid-bg); color: var(--sev-mid); }
.chip.low { background: var(--sev-low-bg); color: var(--sev-low); }
.chip.uncertain { background: var(--bg); color: var(--ink-2); border: 1px dashed var(--ink-3); }
.chip.pass { background: var(--pass-bg); color: var(--pass); }
</style>
