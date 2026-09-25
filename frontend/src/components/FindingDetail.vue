<script setup lang="ts">
import { computed } from "vue";

import type { Finding } from "@/api/types";

const props = defineProps<{
  selected: Finding | null;
  /** 是否展开「修改后展示」（可选，默认隐藏；由报告页统一开关控制） */
  showRevision?: boolean;
}>();
const emit = defineEmits<{
  (event: "locate", finding: Finding): void;
  (event: "ask", finding: Finding): void;
  (event: "update:showRevision", value: boolean): void;
}>();

const revisionOpen = computed({
  get: () => props.showRevision === true,
  set: (value: boolean) => emit("update:showRevision", value),
});

const current = computed(() => props.selected);
</script>

<template>
  <section class="detail card">
    <header class="head">
      <b>问题详情</b>
      <label class="switch">
        <input v-model="revisionOpen" type="checkbox" />
        显示修改后
      </label>
    </header>

    <p v-if="!current" class="empty">点击左侧任意问题，查看证据、修改建议与修改后示范。</p>

    <template v-else>
      <h3>{{ current.headline }}</h3>
      <p v-if="current.description" class="desc">{{ current.description }}</p>

      <div class="block">
        <span class="label">修改建议</span>
        <p>{{ current.suggestion || "（本条未给出具体建议）" }}</p>
      </div>

      <div v-if="revisionOpen" class="block revision">
        <span class="label">修改后（示范）</span>
        <p>{{ current.suggested_revision || "（本条暂无示范改写，可点击「追问这条」获取针对性表述）" }}</p>
      </div>

      <div class="actions">
        <button type="button" @click="emit('locate', current)">定位原文</button>
        <button type="button" class="ask" @click="emit('ask', current)">追问这条</button>
      </div>
    </template>
  </section>
</template>

<style scoped>
.detail { margin-top: 16px; }
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.switch { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--ink-2); cursor: pointer; }
h3 { margin: 6px 0 8px; font-size: 15px; }
.desc { color: var(--ink-2); margin: 0 0 10px; }
.block { border-left: 3px solid var(--line); padding: 6px 12px; margin: 8px 0; }
.block.revision { border-left-color: var(--accent); background: var(--accent-soft); border-radius: 0 8px 8px 0; }
.block p { margin: 2px 0 0; white-space: pre-wrap; }
.label { font-size: 12px; color: var(--ink-3); }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.actions button { font-size: 12px; padding: 5px 12px; border-radius: 8px; border: 1px solid var(--line); background: #fff; cursor: pointer; }
.actions .ask { color: var(--accent); border-color: var(--accent); }
.empty { color: var(--ink-3); margin: 0; }
</style>
