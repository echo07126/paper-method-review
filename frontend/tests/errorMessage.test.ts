import assert from "node:assert/strict";
import { test } from "node:test";

import { detailMessage } from "../src/api/errorMessage.ts";

test("FastAPI 校验错误转成可读提示", () => {
  const message = detailMessage([
    { loc: ["body", "question"], msg: "String should have at most 500 characters", type: "string_too_long" },
  ]);
  assert.equal(message, "请求参数不合法（question: String should have at most 500 characters）");
});

test("多条校验错误合并，并去掉 body/query 前缀", () => {
  const message = detailMessage([
    { loc: ["body", "finding_id"], msg: "无效" },
    { loc: ["body", "question"], msg: "太短" },
    { loc: ["query", "format"], msg: "不支持" },
  ]);
  assert.equal(message, "请求参数不合法（finding_id: 无效；question: 太短；format: 不支持）");
});

test("没有 loc 时只保留消息", () => {
  assert.equal(detailMessage([{ msg: "出错了" }]), "请求参数不合法（出错了）");
});

test("非 422 形态返回 null，交由调用方回退到通用文案", () => {
  assert.equal(detailMessage(undefined), null);
  assert.equal(detailMessage(null), null);
  assert.equal(detailMessage([]), null);
  assert.equal(detailMessage("plain text"), null);
  assert.equal(detailMessage([{}]), null);
});
