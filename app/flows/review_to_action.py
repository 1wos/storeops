"""
Review-to-Action v0 — 고객 리뷰(디지털 신호)를 매장 운영 액션으로 연결.
Review-to-Action v0 — turn customer reviews (the digital signal) into store operations.

흐름 / flow (per review, one trace_id):
  1) Gemini 구조화 분석: sentiment + issue_type + product_mention + reply_draft
  2) product_mention 을 Atlas Search/Vector 로 카탈로그 매칭
  3) 매칭 상품의 재고/저재고 상태 확인
  4) 운영 액션이 필요하거나(품절·품질 등) 민감하면 → 'Needs you' 승인 인박스로
  5) 모든 단계를 agent_action_logs(Evidence trail)에 trace_id 로 기록

기존 인프라 재사용(match_label / 승인 인박스 / evidence). 데모 안전: 시드/목업만, 라이브 API 없음.
Reuses existing infra (match_label / approval inbox / evidence). Demo-safe: seeded/mock only.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from enum import Enum

from bson import ObjectId
from pydantic import BaseModel, Field
from pymongo.database import Database

from ..config import bootstrap_genai_env, settings
from ..core.audit import log_action, new_trace
from ..core.product_search import match_label
from ..db import STORE_ID, safe_oid

REVIEW_MODEL = settings.agent_model


# ── Gemini 구조화 출력 스키마 / structured-output schema ──
class Sentiment(str, Enum):
    positive = "positive"; neutral = "neutral"; negative = "negative"; mixed = "mixed"


class IssueType(str, Enum):
    praise = "praise"
    inventory_issue = "inventory_issue"
    service_issue = "service_issue"
    refund_or_complaint = "refund_or_complaint"
    pickup_delivery_issue = "pickup_delivery_issue"
    other = "other"


class Severity(str, Enum):
    low = "low"; medium = "medium"; high = "high"


class ReviewAnalysis(BaseModel):
    sentiment: Sentiment
    issue_type: IssueType = Field(description="Primary (most operationally relevant) issue")
    product_mentions: list[str] = Field(default_factory=list,
        description="Catalog products named or clearly implied, e.g. ['Brownie','Oat Milk Latte']")
    requires_action: bool = Field(description="Does this need an operational action or owner attention?")
    severity: Severity = Field(default=Severity.low)
    reply_draft: str = Field(description="A short, warm, professional reply the owner could send")


ROUTABLE = {"inventory_issue", "refund_or_complaint", "pickup_delivery_issue"}


def route_decision(issue_type: str, severity: str, inv_low: bool) -> tuple[str, bool]:
    """
    순수 라우팅 규칙 — Annotation Guide 와 1:1 대응, 결정적이라 golden eval 로 검증 가능.
    Pure routing rule (matches the Annotation Guide 1:1; deterministic, so it is golden-testable):
      - inventory_issue → 점주에게 라우팅 (실제 저재고면 restock, 아니면 owner_reply 로 통지)
      - refund_or_complaint / pickup_delivery_issue / high severity → owner_reply, 라우팅
      - 그 외(praise / service_issue(저severity) / other) → 'none', reply 초안만(인박스 X)
    inventory_issue → owner approval always (a reported stock problem is worth the owner's eyes);
    refund/complaint/pickup or high severity → owner_reply; else reply-draft only (no inbox clutter).
    Returns (recommended_action, route_to_needs_you).
    """
    if issue_type == "inventory_issue":
        return ("restock" if inv_low else "owner_reply"), True
    if issue_type in ROUTABLE or severity == "high":
        return "owner_reply", True
    return "none", False


_SYSTEM = (
    "You are the customer-review component of an inventory-aware small-commerce operations "
    "agent (a cafe in the demo). Read ONE customer review and classify it.\n"
    "issue_type (pick the single most operationally relevant one): "
    "praise | inventory_issue (out of stock / ran out / sold out) | service_issue (wait, staff, "
    "pickup delay) | refund_or_complaint (quality, safety/hygiene, refund, payment problem) | "
    "pickup_delivery_issue (online/pickup/delivery order problem) | other (incl. price/value/"
    "portion-size complaints — these are 'other', NOT refund_or_complaint).\n"
    "Precedence: a product being SOLD OUT / out of stock is always inventory_issue, even if it "
    "happened at pickup or via the app. pickup_delivery_issue is only for pickup/delivery PROCESS "
    "problems (wrong / missing / late order, wrong address) that are NOT stock-outs. Between "
    "service_issue and pickup_delivery_issue, if a pickup/delivery/online order is mentioned, "
    "prefer pickup_delivery_issue even if it also describes a wait.\n"
    "Rules: list ALL catalog products named or clearly implied in product_mentions (e.g. "
    "['Brownie','Oat Milk Latte']); use sentiment 'mixed' when there is both praise and a "
    "complaint; set requires_action=true when an operational action or owner attention is "
    "warranted; mark safety/hygiene/refund as high severity; write a short, warm, professional "
    "reply_draft. Reply in English."
)


# ── 샘플 리뷰 시드 (멱등) / seed sample reviews (idempotent) ──
_SEED = [
    {"source": "google", "author": "Priya N.", "rating": 3,
     "text": "Loved the oat latte, but the brownies were sold out again."},
    {"source": "google", "author": "Mina K.", "rating": 2,
     "text": "Came in for an oat milk latte but they were out again. Third time this month."},
    {"source": "google", "author": "Dan P.", "rating": 5,
     "text": "The cold brew here is the best in the neighborhood. Smooth and strong."},
    {"source": "yelp", "author": "Sara L.", "rating": 1,
     "text": "There was a hair in my brownie. Pretty gross, won't be coming back."},
    {"source": "yelp", "author": "Jae W.", "rating": 3,
     "text": "Coffee is good but the cold brew tasted watery today, maybe a bad batch?"},
    {"source": "google", "author": "Tom H.", "rating": 4,
     "text": "Love the brownies. Service was a little slow during the lunch rush though."},
    {"source": "google", "author": "Hyo J.", "rating": 2,
     "text": "Prices went up and the latte portion feels smaller now."},
    {"source": "yelp", "author": "Ravi S.", "rating": 5,
     "text": "Friendly staff, cozy spot. Oat milk latte was perfect."},
    {"source": "google", "author": "Lena M.", "rating": 1,
     "text": "Ordered a cold brew, waited 20 minutes, then they said it was sold out."},
]


def seed_reviews(db: Database, store_id: str = STORE_ID) -> int:
    """샘플 리뷰가 없으면 채운다. Seed sample reviews if the collection is empty for this store."""
    if db.reviews.count_documents({"store_id": store_id}) > 0:
        return 0
    now = datetime.now(timezone.utc)
    db.reviews.insert_many([
        {**r, "store_id": store_id, "status": "new", "created_at": now} for r in _SEED])
    return len(_SEED)


def list_reviews(db: Database, store_id: str = STORE_ID, limit: int = 20) -> list[dict]:
    rows = db.reviews.find({"store_id": store_id}).sort("created_at", -1).limit(max(1, min(limit, 100)))
    return [{"review_id": str(r["_id"]), "source": r.get("source"), "author": r.get("author"),
             "rating": r.get("rating"), "text": r.get("text"), "status": r.get("status", "new"),
             "sentiment": r.get("sentiment"), "issue_type": r.get("issue_type")} for r in rows]


def catalog_names(db: Database, store_id: str = STORE_ID, limit: int = 60) -> list[str]:
    """카탈로그 상품명(프롬프트 힌트용). Catalog product names to constrain mention extraction."""
    return [d["name"] for d in db.products.find({"store_id": store_id}, {"name": 1, "_id": 0}).limit(limit)
            if d.get("name")]


def _analyze(text: str, catalog: list[str] | None = None) -> ReviewAnalysis:
    """Gemini 구조화 분석(일시적 오류 백오프). Structured Gemini analysis with backoff."""
    bootstrap_genai_env()
    from google import genai
    from google.genai import types

    client = genai.Client()  # 인라인 금지: 변수 유지 / keep alive (inline temp gets GC'd mid-call)
    # 카탈로그를 주어 product_mentions 추출을 실제 SKU 로 제약(정확도↑). Constrain mentions to real SKUs.
    contents = text
    if catalog:
        contents = (f"Known catalog products: {', '.join(catalog)}.\n"
                    f"Only put a product in product_mentions if it corresponds to one of these "
                    f"(use the EXACT catalog name); do not invent products.\n\nReview: {text}")
    cfg = types.GenerateContentConfig(
        system_instruction=_SYSTEM, response_mime_type="application/json",
        response_schema=ReviewAnalysis, temperature=0.1)
    delay = 2.0
    for attempt in range(4):
        try:
            resp = client.models.generate_content(model=REVIEW_MODEL, contents=contents, config=cfg)
            return resp.parsed if isinstance(resp.parsed, ReviewAnalysis) \
                else ReviewAnalysis.model_validate_json(resp.text)
        except Exception as exc:  # noqa: BLE001
            if attempt == 3:
                raise
            print(f"[review] retry {attempt + 1}/3 after error: {str(exc)[:80]}")
            time.sleep(delay)
            delay *= 2


def _inventory_status(db: Database, product_id: str) -> dict:
    """매칭 상품의 재고/저재고 상태. Inventory/low status for the matched product."""
    pid = safe_oid(product_id)
    inv = db.inventory.find_one({"store_id": STORE_ID, "product_id": pid}) if pid else None
    if not inv:
        return {"known": False}
    avail = inv.get("on_hand", 0) - inv.get("reserved", 0)
    return {"known": True, "available": avail, "threshold": inv.get("threshold", 0),
            "low": avail <= inv.get("threshold", 0)}


def scan_reviews(db: Database, store_id: str = STORE_ID, limit: int = 12) -> dict:
    """
    새 리뷰들을 분석→매칭→재고확인→reply 초안→(필요시) Needs You 라우팅→evidence 기록.
    Analyze new reviews → match → check stock → draft reply → route actions to Needs You → log evidence.
    """
    seed_reviews(db, store_id)
    new_reviews = list(db.reviews.find({"store_id": store_id, "status": "new"}).limit(max(1, limit)))
    catalog = catalog_names(db, store_id)   # 프롬프트 힌트(추출 제약) 1회 조회 / fetch once for the prompt hint
    processed, actions_created = [], 0

    for r in new_reviews:
        trace = new_trace()
        analysis = _analyze(r["text"], catalog)
        log_action(db, store_id=store_id, trace_id=trace, action_type="read",
                   tool_name="classify_review", input_refs=[f"reviews:{r['_id']}"],
                   summary=f"{analysis.sentiment.value}/{analysis.issue_type.value} "
                           f"(action={analysis.requires_action})")

        # 언급된 상품들을 각각 Atlas Search/Vector 로 매칭 → 액션 대상 1개 선택
        # (저재고인 매칭을 우선; inventory_issue 의 restock 대상이 되게). Match each mention; pick the
        # actionable product (prefer a low-stock match so an inventory_issue can become a restock).
        matched, matched_id, matched_name, inv = [], None, None, {"known": False}
        for mention in analysis.product_mentions:
            m = match_label(db, mention, settings.review_match_confidence)
            if not m.get("best_product_id"):
                continue
            st = _inventory_status(db, m["best_product_id"])
            cand = {"id": m["best_product_id"], "name": m.get("best_name"),
                    "method": m.get("method"), "inv": st}
            matched.append(cand)
            if matched_id is None or (st.get("low") and not inv.get("low")):
                matched_id, matched_name, inv = cand["id"], cand["name"], st
        # 매칭 성공이면 실제 상품 ref(products:{id})를, 실패해도 시도 자체를 evidence 에 남긴다.
        # Log a resolvable product ref on a hit; on a miss still record the attempt for the trail.
        if analysis.product_mentions or matched:
            refs = [f"products:{matched_id}"] if matched_id else ["products"]
            summary = (f"matched {[c['name'] for c in matched]} -> target {matched_name}"
                       if matched else f"no catalog match for {analysis.product_mentions}")
            log_action(db, store_id=store_id, trace_id=trace, action_type="read",
                       tool_name="match_products", input_refs=refs, summary=summary)

        # 권장 액션 + Needs You 라우팅 — 순수함수(Annotation Guide 와 동일 규칙)로 결정.
        # Recommended action + routing, via the pure rule that matches the Annotation Guide.
        recommended, route = route_decision(
            analysis.issue_type.value, analysis.severity.value, bool(inv.get("low")))

        action_id = None
        if route:
            action_id = db.review_actions.insert_one({
                "store_id": store_id, "review_id": r["_id"], "review_excerpt": r["text"][:140],
                "sentiment": analysis.sentiment.value, "issue_type": analysis.issue_type.value,
                "severity": analysis.severity.value, "product_mentions": analysis.product_mentions,
                "matched_product_id": safe_oid(matched_id) if matched_id else None,
                "product_name": matched_name, "inventory_status": inv,
                "suggested_owner_action": recommended, "reply_draft": analysis.reply_draft,
                "requires_owner_approval": True, "status": "pending",
                "created_at": datetime.now(timezone.utc),
            }).inserted_id
            log_action(db, store_id=store_id, trace_id=trace, action_type="write",
                       tool_name="route_review_action", input_refs=[f"reviews:{r['_id']}"],
                       output_refs=[f"review_actions:{action_id}"],
                       summary=f"Routed to Needs you: {recommended} ({analysis.issue_type.value})")
            actions_created += 1

        db.reviews.update_one({"_id": r["_id"]}, {"$set": {
            "status": "processed", "sentiment": analysis.sentiment.value,
            "issue_type": analysis.issue_type.value, "trace_id": trace,
            "processed_at": datetime.now(timezone.utc)}})

        processed.append({
            "review_id": str(r["_id"]), "author": r.get("author"), "rating": r.get("rating"),
            "text": r["text"], "sentiment": analysis.sentiment.value,
            "issue_type": analysis.issue_type.value, "product_mentions": analysis.product_mentions,
            "product_name": matched_name, "inventory_status": inv,
            "recommended_action": recommended, "requires_owner_approval": bool(action_id),
            "reply_draft": analysis.reply_draft, "routed_to_needs_you": bool(action_id),
            "trace_id": trace})

    return {"processed": processed, "processed_count": len(processed),
            "actions_created": actions_created}


def pending_review_actions(db: Database, store_id: str = STORE_ID) -> list[dict]:
    """Needs You 에 표시할 리뷰발 액션. Review-derived actions for the approval inbox."""
    rows = db.review_actions.find({"store_id": store_id, "status": "pending"}).sort("created_at", -1)
    return [{"action_id": str(a["_id"]), "name": a.get("product_name") or a.get("issue_type"),
             "issue_type": a.get("issue_type"), "severity": a.get("severity"),
             "recommended_action": a.get("suggested_owner_action"),
             "excerpt": a.get("review_excerpt"), "reply_draft": a.get("reply_draft")} for a in rows]


def resolve_review_action(db: Database, action_id: str, decision: str, by: str = "owner") -> dict:
    """리뷰 액션 승인/거절(상태만 기록, 다운스트림 부작용 없음). Approve/reject a review action."""
    oid = safe_oid(action_id)
    if oid is None:
        return {"ok": False, "error": "invalid action_id"}
    status = "approved" if decision == "approve" else "rejected"
    trace = new_trace()
    res = db.review_actions.update_one(
        {"_id": oid}, {"$set": {"status": status, "owner_decision": by,
                                "decided_at": datetime.now(timezone.utc)}})
    if res.matched_count == 0:
        return {"ok": False, "error": "action not found"}
    log_action(db, store_id=STORE_ID, trace_id=trace, action_type="write",
               tool_name=f"{decision}_review_action", input_refs=[f"review_actions:{action_id}"],
               output_refs=[f"review_actions:{action_id}"],
               summary=f"Owner {status} a review action")
    return {"ok": True, "action_id": action_id, "status": status}
