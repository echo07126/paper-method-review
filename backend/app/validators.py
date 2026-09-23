from app.core.errors import AppError

DOCX_MAGIC = b"PK\x03\x04"
ALLOWED_EXTENSIONS = {".docx"}


def validate_upload(filename: str, size: int, first_bytes: bytes, max_mb: int) -> str:
    lower = filename.lower()
    ext = lower[lower.rfind("."):] if "." in lower else ""
    if ext == ".pdf":
        raise AppError("pdf_not_supported", "一期仅支持 DOCX；PDF 解析将在后续版本提供。", 400)
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError("unsupported_file_type", "一期仅支持 DOCX 文件。", 400)
    if size <= 0:
        raise AppError("empty_file", "上传文件为空。", 400)
    if size > max_mb * 1024 * 1024:
        raise AppError("file_too_large", f"文件超过 {max_mb}MB 限制。", 413)
    if not first_bytes.startswith(DOCX_MAGIC):
        raise AppError("file_content_mismatch", "文件内容与 DOCX 格式不符（伪造扩展名？）。", 400)
    return ext


MAX_UNCOMPRESSED_MB = 300
MAX_COMPRESSION_RATIO = 120


def validate_docx_container(path, max_pages: int, max_uncompressed_mb: int = MAX_UNCOMPRESSED_MB) -> dict:
    """DOCX 容器级安全校验：解压体积（压缩炸弹）与页数上限。"""
    import zipfile

    info = {"uncompressed_mb": 0.0, "pages": None}
    try:
        with zipfile.ZipFile(path) as archive:
            total = sum(item.file_size for item in archive.infolist())
            info["uncompressed_mb"] = round(total / 1024 / 1024, 2)
            compressed = max(sum(item.compress_size for item in archive.infolist()), 1)
            if total > max_uncompressed_mb * 1024 * 1024 or total / compressed > MAX_COMPRESSION_RATIO:
                raise AppError("file_too_large_uncompressed", "文档解压后体积异常，已拒绝处理。", 413)
            if "docProps/app.xml" in archive.namelist():
                import re

                xml = archive.read("docProps/app.xml").decode("utf-8", errors="ignore")
                match = re.search(r"<Pages>(\d+)</Pages>", xml)
                if match:
                    info["pages"] = int(match.group(1))
    except zipfile.BadZipFile as exc:
        raise AppError("file_corrupted", "文件不是有效的 DOCX（压缩包损坏）。", 400) from exc

    if info["pages"] and max_pages and info["pages"] > max_pages:
        raise AppError("too_many_pages", f"文档页数 {info['pages']} 超过上限 {max_pages} 页。", 413)
    return info
