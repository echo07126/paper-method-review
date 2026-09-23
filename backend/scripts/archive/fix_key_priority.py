""".env 优先于系统环境变量（避免环境里的旧 Key 覆盖项目配置）。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "core" / "config.py"
text = path.read_text(encoding="utf-8")

if "settings_customise_sources" not in text:
    text = text.replace(
        "from pydantic_settings import BaseSettings, SettingsConfigDict",
        "from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource",
    )
    text = text.replace(
        "    @property\n    def origins(self) -> list[str]:",
        '''    @classmethod
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
    def origins(self) -> list[str]:''',
    )
    path.write_text(text, encoding="utf-8")
    print("已设置 .env 优先")
else:
    print("已存在优先级设置")
