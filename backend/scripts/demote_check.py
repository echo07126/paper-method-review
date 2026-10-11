"""接口级验证：保守模式（demote_on_figures）经 API 生效。

配置隔离说明：`model_config.env_file` 在类定义时固化为 `backend/.env`，
仅设 `os.environ` 会被 `.env` 覆盖。因此派生 `env_file=None` 的子类构造隔离实例，
并调用 `set_settings_override()` 全局注入，确保本次验证不触碰真实 `./data`。
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from docx import Document  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic_settings import SettingsConfigDict  # noqa: E402

from app.core.config import Settings, set_settings_override  # noqa: E402
from app.main import app  # noqa: E402
from app.storage.db import init_db  # noqa: E402

PREFIX = "/api/v1"


class IsolatedSettings(Settings):
    """断开 backend/.env，使显式入参成为唯一配置来源（保证测试隔离）。"""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def build(path: Path) -> None:
    doc = Document()
    doc.add_heading("3. Results", level=1)
    doc.add_paragraph("Figure 1 shows the accuracy of 0.91 for the proposed model.")
    doc.save(path)


def wait_task(client: TestClient, prefix: str, task_id: str, timeout: float = 30.0) -> dict:
    """轮询任务至终态（重接口已异步化：POST 202 + GET /tasks/{id}）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{prefix}/tasks/{task_id}")
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["state"] == "succeeded":
            return payload["result"]
        if payload["state"] == "failed":
            raise AssertionError(f"任务失败：{payload['error']}")
        time.sleep(0.05)
    raise AssertionError("任务超时未完成")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="demote_check_"))
    settings = IsolatedSettings(
        db_path=str(tmp / "app.db"),
        temp_dir=str(tmp / "tmp"),
        checklist_dir=str(ROOT / "checklists"),
        app_env="dev",
        docs_enabled=False,
    )
    set_settings_override(settings)
    init_db(settings.db_path)

    sample = tmp / "figure_only.docx"
    build(sample)

    try:
        with TestClient(app) as client:
            with sample.open("rb") as handle:
                upload = client.post(f"{PREFIX}/uploads", files={"file": (sample.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
            assert upload.status_code == 200, upload.text
            document_id = upload.json()["document_id"]

            strict_task = client.post(f"{PREFIX}/reviews", json={"document_id": document_id, "use_llm": False, "demote_on_figures": False})
            conservative_task = client.post(f"{PREFIX}/reviews", json={"document_id": document_id, "use_llm": False, "demote_on_figures": True})
            assert strict_task.status_code == 202 and conservative_task.status_code == 202, "重接口应返回 202（任务模式）"
            strict = wait_task(client, PREFIX, strict_task.json()["task_id"])
            conservative = wait_task(client, PREFIX, conservative_task.json()["task_id"])

            print("strict      :", strict["counts"], "figures=", strict["figure_references"], "demote=", strict["demote_on_figures"])
            print("conservative:", conservative["counts"], "figures=", conservative["figure_references"], "demote=", conservative["demote_on_figures"])
            assert conservative["demote_on_figures"] is True
            assert conservative["counts"]["total"] < strict["counts"]["total"], "保守模式应把依赖图表的条目降级"
    finally:
        set_settings_override(None)

    real_data = (ROOT / "data").resolve()
    assert not real_data.exists() or not any(real_data.iterdir()), f"隔离失效：真实 data/ 被写入 {real_data}"

    print("DEMOTE CHECK PASS")
    print(" - 隔离目录 :", tmp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
