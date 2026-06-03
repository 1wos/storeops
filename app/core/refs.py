"""
Evidence trail 의 ref 해석 — "coll:id" 포인터를 실제 MongoDB 문서로.
Reference resolution for the evidence trail — "coll:id" pointer → real document.
점주(와 심사위원)가 에이전트 행동의 근거 문서를 직접 보게 한다.
Lets the owner (and judges) see the exact documents behind each agent action.
"""
from __future__ import annotations

from bson import ObjectId
from pymongo.database import Database


def parse_ref(ref: str):
    i = ref.find(":")
    if i == -1:
        return ref, None
    return ref[:i], ref[i + 1:]


def resolve_refs(db: Database, refs):
    by_collection: dict[str, list] = {}
    out = []
    for ref in refs:
        collection, _id = parse_ref(ref)
        if _id is None:
            out.append({"ref": ref, "collection": collection, "id": None, "doc": None})
            continue
        by_collection.setdefault(collection, []).append((ref, _id))
    for collection, items in by_collection.items():
        candidates = []
        for _ref, _id in items:
            candidates.append(_id)
            if ObjectId.is_valid(_id):
                candidates.append(ObjectId(_id))
        docs = list(db[collection].find({"_id": {"$in": candidates}}))
        by_id = {str(d["_id"]): d for d in docs}
        for ref, _id in items:
            out.append({"ref": ref, "collection": collection, "id": _id, "doc": by_id.get(str(_id))})
    return out
