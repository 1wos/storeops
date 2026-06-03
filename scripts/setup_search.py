"""
Atlas Search + Vector Search 셋업 (1회 실행).
Set up Atlas Search + Vector Search on `products` (run once).

1) 모든 상품에 Gemini 임베딩 적재 / embed every product (Gemini, Google-provided model)
2) Atlas Search 인덱스 + Vector Search 인덱스 생성 / create both search indexes

인덱스 빌드는 비동기라 생성 후 1~2분 뒤 쿼리 가능해진다.
Index build is async; queries work ~1-2 min after creation.

    python scripts/setup_search.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.product_search import embed_products, ensure_search_indexes  # noqa: E402
from app.db import get_db  # noqa: E402


def main():
    db = get_db()
    print("Embedding products (Gemini)…")
    n = embed_products(db)
    print(f"  embedded {n} products")
    print("Creating Atlas Search + Vector Search indexes…")
    ensure_search_indexes(db)
    print("Done. Indexes build asynchronously — give them ~1-2 minutes.")


if __name__ == "__main__":
    main()
