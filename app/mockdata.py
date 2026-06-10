"""
MOCK 모드 — Atlas/Vertex 크리덴셜 없이도 전체 UI/흐름이 도는 가짜 데이터.
Mock mode — realistic canned data so the whole UI/flow runs with NO Atlas/Vertex creds.

목적: 팀원 누구나 `MOCK_MODE=true uvicorn ...` 로 즉시 통합본을 띄워 만져보고,
프론트엔드/추가 기능을 함께 논의할 수 있게 한다(설정·배선 0).
Purpose: any teammate can boot the integrated app instantly (no setup) to click through it
and discuss frontend/features. Enabled by config.mock_mode (env MOCK_MODE=true).
"""
from __future__ import annotations

_PRODUCTS = [
    {"product_id": "p_coldbrew", "name": "Cold Brew", "category": "drink", "price": 4.5,
     "available": 12, "threshold": 6},
    {"product_id": "p_oatlatte", "name": "Oat Milk Latte", "category": "drink", "price": 5.5,
     "available": 4, "threshold": 5},
    {"product_id": "p_brownie", "name": "Brownie", "category": "pastry", "price": 3.5,
     "available": 8, "threshold": 5},
]

_TRACE = "trace_mock_0001"


def availability() -> dict:
    items = [dict(p, low=p["available"] <= p["threshold"]) for p in _PRODUCTS]
    return {"items": items}


def summary(today: bool = True) -> dict:
    return {"orders": 17, "revenue": 131.95, "agent_actions": 42,
            "low_stock": [{"name": "Oat Milk Latte", "available": 4, "threshold": 5}],
            "top_items": [{"name": "Cold Brew", "qty": 9}, {"name": "Brownie", "qty": 6}]}


def digest() -> dict:
    return {"orders": 17, "revenue": 131.95, "low_stock": 1, "needs_you": 2, "agent_actions": 42}


def impact() -> dict:
    return {"actions_automated": 23, "decisions_chained": 42, "traces": 17,
            "avg_steps_per_trace": 2.5, "restocks_flagged": 3, "oos_recs_avoided": "guaranteed",
            "owner_minutes_saved_est": 17, "basis": "MOCK data (demo)"}


def _recon_checks() -> list:
    names = ["orders_have_inventory_events", "order_events_are_negative", "no_negative_stock",
             "low_stock_has_restock_task", "review_actions_have_source_review",
             "write_refs_resolve_in_evidence"]
    details = ["3/3 confirmed orders have events", "0 order-sourced events with non-negative delta",
               "0 products with on_hand<0", "1/1 low items have a pending restock",
               "0 orphan review actions", "9/9 today's write refs resolve to a document"]
    return [{"name": n, "passed": True, "detail": d} for n, d in zip(names, details)]


def reconciliation() -> dict:
    return {"checks": _recon_checks(), "passed": 6, "total": 6, "healthy": True}


def daily_report() -> dict:
    return {"orders_today": 17, "revenue_today": 131.95, "agent_actions": 12, "review_actions": 2,
            "restock_tasks_created": 1, "pending_approvals": 3, "mcp_calls": 2,
            "estimated_minutes_saved": 17, "errors": 0, "window": "today (UTC)",
            "ops_health": {"passed": 6, "total": 6, "checks": _recon_checks()},
            "summary": ("While you were off-duty, Off-Duty took 12 agent actions, processed 17 "
                        "customer orders, routed 2 review issues to Needs you, and created 1 restock "
                        "task. No failed tool calls were detected. All ops-health checks passed.")}


def ops() -> dict:
    return {"total_actions": 42, "errors": 0, "success_rate": 1.0, "writes": 23,
            "by_tool": [{"tool": "get_availability", "count": 12, "errors": 0},
                        {"tool": "create_order", "count": 9, "errors": 0},
                        {"tool": "write_inventory_event", "count": 9, "errors": 0},
                        {"tool": "mongodb_mcp.list-collections", "count": 1, "errors": 0}]}


def explain() -> dict:
    return {"collection": "orders",
            "pipeline": [{"$match": {"store_id": "store_001", "status": "confirmed"}},
                         {"$group": {"_id": None, "orders": {"$sum": 1},
                                     "revenue": {"$sum": "$total"}}}],
            "plan_stage": "IXSCAN", "index_used": "store_id_1_status_1_created_at_-1"}


