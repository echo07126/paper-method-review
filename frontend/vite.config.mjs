import { fileURLToPath, URL } from "node:url";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    // 显式绑定 IPv4 回环。Vite 默认 host 是 `localhost`，在启用了 IPv6 的 Windows 上
    // Node 会把它解析成 ::1 并**只监听 IPv6**，于是文档/演示脚本里写的 http://127.0.0.1:5173
    // 会直接「拒绝连接」；固定成 127.0.0.1 后两个写法都能用。
    host: "127.0.0.1",
    port: 5173,
    // 仅本机开发用；对外交付走 nginx（见 frontend/nginx.conf），不要把 dev server 暴露到局域网。
    strictPort: true,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
});
