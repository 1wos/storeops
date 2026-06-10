"""
리뷰 시드 적재 — 실제 데이터 샘플(선택) + 데모 특화 synthetic 을 normalize 해서 MongoDB reviews 에 upsert.
Load review seed — optionally sample real data + product-specific synthetic, normalize, upsert into MongoDB.

대형 원본 데이터셋은 커밋하지 않는다(data/raw gitignore). 스크립트로 샘플만 가져온다.
No large raw datasets are committed (data/raw is git-ignored); we only sample via this script.

사용 / usage:
    python scripts/prepare_review_seed.py              # 큐레이션 synthetic 만 적재(네트워크/의존성 없음)
    python scripts/prepare_review_seed.py --hf 40      # + Hugging Face Yelp 40개 샘플(datasets 설치 시)
    python scripts/prepare_review_seed.py --reset      # 기존 reviews/review_actions 비우고 다시 적재

normalized reviews schema:
  {review_id, store_id, source, channel, rating, text, created_at, status}
  source : huggingface_yelp | kaggle_restaurant | synthetic_demo
  channel: yelp | google | demo
"""
import argparse
import hashlib
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import STORE_ID, get_db  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RAW_DIR = os.path.join(_ROOT, "data", "raw")

# 데모 제품(Cold Brew / Oat Milk Latte / Brownie)에 묶인 synthetic 리뷰 — 실데이터가 우리 상품명과
# 안 맞을 수 있어 항상 함께 적재. Always-on synthetic reviews tied to the demo products.
SYNTHETIC = [
    (3, "Loved the oat latte, but the brownies were sold out again."),
    (2, "Came in for an oat milk latte but they were out again. Third time this month."),
    (1, "Ordered a cold brew, waited 20 minutes, then they said it was sold out."),
    (5, "The cold brew here is the best in the neighborhood. Smooth and strong."),
    (1, "There was a hair in my brownie. Pretty gross, won't be coming back."),
    (3, "Coffee is good but the cold brew tasted watery today, maybe a bad batch?"),
    (4, "Love the brownies. Service was a little slow during the lunch rush though."),
    (2, "Prices went up and the latte portion feels smaller now."),
    (5, "Friendly staff, cozy spot. Oat milk latte was perfect."),
    (1, "My pickup order was missing the brownie I paid for."),
]


def _doc(source, channel, rating, text):
    rid = "rv_" + hashlib.sha1(f"{source}:{text}".encode()).hexdigest()[:12]
    return {"review_id": rid, "store_id": STORE_ID, "source": source, "channel": channel,
            "rating": int(rating), "text": " ".join(str(text).split())[:300],
            "created_at": datetime.now(timezone.utc), "status": "new"}


def _hf_sample(n: int) -> list[dict]:
    """선택: datasets 설치 시 Yelp 에서 n개 샘플(원문 data/raw 저장). Optional HF Yelp sample → data/raw."""
    try:
        from datasets import load_dataset
    except Exception:  # noqa: BLE001
        print("[seed] `datasets` not installed — skipping HF; synthetic seed is enough.")
        return []
    print(f"[seed] sampling {n} reviews from Hugging Face Yelp/yelp_review_full …")
    ds = load_dataset("Yelp/yelp_review_full", split=f"train[:{n}]")
    os.makedirs(_RAW_DIR, exist_ok=True)
    import json
    with open(os.path.join(_RAW_DIR, "yelp_sample.jsonl"), "w") as f:
        for r in ds:
            f.write(json.dumps({"label": r.get("label"), "text": r.get("text")}, ensure_ascii=False) + "\n")
    print(f"[seed] wrote raw sample → data/raw/yelp_sample.jsonl (git-ignored)")
    return [_doc("huggingface_yelp", "yelp", int(r.get("label", 0)) + 1, r.get("text", "")) for r in ds]


