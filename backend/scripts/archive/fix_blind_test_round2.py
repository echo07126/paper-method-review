"""盲测第二轮修复：规则按类型过滤、R-12 模式确认、前端字段同步 paper_type。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

# 1) reviewer：综述类型下过滤规则结论
reviewer = APP / "engine" / "reviewer.py"
text = reviewer.read_text(encoding="utf-8")
old = "    elements = extract_elements(document)\n    rule_findings = run_rules(document, elements)"
new = ("    elements = extract_elements(document)\n"
       "    rule_findings = run_rules(document, elements)\n"
       "    if paper_type == \"review\":\n"
       "        rule_findings = [f for f in rule_findings if f.checklist_item_id in REVIEW_ALLOWED_ITEMS]")
if old in text and "paper_type == \"review\":" not in text.split("rule_findings = run_rules")[1][:200]:
    text = text.replace(old, new, 1)
reviewer.write_text(text, encoding="utf-8")
print("reviewer 已按类型过滤规则结论")

# 2) 确认 R-12 超参搜索信号是否含“通过交叉验证”
rules = APP / "engine" / "rules.py"
text = rules.read_text(encoding="utf-8")
if "通过交叉验证" not in text:
    text = text.replace(
        'HYPER_SEARCH_SIGNAL = re.compile(\n    r"(网格搜索|随机搜索|搜索空间|超参数搜索|调参|取值范围|grid\\s*search|random\\s*search|search\\s*space|hyper[\\s-]?parameter\\s*(?:search|tuning)|tuned)",',
        'HYPER_SEARCH_SIGNAL = re.compile(\n    r"(网格搜索|随机搜索|搜索空间|超参数搜索|调参|取值范围|交叉验证确定|通过交叉验证|由交叉验证|grid\\s*search|random\\s*search|search\\s*space|hyper[\\s-]?parameter\\s*(?:search|tuning)|tuned)",',
    )
    rules.write_text(text, encoding="utf-8")
    print("R-12 已补充交叉验证信号" if "通过交叉验证" in text else "R-12 替换未命中，请人工检查")
else:
    print("R-12 已含交叉验证信号")

# 3) 前端类型同步 paper_type
types = ROOT / "frontend" / "src" / "api" / "types.ts"
text = types.read_text(encoding="utf-8")
if "paper_type" not in text:
    text = text.replace(
        "  figure_references: number;\n  demote_on_figures: boolean;\n}",
        "  figure_references: number;\n  demote_on_figures: boolean;\n  paper_type: string;\n}",
    )
    text = text.replace(
        "  notes: string[];\n  figure_references: number;\n  demote_on_figures: boolean;\n}\n\nexport interface SectionSummary",
        "  notes: string[];\n  figure_references: number;\n  demote_on_figures: boolean;\n  paper_type: string;\n}\n\nexport interface SectionSummary",
    )
    types.write_text(text, encoding="utf-8")
    print("前端类型已加入 paper_type")

# 4) 报告页显示论文类型
view = ROOT / "frontend" / "src" / "views" / "ReportView.vue"
text = view.read_text(encoding="utf-8")
if "paper_type" not in text:
    text = text.replace(
        '    <p v-if="report.figure_references" class="figure-note">',
        '    <p v-if="report.paper_type === \'review\'" class="figure-note">\n'
        '      ℹ 识别为综述/理论论文（非实证）：已跳过数据划分、基线、消融、统计检验、可复现性等实证类检查。\n'
        '    </p>\n'
        '    <p v-if="report.figure_references" class="figure-note">',
    )
    view.write_text(text, encoding="utf-8")
    print("报告页已加类型提示")
