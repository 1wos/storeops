"""
Customer Ordering sub-agent. 가용성 기반 주문/추천/협상.
Customer Ordering sub-agent. Availability-grounded ordering / recommendation / negotiation.

스키마: inventory.product_id 는 ObjectId, 쓰기는 pymongo(sync).
Schema: inventory.product_id is an ObjectId; writes use pymongo (sync).
"""
from __future__ import annotations

from datetime import datetime, timezone

from google.adk.agents import Agent
from pymongo.errors import DuplicateKeyError

from ..config import settings
from ..core.audit import log_action, new_trace
from ..db import STORE_ID, get_db, safe_oid
from .inventory import create_restock_task, write_inventory_event


def get_availability() -> dict:
    """
    재고가 있는 상품만 반환(재고-예약>0). 주문/추천 전에 반드시 호출.
    Return only in-stock products (on_hand-reserved>0). Call before recommending.
    """
    db = get_db()
    items = list(db.inventory.aggregate([
        {"$match": {"store_id": STORE_ID}},
        {"$lookup": {"from": "products", "localField": "product_id", "foreignField": "_id", "as": "p"}},
        {"$unwind": "$p"},
        {"$addFields": {"available": {"$max": [0, {"$subtract": ["$on_hand", "$reserved"]}]}}},
        {"$match": {"available": {"$gt": 0}}},
        {"$project": {"_id": 0, "product_id": {"$toString": "$product_id"}, "name": "$p.name",
                      "category": "$p.category", "price": "$p.price", "available": 1, "threshold": 1}},
        {"$sort": {"category": 1, "name": 1}},
    ]))
    db_log = get_db()
    log_action(db_log, store_id=STORE_ID, trace_id=new_trace(), action_type="read",
               tool_name="get_availability", input_refs=["inventory", "products"],
               summary=f"Listed {len(items)} available items")
    return {"available_items": items, "total_count": len(items)}


