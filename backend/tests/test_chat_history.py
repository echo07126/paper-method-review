"""追问多轮上下文：上限截断、落库上限与删除传播（需求 15.5.4 / 16.2）。"""
from pathlib import Path

from app.core.config import Settings
from app.engine.chat_history import build_chat_messages, truncate_history
from app.storage.db import init_db
from app.storage.maintenance import cleanup_expired
from app.storage.repository import Store


def _history(turns: int, width: int = 10) -> list[dict]:
    messages: list[dict] = []
    for index in range(turns):
        messages.append({"role": "user", "content": f"u{index}" + "x" * width})
        messages.append({"role": "assistant", "content": f"a{index}" + "y" * width})
    return messages


def test_default_limits_match_confirmed_spec() -> None:
    """上限取值必须与需求 15.5.4 定稿一致（10 轮 / 20 条 + 8000 字符）。"""
    settings = Settings()
    assert settings.chat_history_max_turns == 10
    assert settings.chat_history_max_chars == 8000


def test_turn_limit_keeps_latest_turns() -> None:
    """超过轮数上限时保留最近 N 轮，最早已被丢弃。"""
    kept, truncated = truncate_history(_history(15), max_turns=10, max_chars=10**6)
    assert truncated is True
    assert len(kept) == 20
    assert kept[0]["content"].startswith("u5")
    assert kept[-1]["content"].startswith("a14")


def test_char_limit_truncates_whole_turns() -> None:
    """字符预算超限时整轮丢弃（不会只留半轮），且发生截断时标记为 True。"""
    kept, truncated = truncate_history(_history(10, width=60), max_turns=10, max_chars=400, system_chars=0)
    assert truncated is True
    assert len(kept) % 2 == 0, "应按整轮丢弃，不应残留半轮"
    assert sum(len(m["content"]) for m in kept) <= 400


def test_system_chars_count_toward_budget() -> None:
    """system 消息计入字符预算：预算被 system 挤占时历史被进一步截断。"""
    generous, _ = truncate_history(_history(4, width=20), max_turns=10, max_chars=500, system_chars=0)
    squeezed, truncated = truncate_history(_history(4, width=20), max_turns=10, max_chars=500, system_chars=400)
    assert len(squeezed) < len(generous)
    assert truncated is True


def test_zero_turns_keeps_no_history() -> None:
    """上限为 0 时不留任何历史（但仍标记发生过截断）。"""
    kept, truncated = truncate_history(_history(3), max_turns=0, max_chars=8000)
    assert kept == []
    assert truncated is True


def test_chat_messages_end_with_current_question() -> None:
    """构造结果必须为 system + 历史 + 当前提问，且 system 只有一个。"""
    messages, _ = build_chat_messages(_history(3), "这句该怎么改？", max_turns=10, max_chars=8000)
    assert messages[0]["role"] == "system"
    assert sum(1 for m in messages if m["role"] == "system") == 1
    assert messages[-1] == {"role": "user", "content": "这句该怎么改？"}


def test_stored_history_is_capped_and_purged(tmp_path: Path) -> None:
    """落库量随上限收敛（每轮 2 条），且 purge_session 会清空追问历史。"""
    db_path = str(tmp_path / "app.db")
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=2)

    keep = 20
    for index in range(30):
        store.append_chat_message(session_id, "rep_x", "user", f"q{index}", keep)
        store.append_chat_message(session_id, "rep_x", "assistant", f"a{index}", keep)

    stored = store.list_chat_messages(session_id, "rep_x")
    assert len(stored) == keep, "落库量应被上限约束"
    assert stored[-1]["content"] == "a29", "应保留最新的消息"

    store.purge_session(session_id)
    connection_rows = store.list_chat_messages(session_id, "rep_x")
    assert connection_rows == [], "purge_session 必须清空追问历史"


def test_expired_session_purges_chat_history(tmp_path: Path) -> None:
    """过期清理同样覆盖追问历史（删除传播一致）。"""
    db_path = str(tmp_path / "app.db")
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=2)
    store.append_chat_message(session_id, "rep_x", "user", "旧提问", keep=20)

    cleanup_expired(db_path, str(tmp_path / "tmp"), retention_hours=0)
    assert store.list_chat_messages(session_id, "rep_x") == []
