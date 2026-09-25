<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";

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
const scope = ref<"finding" | "fulltext">("finding");
const body = ref<HTMLElement | null>(null);

/** 会话数据被清理后，用本地上下文继续追问（服务端仅在落库为空时采用）。 */
let localHistory: ChatMessage[] = [];

const scopeLabel = computed(() => (scope.value === "fulltext" ? "全文问答" : "追问这条"));

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
  void scrollToBottom();
  try {
    const { data } = await client.post<ChatResponse>(`/reports/${props.reportId}/chat`, {
      question: contextualQuestion(question),
      // 自由提问不绑定单条 finding，后端据此注入全文并记忆上下文
      finding_id: props.finding?.finding_id ?? null,
      history: localHistory,
    });
    messages.value.push({ role: "assistant", content: data.answer });
    localHistory = data.history;
    truncated.value = data.truncated;
    scope.value = data.scope;
    if (data.note) error.value = data.note;
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
    void scrollToBottom();
  }
}

async function scrollToBottom() {
  await nextTick();
  const host = body.value;
  if (host) host.scrollTop = host.scrollHeight;
}

function reset() {
  messages.value = [];
  localHistory = [];
  truncated.value = false;
  error.value = "";
  scope.value = props.finding ? "finding" : "fulltext";
  if (props.finding) {
    messages.value.push({
      role: "assistant",
      content: `已定位「${props.finding.headline}」。可以继续追问这条问题的改法，也可以直接问全文可优化、可扩展的方向。`,
    });
  } else {
    messages.value.push({
      role: "assistant",
      content: "已读取全文。你可以询问任意段落的写法、方法学可优化点，或后续可扩展的研究方向。",
    });
  }
}

watch(
  () => [props.open, props.finding?.finding_id] as const,
  ([open]) => {
    if (!open) return;
    reset();
    void scrollToBottom();
  },
);
</script>

<template>
  <aside v-if="open" class="drawer" aria-label="论文问答">
    <header class="head">
      <div class="head-main">
        <b>{{ scopeLabel }}</b>
        <span class="scope-chip">{{ scope === "fulltext" ? "已载入全文" : "绑定当前问题" }}</span>
      </div>
      <button class="close" type="button" @click="emit('close')">✕</button>
    </header>

    <p v-if="finding" class="ctx">
      当前上下文：{{ finding.headline }}（段落 {{ finding.anchors[0]?.paragraph_index ?? "-" }}）
      · 也可直接问全文其他问题
    </p>
    <p v-else class="ctx">上下文：全文 · 模型已读取本文内容并记忆本会话对话</p>

    <div ref="body" class="body">
      <div
        v-for="(message, index) in messages"
        :key="index"
        class="bubble"
        :class="message.role === 'user' ? 'q' : 'a'"
      >
        {{ message.content }}
      </div>
      <div v-if="loading" class="bubble a thinking">正在思考…</div>
    </div>

    <p v-if="truncated" class="hint">上下文已达上限（最近 10 轮 / 8000 字符），更早的对话已被截断。</p>
    <p v-if="error" class="error">{{ error }}</p>

    <form class="composer" @submit.prevent="send">
      <input
        v-model="input"
        :placeholder="finding ? '追问这条，或直接问全文…' : '询问本文可优化、可扩展的方向…'"
        :disabled="loading"
      />
      <button type="submit" :disabled="loading || !input.trim()">发送</button>
    </form>
  </aside>
</template>

<style scoped>
.drawer {
  position: fixed; top: 0; right: 0; bottom: 0; width: 420px; max-width: 92vw;
  background: #fff; box-shadow: -12px 0 40px rgba(20, 24, 40, 0.12);
  display: flex; flex-direction: column; z-index: 80;
}
.head { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid var(--line); }
.head-main { display: flex; align-items: center; gap: 8px; }
.scope-chip { font-size: 11px; color: var(--accent-ink); background: var(--accent-soft); border-radius: 999px; padding: 2px 8px; }
.close { border: none; background: transparent; cursor: pointer; font-size: 14px; color: var(--ink-3); }
.ctx { margin: 0; padding: 8px 18px; font-size: 12px; color: var(--ink-3); border-bottom: 1px solid var(--line); }
.body { flex: 1; overflow: auto; padding: 16px 18px; display: flex; flex-direction: column; }
.bubble { max-width: 86%; padding: 9px 13px; border-radius: 12px; margin: 6px 0; white-space: pre-wrap; font-size: 13.5px; }
.bubble.q { background: var(--accent); color: #fff; align-self: flex-end; border-bottom-right-radius: 4px; }
.bubble.a { background: var(--bg); align-self: flex-start; border-bottom-left-radius: 4px; }
.bubble.thinking { color: var(--ink-3); }
.hint { margin: 0; padding: 6px 18px; font-size: 12px; color: var(--ink-3); }
.error { margin: 0; padding: 6px 18px; font-size: 12px; color: var(--sev-high); }
.composer { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--line); }
.composer input { flex: 1; padding: 9px 12px; border: 1px solid var(--line); border-radius: 10px; font-size: 13.5px; }
.composer button { background: var(--accent); color: #fff; border: none; border-radius: 10px; padding: 0 16px; cursor: pointer; }
.composer button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
