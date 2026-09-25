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
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null;
  error.value = "";
}

function onDrop(event: DragEvent) {
  event.preventDefault();
  const dropped = event.dataTransfer?.files?.[0] ?? null;
  if (dropped) {
    file.value = dropped;
    error.value = "";
  }
}

async function upload() {
  if (!file.value) {
    error.value = "请先选择 DOCX 文件（一期仅支持 DOCX，PDF 支持将在后续版本提供）。";
    return;
  }
  if (!file.value.name.toLowerCase().endsWith(".docx")) {
    error.value = "一期仅支持 DOCX；PDF 支持将在后续版本提供。";
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
  <div class="upload-wrap">
    <div class="hero-kicker">给论文做一次「方法学体检」</div>
    <h1>投稿前，先让 AI 帮你查一遍研究设计与统计方法</h1>
    <p class="muted">上传论文（DOCX）→ 按清单逐条体检 → 输出可定位到原文的审查报告</p>

    <label
      class="dropzone"
      :class="{ ready: file }"
      @dragover.prevent
      @drop="onDrop"
    >
      <input class="file-input" type="file" accept=".docx" @change="onPick" />
      <div class="dz-icon">📄</div>
      <p class="dz-title">{{ file ? file.name : "点击或拖拽论文到此处" }}</p>
      <p class="tiny">
        当前支持 DOCX · 建议 50MB 以内 · 60 页以内 · 即传即审，可随时删除（PDF 支持将在后续版本提供）
      </p>
    </label>

    <button class="btn primary" :disabled="loading || !file" @click="upload">
      {{ loading ? "上传解析中…" : "上传并解析 →" }}
    </button>

    <div class="flow-mini">
      <span><b>1</b> 上传与解析</span><span>→</span>
      <span><b>2</b> 结构化审查</span><span>→</span>
      <span><b>3</b> 分级报告与定位</span><span>→</span>
      <span><b>4</b> 修改后对比</span>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="privacy-note">
      🔒 论文内容将发送至大模型服务商，仅用于本次审查、不作为训练数据；服务端仅在本次会话内暂存正文
      （随机文件名的临时目录与结构化中间结果），可随时一键删除，会话过期或服务重启后自动清除。
    </div>
  </div>
</template>

<style scoped>
.upload-wrap { max-width: 760px; margin: 36px auto 0; text-align: center; }
.hero-kicker { color: var(--accent-strong); font-weight: 600; letter-spacing: 0.5px; }
.upload-wrap h1 { font-size: 30px; margin: 10px 0 12px; font-weight: 700; }
.muted { color: var(--ink-2); }
.dropzone {
  display: block; margin: 26px auto 16px; padding: 44px 20px; cursor: pointer;
  border: 2px dashed #d4d8e3; border-radius: var(--radius); background: var(--panel);
  max-width: 560px; transition: 0.15s;
}
.dropzone:hover { border-color: var(--accent); background: var(--accent-soft); }
.dropzone.ready { border-color: var(--accent); background: var(--accent-soft); }
.file-input { display: none; }
.dz-icon { font-size: 34px; }
.dz-title { font-weight: 600; margin-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding: 0 12px; }
.tiny { color: var(--ink-3); font-size: 12px; }
.btn { border: 1px solid #d4d8e3; background: #fff; color: var(--ink); padding: 9px 18px; border-radius: 10px; font-size: 14px; font-weight: 500; cursor: pointer; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; padding: 11px 26px; }
.btn.primary:disabled { opacity: 0.55; cursor: not-allowed; }
.flow-mini { display: flex; justify-content: center; gap: 10px; margin: 22px 0; font-size: 13px; color: var(--ink-2); flex-wrap: wrap; }
.flow-mini b { color: var(--accent-strong); }
.privacy-note {
  max-width: 640px; margin: 18px auto 0; font-size: 12px; color: var(--ink-3);
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 8px 14px; text-align: left;
}
.error { color: var(--sev-high); }
</style>
