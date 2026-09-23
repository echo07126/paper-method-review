"""修正 gen_api_doc：支持数组响应（list[Schema]）与嵌套对象展开。"""
from pathlib import Path

path = Path(__file__).resolve().parent / "gen_api_doc.py"
text = path.read_text(encoding="utf-8")
old = '''def fields(spec: dict, schema: dict, limit: int = 8) -> str:
    ref = schema.get("$ref")
    if ref:
        name = ref.split("/")[-1]
        schema = spec.get("components", {}).get("schemas", {}).get(name, {})
    props = list(schema.get("properties", {}).keys())
    if not props:
        return "—"
    return ", ".join(props[:limit]) + ("…" if len(props) > limit else "")'''
new = '''def resolve(spec: dict, schema: dict) -> dict:
    if not isinstance(schema, dict):
        return {}
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return spec.get("components", {}).get("schemas", {}).get(name, {})
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict):
        resolved = resolve(spec, schema["items"])
        return {**resolved, "_is_array": True}
    return schema


def fields(spec: dict, schema: dict, limit: int = 8) -> str:
    schema = resolve(spec, schema)
    props = list(schema.get("properties", {}).keys())
    if not props:
        return "—"
    text = ", ".join(props[:limit]) + ("…" if len(props) > limit else "")
    return f"[{text}]" if schema.get("_is_array") else text'''
if old in text:
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("gen_api_doc 数组处理已修正")
else:
    print("[warn] 未找到 fields 函数")
