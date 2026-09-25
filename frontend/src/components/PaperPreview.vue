<script setup lang="ts">
import { computed } from "vue";

import type { Table } from "@/api/types";

const props = defineProps<{
  paragraphs: Array<{ index: number; text: string }>;
  tables?: Table[];
  highlightIndex?: number | null;
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
</script>

<template>
  <div class="card paper">
    <template v-for="(block, position) in blocks" :key="position">
      <p v-if="block.kind === 'para'" :class="{ hl: block.index === highlightIndex }">
        {{ block.text }}
      </p>
      <figure
        v-else
        class="table-block"
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
.paper { max-height: 70vh; overflow: auto; }
.paper p { margin: 8px 0; text-align: justify; }
.hl { background: #ffe58f; border-radius: 3px; }
.table-block { margin: 12px 0; }
.table-block figcaption { font-size: 13px; color: #555; margin-bottom: 4px; }
.table-block table { border-collapse: collapse; font-size: 13px; }
.table-block th,
.table-block td { border: 1px solid #d9d9d9; padding: 4px 8px; text-align: left; }
.table-block th { background: #fafafa; }
</style>
