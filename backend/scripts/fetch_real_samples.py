"""抓取 Europe PMC 开放获取论文 -> 抽取方法/结果片段 -> 改写为中文样本。

仅保存改写后的中文文本与来源/许可信息，不保存英文原文；同源 PMID 自动去重。
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402
from docx import Document  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.engine.llm_provider import DeepSeekProvider, LLMUnavailable  # noqa: E402

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
SECTION_KEYS = ("method", "material", "statistical", "experiment", "result", "evaluation", "analysis")
UA = {"User-Agent": "paper-method-review/0.1 (research prototype)"}


def search_epmc(term: str, limit: int) -> list[dict]:
    response = httpx.get(
        f"{EPMC}/search",
        params={"query": f"({term}) AND OPEN_ACCESS:Y", "format": "json", "resultType": "core", "pageSize": limit},
        timeout=60,
        headers=UA,
    )
    response.raise_for_status()
    results = response.json().get("resultList", {}).get("result", [])
    return [
        {"pmcid": item.get("pmcid"), "title": item.get("title", ""), "license": (item.get("license") or "").lower()}
        for item in results
        if item.get("pmcid")
    ]


def license_ok(value: str) -> bool:
    """仅接受允许演绎与商用的许可：CC-BY / CC-BY-SA / CC0 / 公有领域。"""
    normalized = value.lower()
    if "cc0" in normalized or "public domain" in normalized:
        return True
    if "nd" in normalized or "nc" in normalized:
        return False
    return "cc" in normalized and "by" in normalized


def fetch_full_text(pmcid: str) -> str:
    response = httpx.get(f"{EPMC}/{pmcid}/fullTextXML", timeout=60, headers=UA)
    if response.status_code != 200:
        return ""
    return response.text


def extract_sections(xml_text: str) -> tuple[str, str]:
    root = ET.fromstring(xml_text)
    license_node = root.find(".//license")
    license_str = ""
    if license_node is not None:
        license_str = license_node.get("{http://www.w3.org/1999/xlink}href") or " ".join((license_node.text or "").split())
    chunks: list[str] = []
    for section in root.iter("sec"):
        title_node = section.find("title")
        title = (title_node.text or "").strip().lower() if title_node is not None else ""
        if not any(key in title for key in SECTION_KEYS):
            continue
        paragraphs = [" ".join(" ".join(p.itertext()).split()) for p in section.iter("p")]
        text = " ".join(p for p in paragraphs if len(p) > 40)
        if text:
            chunks.append(text)
    if not chunks:
        paragraphs = [" ".join(" ".join(p.itertext()).split()) for p in root.iter("p")]
        chunks = [" ".join(p for p in paragraphs if len(p) > 60)]
    return license_str, "\n".join(chunks)[:6000]


def rewrite_to_chinese(provider: DeepSeekProvider, title: str, source_text: str) -> dict:
    prompt = (
        "你是科研写作助手。请把下面来自公开论文的方法/结果片段改写成中文论文段落，要求：\n"
        "1) 保留全部方法学事实（样本量、数据划分、统计检验、p 值、评价指标、基线、消融、随机种子等），"
        "原文没有的信息一律不得添加，也不得编造结论；\n"
        "2) 用你自己的表述重写，不得逐字翻译；\n"
        "3) 输出 JSON：{\"title_zh\": str, \"paragraphs\": [str, ...]}，段落 4-8 段，每段 60-200 字。\n\n"
        f"原题：{title}\n\n片段：\n{source_text}"
    )
    result = provider.complete_structured(
        [{"role": "system", "content": "你只输出 JSON。"}, {"role": "user", "content": prompt}]
    )
    return json.loads(result.content)


def build_docx(payload: dict, path: Path) -> None:
    doc = Document()
    doc.add_heading(payload.get("title_zh", "改写样本"), level=0)
    doc.add_heading("2. 方法", level=1)
    for paragraph in payload.get("paragraphs", []):
        doc.add_paragraph(paragraph)
    doc.save(path)


def existing_pmcids(truth_dir: Path) -> set[str]:
    used: set[str] = set()
    for truth_path in truth_dir.glob("real-*.json"):
        try:
            source = json.loads(truth_path.read_text(encoding="utf-8")).get("source") or ""
        except json.JSONDecodeError:
            continue
        match = re.search(r"(PMC\d+)", source)
        if match:
            used.add(match.group(1))
    return used


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--term", default='("deep learning") AND ("statistical significance")')
    args = parser.parse_args()

    settings = get_settings()
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.llm_timeout_seconds,
        max_retries=1,
        max_concurrency=1,
    )

    real_dir = ROOT / "samples" / "real"
    truth_dir = ROOT / "samples" / "ground_truth"
    real_dir.mkdir(parents=True, exist_ok=True)
    used = existing_pmcids(truth_dir)

    candidates = search_epmc(args.term, args.limit * 5)
    print(f"Europe PMC 候选：{len(candidates)} 篇（已用 {len(used)} 篇同源样本）")

    existing = len(list(real_dir.glob("real-*.docx")))
    saved = 0
    for candidate in candidates:
        if saved >= args.limit:
            break
        if candidate["pmcid"] in used:
            print(f"  跳过（同源样本已存在）：{candidate['pmcid']}")
            continue
        if not license_ok(candidate["license"]):
            print(f"  跳过（许可非 CC-BY 类）：{candidate['pmcid']} license={candidate['license']}")
            continue
        xml_text = fetch_full_text(candidate["pmcid"])
        if not xml_text:
            print(f"  跳过（无全文 XML）：{candidate['pmcid']}")
            continue
        license_str, excerpt = extract_sections(xml_text)
        if len(excerpt) < 800:
            print(f"  跳过（片段过短）：{candidate['pmcid']}")
            continue
        try:
            payload = rewrite_to_chinese(provider, candidate["title"], excerpt)
        except (LLMUnavailable, ValueError, json.JSONDecodeError) as exc:
            print(f"  跳过（改写失败）：{candidate['pmcid']} -> {exc}")
            continue
        saved += 1
        used.add(candidate["pmcid"])
        sample_id = f"real-{existing + saved:03d}"
        build_docx(payload, real_dir / f"{sample_id}.docx")
        truth = {
            "sample_id": sample_id,
            "title": payload.get("title_zh", candidate["title"]),
            "type": "real",
            "source": f"https://europepmc.org/article/MED/{candidate['pmcid']}",
            "license": license_str or candidate["license"],
            "language": "zh",
            "items": [],
            "note": "改写自 Europe PMC 开放获取全文；标准答案待人工核对标注",
        }
        (truth_dir / f"{sample_id}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  已生成 {sample_id}：{payload.get('title_zh')}（license={truth['license']}）")

    print(f"完成：新增 {saved} 篇 -> samples/real/")
    return 0 if saved else 1


if __name__ == "__main__":
    raise SystemExit(main())
