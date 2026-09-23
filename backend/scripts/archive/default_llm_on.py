"""模型顾问默认启用：服务端配置 + 请求级可覆盖；前端复选框默认勾选。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

# 1) 配置项：llm_default_enabled
cfg = APP / "core" / "config.py"
text = cfg.read_text(encoding="utf-8")
if "llm_default_enabled" not in text:
    text = text.replace(
        "    llm_verify_enabled: bool = True",
        "    llm_default_enabled: bool = True\n    llm_verify_enabled: bool = True",
    )
    cfg.write_text(text, encoding="utf-8")
    print("config 已加 llm_default_enabled")

# 2) 请求模型：use_llm 可空，未传时取服务端默认
route = APP / "api" / "routes_review.py"
text = route.read_text(encoding="utf-8")
text = text.replace("    use_llm: bool = False", "    use_llm: bool | None = None")
text = text.replace(
    "    provider = build_provider(settings) if payload.use_llm else None",
    "    use_llm = settings.llm_default_enabled if payload.use_llm is None else payload.use_llm\n"
    "    provider = build_provider(settings) if use_llm else None",
)
text = text.replace(
    "    report = review_document(document, items, provider=provider, use_llm=payload.use_llm, demote_on_figures=payload.demote_on_figures)",
    "    report = review_document(\n"
    "        document, items, provider=provider, use_llm=use_llm, demote_on_figures=payload.demote_on_figures\n"
    "    )",
)
text = text.replace(
    '    audit("review_created", report_id=report.report_id, problems=report.counts.get("total", 0), use_llm=payload.use_llm)',
    '    audit("review_created", report_id=report.report_id, problems=report.counts.get("total", 0), use_llm=use_llm)',
)
route.write_text(text, encoding="utf-8")
print("routes_review 已改为服务端默认 + 请求覆盖")

# 3) 前端：默认勾选
view = ROOT / "frontend" / "src" / "views" / "ParseView.vue"
text = view.read_text(encoding="utf-8")
text = text.replace("const useLlm = ref(false);", "const useLlm = ref(true);")
text = text.replace(
    '启用模型顾问（把模型建议列为「存疑」，会产生 API token 消耗）',
    '启用模型顾问（默认开启；模型建议列为「存疑」，会产生 API token 消耗）',
)
text = text.replace(
    '        : "本次未启用模型顾问（仅规则判定），tokens 消耗为 0",',
    '        : "本次已手动关闭模型顾问（仅规则判定），tokens 消耗为 0",',
)
view.write_text(text, encoding="utf-8")
print("前端复选框已默认勾选")

# 4) .env / .env.example
for name in (".env", ".env.example"):
    path = ROOT / "backend" / name
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    if "LLM_DEFAULT_ENABLED" not in text:
        text = text.replace("LLM_VERIFY_ENABLED=true", "LLM_DEFAULT_ENABLED=true\nLLM_VERIFY_ENABLED=true")
        path.write_text(text, encoding="utf-8")
        print(f"{name} 已加 LLM_DEFAULT_ENABLED")
