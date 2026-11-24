"""Tenant-isolated Hybrid Retriever (BM25 lexical + hashed dense cosine + Reciprocal Rank Fusion).

Operates strictly inside a TenantContext so School A can never retrieve School B's curriculum.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from typing import Any

from storage import MultiTenantStore, TenantContext

TOKEN_RE = re.compile(r"[a-z0-9_]+")
STOPWORDS = {
    "am", "an", "as", "at", "be", "by", "do", "go", "he", "if", "in", "is",
    "it", "me", "my", "no", "of", "on", "or", "so", "to", "up", "us", "we",
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "what", "how", "why", "can", "you", "your", "into", "about", "does", "have",
    "explain", "help", "please", "tell", "find", "show", "give", "using",
}
EMBED_DIM = 512


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


def hashed_embedding(text: str) -> list[float]:
    """Deterministic lightweight semantic projection (bigrams + unigrams) for offline DEMO_MODE."""
    tokens = tokenize(text)
    vec = [0.0] * EMBED_DIM
    features = list(tokens) + [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    for feat in features:
        h = int(hashlib.blake2b(feat.encode("utf-8"), digest_size=8).hexdigest(), 16)
        idx = h % EMBED_DIM
        sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_sim(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def retrieve_hybrid(
    store: MultiTenantStore,
    tenant: TenantContext,
    query: str,
    top_k: int = 3,
    subject: str | None = None,
    grade_level: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve strictly tenant-scoped textbook chunks using BM25 + dense cosine RRF fusion."""
    chunks = store.list_chunks(tenant, subject=subject, grade_level=grade_level)
    if not chunks:
        return []

    q_tokens = tokenize(query)
    if not q_tokens:
        return []

    doc_tokens = [tokenize(f"{c['parent_context']} {c['content']}") for c in chunks]
    avgdl = sum(len(dt) for dt in doc_tokens) / max(len(doc_tokens), 1)
    doc_freq: Counter[str] = Counter()
    for dt in doc_tokens:
        for tok in set(dt):
            doc_freq[tok] += 1

    n_docs = len(chunks)
    k1, b = 1.5, 0.75

    bm25_scores: list[tuple[int, float]] = []
    for idx, dt in enumerate(doc_tokens):
        tf = Counter(dt)
        dl = len(dt) or 1
        score = 0.0
        for tok in q_tokens:
            df = doc_freq.get(tok, 0)
            if df == 0:
                continue
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
            freq = tf.get(tok, 0)
            if freq > 0:
                score += idf * ((freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl)))
        bm25_scores.append((idx, score))

    q_vec = hashed_embedding(query)
    dense_scores: list[tuple[int, float]] = []
    for idx, ch in enumerate(chunks):
        c_vec = hashed_embedding(f"{ch['parent_context']} {ch['content']}")
        dense_scores.append((idx, max(0.0, cosine_sim(q_vec, c_vec))))

    bm25_rank = {
        idx: rank
        for rank, (idx, score) in enumerate(sorted(bm25_scores, key=lambda x: -x[1]), start=1)
        if score > 0
    }
    dense_rank = {
        idx: rank
        for rank, (idx, score) in enumerate(sorted(dense_scores, key=lambda x: -x[1]), start=1)
        if score >= 0.28
    }

    bm25_map = dict(bm25_scores)
    dense_map = dict(dense_scores)
    rrf_k = 30
    fused: list[tuple[float, dict[str, Any]]] = []

    for idx, ch in enumerate(chunks):
        # Require real lexical hit or strong dense match so out-of-curriculum queries cleanly abstain
        if idx not in bm25_rank and idx not in dense_rank:
            continue
        score = 0.0
        if idx in bm25_rank:
            score += 1.0 / (rrf_k + bm25_rank[idx])
        if idx in dense_rank:
            score += 1.0 / (rrf_k + dense_rank[idx])

        # Slight boost for exact equation / table / diagram matches when query hints at them
        q_low = query.lower()
        if ch["block_type"] == "equation" and any(w in q_low for w in ("formula", "equation", "calculate", "solve", "acceleration")):
            score *= 1.12
        if ch["block_type"] == "diagram" and any(w in q_low for w in ("graph", "diagram", "chart", "curve", "slope", "area", "ramp")):
            score *= 1.15

        enriched = dict(ch)
        enriched["rrf_score"] = round(score, 5)
        enriched["bm25_score"] = round(bm25_map.get(idx, 0.0), 4)
        enriched["dense_score"] = round(dense_map.get(idx, 0.0), 4)
        enriched["citation_label"] = (
            f"{ch['textbook_title']} · {ch['chapter_title']} · {ch['section_title']} "
            f"(p.{ch['page_number']}, {ch['block_type']})"
        )
        fused.append((score, enriched))

    fused.sort(key=lambda pair: -pair[0])
    return [item for _, item in fused[:top_k]]
