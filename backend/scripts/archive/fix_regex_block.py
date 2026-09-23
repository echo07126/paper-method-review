from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "rules.py"
lines = path.read_text(encoding="utf-8").splitlines()
out: list[str] = []
skip = False
for line in lines:
    if line.startswith("LEAK_ON_TEST_PATTERN = re.compile("):
        out.append("LEAK_ON_TEST_PATTERN = re.compile(")
        out.append('    r"(测试集[^。；，]{0,12}(调参|调优|调超参|选择超参数|模型选择|网格搜索)|"')
        out.append('    r"(调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于|使用|利用|在)?测试集)",')
        out.append("    re.IGNORECASE,")
        out.append(")")
        skip = True
        continue
    if skip:
        if line.strip().startswith(r'    (调参|模型选择|超参数选择|网格搜索)'):
            continue
        if line.strip() == ")":
            skip = False
            continue
        if line.strip().startswith(")") or line.strip().startswith("SPLIT_DETAIL_PATTERN"):
            skip = False
    out.append(line)
path.write_text("\n".join(out) + "\n", encoding="utf-8")
print("已修复 LEAK_ON_TEST_PATTERN")
