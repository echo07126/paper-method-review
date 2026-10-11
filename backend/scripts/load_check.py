"""负载性能测试：在固定样本上测「上传 + 规则审查」的并发吞吐与延迟。

口径
----
- **进程内 ASGI**（`httpx.ASGITransport`）：只测应用路径（路由 + 解析 + 规则引擎 + 序列化），
  不含 uvicorn 的 HTTP 栈；这样无需外起服务，也不依赖机器端口占用，结果可复现。
- **不触碰 backend/.env 与真实 `data/`**：经 `app.core.config.set_settings_override()` 注入
  隔离配置（独立 db/temp），并把三档限流阈值调高，避免并发测试被 429 打断而失真。
- 并发梯度默认 1/2/4/8/16，每档 `--rounds` 轮；样本默认 `samples/real/real-001.docx`（37 KB 口径样本）。
- 指标：成功率、上传/审查延迟 p50/p95/max、墙钟、相对单路的并行加速比、健康检查探针 p50/p95/max。
- **审查已任务化**：`POST /reviews` 立即返回 202，`one_request` 提交后轮询 `GET /tasks/{task_id}` 至
  `succeeded` 才计完成，因此「审查延迟」含排队等待。任务并发上限由 `TASK_MAX_WORKERS`（默认 2）决定，
  高并发档位下审查呈排队特征（这是有意的配额保护，不是性能回归）；规则模式单任务毫秒级，排队不明显。

仅作性能观测，**不进入 CI**（计时类断言受机器负载影响，易造成假阳性门禁失败）。
"""
import argparse
import asyncio
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic_settings import SettingsConfigDict  # noqa: E402

from app.core.config import Settings, set_settings_override  # noqa: E402
from app.main import app  # noqa: E402
from app.storage.db import init_db  # noqa: E402

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PREFIX = "/api/v1"


