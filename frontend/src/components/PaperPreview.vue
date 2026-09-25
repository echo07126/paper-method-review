<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

import type { Table } from "@/api/types";

const props = defineProps<{
  paragraphs: Array<{ index: number; text: string }>;
  tables?: Table[];
  highlightIndex?: number | null;
  /** 由父组件统一滚动时置 true：自身只负责高亮，不再抢占滚动 */
  externalScroll?: boolean;
  /** 最小高度：内容不足时仍撑开容器，避免看起来「显示不全」 */
  minHeight?: string;
}>();

type Block = { kind: "para"; index: number; text: string } | { kind: "table"; table: Table };

// 表格已从正文段落流移出，按锚点（其前一段的序号）插回原文位置
const blocks = computed<Block[]>(() => {
  const sorted = [...(props.tables ?? [])].sort(
    (a, b) => a.anchor.paragraph_index - b.anchor.paragraph_index,
  );
  const result: Block[] = [];
  let cursor = 0;
  for (const table of sorted) {
    while (
      cursor < props.paragraphs.length &&
      props.paragraphs[cursor].index <= table.anchor.paragraph_index
    ) {
      const paragraph = props.paragraphs[cursor++];
      result.push({ kind: "para", index: paragraph.index, text: paragraph.text });
    }
    result.push({ kind: "table", table });
  }
  while (cursor < props.paragraphs.length) {
    const paragraph = props.paragraphs[cursor++];
    result.push({ kind: "para", index: paragraph.index, text: paragraph.text });
  }
  return result;
});

const paper = ref<HTMLElement | null>(null);

// 点击左侧问题 → 右侧滚动到对应段落（段落由后端锚点 paragraph_index 定位）
async function scrollToHighlight(index: number | null | undefined) {
  await nextTick();
  const host = paper.value;
  if (!host || index === null || index === undefined) return;
  const target =
    host.querySelector<HTMLElement>(`[data-paragraph-index="${index}"]`) ??
    host.querySelector<HTMLElement>(".hl");
  if (!target) return;
  // 表格等块状元素可能尚未完成布局，用 rAF 再量一次位置，避免定位偏移
  await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  const top = target.offsetTop - host.clientHeight / 2 + target.clientHeight / 2;
  host.scrollTo({ top: Math.max(top, 0), behavior: "smooth" });
}

watch(
  () => props.highlightIndex,
  (index) => {
    if (props.externalScroll) return;
    void scrollToHighlight(index);
  },
  { immediate: true },
);

/** 供对比页等父组件主动触发定位（watch 只覆盖高亮值变化）。 */
defineExpose({ scrollToParagraph: scrollToHighlight });
</script>

<template>
  <div ref="paper" class="card paper" :style="minHeight ? { minHeight } : undefined">
    <template v-for="(block, position) in blocks" :key="position">
      <p
        v-if="block.kind === 'para'"
        :data-paragraph-index="block.index"
        :class="{ hl: block.index === highlightIndex }"
      >
        {{ block.text }}
      </p>
      <figure
        v-else
        class="table-block"
        :data-paragraph-index="block.table.anchor.paragraph_index"
        :class="{ hl: block.table.anchor.paragraph_index === highlightIndex }"
      >
        <figcaption v-if="block.table.caption">{{ block.table.caption }}</figcaption>
        <table>
          <thead v-if="block.table.header_rows > 0">
            <tr>
              <th v-for="(cell, column) in block.table.rows[0]" :key="column">{{ cell ?? "" }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, line) in block.table.rows.slice(block.table.header_rows)" :key="line">
              <td v-for="(cell, column) in row" :key="column">{{ cell ?? "" }}</td>
            </tr>
          </tbody>
        </table>
      </figure>
    </template>
    <p v-if="!blocks.length" class="empty">原文不可见（会话可能已过期）。</p>
  </div>
</template>

<style scoped>
.paper { max-height: 70vh; overflow: auto; scroll-behavior: smooth; }
.paper p { margin: 8px 0; text-align: justify; }
.hl { background: #ffe58f; border-radius: 3px; }
.table-block { margin: 12px 0; }
.table-block figcaption { font-size: 13px; color: #555; margin-bottom: 4px; }
.table-block table { border-collapse: collapse; font-size: 13px; }
.table-block th,
.table-block td { border: 1px solid #d9d9d9; padding: 4px 8px; text-align: left; }
.table-block th { background: #fafafa; }
</style>
