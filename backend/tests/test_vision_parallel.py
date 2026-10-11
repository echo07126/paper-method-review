"""视觉识读并行化：乱序完成下 findings 顺序仍等于图片顺序，token 合计等于串行之和（§1.6）。"""
import base64
import json
import re
import threading
import time
from pathlib import Path

from app.engine.llm_provider import LLMResult
from app.engine.vision import read_figure_values
from app.models.schemas import Anchor, DocumentIR, ImageRef

PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class OutOfOrderProvider:
    """让越靠后的图片越快返回，制造与提交顺序相反的完成顺序，验证「按提交顺序取回」。"""

    def __init__(self, total: int) -> None:
        self.total = total
        self.started: list[int] = []
        self._lock = threading.Lock()

    def complete_structured(self, messages, temperature: float = 0.0):
        text = messages[1]["content"][0]["text"]
        index = int(re.search(r"图(\d+)", text).group(1))
        with self._lock:
            self.started.append(index)
        # 图1 最慢、图N 最快 → 完成顺序与提交顺序相反
        time.sleep(0.05 * (self.total - index + 1))
        return LLMResult(
            content=json.dumps({"values": [f"值{index}"], "concern": None}),
            model="fake",
            tokens={"input": 11, "output": 7},
            retries=0,
            duration_ms=1,
        )

    def complete_text(self, messages, temperature: float = 0.3):
        raise AssertionError("视觉识读不应调用 complete_text")


def _document_with_images(tmp_path: Path, count: int) -> DocumentIR:
    images = []
    for index in range(count):
        filename = f"fig{index + 1}.png"
        (tmp_path / filename).write_bytes(PNG_1x1)
        images.append(
            ImageRef(
                id=f"img_{index}",
                index=index,
                media_type="image/png",
                byte_size=len(PNG_1x1),
                filename=filename,
                caption=f"图{index + 1} 标题",
                anchor=Anchor(paragraph_index=index),
            )
        )
    return DocumentIR(source_name="x.docx", parser="docx", parser_version="1.3", images=images)


def test_parallel_vision_preserves_order_and_tokens(tmp_path: Path) -> None:
    count = 3
    document = _document_with_images(tmp_path, count)
    provider = OutOfOrderProvider(count)

    findings, tokens = read_figure_values(document, provider, tmp_path)

    assert [f.provenance["image_index"] for f in findings] == [0, 1, 2], "findings 顺序必须等于图片顺序"
    assert [f.provenance["vision_values"] for f in findings] == [["值1"], ["值2"], ["值3"]]
    assert tokens == {"input": 11 * count, "output": 7 * count}, "token 合计必须等于逐张之和"


def test_single_image_stays_serial(tmp_path: Path) -> None:
    """仅一张图时不进线程池，行为与串行一致。"""
    document = _document_with_images(tmp_path, 1)
    findings, tokens = read_figure_values(document, OutOfOrderProvider(1), tmp_path)
    assert len(findings) == 1
    assert tokens == {"input": 11, "output": 7}