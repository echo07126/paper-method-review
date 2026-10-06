import axios from "axios";

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
    const wrapped = new Error(payload.message ?? "网络或服务异常，请稍后重试。");
    Object.assign(wrapped, { code: payload.code ?? "network_error", requestId: payload.request_id });
    return Promise.reject(wrapped);
  },
);

export default client;
