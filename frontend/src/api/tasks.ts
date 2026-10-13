import client from "@/api/client";
import { createPoll, type PollState } from "@/api/pollMachine";
import type { TaskAccepted, TaskStatusResponse } from "@/api/types";

/**
 * 重接口异步化：POST 立即拿到 202 + task_id，再轮询 GET /tasks/{task_id} 取结果。
 *
 * 任务在服务端受控线程池里跑，HTTP 请求寿命与任务寿命解耦——提交后不再有
 * 「一个请求挂到模型链路跑完」的长等待，前端只需短请求轮询。
 *
 * 调度、超时、重试与取消的规则都在 `pollMachine.ts`（已单测覆盖）；这里只做 HTTP 适配。
 */

/** 轮询间隔：够快拿到规则模式的秒级结果，又不至于把后端打满。 */
const POLL_INTERVAL_MS = 1500;
/** 轮询总上限，与后端任务保留期同一量级；超时给出可读提示而非静默挂起。 */
const POLL_TIMEOUT_MS = 10 * 60 * 1000;
/** 连续失败容忍次数：单次网络抖动/限流不应放弃一个仍在服务端执行的任务。 */
const MAX_CONSECUTIVE_FAILURES = 5;

export interface SubmitAndPollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  /** 每次拿到新状态时回调（queued/running/succeeded/failed），供界面展示阶段。 */
  onState?: (state: string, kind: string) => void;
}

/**
 * 轮询句柄式 Promise：既可 `await`，也可 `cancel()`。
 *
 * 调用方在组件卸载/切换上下文时必须 `cancel()`，否则轮询最多会继续 10 分钟，
 * 且回包会写进已经离开的页面（甚至把人 `router.push` 拉回报告页）。
 * `cancel()` 只停止轮询，不会取消服务端任务（任务照常跑完并落库）。
 */
export type PollPromise<T> = Promise<T> & { cancel: () => void };

export function submitAndPoll<T>(
  url: string,
  body: unknown,
  options: SubmitAndPollOptions = {},
): PollPromise<T> {
  // POST 阶段也可能还没拿到 task_id 就被取消（组件已卸载），因此这里也记一个标志，
  // 避免取消后仍然发起轮询。
  let cancelled = false;
  let cancelPoll: (() => void) | null = null;

  const promise = (async (): Promise<T> => {
    const { data: accepted } = await client.post<TaskAccepted>(url, body);
    if (cancelled) return undefined as unknown as T;
    const pollUrl = accepted.poll_url || `/tasks/${accepted.task_id}`;
    options.onState?.(accepted.state, accepted.kind);

    const handle = createPoll<T>({
      intervalMs: options.intervalMs ?? POLL_INTERVAL_MS,
      timeoutMs: options.timeoutMs ?? POLL_TIMEOUT_MS,
      maxConsecutiveFailures: MAX_CONSECUTIVE_FAILURES,
      poll: async (): Promise<PollState<T>> =>
        (await client.get<TaskStatusResponse<T>>(pollUrl)).data,
      onState: options.onState,
    });
    cancelPoll = handle.cancel;
    return await handle.promise;
  })() as PollPromise<T>;

  promise.cancel = () => {
    cancelled = true;
    cancelPoll?.();
  };
  return promise;
}
