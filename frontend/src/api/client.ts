import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? "/api/v1",
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
