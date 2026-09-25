"""全局配置：唯一配置来源与运行时覆盖注入点。

优先级（`settings_customise_sources` 决定）：显式入参 > 项目 backend/.env > 系统环境变量 > secrets。

因为 `model_config.env_file` 在类定义时固化为 `backend/.env`，测试与脚本若只设
`os.environ` 会被 `.env` 覆盖（导致写入真实 `./data`），因此这里提供一个显式的
运行时覆盖注入点 `set_settings_override()`，供 `api_check.py` / `demote_check.py` 等
脚本与 pytest 使用：注入实例对所有 `from app.core.config import get_settings` 的
调用方统一生效。
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    app_env: str = "dev"
    debug: bool = True
    docs_enabled: bool = True
    allowed_origins: str = "http://localhost:5173"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    llm_max_concurrency: int = 2
    llm_default_enabled: bool = True
    llm_verify_enabled: bool = True
    llm_advisory_only: bool = True
    demote_on_figures: bool = False
    rate_limit_uploads_per_minute: int = 20
    rate_limit_reviews_per_minute: int = 10
    rate_limit_reads_per_minute: int = 120
    llm_verify_max_items: int = 6
    # L3 图像内容识读（P2-3）：按图片计费，需显式开启并限制张数
    llm_vision_enabled: bool = True
    llm_vision_max_images: int = 4
    # 追问多轮上下文上限（需求 15.5.4）：10 轮 / 20 条消息 + 历史总字符 8000（含 system）
    chat_history_max_turns: int = 10
    chat_history_max_chars: int = 8000

    max_upload_mb: int = 50
    max_pages: int = 60
    session_ttl_hours: int = 2
    data_retention_hours: int = 2

    db_path: str = "./data/app.db"
    temp_dir: str = "./data/tmp"
    checklist_dir: str = "../checklists"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        """优先级：显式入参 > 项目 .env > 系统环境变量 > secrets 文件。

        目的：项目目录内的 .env 是该项目的唯一真实配置来源，避免宿主机/会话里
        残留的旧环境变量（如旧的 DEEPSEEK_API_KEY）静默覆盖。
        """
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)

    @property
    def origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def guard_production(self) -> list[str]:
        """生产配置守卫：返回告警列表；出现严重配置（prod 下开 debug/docs）时抛错。"""
        problems: list[str] = []
        if "*" in self.origins:
            problems.append("ALLOWED_ORIGINS 不能包含通配符 *（与凭据 Cookie 同用不安全）")
        if self.app_env != "dev":
            if self.debug:
                problems.append("生产环境必须关闭 DEBUG")
            if self.docs_enabled:
                problems.append("生产环境必须关闭或保护 API Docs")
        if problems:
            raise RuntimeError("配置不合规：" + "；".join(problems))
        return problems

    def require_llm(self) -> None:
        if not self.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")


_OVERRIDE: Settings | None = None


@lru_cache
def _build_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    """读取全局配置；若已通过 `set_settings_override` 注入实例，则返回该实例。"""
    if _OVERRIDE is not None:
        return _OVERRIDE
    return _build_settings()


def set_settings_override(settings: Settings | None) -> None:
    """注入/清除运行时配置覆盖（供测试与冒烟脚本实现真正的环境隔离）。

    注意：`model_config.env_file` 在类定义时固化为 `backend/.env`，
    仅设置 `os.environ` 无法覆盖 `.env`，必须用本函数注入完整实例。
    """
    global _OVERRIDE
    _OVERRIDE = settings
    _build_settings.cache_clear()
