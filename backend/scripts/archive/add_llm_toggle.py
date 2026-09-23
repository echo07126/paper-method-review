"""前端增加“启用模型顾问”开关，并展示 token 消耗。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FE = ROOT / "frontend" / "src"

# 1) session store：保存 token 摘要
store = FE / "stores" / "session.ts"
text = store.read_text(encoding="utf-8")
if "tokensSummary" not in text:
    text = text.replace(
        "    reportId: \"\" as string,",
        "    reportId: \"\" as string,\n    tokensSummary: \"\" as string,",
    )
    text = text.replace(
        "    setReport(reportId: string) {\n      this.reportId = reportId;\n    },",
        "    setReport(reportId: string) {\n      this.reportId = reportId;\n    },\n    setTokens(tokensSummary: string) {\n      this.tokensSummary = tokensSummary;\n    },",
    )
    store.write_text(text, encoding="utf-8")
    print("session store 已加 tokensSummary")

# 2) ParseView：开关 + 传参 + 记录 token
view = FE / "views" / "ParseView.vue"
text = view.read_text(encoding="utf-8")
if "useLlm" not in text:
    text = text.replace(
        "const demoteOnFigures = ref(false);",
        "const demoteOnFigures = ref(false);\nconst useLlm = ref(false);",
    )
    text = text.replace(
        '      use_llm: false,',
        '      use_llm: useLlm.value,',
    )
    text = text.replace(
        "    store.setReport(data.report_id);",
        '    const tokens = data.tokens ?? {};\n'
        '    store.setTokens(\n'
        '      useLlm.value\n'
        '        ? `模型顾问已启用：本次消耗 tokens 输入 ${tokens.input ?? 0} / 输出 ${tokens.output ?? 0}`\n'
        '        : "本次未启用模型顾问（仅规则判定），tokens 消耗为 0",\n'
        '    );\n'
        '    store.setReport(data.report_id);',
    )
    text = text.replace(
        '    <label class="option"><input v-model="demoteOnFigures" type="checkbox" /> 图表未解析时保守处理（可能依赖图表的条目列为「存疑」）</label>',
        '    <label class="option"><input v-model="useLlm" type="checkbox" /> 启用模型顾问（把模型建议列为「存疑」，会产生 API token 消耗）</label>\n'
        '    <label class="option"><input v-model="demoteOnFigures" type="checkbox" /> 图表未解析时保守处理（可能依赖图表的条目列为「存疑」）</label>',
    )
    view.write_text(text, encoding="utf-8")
    print("ParseView 已加模型开关")

# 3) ReportView：显示 token 摘要
report = FE / "views" / "ReportView.vue"
text = report.read_text(encoding="utf-8")
if "tokensSummary" not in text:
    text = text.replace(
        '    <p v-if="report.paper_type === \'review\'" class="figure-note">',
        '    <p v-if="store.tokensSummary" class="figure-note">ℹ {{ store.tokensSummary }}</p>\n'
        '    <p v-if="report.paper_type === \'review\'" class="figure-note">',
    )
    report.write_text(text, encoding="utf-8")
    print("ReportView 已显示 token 摘要")
