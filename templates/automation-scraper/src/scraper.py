"""Day {{DAY_PADDED}} — {{TITLE}} (Zero-Dependency Offline-First Scraper Starter)."""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
MOCK_HTML = BASE_DIR / "sample_data" / "mock_page.html"
OUTPUT_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "output")


def parse_listings(html: str) -> list[dict[str, str]]:
    pattern = re.compile(
        r'<article class="listing" data-id="(?P<id>[^"]+)">.*?'
        r"<h2>(?P<title>[^<]+)</h2>.*?"
        r'<span class="price">(?P<price>[^<]+)</span>.*?'
        r'<span class="seller">(?P<seller>[^<]+)</span>.*?</article>',
        re.DOTALL,
    )
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in pattern.finditer(html):
        item = {k: v.strip() for k, v in match.groupdict().items()}
        if item["id"] not in seen:
            seen.add(item["id"])
            rows.append(item)
    return rows


def main() -> int:
    html = MOCK_HTML.read_text(encoding="utf-8")
    rows = parse_listings(html)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = OUTPUT_DIR / "results.json"
    csv_path = OUTPUT_DIR / "results.csv"

    json_path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"Extracted {len(rows)} deduplicated records -> {json_path.name}, {csv_path.name}")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
