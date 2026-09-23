from pathlib import Path

import pytest

from app.core.errors import AppError
from app.storage.files import save_upload
from app.storage.repository import Store


def test_cross_session_access_returns_404(tmp_path: Path) -> None:
    store = Store(str(tmp_path / "app.db"))
    from app.storage.db import init_db

    init_db(str(tmp_path / "app.db"))
    session_a, _ = store.create_session(2)
    document_id = store.save_document(session_a, "a.docx", "{}")
    session_b, _ = store.create_session(2)
    with pytest.raises(AppError) as exc:
        store.authorized_document(session_b, document_id)
    assert exc.value.status == 404


def test_fake_extension_rejected(tmp_path: Path) -> None:
    with pytest.raises(AppError) as exc:
        save_upload(str(tmp_path), "sess_x", "fake.docx", b"NOTADOCX", 50)
    assert exc.value.code == "file_content_mismatch"


def test_file_too_large_rejected(tmp_path: Path) -> None:
    big = b"PK\x03\x04" + b"0" * (2 * 1024 * 1024)
    with pytest.raises(AppError) as exc:
        save_upload(str(tmp_path), "sess_y", "big.docx", big, 1)
    assert exc.value.code == "file_too_large"