class IsolatedSettings(Settings):
    """断开 backend/.env，使显式入参成为唯一配置来源（保证不写入真实 data/）。"""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def pick_sample(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in (ROOT / "samples" / "real" / "real-001.docx", ROOT / "samples" / "fixtures" / "synthetic-001.docx"):
        if candidate.exists():
            return candidate
    raise SystemExit("未找到测试样本，请用 --sample 指定 .docx 路径。")


async def probe_health(client: httpx.AsyncClient, stop: asyncio.Event, samples: list[float]) -> None:
    """负载期间持续探测健康检查，用来观察事件循环/线程池是否被拖慢。"""
    while not stop.is_set():
        started = time.perf_counter()
        try:
            await client.get(f"{PREFIX}/health")
        except Exception:  # 探针失败不应中断压测
            pass
        samples.append((time.perf_counter() - started) * 1000)
        await asyncio.sleep(0.05)


async def poll_task(client: httpx.AsyncClient, task_id: str, timeout: float = 300.0) -> dict:
    """轮询任务至终态，返回 result（重接口已异步化：POST 202 + GET /tasks/{id}）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = await client.get(f"{PREFIX}/tasks/{task_id}")
        response.raise_for_status()
        payload = response.json()
        if payload["state"] == "succeeded":
            return payload["result"]
        if payload["state"] == "failed":
            raise RuntimeError(f"任务失败：{payload['error']}")
        await asyncio.sleep(0.02)
    raise TimeoutError("任务超时未完成")


async def one_request(client: httpx.AsyncClient, name: str, payload: bytes) -> tuple[float, float]:
    """一次完整链路：上传 → 规则审查（提交任务并轮询至终态）。返回 (上传耗时 ms, 审查耗时 ms)。"""
    started = time.perf_counter()
    upload = await client.post(f"{PREFIX}/uploads", files={"file": (name, payload, DOCX_TYPE)})
    uploaded = time.perf_counter()
    upload.raise_for_status()
    document_id = upload.json()["document_id"]
    review = await client.post(f"{PREFIX}/reviews", json={"document_id": document_id, "use_llm": False})
    review.raise_for_status()
    await poll_task(client, review.json()["task_id"])
    reviewed = time.perf_counter()
    return (uploaded - started) * 1000, (reviewed - uploaded) * 1000


async def run_level(
    client: httpx.AsyncClient, level: int, rounds: int, name: str, payload: bytes
) -> dict:
    uploads: list[float] = []
    reviews: list[float] = []
    failures = 0
    wall_seconds = 0.0
    for _ in range(rounds):
        started = time.perf_counter()
        results = await asyncio.gather(
            *(one_request(client, name, payload) for _ in range(level)), return_exceptions=True
        )
        wall_seconds += time.perf_counter() - started
        for result in results:
            if isinstance(result, BaseException):
                failures += 1
                continue
            upload_ms, review_ms = result
            uploads.append(upload_ms)
            reviews.append(review_ms)
    return {
        "level": level,
        "rounds": rounds,
        "ok": level * rounds - failures,
        "total": level * rounds,
        "uploads": uploads,
        "reviews": reviews,
        "wall_s": wall_seconds / rounds,
        "serial_s": (sum(uploads) + sum(reviews)) / 1000 / rounds if uploads else 0.0,
    }


async def main_async(args: argparse.Namespace) -> int:
    sample = pick_sample(args.sample)
    payload = sample.read_bytes()

    tmp = Path(tempfile.mkdtemp(prefix="load_check_"))
    settings = IsolatedSettings(
        db_path=str(tmp / "app.db"),
        temp_dir=str(tmp / "tmp"),
        checklist_dir=str(ROOT / "checklists"),
        app_env="dev",
        docs_enabled=False,
        rate_limit_uploads_per_minute=100000,
        rate_limit_reviews_per_minute=100000,
        rate_limit_reads_per_minute=100000,
    )
    set_settings_override(settings)
    init_db(settings.db_path)

    transport = httpx.ASGITransport(app=app)
    levels = [int(item) for item in args.levels.split(",") if item.strip()]
    print(f"样本：{sample.name}（{len(payload) / 1024:.1f} KB）　并发梯度：{levels}　每档 {args.rounds} 轮")
    print()
    print(f"{'并发':<6}{'成功':<10}{'上传 p50/p95/max(ms)':<26}{'审查 p50/p95/max(ms)':<26}{'墙钟(s)':<10}{'加速比':<8}{'探针 p50/p95/max(ms)'}")
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://load", timeout=300) as client:
            await client.get(f"{PREFIX}/health")
            baseline_wall = 0.0
            for level in levels:
                stop = asyncio.Event()
                probes: list[float] = []
                probe_task = asyncio.create_task(probe_health(client, stop, probes))
                row = await run_level(client, level, args.rounds, sample.name, payload)
                stop.set()
                await probe_task
                if level == levels[0]:
                    baseline_wall = row["wall_s"] / max(level, 1)
                speedup = (baseline_wall * level / row["wall_s"]) if row["wall_s"] else 0.0
                print(
                    f"{level:<6}{row['ok']}/{row['total']:<8}"
                    f"{percentile(row['uploads'], 50):<9.0f}{percentile(row['uploads'], 95):<9.0f}{max(row['uploads'], default=0):<8.0f}"
                    f"{percentile(row['reviews'], 50):<9.0f}{percentile(row['reviews'], 95):<9.0f}{max(row['reviews'], default=0):<8.0f}"
                    f"{row['wall_s']:<10.2f}{speedup:<8.2f}"
                    f"{percentile(probes, 50):<9.1f}{percentile(probes, 95):<9.1f}{max(probes, default=0):<8.1f}"
                )
    finally:
        set_settings_override(None)

    real_data = (ROOT / "data").resolve()
    assert not real_data.exists() or not any(real_data.iterdir()), f"隔离失效：真实 data/ 被写入 {real_data}"
    print()
    print("负载检查完成（进程内 ASGI，隔离自证通过）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="1,2,4,8,16", help="并发梯度，逗号分隔")
    parser.add_argument("--rounds", type=int, default=1, help="每档轮次")
    parser.add_argument("--sample", default=None, help="测试用 .docx 路径（默认 samples/real/real-001.docx）")
    return asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())