def _kaggle_sample(n: int, dataset: str = "joebeachcapital/restaurant-reviews") -> list[dict]:
    """선택: Kaggle 음식점 리뷰 n개(카페 vertical 에 더 가까움). data/raw/kaggle 에 저장.
    Optional Kaggle restaurant-reviews sample (closer to the cafe vertical) → data/raw/kaggle."""
    import csv
    import glob
    import subprocess
    out_dir = os.path.join(_RAW_DIR, "kaggle")
    os.makedirs(out_dir, exist_ok=True)
    print(f"[seed] downloading Kaggle dataset '{dataset}' …")
    try:
        subprocess.run(["kaggle", "datasets", "download", "-d", dataset, "-p", out_dir, "--unzip"],
                       check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("[seed] `kaggle` CLI not installed — skipping Kaggle.")
        return []
    except subprocess.CalledProcessError as e:
        print(f"[seed] Kaggle download failed (auth/dataset?): {e.stderr[:160]}")
        return []
    csvs = glob.glob(os.path.join(out_dir, "*.csv"))
    if not csvs:
        print("[seed] no CSV found in Kaggle download.")
        return []
    rows = []
    with open(max(csvs, key=os.path.getsize), newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        # 텍스트/평점 컬럼 자동 감지(데이터셋마다 헤더가 달라서). Auto-detect text/rating columns.
        for row in reader:
            text = next((row[k] for k in row if k and k.lower() in
                         ("review", "text", "reviews", "comment", "content") and row[k]), None)
            if not text:
                continue
            rating = next((row[k] for k in row if k and "rat" in k.lower() and str(row[k]).strip()), 3)
            try:
                rating = int(float(str(rating).split()[0]))
            except Exception:  # noqa: BLE001
                rating = 3
            rows.append(_doc("kaggle_restaurant", "google", max(1, min(rating, 5)), text))
            if len(rows) >= n:
                break
    print(f"[seed] parsed {len(rows)} Kaggle reviews (raw kept in data/raw/kaggle, git-ignored)")
    return rows


def main():
    ap = argparse.ArgumentParser(description="Seed MongoDB reviews (synthetic + optional real)")
    ap.add_argument("--hf", type=int, default=0, metavar="N", help="also sample N from Hugging Face Yelp")
    ap.add_argument("--kaggle", type=int, default=0, metavar="N",
                    help="also sample N from Kaggle restaurant-reviews (needs kaggle CLI + token)")
    ap.add_argument("--reset", action="store_true", help="clear reviews + review_actions first")
    args = ap.parse_args()

    db = get_db()
    if args.reset:
        d1 = db.reviews.delete_many({"store_id": STORE_ID}).deleted_count
        d2 = db.review_actions.delete_many({"store_id": STORE_ID}).deleted_count
        print(f"[seed] reset: removed {d1} reviews, {d2} review_actions")

    docs = [_doc("synthetic_demo", "demo", r, t) for r, t in SYNTHETIC]
    docs += _hf_sample(args.hf) if args.hf else []
    docs += _kaggle_sample(args.kaggle) if args.kaggle else []

    inserted = 0
    for d in docs:
        res = db.reviews.update_one(
            {"store_id": STORE_ID, "review_id": d["review_id"]},
            {"$setOnInsert": d}, upsert=True)        # 멱등 / idempotent
        inserted += 1 if res.upserted_id is not None else 0

    total = db.reviews.count_documents({"store_id": STORE_ID})
    by_src = list(db.reviews.aggregate([
        {"$match": {"store_id": STORE_ID}},
        {"$group": {"_id": "$source", "n": {"$sum": 1}}}]))
    print(f"[seed] inserted {inserted} new (skipped existing); reviews total = {total}")
    for s in by_src:
        print(f"        {s['_id']}: {s['n']}")
    print("[seed] run the agent on them: POST /api/reviews/scan  (or the console 'Scan reviews' button)")


if __name__ == "__main__":
    main()
