<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <div class="card notfound">
    <h2>页面不存在</h2>
    <p class="muted">该地址没有对应的页面（可能是链接过期或输入有误）。</p>
    <div class="ops">
      <button class="primary" @click="router.push({ name: 'upload' })">回到上传页</button>
      <button @click="router.push({ name: 'history' })">查看报告历史</button>
    </div>
  </div>
</template>

<style scoped>
h2 { margin: 0 0 6px; font-size: 20px; }
.muted { color: var(--ink-2); margin: 0 0 16px; }
.ops { display: flex; gap: 10px; }
.ops button { border: 1px solid var(--line); background: #fff; border-radius: 10px; padding: 9px 18px; cursor: pointer; font-size: 14px; }
.ops .primary { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
