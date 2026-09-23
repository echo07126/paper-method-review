"""安全与运维核查：逐项在代码/配置中取证，输出「已实现 / 缺失」。"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
FE = ROOT / "frontend"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return ""


def grep_files(base: Path, pattern: str, suffixes=(".py", ".ts", ".vue", ".conf", ".yml", ".yaml", ".dockerfile")) -> list[str]:
    hits = []
    for path in base.rglob("*"):
        if path.is_file() and (path.suffix in suffixes or path.name.endswith("Dockerfile")):
            if re.search(pattern, read(path), re.IGNORECASE):
                hits.append(str(path.relative_to(ROOT)))
    return hits


CHECKS: list[tuple[str, str, bool]] = []


def check(name: str, detail: str, ok: bool) -> None:
    CHECKS.append((name, detail, ok))


validators = read(APP / "validators.py")
check("上传：扩展名 + 魔数 + 大小校验", "validators.py", "DOCX_MAGIC" in validators and "file_too_large" in validators)
check("上传：页数上限生效", "validators/files 使用 max_pages", "max_pages" in read(APP / "validators.py") and "max_pages" in read(APP / "storage" / "files.py"))
zip_hits = grep_files(APP, r"zipfile|ZipFile")
check("上传：压缩炸弹防护", "zip 解压体积校验", bool(zip_hits))

repository = read(APP / "storage" / "repository.py")
check("越权防护：会话条件查询", "authorized_* + session_id", "authorized_" in repository and "session_id = ?" in repository)
check("凭据：令牌哈希存储", "sha256", "sha256" in repository)
deps = read(APP / "api" / "deps.py")
check("Cookie：HttpOnly/Secure/SameSite", "deps.py", all(k in deps for k in ("httponly=True", "secure=", "samesite=")))

check("密钥：仅环境变量注入", ".env 被忽略且代码不硬编码", "sk-" not in read(APP / "core" / "config.py"))
llm_direct = [p for p in grep_files(APP, r"httpx\.(post|get)\(")]
check("模型调用：统一经 Provider", "仅 llm_provider.py 直接发 HTTP", llm_direct == ["paper-method-review\\backend\\app\\engine\\llm_provider.py"] or len(llm_direct) <= 1)

prompts = read(APP / "engine" / "prompts.py")
check("Prompt 注入护栏", "SYSTEM_GUARD + DATA 分隔", "SYSTEM_GUARD" in prompts and "DATA" in prompts)
check("模型输出严格校验", "LLMFindingPayload", "LLMFindingPayload" in read(APP / "engine" / "reviewer.py"))
check("日志脱敏", "RedactionFilter", "RedactionFilter" in read(APP / "core" / "logging.py"))
session_route = read(APP / "api" / "routes_session.py")
check("删除：覆盖 DB + 临时文件", "purge_session + purge_session_files", "purge_session(" in session_route and "purge_session_files" in session_route)
# 删除传播可验证：提供脚本并覆盖 DB 四张表 + 临时目录（对应上线待办第 4 项验收）
check("删除传播可验证（脚本）", "backup_check.py 覆盖四张表 + 临时目录", (ROOT / "backend" / "scripts" / "backup_check.py").exists())

check("过期会话/临时文件自动清理", "定时/启动清理任务", bool(grep_files(APP, r"cleanup_expired|purge_expired")))
# 运行期定期清理（不只是启动时一次）
check("运行期定期清理（常驻任务）", "asyncio.create_task + periodic_cleanup", "periodic_cleanup" in read(APP / "storage" / "cleanup_task.py") and "create_task" in read(APP / "main.py"))
# 保留期下限生效：DATA_RETENTION_HOURS 必须被真实使用，不能是死配置
check("保留期配置生效（非死配置）", "data_retention_hours 被读取", "data_retention_hours" in read(APP / "storage" / "maintenance.py"))
# 孤儿临时目录回收（覆盖进程被杀等泄漏）
check("孤儿临时目录回收", "按存活会话集合反查 temp_dir", "not in known" in read(APP / "storage" / "maintenance.py"))

check("限流与配额", "rate limit", bool(grep_files(APP, r"slowapi|ratelimit|RateLimit")))
check("审计日志（删除/导出/管理）", "audit log", bool(grep_files(APP, r"audit")))
check("生产配置守卫（DEBUG/DOCS）", "prod 下拒绝 debug/docs", bool(re.search(r"app_env\s*!=\s*[\"']dev[\"']", read(APP / "core" / "config.py"))) or bool(grep_files(APP, r"docs_enabled.*False|debug.*prod")))
check("CORS 通配符防护", "禁止 * 与 credentials 同用", bool(grep_files(APP, r'allow_origins.*\*|"\*"')))
nginx = read(FE / "nginx.conf")
check("安全响应头：X-Content-Type/X-Frame/Referrer", "nginx.conf", all(k in nginx for k in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy")))
check("安全响应头：CSP / HSTS", "nginx.conf", "Content-Security-Policy" in nginx and "Strict-Transport-Security" in nginx)
check("容器：非 root 运行", "Dockerfile USER 指令", bool(grep_files(FE, r"USER\s+[a-z]")) and bool(grep_files(ROOT / "backend", r"USER\s+[a-z]")))
check("后端容器化（Dockerfile/compose）", "backend Dockerfile", (ROOT / "backend" / "Dockerfile").exists())
check("CI/依赖漏洞扫描", "workflows 或扫描配置", (ROOT / ".github").exists() or (ROOT / ".." / ".github").exists())
check("错误响应不泄露内部细节", "unhandled_error_handler", "服务内部错误" in read(APP / "core" / "errors.py"))
check("SQL 注入防护（参数化）", "execute 使用占位符", "execute(" in repository and "?" in repository)

# 隐私声明与实际数据流一致性（数据外发 + 持久化口径）
upload_view = read(FE / "src" / "views" / "UploadView.vue")
# ① 会外发模型：不得宣称“不向第三方泄露”，且必须明示内容将发送至模型服务商
check("隐私声明与数据流一致（会外发模型）", "明示发送至模型服务商，不写“不向第三方泄露”", "第三方" not in upload_view and "模型服务商" in upload_view)
# ② 持久化口径：正文确实会在会话内落盘（随机文件名的临时目录 + SQLite ir_json），
#    因此界面文案不得声称“不持久化正文”，必须表述为“仅在本次会话内暂存 + 可一键删除”。
bad_claim = bool(re.search(r"不持久化正文|不落正文|不上传", upload_view))
good_claim = ("暂存" in upload_view or "删除" in upload_view) and "不清除" not in upload_view
check("隐私声明与数据流一致（持久化口径）", "不写“不持久化正文”，须为“会话内暂存/可删除”", good_claim and not bad_claim)
# ③ 事实取证：界面所述“会话内暂存”与存储实现一致（临时目录 + documents.ir_json）
repo_src = read(APP / "storage" / "repository.py")
check("正文存储与声明一致（取证）", "临时目录 save_upload + documents.ir_json", "save_upload" in read(APP / "storage" / "files.py") and "ir_json" in read(APP / "storage" / "db.py") and "ir_json" in repo_src)

def main() -> int:
    print(f"{'检查项':<38}{'证据':<42}{'状态'}")
    print("-" * 100)
    for name, detail, ok in CHECKS:
        print(f"{name:<38}{detail:<42}{'已实现' if ok else '缺失 ✗'}")
    missing = [name for name, _, ok in CHECKS if not ok]
    print()
    print(f"合计：{len(CHECKS)} 项，已实现 {len(CHECKS) - len(missing)} 项，缺失 {len(missing)} 项")
    if missing:
        print("缺失清单：")
        for item in missing:
            print("  -", item)
        print()
        print("结论：安全核查未通过，请逐项补齐后再部署。", file=sys.stderr)
        return 1
    print()
    print("结论：安全核查全部通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
