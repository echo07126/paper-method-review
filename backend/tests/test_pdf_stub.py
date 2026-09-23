from pathlib import Path

import pytest

from app.core.errors import AppError
from app.storage.files import save_upload


def test_pdf_rejected_in_phase_one(tmp_path: Path) -> None:
    with pytest.raises(AppError) as exc:
        save_upload(str(tmp_path), "sess_pdf", "paper.pdf", b"%PDF-1.4 fake", 50)
    assert exc.value.code == "pdf_not_supported"
