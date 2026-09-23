<script setup lang="ts">
defineProps<{ paragraphs: Array<{ index: number; text: string }>; highlightIndex?: number | null }>();
</script>

<template>
  <div class="card paper">
    <p
      v-for="paragraph in paragraphs"
      :key="paragraph.index"
      :class="{ hl: paragraph.index === highlightIndex }"
    >
      {{ paragraph.text }}
    </p>
  </div>
</template>

<style scoped>
.paper { max-height: 70vh; overflow: auto; }
.paper p { margin: 8px 0; text-align: justify; }
.hl { background: #ffe58f; border-radius: 3px; }
</style>
