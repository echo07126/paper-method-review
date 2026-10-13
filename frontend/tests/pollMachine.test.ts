import assert from "node:assert/strict";
import { test } from "node:test";

import { createPoll, timeoutMessage, type PollState } from "../src/api/pollMachine.ts";

/** 可手动推进的时钟与定时器：让轮询行为在测试里完全确定，无需等待真实秒数。 */
function makeClock() {
  let current = 0;
  let nextHandle = 1;
  const queue: Array<{ handle: number; fn: () => void; at: number }> = [];

  return {
    now: () => current,
    setTimerFn: (fn: () => void, ms: number) => {
      const handle = nextHandle++;
      queue.push({ handle, fn, at: current + ms });
      return handle;
    },
    clearTimerFn: (handle: number) => {
      const index = queue.findIndex((entry) => entry.handle === handle);
      if (index >= 0) queue.splice(index, 1);
    },
    pending: () => queue.length,
    /** 推进时间并跑完到期的回调（回调内可能再排新定时器）。 */
    async advance(ms: number) {
      current += ms;
      for (;;) {
        const index = queue.findIndex((entry) => entry.at <= current);
        if (index < 0) break;
        const [entry] = queue.splice(index, 1);
        entry.fn();
        await drain();
      }
    },
  };
}

async function drain() {
  for (let index = 0; index < 10; index += 1) {
    await new Promise<void>((resolve) => setImmediate(resolve));
  }
}

function scriptedPoll<T>(states: PollState<T>[]) {
  const calls: number[] = [];
  let index = 0;
  return {
    calls,
    poll: async (): Promise<PollState<T>> => {
      calls.push(index);
      const state = states[Math.min(index, states.length - 1)];
      index += 1;
      return state;
    },
  };
}

const BASE = { intervalMs: 100, timeoutMs: 1000, maxConsecutiveFailures: 3 };

test("已成功状态直接返回结果", async () => {
  const clock = makeClock();
  const scripted = scriptedPoll<string>([{ state: "succeeded", kind: "review", result: "ok" }]);
  const handle = createPoll<string>({ ...BASE, ...clock, poll: scripted.poll });

  await clock.advance(100);
  assert.equal(await handle.promise, "ok");
  assert.equal(scripted.calls.length, 1);
});

test("queued/running 会继续轮询直到 succeeded", async () => {
  const clock = makeClock();
  const seen: string[] = [];
  const scripted = scriptedPoll<string>([
    { state: "queued", kind: "review" },
    { state: "running", kind: "review" },
    { state: "succeeded", kind: "review", result: "done" },
  ]);
  const handle = createPoll<string>({
    ...BASE,
    ...clock,
    poll: scripted.poll,
    onState: (state) => seen.push(state),
  });

  await clock.advance(100);
  await clock.advance(100);
  await clock.advance(100);
  assert.equal(await handle.promise, "done");
  assert.deepEqual(seen, ["queued", "running", "succeeded"]);
});

test("failed 状态按 error.message 拒绝", async () => {
  const clock = makeClock();
  const handle = createPoll<string>({
    ...BASE,
    ...clock,
    poll: async () => ({
      state: "failed",
      kind: "review",
      error: { code: "internal_error", message: "模型调用失败" },
    }),
  });
  // 拒绝发生在定时器回调内，必须在推进时钟之前挂上处理器，否则会成为未处理的 rejection
  const guarded = handle.promise.catch((err: Error) => err.message);

  await clock.advance(100);
  assert.equal(await guarded, "模型调用失败");
});

test("超过总超时后拒绝并停止轮询", async () => {
  const clock = makeClock();
  const scripted = scriptedPoll<string>([{ state: "running", kind: "review" }]);
  const handle = createPoll<string>({ ...BASE, ...clock, poll: scripted.poll });
  const guarded = handle.promise.catch((err: Error) => err.message);

  await clock.advance(100);
  await clock.advance(1000);

  assert.equal(await guarded, timeoutMessage(BASE.timeoutMs));
  assert.equal(clock.pending(), 0, "超时后不应再排新的定时器");
});

test("单次失败后重试，随后成功", async () => {
  const clock = makeClock();
  let attempts = 0;
  const handle = createPoll<string>({
    ...BASE,
    ...clock,
    poll: async () => {
      attempts += 1;
      if (attempts === 1) {
        const err = new Error("网络抖动") as Error & { status?: number };
        err.status = 500;
        throw err;
      }
      return { state: "succeeded", kind: "review", result: "recovered" };
    },
  });

  await clock.advance(100);
  await clock.advance(100);
  assert.equal(await handle.promise, "recovered");
  assert.equal(attempts, 2);
});

test("连续失败超过容忍次数后放弃", async () => {
  const clock = makeClock();
  let attempts = 0;
  const handle = createPoll<string>({
    ...BASE,
    maxConsecutiveFailures: 2,
    ...clock,
    poll: async () => {
      attempts += 1;
      const err = new Error("boom") as Error & { status?: number };
      err.status = 500;
      throw err;
    },
  });
  const guarded = handle.promise.catch((err: Error) => err.message);

  for (let round = 0; round < 6; round += 1) await clock.advance(100);
  assert.equal(await guarded, "boom");
  assert.equal(attempts, 3, "容忍 2 次失败 => 共 3 次尝试");
});

test("404 立即失败，不做重试", async () => {
  const clock = makeClock();
  let attempts = 0;
  const handle = createPoll<string>({
    ...BASE,
    maxConsecutiveFailures: 5,
    ...clock,
    poll: async () => {
      attempts += 1;
      const err = new Error("task 不存在或无权访问。") as Error & { status?: number };
      err.status = 404;
      throw err;
    },
  });
  const guarded = handle.promise.catch((err: Error) => err.message);

  await clock.advance(100);
  assert.equal(await guarded, "task 不存在或无权访问。");
  assert.equal(attempts, 1, "404 不应重试");
  assert.equal(clock.pending(), 0);
});

test("cancel 停止轮询且不再回调", async () => {
  const clock = makeClock();
  const scripted = scriptedPoll<string>([{ state: "running", kind: "review" }]);
  let settled = false;
  const handle = createPoll<string>({ ...BASE, ...clock, poll: scripted.poll });
  void handle.promise.then(
    () => {
      settled = true;
    },
    () => {
      settled = true;
    },
  );

  await clock.advance(100);
  assert.equal(scripted.calls.length, 1);
  handle.cancel();
  await clock.advance(1000);
  await drain();

  assert.equal(scripted.calls.length, 1, "取消后不得再轮询");
  assert.equal(clock.pending(), 0, "取消后不得残留定时器");
  assert.equal(settled, false, "取消不是失败：promise 不应被拒绝或解决");
});

test("timeoutMessage 按配置换算分钟", () => {
  assert.match(timeoutMessage(600000), /10 分钟/);
  assert.match(timeoutMessage(30000), /1 分钟/);
});
