"""通过 PMC OA 服务补全 real 样本的许可信息。"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402

TRUTH = ROOT / "samples" / "ground_truth"


def fetch_license(pmcid: str) -> str:
    try:
        response = httpx.get(
            f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}",
            timeout=30,
            headers={"User-Agent": "paper-method-review/0.1"},
        )
        if response.status_code != 200:
            return "unknown"
        root = ET.fromstring(response.text)
        record = root.find(".//record")
        if record is not None and record.get("license"):
            return record.get("license")
        return "not-in-oa-subset"
    except (httpx.HTTPError, ET.ParseError):
        return "unknown"


def main() -> int:
    updated = 0
    for path in sorted(TRUTH.glob("real-*.json")):
        truth = json.loads(path.read_text(encoding="utf-8"))
        match = re.search(r"PMC(\d+)", truth.get("source") or "")
        if not match:
            continue
        license_value = fetch_license(f"PMC{match.group(1)}")
        truth["license"] = license_value
        path.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
        updated += 1
        print(f"{truth['sample_id']} license -> {license_value}")
    print(f"updated {updated} real samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
