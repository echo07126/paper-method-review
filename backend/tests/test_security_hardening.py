import zipfile
from pathlib import Path

import pytest
from docx import Document

from app.core.config import Settings
from app.core.errors import AppError
from app.core.ratelimit import _hit
from app.storage.db import connect, init_db
from app.storage.maintenance import cleanup_expired
from app.storage.repository import Store
from app.validators import validate_docx_container


def make_docx(path: Path, text: str = "hello") -> None:
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)


def test_zip_bomb_guard(tmp_path: Path) -> None:
    source = tmp_path / "big.docx"
    make_docx(source, "A" * (2 * 1024 * 1024))
    with pytest.raises(AppError) as exc:
        validate_docx_container(source, max_pages=60, max_uncompressed_mb=1)
    assert exc.value.code in {"file_too_large_uncompressed"}


def test_page_limit_guard(tmp_path: Path) -> None:
    source = tmp_path / "pages.docx"
    make_docx(source)
    rewritten = tmp_path / "pages2.docx"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(rewritten, "w") as target:
        for item in original.infolist():
            data = original.read(item.filename)
            if item.filename == "docProps/app.xml":
                data = b'<?xml version="1.0"?><Properties><Pages>999</Pages></Properties>'
            target.writestr(item, data)
        if "docProps/app.xml" not in original.namelist():
            target.writestr("docProps/app.xml", b'<?xml version="1.0"?><Properties><Pages>999</Pages></Properties>')
    with pytest.raises(AppError) as exc:
        validate_docx_container(rewritten, max_pages=60)
    assert exc.value.code == "too_many_pages"


def test_rate_limit_window() -> None:
    bucket = "test-bucket-unique"
    assert _hit(bucket, 2) is True
    assert _hit(bucket, 2) is True
    assert _hit(bucket, 2) is False


def test_production_config_guard() -> None:
    with pytest.raises(RuntimeError):
        Settings(app_env="prod", debug=True, docs_enabled=False, allowed_origins="https://example.com").guard_production()
    with pytest.raises(RuntimeError):
        Settings(app_env="prod", debug=False, docs_enabled=True, allowed_origins="https://example.com").guard_production()
    with pytest.raises(RuntimeError):
        Settings(app_env="dev", debug=True, docs_enabled=True, allowed_origins="*").guard_production()
    Settings(app_env="prod", debug=False, docs_enabled=False, allowed_origins="https://example.com").guard_production()


def test_cleanup_expired_sessions_and_temp(tmp_path: Path) -> None:
    db_path = str(tmp_path / "app.db")
    temp_dir = tmp_path / "tmp"
    init_db(db_path)
    store = Store(db_path)
    session_id, _ = store.create_session(ttl_hours=1)

    user_dir = temp_dir / session_id
    user_dir.mkdir(parents=True)
    (user_dir / "paper.docx").write_bytes(b"PK\x03\x04")

    connection = connect(db_path)
    try:
        connection.execute("UPDATE sessions SET expires_at = ? WHERE id = ?", ("2000-01-01T00:00:00+00:00", session_id))
        connection.commit()
    finally:
        connection.close()

    result = cleanup_expired(db_path, str(temp_dir))
    assert result["removed_sessions"] == 1
    assert not user_dir.exists()

    connection = connect(db_path)
    try:
        remaining = connection.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"]
    finally:
        connection.close()
    assert remaining == 0