def db_health() -> dict:
    return {"collections": [{"collection": c, "count": n, "indexes": i} for c, n, i in [
        ("products", 71, 2), ("inventory", 3, 1), ("orders", 17, 2),
        ("inventory_events", 18, 1), ("restock_tasks", 3, 1), ("agent_action_logs", 42, 2),
        ("shelf_observations", 2, 1)]]}


def timeline(limit: int = 20) -> list:
    return [
        {"trace_id": _TRACE, "title": "Order: Cold Brew + Brownie", "outcome": "success",
         "steps": [{"tool_name": "get_availability", "action_type": "read"},
                   {"tool_name": "create_order", "action_type": "write"},
                   {"tool_name": "write_inventory_event", "action_type": "write"}]},
        {"trace_id": "trace_mock_0002", "title": "Owner summary", "outcome": "success",
         "steps": [{"tool_name": "get_owner_summary", "action_type": "read"}]},
        {"trace_id": "trace_mock_0003", "title": "Shelf photo analyzed", "outcome": "success",
         "steps": [{"tool_name": "analyze_shelf_photo", "action_type": "vision"},
                   {"tool_name": "match_products", "action_type": "read"}]},
    ][:max(1, limit)]


def evidence(trace_id: str) -> dict:
    # 리뷰 trace 면 분류→매칭→라우팅 trail 을 반환(주문 trail 과 구분). Review trace → review trail.
    if "rev" in (trace_id or ""):
        return {"trace_id": trace_id, "step_count": 3, "evidence_count": 2,
                "steps": [
                    {"action_type": "read", "tool_name": "classify_review",
                     "summary": "mixed/inventory_issue (action=True)"},
                    {"action_type": "read", "tool_name": "match_products",
                     "summary": "matched ['Oat Milk Latte', 'Brownie'] -> target Brownie"},
                    {"action_type": "write", "tool_name": "route_review_action",
                     "summary": "Routed to Needs you: restock (inventory_issue)"}],
                "evidence": {
                    "reviews": [{"doc": {"_id": "rv_mock", "channel": "demo", "rating": 3,
                                         "text": "Loved the oat latte, but the brownies were sold out again.",
                                         "issue_type": "inventory_issue"}}],
                    "review_actions": [{"doc": {"product_name": "Brownie", "suggested_owner_action": "restock",
                                                "requires_owner_approval": True, "status": "pending"}}]}}
    return {"trace_id": trace_id, "step_count": 3, "evidence_count": 3,
            "steps": [
                {"action_type": "read", "tool_name": "get_availability",
                 "summary": "Listed 3 available items"},
                {"action_type": "write", "tool_name": "create_order",
                 "summary": "Created order, total 8.00"},
                {"action_type": "write", "tool_name": "write_inventory_event",
                 "summary": "stock 13 -> 12 (delta -1)"}],
            "evidence": {
                "orders": [{"doc": {"_id": "ord_mock", "status": "confirmed", "total": 8.0,
                                    "items": [{"name": "Cold Brew", "qty": 1, "unit_price": 4.5},
                                              {"name": "Brownie", "qty": 1, "unit_price": 3.5}]}}],
                "inventory_events": [{"doc": {"product": "Cold Brew", "before": 13, "after": 12,
                                              "delta": -1, "type": "order_decrement"}}]}}


def approvals() -> dict:
    return {"total": 3,
            "restock": [{"task_id": "task_mock_1", "name": "Oat Milk Latte"}],
            "suggestions": [{"suggestion_id": "sugg_mock_1", "name": "Brownie",
                             "signal": "low", "confidence": 0.82}],
            "reviews": [{"action_id": "rev_mock_1", "name": "Brownie", "issue_type": "inventory_issue",
                         "severity": "medium", "recommended_action": "restock",
                         "excerpt": "Loved the oat latte, but the brownies were sold out again.",
                         "reply_draft": "So glad you loved the oat latte! Sorry the brownies were out — restocking now."}]}


