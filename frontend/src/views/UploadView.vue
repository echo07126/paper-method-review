<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import client from "@/api/client";
import type { UploadResponse } from "@/api/types";
import { useSessionStore } from "@/stores/session";

const router = useRouter();
const store = useSessionStore();
const file = ref<File | null>(null);
const error = ref("");
const loading = ref(false);

function onPick(event: Event) {
  const target = event.target as HTMLInputElement;
  file.value = target.files?.[0] ?? null;
}

async function upload() {
  if (!file.value) {
    error.value = "请先选择 DOCX 文件（一期仅支持 DOCX，PDF 支持将在后续版本提供）。";
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    const form = new FormData();
    form.append("file", file.value);
    const { data } = await client.post<UploadResponse>("/uploads", form);
    store.setUpload(data.document_id, data.sections, data.warnings);
    router.push({ name: "parse" });
  } catch (err) {
    error.value = (err as Error).message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="card">
    <h1>给论文做一次「方法学体检」</h1>
    <p class="muted">上传 DOCX → 解析分章 → 结构化审查 → 可定位原文的报告（一期仅支持 DOCX，PDF 支持将在后续版本提供）</p>
    <input type="file" accept=".docx" @change="onPick" />
    <button class="primary" :disabled="loading" @click="upload">
      {{ loading ? "上传中…" : "上传并解析" }}
    </button>
    <p v-if="error" class="error">{{ error }}</p>
    <p class="muted">隐私说明：论文内容将发送至大模型服务商，仅用于本次审查、不作为训练数据；服务端仅在本次会话内暂存正文（随机文件名的临时目录与结构化中间结果），可随时一键删除，会话过期或服务重启后自动清除。</p>
  </div>
</template>

<style scoped>
h1 { font-size: 24px; margin: 0 0 8px; }
.muted { color: var(--ink-2); }
.primary { margin-left: 12px; background: var(--accent); color: #fff; border: none; padding: 9px 18px; border-radius: 10px; cursor: pointer; }
.error { color: var(--sev-high); }
</style>
