/**
 * 轮询状态机：只负责「间隔调度 / 总超时 / 连续失败重试 / 取消」，不依赖任何 HTTP 客户端。
 *
 * 抽成独立模块有两个理由：
 * 1. 这几条规则是最容易写错、又最难人工复现的部分（1–3 分钟的任务 + 偶发网络抖动）；
 * 2. 时钟与定时器可注入，单测里能完全确定性地驱动时间，无需等待真实秒数。
 *
 * 约定：`poll()` 返回的任务状态为 `queued | running | succeeded | failed`；
 * `succeeded` 时取 `result`，`failed` 时取 `error.message`。
 * `poll()` 抛出的错误若带 `status === 404`，视为致命（任务不存在，重试无意义）。
 */

export interface PollState<T> {
  state: string;
  kind: string;
  result?: T | null;
  error?: { code: string; message: string } | null;
}

export interface PollScheduleOptions<T> {
  intervalMs: number;
  timeoutMs: number;
  /** 连续失败容忍次数；超过即失败。单次抖动不应放弃仍在服务端执行的任务。 */
  maxConsecutiveFailures: number;
  poll: () => Promise<PollState<T>>;
  /** 每次拿到状态时回调（含首次入队状态），供界面展示阶段。 */
  onState?: (state: string, kind: string) => void;
  /** 可注入的时钟与定时器（单测用）。默认使用 window/Date。 */
  now?: () => number;
  setTimerFn?: (handler: () => void, ms: number) => number;
  clearTimerFn?: (handle: number) => void;
}

export interface PollHandle<T> {
  promise: Promise<T>;
  cancel: () => void;
}

export const POLL_FAILED_FALLBACK = "任务执行失败，请稍后重试。";

export function timeoutMessage(timeoutMs: number): string {
  const minutes = Math.max(1, Math.round(timeoutMs / 60000));
  return `任务处理超时（已超过 ${minutes} 分钟），请稍后在报告列表查看结果或重试。`;
}

export function createPoll<T>(options: PollScheduleOptions<T>): PollHandle<T> {
  const now = options.now ?? (() => Date.now());
  const setTimer =
    options.setTimerFn ?? ((handler: () => void, ms: number) => window.setTimeout(handler, ms));
  const clearTimer =
    options.clearTimerFn ?? ((handle: number) => window.clearTimeout(handle));
  const deadline = now() + options.timeoutMs;

  let timer: number | null = null;
  let cancelled = false;

  const stopTimer = () => {
    if (timer !== null) {
      clearTimer(timer);
      timer = null;
    }
  };

  const promise = new Promise<T>((resolve, reject) => {
    let failures = 0;

    const schedule = () => {
      if (!cancelled) timer = setTimer(tick, options.intervalMs);
    };

    function tick() {
      if (cancelled) return;
      if (now() > deadline) {
        reject(new Error(timeoutMessage(options.timeoutMs)));
        return;
      }
      options
        .poll()
        .then((data) => {
          if (cancelled) return;
          failures = 0;
          options.onState?.(data.state, data.kind);
          if (data.state === "succeeded") {
            resolve(data.result as T);
            return;
          }
          if (data.state === "failed") {
            reject(new Error(data.error?.message ?? POLL_FAILED_FALLBACK));
            return;
          }
          schedule();
        })
        .catch((err: unknown) => {
          if (cancelled) return;
          failures += 1;
          const status = (err as { status?: number } | null)?.status;
          if (status === 404 || failures > options.maxConsecutiveFailures) {
            reject(err as Error);
            return;
          }
          schedule();
        });
    }

    schedule();
  });

  return {
    promise,
    cancel: () => {
      cancelled = true;
      stopTimer();
    },
  };
}
