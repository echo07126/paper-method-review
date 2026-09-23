<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const steps = [
  { name: "upload", label: "① 上传" },
  { name: "parse", label: "② 解析预览" },
  { name: "report", label: "③ 审查报告" },
  { name: "compare", label: "④ 修改对比" },
];
const historyRoute = { name: "history", label: "报告历史" };

const active = computed(() => route.name);

function go(name: string) {
  if (name === "upload") {
    router.push({ name: "upload" });
    return;
  }
  router.push({ name });
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="brand"><span class="logo">检</span>论文方法论审查助手</div>
      <nav class="steps">
        <button
          v-for="step in steps"
          :key="step.name"
          :class="{ active: active === step.name }"
          @click="go(step.name)"
        >
          {{ step.label }}
        </button>
        <span class="divider" />
        <button
          :class="{ active: active === historyRoute.name }"
          data-testid="nav-history"
          @click="go(historyRoute.name)"
        >
          {{ historyRoute.label }}
        </button>
      </nav>
      <div class="guest">访客模式 · 免登录</div>
    </header>

    <main class="app-main">
      <router-view />
    </main>

    <footer class="footer">示例为自建脱敏演示稿 · 即传即审 · 可随时删除 · 不用于模型训练</footer>
  </div>
</template>

<style scoped>
.topbar {
  display: flex; align-items: center; gap: 20px; padding: 12px 28px;
  background: var(--panel); border-bottom: 1px solid var(--line);
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 600; }
.logo {
  width: 30px; height: 30px; border-radius: 9px; background: var(--accent);
  color: #fff; display: grid; place-items: center; font-weight: 700;
}
.steps { display: flex; gap: 4px; margin: 0 auto; background: var(--bg); border: 1px solid var(--line); border-radius: 999px; padding: 4px; align-items: center; }
.steps button { border: none; background: transparent; color: var(--ink-2); padding: 6px 14px; border-radius: 999px; cursor: pointer; font-size: 13px; }
.steps button.active { background: var(--accent); color: #fff; }
.divider { width: 1px; height: 18px; background: var(--line); margin: 0 6px; }
.guest { font-size: 12px; color: var(--ink-3); }
.footer { border-top: 1px solid var(--line); background: var(--panel); padding: 12px 28px; font-size: 12px; color: var(--ink-3); text-align: center; }
</style>