def reviews_list() -> dict:
    return {"reviews": [
        {"review_id": "r1", "source": "google", "author": "Priya N.", "rating": 3,
         "text": "Loved the oat latte, but the brownies were sold out again.", "status": "processed",
         "sentiment": "mixed", "issue_type": "inventory_issue"},
        {"review_id": "r2", "source": "google", "author": "Dan P.", "rating": 5,
         "text": "The cold brew here is the best in the neighborhood.", "status": "processed",
         "sentiment": "positive", "issue_type": "praise"},
        {"review_id": "r3", "source": "yelp", "author": "Sara L.", "rating": 1,
         "text": "There was a hair in my brownie.", "status": "new", "sentiment": None, "issue_type": None}]}


def reviews_scan() -> dict:
    return {"processed_count": 3, "actions_created": 2, "processed": [
        {"review_id": "r1", "author": "Priya N.", "rating": 3, "sentiment": "mixed",
         "issue_type": "inventory_issue", "product_mentions": ["Oat Milk Latte", "Brownie"],
         "product_name": "Brownie",
         "inventory_status": {"known": True, "available": 0, "threshold": 5, "low": True},
         "recommended_action": "restock", "requires_owner_approval": True,
         "reply_draft": "So glad you loved the oat latte! Sorry the brownies were out — restocking now.",
         "routed_to_needs_you": True, "trace_id": "trace_mock_rev_1",
         "text": "Loved the oat latte, but the brownies were sold out again."},
        {"review_id": "r3", "author": "Sara L.", "rating": 1, "sentiment": "negative",
         "issue_type": "refund_or_complaint", "product_mentions": ["Brownie"], "product_name": "Brownie",
         "inventory_status": {"known": True, "available": 10, "threshold": 5, "low": False},
         "recommended_action": "owner_reply", "requires_owner_approval": True,
         "reply_draft": "We're so sorry about that, this isn't our standard. Please DM us so we can make it right.",
         "routed_to_needs_you": True, "trace_id": "trace_mock_rev_2",
         "text": "There was a hair in my brownie."},
        {"review_id": "r2", "author": "Dan P.", "rating": 5, "sentiment": "positive",
         "issue_type": "praise", "product_mentions": ["Cold Brew"], "product_name": "Cold Brew",
         "inventory_status": {"known": True, "available": 12, "threshold": 6, "low": False},
         "recommended_action": "none", "requires_owner_approval": False,
         "reply_draft": "Thank you so much, see you again soon!",
         "routed_to_needs_you": False, "trace_id": "trace_mock_rev_3",
         "text": "The cold brew here is the best in the neighborhood."}]}


def chat(message: str) -> dict:
    """아주 단순한 키워드 라우팅으로 그럴듯한 답 + 위임 경로를 만든다. Canned but plausible."""
    m = (message or "").lower()
    if any(k in m for k in ["sale", "today", "summary", "revenue", "how", "rundown", "happen"]):
        return {"answer": "Today: 17 orders, $131.95 revenue. 1 item low (Oat Milk Latte). "
                          "2 things need your approval. [MOCK]",
                "delegation_path": ["off_duty_supervisor", "owner_agent"]}
    if any(k in m for k in ["stock", "low", "restock", "inventory"]):
        return {"answer": "Oat Milk Latte is low (4 left, threshold 5). A restock task is waiting "
                          "in your approval inbox. [MOCK]",
                "delegation_path": ["off_duty_supervisor", "inventory_agent"]}
    return {"answer": "We have Cold Brew ($4.50), Oat Milk Latte ($5.50), and Brownie ($3.50) "
                      "available right now. Would you like to order? [MOCK]",
            "delegation_path": ["off_duty_supervisor", "ordering_agent"]}


def mcp_proof(message: str = "") -> dict:
    return {"query": message or "List the collections, then count the products.",
            "trace_id": _TRACE,
            "tool_calls": [{"tool": "list-collections", "args": {"database": "offduty"}},
                           {"tool": "count", "args": {"database": "offduty", "collection": "products"}}],
            "answer": "The offduty database has 7 collections; there are 71 products. [MOCK]",
            "via": "MongoDB MCP server (mock)"}


def vision_analyze() -> dict:
    return {"caption": "A cafe shelf with cold brew bottles running low and a full brownie tray. [MOCK]",
            "detected": [{"label": "cold brew bottle", "product_name": "Cold Brew", "stock_signal": "low"},
                         {"label": "brownie", "product_name": "Brownie", "stock_signal": "ok"}],
            "suggestions_created": 1}
