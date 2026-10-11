import client from "@/api/client";
import type { TaskAccepted, TaskStatusResponse } from "@/api/types";

/**
 * 重接口异步化：POST 立即拿到 202 + task_id，再轮询 GET /tasks/{task_id} 取结果。
 *
 * 任务在服务端受控线程池里跑，HTTP 请求寿命与任务寿命解耦——提交后不再有
 * 「一个请求挂到模型链路跑完」的长等待，前端只需短请求轮询。
 */

/** 轮询间隔：够快拿到规则模式的秒级结果，又不至于把后端打满。 */
const POLL_INTERVAL_MS = 1500;
/** 轮询总上限，与后端任务保留期同一量级；超时给出可读提示而非静默挂起。 */
const POLL_TIMEOUT_MS = 10 * 60 * 1000;

export interface SubmitAndPollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  /** 每次拿到新状态时回调（queued/running/succeeded/failed），供界面展示阶段。 */
  onState?: (state: string, kind: string) => void;
}

export async function submitAndPoll<T>(
  url: string,
  body: unknown,
  options: SubmitAndPollOptions = {},
): Promise<T> {
  const interval = options.intervalMs ?? POLL_INTERVAL_MS;
  const deadline = Date.now() + (options.timeoutMs ?? POLL_TIMEOUT_MS);

  const { data: accepted } = await client.post<TaskAccepted>(url, body);
  const pollUrl = accepted.poll_url || `/tasks/${accepted.task_id}`;
  options.onState?.(accepted.state, accepted.kind);

  return new Promise<T>((resolve, reject) => {
    const tick = () => {
      if (Date.now() > deadline) {
        reject(new Error("任务处理超时（已超过 10 分钟），请稍后在报告列表查看结果或重试。"));
        return;
      }
      client
        .get<TaskStatusResponse<T>>(pollUrl)
        .then(({ data }) => {
          options.onState?.(data.state, data.kind);
          if (data.state === "succeeded") {
            resolve(data.result as T);
            return;
          }
          if (data.state === "failed") {
            reject(new Error(data.error?.message ?? "任务执行失败，请稍后重试。"));
            return;
          }
          window.setTimeout(tick, interval);
        })
        .catch((err) => reject(err as Error));
    };
    window.setTimeout(tick, interval);
  });
}