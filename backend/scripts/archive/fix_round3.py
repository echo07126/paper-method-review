"""第三轮修复：表/图题不计为标题；R-15 锚点避开表格；局限词表补“开放问题/挑战”等。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"

# 1) 解析器：图表题（图1/表2/Figure 3/Table 4）不作为标题
parser = APP / "parsers" / "docx_parser.py"
text = parser.read_text(encoding="utf-8")
if "CAPTION_PATTERN" not in text:
    text = text.replace(
        'HEURISTIC_MAX_LENGTH = 80',
        'HEURISTIC_MAX_LENGTH = 80\nCAPTION_PATTERN = re.compile(r"^\\s*(图|表|附图|附表|Fig\\.?|Figure|Table)\\s*\\d+", re.IGNORECASE)',
    )
    text = text.replace(
        '    stripped = text.strip()\n    if not stripped or len(stripped) > HEURISTIC_MAX_LENGTH:\n        return False, 1, ""',
        '    stripped = text.strip()\n'
        '    if not stripped or len(stripped) > HEURISTIC_MAX_LENGTH:\n'
        '        return False, 1, ""\n'
        '    if CAPTION_PATTERN.match(stripped):\n'
        '        return False, 1, ""',
    )
    parser.write_text(text, encoding="utf-8")
    print("解析器已排除图表题作为标题")

# 2) 局限词表补充
elements = APP / "engine" / "elements.py"
text = elements.read_text(encoding="utf-8")
old = '        r"(局限|不足之处|未来工作|伦理|合规声明|后续工作|讨论其局限)",'
new = '        r"(局限|不足之处|未来工作|伦理|合规声明|后续工作|讨论其局限|开放问题|开放挑战|尚未解决|待解决|未来方向|展望|研究空白|挑战)",'
if old in text:
    elements.write_text(text.replace(old, new), encoding="utf-8")
    print("局限词表已补充")
else:
    print("[warn] 未找到局限词表锚点")

# 3) R-15 锚点：最后一段“非表格”正文
rules = APP / "engine" / "rules.py"
text = rules.read_text(encoding="utf-8")
old = '''    return [_problem("R-15", Severity.LOW, "未见局限性讨论",
                     "全文未检出「局限 / 不足 / 未来工作 / 伦理」相关讨论。",
                     "补充局限性章节，说明数据范围、泛化性与伦理合规边界。",
                     [_anchor(_last_paragraph_index(document))], "R-15")]'''
new = '''    body_indexes = [p.index for p in document.paragraphs if p.style != "Table"]
    anchor_index = max(body_indexes) if body_indexes else _last_paragraph_index(document)
    return [_problem("R-15", Severity.LOW, "未见局限性讨论",
                     "全文未检出「局限 / 不足 / 未来工作 / 开放问题 / 伦理」相关讨论。",
                     "补充局限性章节，说明数据范围、泛化性、开放问题与伦理合规边界。",
                     [_anchor(anchor_index)], "R-15")]'''
if old in text:
    rules.write_text(text.replace(old, new), encoding="utf-8")
    print("R-15 锚点已避开表格")
else:
    print("[warn] 未找到 R-15 锚点代码")
