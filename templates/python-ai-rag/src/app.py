"""Day {{DAY_PADDED}} — {{TITLE}} (Starter Entry Point)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_KB = BASE_DIR / "sample_data" / "knowledge_base.json"


def retrieve(query: str, docs: list[dict[str, str]]) -> list[dict[str, str]]:
    tokens = {t.lower().strip(".,?!") for t in query.split() if len(t) > 2}
    scored = []
    for doc in docs:
        haystack = f"{doc['title']} {doc['content']}".lower()
        hits = sum(1 for tok in tokens if tok in haystack)
        if hits > 0:
            scored.append((hits, doc))
    scored.sort(key=lambda pair: -pair[0])
    return [doc for _, doc in scored[:3]]


def run_pipeline(query: str) -> dict[str, object]:
    demo_mode = os.getenv("DEMO_MODE", "true").lower() == "true"
    docs = json.loads(SAMPLE_KB.read_text(encoding="utf-8"))
    matches = retrieve(query, docs)

    if not matches:
        return {
            "mode": "demo" if demo_mode else "live",
            "query": query,
            "decision": "escalate_human",
            "confidence": 0.25,
            "citations": [],
            "answer": "Insufficient grounded evidence found in knowledge base; escalated for human review.",
        }

    return {
        "mode": "demo" if demo_mode else "live",
        "query": query,
        "decision": "grounded_response",
        "confidence": 0.92,
        "citations": [m["id"] for m in matches],
        "answer": f"Grounded answer based on [{matches[0]['id']}]: {matches[0]['content']}",
    }


def main() -> int:
    query = " ".join(sys.argv[1:]).strip() or "What are the API token rate limits?"
    result = run_pipeline(query)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
