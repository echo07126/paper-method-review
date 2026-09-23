"""修正隐私文案：如实说明内容会发送至模型服务商（合规的“明示”要求）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

view = ROOT / "frontend" / "src" / "views" / "UploadView.vue"
text = view.read_text(encoding="utf-8")
old = "<p class=\"muted\">隐私说明：论文仅用于本次审查，不留存、不用于训练；可随时删除。</p>"
new = "<p class=\"muted\">隐私说明：论文内容将发送至大模型服务商，仅用于本次审查、不作为训练数据；服务端不持久化正文，可随时一键删除。</p>"
if old in text:
    view.write_text(text.replace(old, new), encoding="utf-8")
    print("UploadView 隐私文案已修正")

mock = ROOT / "frontend" / "mockup" / "index.html"
mtext = mock.read_text(encoding="utf-8")
mold = "🔒 隐私说明（原型示意）：论文仅用于本次审查，不留存、不用于训练、不向第三方泄露；可随时删除。示例为自建脱敏演示稿。"
mnew = "🔒 隐私说明（原型示意）：论文内容将发送至大模型服务商，仅用于本次审查、不用于训练；可随时删除。示例为自建脱敏演示稿。"
if mold in mtext:
    mock.write_text(mtext.replace(mold, mnew), encoding="utf-8")
    print("mockup 隐私文案已修正")
