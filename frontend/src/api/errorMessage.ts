/**
 * 错误信息归一化（与 HTTP 客户端解耦，便于单测）。
 */

/**
 * FastAPI 请求体校验失败返回 `{detail: [{loc, msg, type}]}`，没有 `message` 字段。
 * 不转换的话前端只会显示「服务异常（HTTP 422）」，用户看不出是哪个字段不合法
 * （例如追问文本超过 500 字上限）。
 */
export function detailMessage(detail: unknown): string | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const parts = detail
    .map((item) => {
      const entry = item as { loc?: unknown[]; msg?: string };
      const loc = Array.isArray(entry?.loc)
        ? entry.loc.filter((part) => part !== "body" && part !== "query").join(".")
        : "";
      const msg = entry?.msg ?? "";
      return loc ? `${loc}: ${msg}` : msg;
    })
    .filter((part): part is string => Boolean(part));
  return parts.length ? `请求参数不合法（${parts.join("；")}）` : null;
}
