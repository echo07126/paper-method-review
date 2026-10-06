import secrets
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.validators import validate_docx_container, validate_upload


def save_upload(temp_dir: str, session_id: str, filename: str, content: bytes, max_mb: int) -> Path:
    ext = validate_upload(filename, len(content), content[:8], max_mb)
    target_dir = Path(temp_dir) / session_id
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{secrets.token_hex(16)}{ext}"
    path = target_dir / safe_name
    path.write_bytes(content)
    settings = get_settings()
    validate_docx_container(path, settings.max_pages)
    return path


def purge_session_files(temp_dir: str, session_id: str) -> None:
    directory = Path(temp_dir) / session_id
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)



