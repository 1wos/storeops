"""
Golden eval — Ground Truth 세트로 review-to-action 분류기의 정확도를 측정.
Golden eval — score the review-to-action classifier against the hand-labeled Ground Truth.

run_demo_checks 의 빠른 가드레일과 달리, 이건 LLM 을 골든셋 전체에 돌려 정확도를 낸다(온디맨드).
Unlike the fast guardrail in run_demo_checks, this runs the LLM over the whole golden set
to report accuracy (issue_type / product mention / routing). Run on demand.

사용 / usage:
    python scripts/run_eval_golden.py             # 전체 골든셋
    python scripts/run_eval_golden.py --limit 6   # 빠른 서브셋
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.product_search import match_label  # noqa: E402
from app.db import STORE_ID, get_db  # noqa: E402
from app.flows.review_to_action import _analyze, _inventory_status, catalog_names, route_decision  # noqa: E402

_GOLD = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "data", "golden", "review_to_action_eval.jsonl")


def _load(limit):
    rows = [json.loads(line) for line in open(_GOLD) if line.strip()]
    return rows[:limit] if limit else rows


def main():
    ap = argparse.ArgumentParser(description="Golden eval for review-to-action")
    ap.add_argument("--limit", type=int, default=0, help="evaluate only the first N cases")
    args = ap.parse_args()

    db = get_db()
    rows = _load(args.limit)
    n = len(rows)
    catalog = catalog_names(db)   # 추출 제약용 카탈로그 / catalog hint
    issue_ok = prod_ok = action_ok = approval_ok = 0
    print(f"Review-to-Action — golden eval ({n} cases)\n" + "=" * 56)

    for i, gt in enumerate(rows, 1):
        a = _analyze(gt["input"], catalog)
        # 매칭 + 액션 대상 상품(저재고 우선) / match + actionable target
        matched_id, inv = None, {"known": False}
        for mention in a.product_mentions:
            m = match_label(db, mention, 0.9)
            if m.get("best_product_id"):
                st = _inventory_status(db, m["best_product_id"])
                if matched_id is None or (st.get("low") and not inv.get("low")):
                    matched_id, inv = m["best_product_id"], st
        action, route = route_decision(a.issue_type.value, a.severity.value, bool(inv.get("low")))

        i_ok = a.issue_type.value == gt["expected_issue_type"]
        exp_prods = {p.lower() for p in gt.get("expected_product_mentions", [])}
        got_prods = {p.lower() for p in a.product_mentions}
        # 라벨이 비었으면 모델도 비어야 정답(빈 기대=빈 예측). empty-expected → empty-got is correct.
        p_ok = (exp_prods & got_prods) == exp_prods if exp_prods else (len(got_prods) == 0)
        # inventory_issue 의 'restock' 라벨은 '저재고일 때'가 전제 — 실제 재고에 맞춰 기대값 산출
        # (라이브에서 해당 상품이 저재고가 아니면 'owner_reply' 가 계약상 정답). Contract-aware expected action.
        exp_action = gt["expected_action"]
        if gt["expected_issue_type"] == "inventory_issue" and exp_action == "restock":
            exp_action = "restock" if inv.get("low") else "owner_reply"
        ac_ok = action == exp_action
        ap_ok = route == gt["requires_owner_approval"]
        issue_ok += i_ok; prod_ok += p_ok; action_ok += ac_ok; approval_ok += ap_ok

        flag = "✓" if (i_ok and ac_ok and ap_ok) else "✗"
        print(f"{flag} [{i:2}] {gt['input'][:54]:54} | issue {a.issue_type.value:20} "
              f"{'ok' if i_ok else 'EXP ' + gt['expected_issue_type']}")

    print("=" * 56)
    print(f"issue_type accuracy : {issue_ok}/{n} ({issue_ok / n:.0%})")
    print(f"product-mention      : {prod_ok}/{n} ({prod_ok / n:.0%})")
    print(f"suggested action     : {action_ok}/{n} ({action_ok / n:.0%})")
    print(f"owner-approval route : {approval_ok}/{n} ({approval_ok / n:.0%})")


if __name__ == "__main__":
    main()
