"""
Owner Audit & Summary sub-agent. 점주가 보는 읽기 측면 + 근거추적.
Owner Audit & Summary sub-agent. The owner-facing read side + evidence trail.

이 sub-agent 는 통합에서 이미 '진짜로' 동작하는 부분 — 나머지 flow 의 본보기.
This sub-agent already works for real — the template the other flows follow.
"""
from __future__ import annotations

from google.adk.agents import Agent

from ..config import settings
from ..core.audit import log_action, new_trace
from ..db import STORE_ID, get_db, start_of_today_utc

# MCP 노트 / MCP note:
#   MongoDB MCP read-evidence 는 인앱에서 LIVE 로 동작한다 — 전용 경로 POST /api/mcp-proof
#   (agents/mcp_agent.py)가 mongodb-mcp-server 를 통해 list-collections·count 등을 실제
#   호출하고 mongodb_mcp.<tool> 로 agent_action_logs 에 남겨 Evidence 에 노출한다.
#   다만 supervisor 안에서 요청마다 npx stdio 를 띄우면 느려서, MCP 는 별도 read 경로로
#   분리하고 메인 흐름(ordering/inventory/owner)은 pymongo 로 간다. 배포 시 remote MCP(Cloud Run).
#   MCP read-evidence runs LIVE in-app via the dedicated POST /api/mcp-proof path
#   (agents/mcp_agent.py): real list-collections/count calls THROUGH mongodb-mcp-server,
#   logged as mongodb_mcp.<tool> in agent_action_logs and shown in the Evidence Panel.
#   It's a separate read channel — the main flows use pymongo (per-request npx in the
#   supervisor would hang). Production hardening = remote MCP (Cloud Run) at deploy.


def get_owner_summary() -> dict:
    """
    오늘의 점주 요약 카드: 주문 수, 매출, 저재고 품목 수, 대기 재입고 수.
    Owner summary cards for today: orders, revenue, low-stock count, pending restocks.
    """
    db = get_db()
    since = start_of_today_utc()
    rows = list(db.orders.aggregate([
        {"$match": {"store_id": STORE_ID, "status": "confirmed", "created_at": {"$gte": since}}},
        {"$group": {"_id": None, "count": {"$sum": 1}, "revenue": {"$sum": "$total"}}},
    ]))
    orders = rows[0]["count"] if rows else 0
    revenue = rows[0]["revenue"] if rows else 0
    low_stock = db.inventory.count_documents(
        {"store_id": STORE_ID, "$expr": {"$lte": ["$on_hand", "$threshold"]}})
    pending = db.restock_tasks.count_documents({"store_id": STORE_ID, "status": "pending"})

    # 읽기 행동도 evidence trail 에 남긴다(자기문서화). Log the read into the trail too.
    log_action(db, store_id=STORE_ID, trace_id=new_trace(), action_type="read",
               tool_name="get_owner_summary", input_refs=["orders", "inventory", "restock_tasks"],
               summary=f"Owner summary: {orders} orders, {low_stock} low-stock")
    return {"orders": orders, "revenue": revenue, "low_stock": low_stock, "pending_restock": pending}


def get_audit_timeline(limit: int = 10) -> list[dict]:
    """
    에이전트 행동을 trace_id 로 묶어 시간순으로 반환(점주 audit 타임라인).
    Agent actions grouped by trace_id, newest first (the owner audit timeline).
    """
    db = get_db()
    traces = list(db.agent_action_logs.aggregate([
        {"$match": {"store_id": STORE_ID}},
        {"$sort": {"timestamp": 1}},
        {"$group": {"_id": "$trace_id", "started_at": {"$first": "$timestamp"},
                    "steps": {"$push": {"tool_name": "$tool_name", "summary": "$summary",
                                        "action_type": "$action_type", "result": "$result"}}}},
        {"$sort": {"started_at": -1}},
        {"$limit": int(limit)},
    ]))
    return [{"trace_id": t["_id"], "step_count": len(t["steps"]), "steps": t["steps"]} for t in traces]


owner_agent = Agent(
    name="owner_agent",
    model=settings.agent_model,
    description="Owner-facing analytics: summary cards and the agent audit timeline.",
    instruction=(
        "You are the Off-Duty owner assistant. Answer the shop owner's questions about "
        "sales, stock, and what the agent did, using get_owner_summary and "
        "get_audit_timeline. Base every number on a tool result; never invent figures. "
        "ALWAYS reply in English, regardless of the language of the question."
    ),
    tools=[get_owner_summary, get_audit_timeline],
)
