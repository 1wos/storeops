"""
Demo golden checks — agent 신뢰성을 정량 검증(평가 하니스).
Demo golden checks — quantitative agent-reliability evaluation (PRD §10.4, Codex #8).

Google agent 모범사례가 강조하는 '평가'를 코드로: 핵심 행동들을 자동 pass/fail 로 채점.
The "evaluation" Google agent best-practices emphasize, as code: score the core
behaviors automatically. Fast + deterministic (uses flow functions, not the slow agent).

    python scripts/run_demo_checks.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.agents.inventory import write_inventory_event  # noqa: E402
from app.agents.ordering import create_order, get_availability  # noqa: E402
from app.core.product_search import match_label  # noqa: E402
from app.db import STORE_ID, get_db  # noqa: E402
from app.flows.owner_read import evidence_for_trace  # noqa: E402

CHECKS = []


def check(name):
    def deco(fn):
        CHECKS.append((name, fn))
        return fn
    return deco


@check("availability_grounding — only in-stock items are offered")
def c_availability(db):
    items = get_availability()["available_items"]
    bad = [i for i in items if i["available"] <= 0]
    return (not bad, f"{len(items)} items offered, {len(bad)} out-of-stock leaked")


@check("owner_rule_compliance — discount clamped to owner cap")
def c_discount(db):
    cap = (db.owner_rules.find_one({"store_id": STORE_ID}) or {}).get("max_discount_pct", 0)
    av = get_availability()["available_items"]
    if not av:
        return (False, "no products to order")
    it = av[0]
    res = create_order([{"product_id": it["product_id"], "name": it["name"], "qty": 1,
                         "unit_price": it["price"]}], discount_pct=cap + 50)
    ok = res.get("applied_discount", 999) <= cap and res.get("discount_clamped")
    return (ok, f"requested {cap+50}%, applied {res.get('applied_discount')}% (cap {cap}%)")


@check("order_loop — order writes inventory_event (+restock if low)")
def c_order_loop(db):
    av = get_availability()["available_items"]
    it = next((x for x in av if x["available"] >= 2), av[0] if av else None)
    if not it:
        return (False, "no product")
    before = db.inventory.find_one({"store_id": STORE_ID, "product_id": _oid(it["product_id"])})["on_hand"]
    res = create_order([{"product_id": it["product_id"], "name": it["name"], "qty": 1, "unit_price": it["price"]}])
    after = db.inventory.find_one({"store_id": STORE_ID, "product_id": _oid(it["product_id"])})["on_hand"]
    evt = db.inventory_events.find_one({"store_id": STORE_ID, "source_order_id": _oid(res["order_id"])})
    ok = after == before - 1 and evt is not None
    return (ok, f"on_hand {before}->{after}, inventory_event={'yes' if evt else 'NO'}")


@check("idempotency — same key returns the same order (no double-write)")
def c_idempotency(db):
    av = get_availability()["available_items"]
    it = av[0]
    key = f"eval-idem-{it['product_id']}"
    db.orders.delete_many({"store_id": STORE_ID, "idempotency_key": key})  # clean slate
    line = [{"product_id": it["product_id"], "name": it["name"], "qty": 1, "unit_price": it["price"]}]
    r1 = create_order(line, idempotency_key=key)
    r2 = create_order(line, idempotency_key=key)  # replay
    count = db.orders.count_documents({"store_id": STORE_ID, "idempotency_key": key})
    ok = r1["order_id"] == r2["order_id"] and r2.get("idempotent") and count == 1
    return (ok, f"same order_id={r1['order_id'] == r2['order_id']}, orders_with_key={count}")


@check("evidence_completeness — order trace resolves to MongoDB docs")
def c_evidence(db):
    av = get_availability()["available_items"]
    it = av[0]
    res = create_order([{"product_id": it["product_id"], "name": it["name"], "qty": 1, "unit_price": it["price"]}])
    ev = evidence_for_trace(db, res["trace_id"], STORE_ID)
    ok = bool(ev) and ev["evidence_count"] >= 1 and any(s["tool_name"] == "create_order" for s in ev["steps"])
    return (ok, f"trace resolved {ev['evidence_count'] if ev else 0} source docs across {len(ev['evidence']) if ev else 0} collections")


@check("atlas_search_live — product matching via Atlas Search/Vector")
def c_search(db):
    m = match_label(db, "cold brew", 0.9)
    ok = bool(m.get("best_name")) and m.get("method") in ("text", "vector", "hybrid")
    return (ok, f"'cold brew' -> {m.get('best_name')} via {m.get('method')}")


@check("vision_guardrail — ambiguous match routes to owner review")
def c_vision_guard(db):
    m = match_label(db, "zxqw unknown item", 0.4)  # nonsense + low confidence
    return (m["ambiguous"], f"low-confidence/unknown match ambiguous={m['ambiguous']} (best={m.get('best_name')})")


@check("review_routing_guardrail — sensitive/stock routes to Needs You, praise does not")
def c_review_routing(db):
    # 순수 라우팅 규칙(결정적) + 상품 매칭(Atlas) 를 GT 기준으로 검증. Deterministic GT for the router.
    from app.flows.review_to_action import route_decision
    cases = [
        route_decision("inventory_issue", "medium", True) == ("restock", True),
        route_decision("inventory_issue", "medium", False) == ("owner_reply", True),
        route_decision("refund_or_complaint", "high", False) == ("owner_reply", True),
        route_decision("praise", "low", False) == ("none", False),
        route_decision("service_issue", "low", False) == ("none", False),
    ]
    brownie = match_label(db, "brownies", 0.9).get("best_name")
    ok = all(cases) and (brownie or "").lower().startswith("brownie")
    return (ok, f"routing {sum(cases)}/5 correct, 'brownies' -> {brownie}")


@check("review_to_action_ground_truth — review classified + matched + routed + traced")
def c_review_gt(db):
    # 정전 GT 케이스를 실제 파이프라인(Gemini 분류+매칭+라우팅)으로 1건 검증. End-to-end on one labeled case.
    from app.flows.review_to_action import scan_reviews
    txt = "Loved the oat latte, but the brownies were sold out again."
    db.reviews.delete_many({"store_id": STORE_ID, "text": txt})
    # 다른 new 리뷰(시드/실데이터)를 잠시 'park' 해서 스캔이 이 케이스만 처리하게 격리.
    # Park other new reviews so the scan isolates this one case (the DB may hold many seeded reviews).
    db.reviews.update_many({"store_id": STORE_ID, "status": "new"}, {"$set": {"status": "_parked"}})
    db.reviews.insert_one({"store_id": STORE_ID, "source": "gt_check", "channel": "demo",
                           "rating": 3, "text": txt, "status": "new"})
    try:
        res = scan_reviews(db, STORE_ID, limit=1)
        p = next((x for x in res["processed"] if x["text"] == txt), None)
    finally:
        db.reviews.update_many({"store_id": STORE_ID, "status": "_parked"}, {"$set": {"status": "new"}})
    if not p:
        return (False, "review not processed")
    ev = evidence_for_trace(db, p["trace_id"], STORE_ID)
    ok = (p["issue_type"] == "inventory_issue"
          and any("brownie" in (m or "").lower() for m in p.get("product_mentions", []))
          and bool(p.get("reply_draft"))
          and p.get("requires_owner_approval") is True
          and bool(ev) and ev.get("evidence_count", 0) >= 1)
    return (ok, f"issue={p['issue_type']}, mentions={p.get('product_mentions')}, "
                f"approval={p.get('requires_owner_approval')}, trace={'yes' if ev else 'NO'}")


@check("reconciliation_clean — ops data-integrity invariants hold after agent actions")
def c_reconcile(db):
    from app.flows.owner_read import reconcile
    r = reconcile(db, STORE_ID)
    failed = [c["name"] for c in r["checks"] if not c["passed"]]
    return (r["healthy"], f"{r['passed']}/{r['total']} checks pass"
            + (f" · failed: {failed}" if failed else ""))


def _oid(pid):
    from bson import ObjectId
    return ObjectId(str(pid))


def main():
    db = get_db()
    print("Off-Duty — demo golden checks\n" + "=" * 48)
    passed = 0
    for name, fn in CHECKS:
        try:
            ok, detail = fn(db)
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"error: {e}"
        passed += bool(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}\n        {detail}")
    print("=" * 48)
    print(f"Reliability: {passed}/{len(CHECKS)} checks passed")
    sys.exit(0 if passed == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
