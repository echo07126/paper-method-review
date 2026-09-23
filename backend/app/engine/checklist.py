import json
from pathlib import Path

from pydantic import ValidationError

from app.models.schemas import ReviewItem

MIN_EXPECTED_ITEMS = 15


class ChecklistError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def load_checklist(path: Path, min_items: int = 1) -> list[ReviewItem]:
    """加载并校验清单：合法 JSON + 逐条 Schema + 条目 ID 唯一。"""
    if not path.exists():
        raise ChecklistError(f"清单文件不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ChecklistError(f"清单不是合法 JSON：{exc}") from exc

    items_payload = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items_payload, list):
        raise ChecklistError("清单格式错误：应为条目数组或包含 items 数组。")

    items: list[ReviewItem] = []
    seen: set[str] = set()
    for position, raw in enumerate(items_payload):
        try:
            item = ReviewItem(**raw)
        except ValidationError as exc:
            raise ChecklistError(f"第 {position + 1} 条清单校验失败：{exc}") from exc
        if item.id in seen:
            raise ChecklistError(f"清单条目 ID 重复：{item.id}")
        seen.add(item.id)
        items.append(item)

    if len(items) < min_items:
        raise ChecklistError(f"清单条目不足：需要 ≥ {min_items} 条，实际 {len(items)} 条。")
    return items


def load_checklist_dir(directory: Path) -> dict[str, list[ReviewItem]]:
    result: dict[str, list[ReviewItem]] = {}
    if not directory.exists():
        return result
    for path in sorted(directory.glob("*.json")):
        result[path.stem] = load_checklist(path)
    return result


def filter_by_template(items: list[ReviewItem], template: str) -> list[ReviewItem]:
    return [item for item in items if not item.templates or template in item.templates]
