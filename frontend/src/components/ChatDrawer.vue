<script setup lang="ts">
import { ref, watch } from "vue";

import client from "@/api/client";
import type { ChatMessage, ChatResponse, Finding } from "@/api/types";

const props = defineProps<{
  open: boolean;
  reportId: string;
  finding: Finding | null;
}>();

const emit = defineEmits<{ (event: "close"): void }>();

const messages = ref<ChatMessage[]>([]);
const input = ref("");
const loading = ref(false);
const error = ref("");
const truncated = ref(false);

/** 会话数据被清理后，用本地上下文继续追问（服务端仅在落库为空时采用）。 */
let localHistory: ChatMessage[] = [];

function contextualQuestion(question: string): string {
  if (!props.finding) return question;
  return `（针对「${props.finding.headline}」）${question}`;
}

async function send() {
  const question = input.value.trim();
  if (!question || loading.value) return;
  input.value = "";
  error.value = "";
  messages.value.push({ role: "user", content: question });
  loading.value = true;
  try {
    const { data } = await client.post<ChatResponse>(`/reports/${props.reportId}/chat`, {
      question: contextualQuestion(question),
      finding_id: props.finding?.finding_id ?? null,
      history: localHistory,
    });
    messages.value.push({ role: "assistant", content: data.answer });
    localHistory = data.history;
    truncated.value = data.truncated;
    if (data.note) error.value = data.note;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.open, props.finding?.finding_id] as const,
  ([open]) => {
    if (!open) return;
    if (messages.value.length === 0 && props.finding) {
      messages.value.push({
        role: "assistant",
        content: `已定位「${props.finding.headline}」。可以直接提问，例如「这句该怎么改？」`,
      });
    }
  },
);
</script>

<template>
  <aside v-if="open" class="drawer">
    <div class="head">
      <b>追问 / 自由提问</b>
      <button @click="emit('close')">✕</button>
    </div>
    <p v-if="finding" class="ctx">当前上下文：{{ finding.headline }}（段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }}）</p>
    <div class="body">
      <div v-for="(message, index) in messages" :key="index" class="bubble" :class="message.role === 'user' ? 'q' : 'a'">
        {{ message.content }}
      </div>
      <div v-if="loading" class="bubble a">正在思考…</div>
    </div>
    <p v-if="truncated" class="hint">上下文已达上限（最近 10 轮 / 8000 字符），更早的对话已被截断。</p>
    <p v-if="error" class="error">{{ error }}</p>
    <form class="composer" @submit.prevent="send">
      <input v-model="input" placeholder="输入问题，回车发送" :disabled="loading" />
      <button type="submit" :disabled="loading || !input.trim()">发送</button>
    </form>
  </aside>
</template>

<style scoped>
.drawer { position: fixed; top: 0; right: 0; bottom: 0; width: 400px; background: #fff; box-shadow: -12px 0 40px rgba(20, 24, 40, 0.12); display: flex; flex-direction: column; }
.head { display: flex; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.ctx { margin: 0; padding: 8px 18px; font-size: 12px; color: var(--ink-3); border-bottom: 1px solid var(--line); }
.body { flex: 1; overflow: auto; padding: 16px; display: flex; flex-direction: column; }
.bubble { max-width: 86%; padding: 9px 13px; border-radius: 12px; margin: 6px 0; white-space: pre-wrap; }
.bubble.q { background: var(--accent); color: #fff; align-self: flex-end; }
.bubble.a { background: var(--bg); align-self: flex-start; }
.hint { margin: 0; padding: 6px 18px; font-size: 12px; color: var(--ink-3); }
.error { margin: 0; padding: 6px 18px; font-size: 12px; color: var(--sev-high); }
.composer { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--line); }
.composer input { flex: 1; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; }
</style>
