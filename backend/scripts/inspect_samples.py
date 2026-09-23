"""打印样本标准答案与 DOCX 正文，便于人工标注核对。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402


def main() -> int:
    for truth_path in sorted((ROOT / "samples" / "ground_truth").glob("*.json")):
        truth = json.loads(truth_path.read_text(encoding="utf-8"))
        docx_path = ROOT / "samples" / ("real" if truth["type"] == "real" else "fixtures") / f"{truth['sample_id']}.docx"
        if not docx_path.exists():
            continue
        print(f"=== {truth['sample_id']} | {truth['title']}")
        print(f"    type={truth['type']} license={truth.get('license')} source={truth.get('source')}")
        print(f"    labels={[item['checklist_item_id'] for item in truth['items']]}")
        document = Document(str(docx_path))
        for index, paragraph in enumerate(document.paragraphs):
            text = paragraph.text.strip()
            if text:
                print(f"    [{index}] {text[:200]}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
