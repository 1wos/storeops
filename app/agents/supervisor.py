"""
Supervisor(오케스트레이터) — 진입점 하나, 위임 구조. 메가 에이전트가 아니다.
Supervisor (orchestrator) — one entry point, delegation. NOT a mega-agent.

시니어 설계: 4개 flow 도구를 한 에이전트에 다 물리면 도구선택 정확도가 떨어진다.
대신 supervisor 가 의도를 보고 알맞은 sub-agent 로 위임(transfer)한다.
Senior design: piling all 4 flows' tools onto one agent degrades tool selection.
Instead the supervisor reads intent and transfers to the right sub-agent.
"""
from __future__ import annotations

from google.adk.agents import Agent

from ..config import settings
from .inventory import inventory_agent
from .ordering import ordering_agent
from .owner import owner_agent
from .vision import vision_agent

# 루트 supervisor. sub_agents 로 등록하면 ADK 가 LLM 기반 위임을 처리한다.
# Root supervisor. Registering sub_agents lets ADK handle LLM-driven delegation.
root_agent = Agent(
    name="off_duty_supervisor",
    model=settings.agent_model,
    description="Off-Duty store manager — routes each request to the right flow.",
    instruction=(
        "You are Off-Duty, an inventory-aware AI store manager for a small offline shop "
        "(a cafe in the demo). Route each request to ONE specialist by its UNDERLYING "
        "INTENT, not by exact keywords — people phrase things in many different ways.\n"
        "- ordering_agent: a customer wants to know what's available, get a recommendation, "
        "ask prices, or place/change an order. e.g. 'what do you have?', 'anything "
        "cold?', 'something sweet please', 'I'll grab a latte', 'what goes with a cold brew?'.\n"
        "- inventory_agent: stock levels, low stock, restock tasks.\n"
        "- vision_agent: a shelf/counter PHOTO was provided for analysis.\n"
        "- owner_agent: the OWNER wants a summary, sales, low-stock, what the agent did, "
        "or the audit trail. e.g. 'how's today?', 'give me a rundown', 'what happened "
        "while I was out?', 'show recent activity', 'any sales?'.\n"
        "Infer intent from meaning, synonyms, and context — NEVER require exact wording. "
        "If a request is genuinely ambiguous, ask ONE short clarifying question instead of "
        "guessing. Do not answer store questions yourself; delegate and keep replies grounded in tools. "
        "ALWAYS respond in English, regardless of the language the user writes in."
    ),
    sub_agents=[ordering_agent, inventory_agent, vision_agent, owner_agent],
)
