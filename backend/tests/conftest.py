import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ROOT = BACKEND.parent

# pytest 默认把临时根目录放在系统 TEMP 下（`pytest-of-<user>/pytest-N`）。在受限环境里该目录
# 可能不可遍历或不可删除，表现为大批 fixture 的 `PermissionError`（看起来像 60+ 个测试失败）；
# 部分 Windows 策略还会在工作区根目录禁止删除子目录，使 pytest 无法清理自己刚建的临时目录。
# 因此把临时根目录固定到仓库内：可写、可清理、且不污染系统临时区。
# 需要放到别处时照常传 `--basetemp=...` —— 显式参数优先于这里设置的临时根目录。
_TEMP_ROOT = ROOT / ".pytest-basetemp"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_TEMP_ROOT)
