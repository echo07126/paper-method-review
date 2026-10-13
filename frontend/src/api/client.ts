import axios from "axios";

import { detailMessage } from "@/api/errorMessage";

/** 接口前缀：导出等需要浏览器直接跳转的链接据此拼接，避免各处硬编码 /api/v1。 */
export const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

const client = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  timeout: 120000,
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const payload = error?.response?.data ?? {};
    const status = error?.response?.status;
    const timedOut =
      error?.code === "ECONNABORTED" || /timeout/i.test(String(error?.message ?? ""));
    let code: string;
    let message: string;
    if (timedOut) {
      code = "timeout";
      message =
        "请求超时：后端未在等待时限内响应。重任务（审查 / 生成修改稿 / 问答）已改为后台任务 + 轮询，若本提示频繁出现，请检查网络或后端服务状态。";
    } else if (!error?.response) {
      code = "network_error";
      message =
        "无法连接后端服务：请确认后端已在 127.0.0.1:8000 运行（或容器已启动），并检查浏览器代理/防火墙未拦截 /api 请求。";
    } else {
      code = payload.code ?? "http_error";
      message =
        payload.message ??
        detailMessage(payload.detail) ??
        `服务异常（HTTP ${status}），请稍后重试。`;
    }
    const wrapped = new Error(message);
    Object.assign(wrapped, { code, requestId: payload.request_id, status });
    return Promise.reject(wrapped);
  },
);

export default client;
