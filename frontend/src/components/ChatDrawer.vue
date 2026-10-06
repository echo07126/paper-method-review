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

type LocalMessage = ChatMessage & { key: number };

const messages = ref<LocalMessage[]>([]);
const input = ref("");
const loading = ref(false);
const error = ref("");
const note = ref("");
const truncated = ref(false);
const scope = ref<"finding" | "fulltext">("finding");
const body = ref<HTMLElement | null>(null);

/** 会话数据被清理后，用本地上下文继续追问（服务端仅在落库为空时采用）。 */
let localHistory: ChatMessage[] = [];
let messageSeq = 0;

function pushMessage(role: "user" | "assistant", content: string) {
  messages.value.push({ role, content, key: ++messageSeq });
}

const isFulltext = computed(() => scope.value === "fulltext");

/** 两种模式在标题、开场白、占位符、示例问法上完全区分，避免被当成同一种对话。 */
const scopeLabel = computed(() => (isFulltext.value ? "全文自由提问" : "追问这条问题"));
const scopeHint = computed(() =>
  isFulltext.value
    ? "模型已通读全文并记忆本会话 · 可问全文任意位置"
    : "仅围绕这一条问题作答 · 不扩展到全文",
);
const placeholder = computed(() =>
  isFulltext.value
    ? "就全文任意部分提问：方法、实验、写作、可扩展方向…"
    : "追问这条问题：为什么算问题、该怎么改…",
);
const starterExamples = computed<string[]>(() =>
  isFulltext.value
    ? [
        "这篇文章最致命的三个方法学问题是什么？",
        "如果只能再补一个实验，补哪个最划算？",
        "结论外推的部分，应该限定到什么范围？",
      ]
    : [
        "这条为什么算问题？审稿人会怎么追问？",
        "给出可直接替换这段的改写句式。",
        "要补哪些数据或实验才算达标？",
      ],
);

function contextualQuestion(question: string): string {
  if (!props.finding) return question;
  return `（针对「${props.finding.headline}」）${question}`;
}

async function send() {
  const question = input.value.trim();
  if (!question || loading.value) return;
  input.value = "";
  error.value = "";
  note.value = "";
  pushMessage("user", question);
  loading.value = true;
  void scrollToBottom();
  try {
    const { data } = await client.post<ChatResponse>(`/reports/${props.reportId}/chat`, {
      question: contextualQuestion(question),
      // 自由提问不绑定单条 finding，后端据此注入全文并记忆上下文
      finding_id: props.finding?.finding_id ?? null,
      history: localHistory,
    });
    pushMessage("assistant", data.answer);
    localHistory = data.history;
    truncated.value = data.truncated;
    scope.value = data.scope;
    if (data.note) note.value = data.note;
  } catch (err) {
    // 请求失败：撤回乐观插入的提问并把内容还给输入框，避免留下无回复的孤立气泡
    messages.value.pop();
    input.value = question;
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
  note.value = "";
  scope.value = props.finding ? "finding" : "fulltext";
  if (props.finding) {
    pushMessage(
      "assistant",
      `已锁定「${props.finding.headline}」（段落 ${props.finding.anchors[0]?.paragraph_index ?? "-"}）。\n` +
        "接下来只围绕这条问题回答：为什么算问题、审稿人会怎么追问、怎么改才算达标。",
    );
  } else {
    pushMessage(
      "assistant",
      "已通读全文并在本会话内记住内容（全文将发送至模型服务商，仅用于本次问答、不作为训练数据）。\n" +
        "可以直接问任意位置：方法学是否站得住、实验够不够、结论能否外推，也可以问这项研究还能往哪扩展。",
    );
  }
}

watch(
  () => [props.open, props.reportId, props.finding?.finding_id] as const,
  ([open]) => {
    if (!open) return;
    reset();
    void scrollToBottom();
  },
);
</script>

<template>
  <aside v-if="open" class="drawer" :class="isFulltext ? 'drawer-fulltext' : 'drawer-finding'" aria-label="论文问答">
    <header class="head">
      <div class="head-main">
        <b>{{ scopeLabel }}</b>
        <span class="scope-chip">{{ isFulltext ? "全文" : "单条" }}</span>
      </div>
      <button class="close" type="button" @click="emit('close')">✕</button>
    </header>

    <p class="ctx">{{ scopeHint }}</p>

    <div ref="body" class="body">
      <div
        v-for="message in messages"
        :key="message.key"
        class="bubble"
        :class="message.role === 'user' ? 'q' : 'a'"
      >
        {{ message.content }}
      </div>
      <div v-if="loading" class="bubble a thinking">正在思考…</div>
      <div v-if="messages.length <= 1 && !loading" class="examples">
        <span class="examples-label">{{ isFulltext ? "试试这样问" : "常见追问" }}</span>
        <button
          v-for="example in starterExamples"
          :key="example"
          type="button"
          class="example"
          @click="input = example"
        >
          {{ example }}
        </button>
      </div>
    </div>

    <p v-if="truncated" class="hint">上下文已达上限（最近 10 轮 / 8000 字符），更早的对话已被截断。</p>
    <p v-if="note" class="hint">{{ note }}</p>
    <p v-if="error" class="error">{{ error }}</p>

    <form class="composer" @submit.prevent="send">
      <input v-model="input" :placeholder="placeholder" :disabled="loading" />
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
.drawer-fulltext { border-top: 3px solid var(--accent); }
.drawer-finding { border-top: 3px solid var(--sev-mid); }
.drawer-fulltext .scope-chip { color: var(--accent-ink); background: var(--accent-soft); }
.drawer-finding .scope-chip { color: var(--sev-mid); background: var(--sev-mid-bg); }
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
.examples { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
.examples-label { font-size: 11.5px; color: var(--ink-3); }
.example {
  text-align: left; font-size: 12.5px; padding: 8px 11px; border-radius: 10px;
  border: 1px dashed var(--line); background: #fff; color: var(--ink-2); cursor: pointer;
}
.example:hover { border-color: var(--accent); color: var(--accent-ink); background: var(--accent-soft); }
.error { margin: 0; padding: 6px 18px; font-size: 12px; color: var(--sev-high); }
.composer { display: flex; gap: 8px; padding: 12px 18px; border-top: 1px solid var(--line); }
.composer input { flex: 1; padding: 9px 12px; border: 1px solid var(--line); border-radius: 10px; font-size: 13.5px; }
.composer button { background: var(--accent); color: #fff; border: none; border-radius: 10px; padding: 0 16px; cursor: pointer; }
.composer button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