def create_order(items: list[dict], discount_pct: float = 0.0, conversation_id: str = "",
                 idempotency_key: str = "") -> dict:
    """
    확정 주문 생성 + 다운스트림 전체 루프 트리거(쓰기). 고객이 확정한 뒤에만 호출.
    Create a confirmed order and trigger the full downstream loop. Call ONLY after
    the customer confirms. Writes order → inventory_events → restock_tasks, all
    tied to one trace_id (so the owner sees the whole chain).

    Args:
        items: [{"product_id": str, "name": str, "qty": int, "unit_price": float}, ...]
        discount_pct: 0-100, 점주 규칙 한도 내 / within owner rules.
        idempotency_key: 같은 키로 재시도하면 중복 생성 대신 기존 주문 반환(재시도 안전).
            same key on retry returns the existing order instead of duplicating it.
    """
    db = get_db()
    trace = new_trace()

    # 멱등성: 에이전트가 같은 요청을 재시도해도 주문이 중복되지 않게.
    # Idempotency: an agent retry of the same request must not create a duplicate order.
    if idempotency_key:
        existing = db.orders.find_one({"store_id": STORE_ID, "idempotency_key": idempotency_key})
        if existing:
            return {"order_id": str(existing["_id"]), "total": existing.get("total"),
                    "idempotent": True, "note": "existing order returned (idempotency key matched)"}

    # 1) 재고 검증 / validate stock
    norm = []
    for it in items:
        pid = safe_oid(it.get("product_id"))
        if pid is None:
            return {"error": f"invalid product_id: {it.get('name', it.get('product_id'))}"}
        inv = db.inventory.find_one({"store_id": STORE_ID, "product_id": pid})
        if not inv:
            return {"error": f"product not found: {it.get('name', it['product_id'])}"}
        available = inv.get("on_hand", 0) - inv.get("reserved", 0)
        if available < int(it["qty"]):
            return {"error": f"insufficient stock for {it.get('name')}: have {available}, need {it['qty']}"}
        norm.append({"pid": pid, "name": it.get("name"), "qty": int(it["qty"]),
                     "unit_price": float(it["unit_price"])})

    # 2) owner_rules 할인한도 적용(가드레일). Clamp discount to owner_rules.max_discount_pct.
    rules = db.owner_rules.find_one({"store_id": STORE_ID}) or {}
    cap = rules.get("max_discount_pct", 100)
    applied_discount = min(float(discount_pct), float(cap))
    clamped = applied_discount < discount_pct
    if clamped:
        log_action(db, store_id=STORE_ID, trace_id=trace, action_type="read",
                   tool_name="check_owner_rules", input_refs=["owner_rules"],
                   summary=f"Discount {discount_pct}% over cap {cap}% -> clamped to {applied_discount}%")

    # 3) 합계 / totals
    subtotal = sum(n["qty"] * n["unit_price"] for n in norm)
    total = round(subtotal * (1 - applied_discount / 100), 2)

    # 3) 주문 삽입 / insert order
    order_doc = {
        "store_id": STORE_ID, "status": "confirmed",
        "items": [{"product_id": n["pid"], "qty": n["qty"], "unit_price": n["unit_price"]} for n in norm],
        "discount_pct": applied_discount, "total": total,
        "source_conversation_id": conversation_id or None,
        "idempotency_key": idempotency_key or None, "created_at": datetime.now(timezone.utc),
    }
    try:
        order_id = db.orders.insert_one(order_doc).inserted_id
    except DuplicateKeyError:
        # 동시 재시도가 unique index 에 걸림 → 먼저 들어간 주문을 반환(진짜 멱등).
        # A concurrent retry hit the unique index → return the order that won the race.
        existing = db.orders.find_one({"store_id": STORE_ID, "idempotency_key": idempotency_key})
        return {"order_id": str(existing["_id"]), "total": existing.get("total"),
                "idempotent": True, "note": "existing order returned (idempotency key matched)"}
    log_action(db, store_id=STORE_ID, trace_id=trace, action_type="write", tool_name="create_order",
               input_refs=[f"conversations:{conversation_id}"] if conversation_id else [],
               output_refs=[f"orders:{order_id}"], summary=f"Created order, total {total}")

    # 4) 재고 이벤트 + 재입고 / inventory events + restock (inventory flow 위임)
    restocks = 0
    for n in norm:
        ev = write_inventory_event(db, n["pid"], -n["qty"], order_id, trace)
        if ev["is_low"]:
            task = create_restock_task(db, n["pid"], ev["event_id"], trace)
            if task.get("task_id"):          # dedup: 새로 만든 경우만 카운트 / count only newly created
                restocks += 1

    return {"order_id": str(order_id), "total": total, "trace_id": trace,
            "requested_discount": discount_pct, "applied_discount": applied_discount,
            "discount_clamped": clamped, "restock_tasks_created": restocks}


def check_owner_rules() -> dict:
    """
    점주 규칙 조회(할인한도·보호재고). 할인/번들 제안 전에 호출.
    Read owner rules (discount cap, protected stock). Call before offering a discount/bundle.
    """
    db = get_db()
    r = db.owner_rules.find_one({"store_id": STORE_ID}) or {}
    log_action(db, store_id=STORE_ID, trace_id=new_trace(), action_type="read",
               tool_name="check_owner_rules", input_refs=["owner_rules"],
               summary=f"Read owner rules (max_discount {r.get('max_discount_pct')}%)")
    return {"max_discount_pct": r.get("max_discount_pct", 0),
            "protected_stock": r.get("protected_stock", {}),
            "approval_required": r.get("approval_required", False)}


ordering_agent = Agent(
    name="ordering_agent",
    model=settings.agent_model,
    description="Handles customer ordering: availability, recommendations, bounded discounts, order creation.",
    instruction=(
        "You take customer orders for Off-Duty. ALWAYS call get_availability before "
        "recommending; only sell in-stock items. Before offering any discount, call "
        "check_owner_rules and stay within max_discount_pct (create_order also enforces "
        "this). Build each item as {product_id, name, qty, unit_price} from "
        "get_availability, then call create_order once the customer agrees. Never invent "
        "prices or stock. ALWAYS reply in English, even if the customer writes in another language."
    ),
    tools=[get_availability, check_owner_rules, create_order],
)
