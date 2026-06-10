"""
Store-State Vision sub-agent. 선반 사진 1장 → Gemini Vision 추출 → shelf_observation
→ 상품 매칭 → 점주 검토용 제안. (데이터셋 학습 X, 사진 1장 실시간 분석 O)
Store-State Vision sub-agent. ONE shelf photo → Gemini Vision extraction →
shelf_observation → product match → owner-review suggestions. (No dataset/training;
a single photo is analyzed at runtime.)

로직은 _sources/Store-State-Vision-Flow 에서 이식하되 우리 골격(pymongo)+config+audit 에 맞춤.
매칭은 M0 에서 바로 되는 텍스트 매칭으로(벡터는 인덱스 생성 후 확장).
Ported from _sources/Store-State-Vision-Flow, adapted to our skeleton. Matching uses
text match (works on M0); vector search is an extension once the index exists.
가드레일(PRD §14): 정확한 개수 X, 코어스 신호 + confidence, 불확실하면 점주 검토.
Guardrails: coarse stock SIGNAL + confidence (never exact counts); uncertain → owner review.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum

from bson import ObjectId
from google.adk.agents import Agent
from pydantic import BaseModel, Field

from ..config import bootstrap_genai_env, settings
from ..core.audit import log_action, new_trace
from ..core.product_search import match_label
from ..db import STORE_ID, get_db

# 비전 모델은 설정으로 — 멀티모달 지원 모델. Vision model is config-driven (multimodal).
VISION_MODEL = os.getenv("VISION_MODEL", settings.agent_model)


# ── Gemini 구조화 출력 스키마 / Gemini structured-output schema ──
class StockSignal(str, Enum):
    out = "out"; low = "low"; ok = "ok"; full = "full"; unknown = "unknown"


class DetectedItem(BaseModel):
    label: str = Field(description="Short product name as seen, e.g. 'oat milk carton'")
    stock_signal: StockSignal = Field(description="Coarse stock level (never an exact count)")
    confidence: float = Field(ge=0.0, le=1.0)
    notes: str | None = None


class GeminiExtraction(BaseModel):
    detected_items: list[DetectedItem] = Field(default_factory=list)
    overall_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    image_caption: str = Field(default="", description="One-sentence description of the scene")


_SYSTEM = (
    "You are the store-state vision component of an inventory-aware cafe manager. "
    "Look at ONE photo of a shelf/counter and report what you see. Rules: report a "
    "COARSE stock signal (out/low/ok/full), never an exact count; give 0-1 confidence "
    "per item; do not invent products you cannot see; prefer the provided catalog names."
)


def _catalog_names(db, limit: int = 60) -> list[str]:
    return [d["name"] for d in db.products.find({"store_id": STORE_ID}, {"name": 1, "_id": 0}).limit(limit)
            if d.get("name")]


def analyze_shelf_photo(image_path: str, owner_note: str = "") -> dict:
    """
    선반/카운터 사진 1장을 Gemini Vision 으로 분석하고 결과를 MongoDB 에 기록.
    Analyze ONE shelf/counter photo with Gemini Vision; persist results to MongoDB.
    재고는 직접 안 고치고 '제안(suggestion)'만 만든다(점주 승인 필요).
    Never writes inventory directly — only proposals that the owner approves.

    Args:
        image_path: 로컬 이미지 파일 경로 / local path to one image file.
        owner_note: 선택 메모 / optional owner note.
    """
    bootstrap_genai_env()
    from google import genai
    from google.genai import types

    db = get_db()
    trace = new_trace()

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

    client = genai.Client()
    hint = "Known catalog products: " + ", ".join(_catalog_names(db))
    parts = [types.Part.from_bytes(data=image_bytes, mime_type=mime), types.Part.from_text(text=hint)]
    if owner_note:
        parts.append(types.Part.from_text(text=f"Owner note: {owner_note}"))

    # 일시적 503/429 백오프 재시도(견고성/§9.5 fallback). Backoff on transient 503/429.
    cfg = types.GenerateContentConfig(
        system_instruction=_SYSTEM, response_mime_type="application/json",
        response_schema=GeminiExtraction, temperature=settings.vision_temperature)
    resp, delay = None, 2.0
    for attempt in range(4):
        try:
            resp = client.models.generate_content(model=VISION_MODEL, contents=parts, config=cfg)
            break
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"[vision] retry {attempt + 1}/3 after error: {str(exc)[:80]}")
            time.sleep(delay)
            delay *= 2
    ext = resp.parsed if isinstance(resp.parsed, GeminiExtraction) \
        else GeminiExtraction.model_validate_json(resp.text)

    # shelf_observation 저장 / persist the observation
    obs_id = "obs_" + uuid.uuid4().hex[:8]
    matched, suggestions = [], 0
    for it in ext.detected_items:
        # Atlas Search + Vector Search 병행 매칭(+모호성 판단). Atlas+Vector match.
        m = match_label(db, it.label, it.confidence)
        matched.append({"label": it.label, "stock_signal": it.stock_signal.value,
                        "confidence": it.confidence, "best_product_id": m["best_product_id"],
                        "product_name": m.get("best_name"), "method": m.get("method"),
                        "ambiguous": m["ambiguous"], "candidates": m["candidates"]})
        # 뚜렷이 매칭 + 저재고면 점주 검토 제안. 모호하면 제안 안 만들고 검토로.
        # Confident match + low stock → owner-review proposal; ambiguous → no auto-proposal.
        if m["best_product_id"] and not m["ambiguous"] and it.stock_signal in (StockSignal.out, StockSignal.low):
            db.inventory_adjustment_suggestions.insert_one({
                "store_id": STORE_ID, "observation_id": obs_id,
                "product_id": ObjectId(m["best_product_id"]), "product_name": m.get("best_name"),
                "suggested_signal": it.stock_signal.value, "match_method": m.get("method"),
                "confidence": it.confidence,
                "review_status": "needs_review" if it.confidence < settings.vision_low_conf else "pending_review",
                "created_at": datetime.now(timezone.utc),
            })
            suggestions += 1

    db.shelf_observations.insert_one({
        "observation_id": obs_id, "store_id": STORE_ID, "image_uri": f"upload://{os.path.basename(image_path)}",
        "status": "proposed", "owner_note": owner_note or None, "image_caption": ext.image_caption,
        "overall_confidence": ext.overall_confidence, "detected_items": matched,
        "created_at": datetime.now(timezone.utc),
    })
    log_action(db, store_id=STORE_ID, trace_id=trace, action_type="write", tool_name="analyze_shelf_photo",
               input_refs=["products"], output_refs=[f"shelf_observations:{obs_id}"],
               summary=f"Vision: {len(matched)} items, {suggestions} suggestions ({ext.image_caption[:40]})")

    return {"observation_id": obs_id, "caption": ext.image_caption,
            "detected": matched, "suggestions_created": suggestions}


def list_shelf_suggestions() -> dict:
    """점주 검토 대기 중인 비전 제안 목록. Pending vision suggestions awaiting owner review."""
    db = get_db()
    rows = list(db.inventory_adjustment_suggestions.find(
        {"store_id": STORE_ID, "review_status": {"$in": ["needs_review", "pending_review"]}}))
    return {"pending": [{"product_name": r.get("product_name"), "signal": r.get("suggested_signal"),
                         "confidence": r.get("confidence")} for r in rows], "count": len(rows)}


vision_agent = Agent(
    name="vision_agent",
    model=settings.agent_model,
    description="Turns a shelf/counter photo into reviewable stock and facility suggestions.",
    instruction=(
        "You analyze store photos for Off-Duty. When given an image path, call "
        "analyze_shelf_photo. Report coarse stock signals with confidence; never invent "
        "exact counts; uncertain updates always require owner review. Use "
        "list_shelf_suggestions to show pending proposals. ALWAYS reply in English."
    ),
    tools=[analyze_shelf_photo, list_shelf_suggestions],
)
