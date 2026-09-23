"""启动时检测环境变量 Key 与 .env 冲突，并记录最终生效的 Key 尾号。"""
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "backend" / "app" / "main.py"
text = path.read_text(encoding="utf-8")

old = "    settings.guard_production()\n    init_db(settings.db_path)"
new = '''    settings.guard_production()

    env_key = os.environ.get("DEEPSEEK_API_KEY", "")
    effective_key = settings.deepseek_api_key
    if env_key and env_key != effective_key:
        safe_logger().warning(
            "env_key_conflict: 环境变量 Key(尾号 %s) 与 .env(尾号 %s) 不一致，按 .env 生效；"
            "如需彻底消除该环境变量，请在宿主应用/启动脚本层面清理后重启应用。",
            env_key[-6:],
            effective_key[-6:],
        )
    safe_logger().info(
        "llm_key_effective tail=%s model=%s base_url=%s",
        effective_key[-6:],
        settings.deepseek_model,
        settings.deepseek_base_url,
    )

    init_db(settings.db_path)'''
if old in text:
    text = text.replace(old, new)
    text = text.replace("from app.core.logging import setup_logging", "from app.core.logging import safe_logger, setup_logging")
    path.write_text(text, encoding="utf-8")
    print("启动告警已加入")
else:
    print("[warn] 未找到 lifespan 锚点")
