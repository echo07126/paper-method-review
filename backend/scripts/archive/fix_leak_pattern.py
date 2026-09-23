from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "engine" / "rules.py"
text = path.read_text(encoding="utf-8")
broken = '''LEAK_ON_TEST_PATTERN = re.compile(
    r"(调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于|使用|利用|在)?测试集)",
    re.IGNORECASE,
)'''
fixed = '''LEAK_ON_TEST_PATTERN = re.compile(
    r"(测试集[^。；，]{0,12}(调参|调优|调超参|选择超参数|模型选择|网格搜索)|"
    r"(调参|模型选择|超参数选择|网格搜索)[^。；，]{0,12}(基于|使用|利用|在)?测试集)",
    re.IGNORECASE,
)'''
if broken in text:
    path.write_text(text.replace(broken, fixed), encoding="utf-8")
    print("LEAK_ON_TEST_PATTERN 已修复")
else:
    print("[warn] 未匹配到目标（请检查文件）")
