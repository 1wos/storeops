"""
데모 리셋 — 리허설로 소모된 재고를 '정답 상태'로 되돌리고, 선택적으로 데모 노이즈를 청소.
Demo reset — restore rehearsal-depleted inventory to a known-good baseline and,
optionally, clear demo noise (orders / events / logs) so each run starts clean.

가장 큰 라이브 데모 리스크는 코드가 아니라 "리허설 몇 번에 데모 DB가 바닥나는 것"이다.
The biggest live-demo risk isn't the code — it's the demo DB getting consumed by rehearsals.

사용 / usage:
    python scripts/reset_demo.py --snapshot   # 지금의 정답 재고를 baseline 으로 저장(1회)
    python scripts/reset_demo.py              # baseline 으로 재고 복원(비파괴)
    python scripts/reset_demo.py --clean      # 위 + 거래/이벤트/로그 청소(데모 직전 추천)
    python scripts/reset_demo.py --status      # 현재 상태만 출력
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import STORE_ID, get_db  # noqa: E402

BASELINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "demo_baseline.json")

# 데모 직전에 비우면 깔끔한 화면이 되는 일회성 거래/관찰 컬렉션(store 스코프).
# Transient per-run collections; clearing them (store-scoped) gives a fresh timeline.
TRANSIENT = [
    "orders", "inventory_events", "restock_tasks",
    "shelf_observations", "inventory_adjustment_suggestions", "agent_action_logs",
    "review_actions",
]


def _inventory_rows(db):
    """현재 재고를 상품명과 함께 조회. Current inventory joined with product names."""
    return list(db.inventory.aggregate([
        {"$match": {"store_id": STORE_ID}},
        {"$lookup": {"from": "products", "localField": "product_id",
                     "foreignField": "_id", "as": "p"}},
        {"$unwind": "$p"},
        {"$project": {"_id": 0, "name": "$p.name", "on_hand": 1,
                      "reserved": 1, "threshold": 1}},
        {"$sort": {"name": 1}},
    ]))


def snapshot(db):
    """지금의 정답 재고 상태를 baseline 파일로 저장. Save the current good state."""
    rows = _inventory_rows(db)
    data = {"store_id": STORE_ID, "inventory": rows}
    with open(BASELINE_PATH, "w") as f:
        json.dump(data, f, indent=2)
    print(f"snapshot saved → {os.path.relpath(BASELINE_PATH)} ({len(rows)} items)")
    for r in rows:
        print(f"  {r['name']}: on_hand {r['on_hand']} · reserved {r['reserved']} · threshold {r['threshold']}")


def reset_inventory(db):
    """baseline 의 on_hand/threshold 로 복원하고 reserved 를 0 으로. Restore from baseline."""
    if not os.path.exists(BASELINE_PATH):
        sys.exit("no baseline yet — run `python scripts/reset_demo.py --snapshot` first "
                 "(while inventory is at the levels you want for the demo).")
    with open(BASELINE_PATH) as f:
        base = json.load(f)

    changed = 0
    for item in base["inventory"]:
        prod = db.products.find_one({"store_id": STORE_ID, "name": item["name"]})
        if not prod:
            print(f"  ! skipped (product not found): {item['name']}")
            continue
        res = db.inventory.update_one(
            {"store_id": STORE_ID, "product_id": prod["_id"]},
            {"$set": {"on_hand": item["on_hand"], "reserved": 0,
                      "threshold": item["threshold"],
                      "updated_at": datetime.now(timezone.utc)}},
        )
        changed += res.modified_count
        print(f"  {item['name']}: on_hand → {item['on_hand']}, reserved → 0")
    print(f"inventory restored ({changed} rows updated)")


def clean_transient(db):
    """리허설로 쌓인 거래/이벤트/로그를 store 스코프로 삭제. Delete demo noise (store-scoped)."""
    print("cleaning transient demo data (store-scoped):")
    for c in TRANSIENT:
        n = db[c].delete_many({"store_id": STORE_ID}).deleted_count
        print(f"  {c}: -{n}")
    # 리뷰는 지우지 않고 상태만 'new' 로 되돌려 다시 스캔 가능하게. Reset reviews to re-scannable.
    rv = db.reviews.update_many(
        {"store_id": STORE_ID},
        {"$set": {"status": "new"}, "$unset": {"sentiment": "", "issue_type": "", "trace_id": "", "processed_at": ""}})
    print(f"  reviews: {rv.modified_count} reset to 'new'")


def status(db):
    print(f"store: {STORE_ID}")
    for r in _inventory_rows(db):
        low = " (LOW)" if r["on_hand"] - r["reserved"] <= r["threshold"] else ""
        print(f"  {r['name']}: avail {r['on_hand'] - r['reserved']} "
              f"(on_hand {r['on_hand']} / reserved {r['reserved']} / thr {r['threshold']}){low}")
    for c in TRANSIENT:
        print(f"  {c}: {db[c].count_documents({'store_id': STORE_ID})} docs")


def main():
    ap = argparse.ArgumentParser(description="Off-Duty demo reset")
    ap.add_argument("--snapshot", action="store_true", help="save current inventory as the baseline")
    ap.add_argument("--clean", action="store_true", help="also delete transient demo data")
    ap.add_argument("--status", action="store_true", help="print current state and exit")
    args = ap.parse_args()

    db = get_db()
    if args.status:
        status(db)
        return
    if args.snapshot:
        snapshot(db)
        return

    reset_inventory(db)
    if args.clean:
        clean_transient(db)
    print("\nfinal state:")
    status(db)


if __name__ == "__main__":
    main()
