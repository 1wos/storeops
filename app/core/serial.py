"""
JSON 직렬화 안전 변환 (ObjectId/datetime → 문자열).
JSON-safe conversion of MongoDB values (ObjectId/datetime → str).
"""
from __future__ import annotations

from datetime import date, datetime

from bson import ObjectId


def to_jsonable(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
