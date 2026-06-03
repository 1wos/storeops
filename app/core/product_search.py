"""
상품 카탈로그 매칭 — Atlas Search($search) + Vector Search($vectorSearch) 병행.
Product catalog matching — Atlas Search ($search) + Vector Search ($vectorSearch).

두 검색을 모두 돌려 RRF 로 merge → 'operational + semantic + vector 한 플랫폼' 시연.
Runs BOTH retrieval modes and merges them with Reciprocal Rank Fusion — operational +
semantic + vector on one platform.

임베딩 모델은 트랙 규칙대로 Google(Gemini) 제공 모델 사용.
Embedding model is a Google-provided model (Gemini), per track rules.
"""
from __future__ import annotations

from pymongo.database import Database

from ..config import bootstrap_genai_env, settings
from ..db import STORE_ID


def embed_text(text: str) -> list[float]:
    """짧은 라벨을 벡터로 임베딩(Gemini). Embed a short label (Gemini)."""
    bootstrap_genai_env()
    from google import genai
    from google.genai import types

    client = genai.Client()
    res = client.models.embed_content(
        model=settings.embed_model, contents=text,
        config=types.EmbedContentConfig(output_dimensionality=settings.embed_dim),
    )
    return list(res.embeddings[0].values)


def _vector_candidates(db: Database, label: str, k: int) -> list[dict]:
    """의미 기반 매칭 / semantic match via Atlas $vectorSearch."""
    try:
        qv = embed_text(label)
    except Exception as exc:  # noqa: BLE001
        print(f"[vector match] embed failed '{label}': {exc}")
        return []
    pipeline = [
        {"$vectorSearch": {"index": settings.product_vector_index, "path": "embedding",
                           "queryVector": qv,
                           "numCandidates": max(k * 10, settings.vector_num_candidates_floor), "limit": k}},
        {"$project": {"_id": 0, "product_id": {"$toString": "$_id"}, "name": 1,
                      "score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        rows = list(db.products.aggregate(pipeline))
    except Exception as exc:  # noqa: BLE001 — index 없으면 빈 결과로 graceful
        print(f"[vector match] failed: {exc}")
        return []
    return [{"product_id": r["product_id"], "name": r.get("name"),
             "score": float(r.get("score", 0.0)), "method": "vector"} for r in rows if r.get("product_id")]


def _text_candidates(db: Database, label: str, k: int) -> list[dict]:
    """어휘 기반 매칭 / lexical match via Atlas $search (fuzzy)."""
    pipeline = [
        {"$search": {"index": settings.product_search_index,
                     "text": {"query": label, "path": ["name", "category"],  # tags 미적재라 제외 / tags unpopulated
                              "fuzzy": {"maxEdits": 1}}}},
        {"$limit": k},
        {"$project": {"_id": 0, "product_id": {"$toString": "$_id"}, "name": 1,
                      "score": {"$meta": "searchScore"}}},
    ]
    try:
        rows = list(db.products.aggregate(pipeline))
    except Exception as exc:  # noqa: BLE001
        print(f"[text match] failed: {exc}")
        return []
    return [{"product_id": r["product_id"], "name": r.get("name"),
             "score": float(r.get("score", 0.0)), "method": "text"} for r in rows if r.get("product_id")]


def _merge(vector: list[dict], text: list[dict]) -> list[dict]:
    """
    Reciprocal Rank Fusion(RRF)으로 두 검색을 융합 — Lucene searchScore 와 cosine
    vectorSearchScore 는 스케일이 달라 그대로 더하면 안 됨. RRF 는 점수 대신 '순위'만 써서
    스케일프리하고 Atlas 하이브리드의 정석. score = Σ 1/(k + rank).
    Fuse the two retrievers with Reciprocal Rank Fusion — Lucene and cosine scores live on
    different scales, so RRF ranks (not raw scores): scale-free, the canonical Atlas recipe.
    """
    k = settings.rrf_k
    fused: dict[str, dict] = {}
    legs: dict[str, set] = {}
    for leg_name, leg in (("vector", vector), ("text", text)):
        for rank, c in enumerate(leg):                 # leg 는 점수 내림차순 / leg is score-desc
            pid = c["product_id"]
            if pid not in fused:
                fused[pid] = dict(c)
                fused[pid]["score"] = 0.0
            fused[pid]["score"] += 1.0 / (k + rank + 1)
            legs.setdefault(pid, set()).add(leg_name)
    for pid, m in fused.items():
        m["method"] = "hybrid" if len(legs[pid]) > 1 else next(iter(legs[pid]))
    return sorted(fused.values(), key=lambda c: c["score"], reverse=True)


def match_label(db: Database, label: str, confidence: float = 1.0) -> dict:
    """
    탐지 라벨 1개를 카탈로그에 매칭하고 모호성 판단(가드레일).
    Match one detected label to the catalog and decide ambiguity (guardrail):
    뚜렷한 1위가 없거나 탐지 confidence가 낮으면 ambiguous → 점주 검토로 라우팅.
    no clear leader or low detection confidence → ambiguous → owner review.
    """
    k = settings.match_candidates
    cands = _merge(_vector_candidates(db, label, k), _text_candidates(db, label, k))[:k]
    if not cands:
        return {"best_product_id": None, "candidates": [], "ambiguous": True}
    best = cands[0]
    runner = cands[1] if len(cands) > 1 else None
    ambiguous = confidence < settings.vision_low_conf
    if runner and best["score"] > 0 and (runner["score"] / best["score"]) > settings.match_ambiguity_ratio:
        ambiguous = True
    return {"best_product_id": None if ambiguous else best["product_id"],
            "best_name": None if ambiguous else best["name"],
            "candidates": cands, "ambiguous": ambiguous, "method": best["method"]}


# ── 셋업: 임베딩 적재 + 인덱스 생성 / setup: embed products + create indexes ──
def embed_products(db: Database) -> int:
    """products 에 embedding 필드 채우기(이름+카테고리). Populate products.embedding."""
    n = 0
    for p in db.products.find({"store_id": STORE_ID}):
        text = f"{p.get('name', '')} {p.get('category', '')}".strip()
        if not text:
            continue
        db.products.update_one({"_id": p["_id"]}, {"$set": {"embedding": embed_text(text)}})
        n += 1
    return n


def ensure_search_indexes(db: Database) -> None:
    """
    products 에 Atlas Search + Vector Search 인덱스 생성(M0에서도 됨, create_search_index).
    Create Atlas Search + Vector Search indexes on products (works on M0).
    """
    try:
        db.products.create_search_index({
            "name": settings.product_search_index,
            "definition": {"mappings": {"dynamic": False, "fields": {
                "name": {"type": "string"}, "category": {"type": "string"}}}},
        })
        print(f"[search index] {settings.product_search_index} requested")
    except Exception as exc:  # noqa: BLE001 — 이미 있거나 / already exists
        print(f"[search index] skipped: {exc}")
    try:
        db.products.create_search_index({
            "name": settings.product_vector_index, "type": "vectorSearch",
            "definition": {"fields": [{"type": "vector", "path": "embedding",
                                       "numDimensions": settings.embed_dim, "similarity": "cosine"}]}},
        )
        print(f"[vector index] {settings.product_vector_index} requested")
    except Exception as exc:  # noqa: BLE001
        print(f"[vector index] skipped: {exc}")
