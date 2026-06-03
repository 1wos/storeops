"""
MongoDB 연결 + 인덱스 관리. 공유 Atlas 가 모든 flow 의 단일 진실원천.
MongoDB connection + index management. The shared Atlas cluster is the single
source of truth across all flows (§6 schema contract).
"""
from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database

from .config import settings


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    # tz_aware=True: 날짜를 UTC aware 로 받아 비교/계산이 안전하다.
    # tz_aware=True so datetimes round-trip as UTC-aware (safe comparisons).
    return MongoClient(settings.mongodb_uri, tz_aware=True)


def get_db() -> Database:
    return get_client()[settings.mongodb_db]


def ensure_indexes(db: Database) -> None:
    """
    읽기 위주 쿼리를 받쳐주는 인덱스. 멱등(idempotent) — 매 부팅마다 안전.
    Indexes backing the read-heavy queries. Idempotent — safe on every boot.
    """
    db.agent_action_logs.create_index([("store_id", ASCENDING), ("timestamp", ASCENDING)])
    db.agent_action_logs.create_index([("store_id", ASCENDING), ("trace_id", ASCENDING)])
    db.orders.create_index([("store_id", ASCENDING), ("status", ASCENDING), ("created_at", DESCENDING)])
    db.inventory.create_index([("store_id", ASCENDING), ("product_id", ASCENDING)])
    db.inventory_events.create_index([("store_id", ASCENDING), ("created_at", DESCENDING)])
    db.restock_tasks.create_index([("store_id", ASCENDING), ("status", ASCENDING)])
    # 멱등성을 DB 레벨에서 강제 — 같은 idempotency_key 로는 두 번 INSERT 불가(동시 재시도 안전).
    # partial 이라 key 없는 주문에는 적용 안 됨. Enforce idempotency at the DB level: a
    # concurrent retry with the same key cannot double-insert. Partial → only keyed orders.
    db.orders.create_index(
        [("store_id", ASCENDING), ("idempotency_key", ASCENDING)],
        unique=True,
        partialFilterExpression={"idempotency_key": {"$type": "string"}},
        name="uniq_idempotency_key",
    )


def start_of_today_utc(now: datetime | None = None) -> datetime:
    """오늘(UTC) 시작 시각 — '오늘' 요약의 윈도우. Start of today (UTC)."""
    now = now or datetime.now(timezone.utc)
    return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)


def safe_oid(value):
    """문자열을 ObjectId로 — 잘못된 값이면 None(크래시 방지). str->ObjectId or None (no crash)."""
    from bson import ObjectId
    try:
        return ObjectId(str(value))
    except Exception:  # noqa: BLE001
        return None


STORE_ID = settings.store_id
