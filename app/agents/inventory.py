"""
Inventory / Restock sub-agent. 주문→재고이벤트→임계치→재입고 task.
Inventory / Restock sub-agent. order → inventory_event → threshold → restock task.

쓰기는 '큐레이트된 도메인 툴'로만 (least privilege). 스키마: inventory.product_id 는 ObjectId.
Writes go only through curated domain tools (least privilege). Schema: inventory.product_id is an ObjectId.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from google.adk.agents import Agent
from pymongo.database import Database

from ..config import settings
from ..core.audit import log_action
from ..db import STORE_ID, get_db


def _as_oid(pid):
    """문자열/ObjectId 모두 허용. Accept str or ObjectId for product_id."""
    return pid if isinstance(pid, ObjectId) else ObjectId(str(pid))


def write_inventory_event(db: Database, product_id, delta: int, order_id, trace_id: str) -> dict:
    """
    재고 변동을 불변 이벤트로 기록하고 on_hand 를 갱신(쓰기 헬퍼).
    Record an immutable inventory event and update on_hand (write helper).
    before/after 상태를 남겨 점주가 감사할 수 있게 한다. Stores before/after for audit.
    """
    pid = _as_oid(product_id)
    # 원자적 갱신($inc) — 읽고-쓰기 사이의 분실 갱신/동시 주문 오버셀 방지.
    # Atomic $inc — avoids the lost-update / concurrent-order oversell of a read-then-$set.
    from pymongo import ReturnDocument
    updated = db.inventory.find_one_and_update(
        {"store_id": STORE_ID, "product_id": pid},
        {"$inc": {"on_hand": delta}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        return_document=ReturnDocument.AFTER,
    )
    after = updated.get("on_hand", 0) if updated else 0
    before = after - delta                      # 원자 갱신 후 역산 / derived after the atomic update
    threshold = updated.get("threshold", 0) if updated else 0

    evt = {
        "store_id": STORE_ID, "product_id": pid,
        "type": "order_decrement" if delta < 0 else "manual_adjust",
        "before": before, "after": after, "delta": delta,
        "source_order_id": order_id, "created_at": datetime.now(timezone.utc),
    }
    evt_id = db.inventory_events.insert_one(evt).inserted_id
    log_action(db, store_id=STORE_ID, trace_id=trace_id, action_type="write",
               tool_name="write_inventory_event",
               input_refs=[f"orders:{order_id}"], output_refs=[f"inventory_events:{evt_id}"],
               summary=f"stock {before} -> {after} (delta {delta})")
    return {"event_id": evt_id, "after": after, "threshold": threshold, "is_low": after <= threshold}


def create_restock_task(db: Database, product_id, event_id, trace_id: str) -> dict:
    """임계치 하회 시 재입고 task 생성(쓰기 헬퍼). 같은 상품의 pending task 가 이미 있으면
    중복 생성하지 않음(upsert) — 인박스/지표가 동일 항목으로 부풀지 않게.
    Raise a restock task on low stock. Upsert on (product, pending) so repeated low events
    don't pile up duplicate pending tasks (which would inflate the inbox + impact metrics)."""
    pid = _as_oid(product_id)
    res = db.restock_tasks.update_one(
        {"store_id": STORE_ID, "product_id": pid, "status": "pending"},
        {"$setOnInsert": {"store_id": STORE_ID, "product_id": pid, "type": "restock",
                          "status": "pending", "source_event_id": event_id,
                          "owner_decision": None, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    if res.upserted_id is None:
        return {"task_id": None, "deduped": True}   # 이미 pending 존재 / a pending task already existed
    task_id = res.upserted_id
    log_action(db, store_id=STORE_ID, trace_id=trace_id, action_type="write",
               tool_name="create_restock_task",
               input_refs=[f"inventory_events:{event_id}"], output_refs=[f"restock_tasks:{task_id}"],
               summary="below threshold -> restock task")
    return {"task_id": str(task_id)}


# ── ADK tool (읽기) / ADK tool (read) ──────────────────────────────
def list_restock_tasks() -> dict:
    """대기 중인 재입고 task 목록. List pending restock tasks for the owner to approve."""
    db = get_db()
    tasks = list(db.restock_tasks.find({"store_id": STORE_ID, "status": "pending"}))
    return {"pending": [{"product_id": str(t["product_id"]), "created_at": t["created_at"].isoformat()}
                        for t in tasks], "count": len(tasks)}


inventory_agent = Agent(
    name="inventory_agent",
    model=settings.agent_model,
    description="Keeps stock correct: writes inventory events and raises restock tasks on low stock.",
    instruction=(
        "You maintain Off-Duty inventory. Report pending restock tasks when asked. "
        "Inventory writes happen as part of order creation; surface low-stock items to the owner. "
        "ALWAYS reply in English."
    ),
    tools=[list_restock_tasks],
)
