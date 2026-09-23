<script setup lang="ts">
defineProps<{ open: boolean; question: string; answer: string }>();
const emit = defineEmits<{ (event: "close"): void }>();
</script>

<template>
  <aside v-if="open" class="drawer">
    <div class="head"><b>追问这条问题</b><button @click="emit('close')">✕</button></div>
    <div class="body">
      <div class="bubble q">{{ question }}</div>
      <div class="bubble a">{{ answer }}</div>
    </div>
  </aside>
</template>

<style scoped>
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: 400px; background: #fff; box-shadow: -12px 0 40px rgba(20, 24, 40, 0.12); display: flex; flex-direction: column; }
.head { display: flex; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.body { flex: 1; overflow: auto; padding: 16px; display: flex; flex-direction: column; }
.bubble { max-width: 86%; padding: 9px 13px; border-radius: 12px; margin: 6px 0; }
.bubble.q { background: var(--accent); color: #fff; align-self: flex-end; }
.bubble.a { background: var(--bg); align-self: flex-start; }
</style>
