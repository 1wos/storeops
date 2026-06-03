"""
진입점 — FastAPI(헬스/채팅) + CLI 러너. supervisor 를 ADK Runner 로 구동한다.
Entry point — FastAPI (health/chat) + CLI runner. Drives the supervisor via ADK Runner.

    uvicorn app.main:app --reload --port 8080      # 서버 / server
    python -m app.main "오늘 매출 어때?"           # CLI 한 번 실행 / one-shot CLI
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import mockdata as mock
from .config import bootstrap_genai_env, settings
from .core.serial import to_jsonable
from .db import STORE_ID, ensure_indexes, get_db, start_of_today_utc
from .flows.owner_read import (
    approve_restock, approve_suggestion, audit_timeline, db_health, evidence_for_trace,
    explain_summary, impact_metrics, morning_digest, ops_metrics, pending_approvals,
    reject_restock, reject_suggestion, reopen_approval, summary_cards,
)

bootstrap_genai_env()  # GOOGLE_API_KEY 등 환경 준비 / prepare genai env from settings

APP_NAME = "off-duty"


async def run_supervisor(query: str, user_id: str = "demo", session_id: str = "s1") -> dict:
    """supervisor 에이전트를 한 번 돌리고 (위임 경로, 최종 답)을 돌려준다.
    Run the supervisor once and return (delegation path, final answer)."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .agents.supervisor import root_agent

    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=sessions)

    path, answer = [], ""
    async for ev in runner.run_async(
        user_id=user_id, session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=query)]),
    ):
        if getattr(ev, "author", None):
            if not path or path[-1] != ev.author:
                path.append(ev.author)              # 어느 에이전트가 처리했나 / which agent handled it
        if ev.is_final_response() and ev.content:
            answer = "".join(p.text for p in ev.content.parts if getattr(p, "text", None))
    return {"answer": answer, "delegation_path": path}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.mock_mode:
        print("[mock] MOCK_MODE on — serving canned data, no Atlas/Vertex needed.")
        yield
        return
    try:
        ensure_indexes(get_db())
    except Exception as e:  # noqa: BLE001 — 인덱스는 best-effort / best-effort on boot
        print("ensure_indexes skipped:", e)
    try:
        # preview 모델 접근 확인 + 안되면 GA 폴백(데모 404 방지). best-effort.
        # Probe the model, fall back to GA if missing (prevents a demo-killing 404).
        from .config import resolve_agent_model
        print("[model] active:", resolve_agent_model(),
              "| vertex:", settings.use_vertex)
    except Exception as e:  # noqa: BLE001
        print("model resolve skipped:", e)
    yield


app = FastAPI(
    title="Off-Duty — integrated agent",
    description="Supervisor + flow sub-agents (ordering / inventory / vision / owner) over MongoDB.",
    version="0.1.0",
    lifespan=lifespan,
)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def ok(data):
    return JSONResponse(content=to_jsonable(data))


_STATIC = os.path.join(os.path.dirname(__file__), "static")


@app.get("/", include_in_schema=False)
def console():
    """Owner Ops Console (다크 운영비서 UI). Owner Ops Console (dark ops-assistant UI)."""
    return FileResponse(os.path.join(_STATIC, "console.html"))


@app.get("/counter", include_in_schema=False)
def counter():
    """Customer Counter — 고객이 에이전트와 주문하는 화면. Customer ordering screen."""
    return FileResponse(os.path.join(_STATIC, "counter.html"))


@app.get("/health", tags=["meta"])
def health():
    if settings.mock_mode:
        return {"ok": True, "store_id": settings.store_id, "model": settings.agent_model, "runtime": "mock"}
    try:
        get_db().command("ping")
        return {"ok": True, "store_id": settings.store_id, "model": settings.agent_model,
                "runtime": "vertex" if settings.use_vertex else "ai-studio"}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "db unavailable", "detail": str(e)[:80]}, status_code=503)


@app.post("/api/chat", tags=["agent"])
async def chat(body: ChatIn):
    """에이전트 실행 — Gemini 429/오류는 우아하게 처리. Run the agent; handle Gemini errors gracefully."""
    if settings.mock_mode:
        return ok(mock.chat(body.message))
    try:
        # 한 턴이 무한정 매달리지 않게 상한(서버측). Bound a single turn so it can't hang forever.
        return to_jsonable(await asyncio.wait_for(run_supervisor(body.message), timeout=settings.chat_timeout))
    except asyncio.TimeoutError:
        return ok({"answer": "That took too long — please try again.", "delegation_path": [], "error": "timeout"})
    except Exception as e:  # noqa: BLE001
        busy = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
        msg = ("The assistant is busy right now (rate limit) — please try again in a moment."
               if busy else "Sorry, I had trouble with that. Could you rephrase?")
        return ok({"answer": msg, "delegation_path": [], "error": str(e)[:100]})


@app.get("/api/availability", tags=["customer"])
def availability():
    """실시간 가용 재고(품절 제외) + 저재고 플래그. Live availability (in-stock only) + low flag."""
    if settings.mock_mode:
        return ok(mock.availability())
    from .agents.ordering import get_availability
    items = get_availability()["available_items"]
    for it in items:
        it["low"] = it.get("available", 0) <= it.get("threshold", 0)
    return ok({"items": items})


# ── Owner Ops Console read/approve API ──────────────────────────────
@app.get("/api/digest", tags=["owner"])
def digest():
    return ok(mock.digest() if settings.mock_mode else morning_digest(get_db()))


@app.get("/api/impact", tags=["owner"])
def impact():
    """Impact / ROI: what the agent did for the owner (actions automated, time saved est.)."""
    return ok(mock.impact() if settings.mock_mode else impact_metrics(get_db()))


@app.get("/api/ops", tags=["owner"])
def ops():
    """Observability: per-tool counts, error rate, writes (agent health)."""
    return ok(mock.ops() if settings.mock_mode else ops_metrics(get_db()))


@app.get("/api/explain", tags=["owner"])
def explain():
    """The actual aggregation + MongoDB query plan behind the summary numbers."""
    return ok(mock.explain() if settings.mock_mode else explain_summary(get_db()))


@app.get("/api/db-health", tags=["owner"])
def db_health_ep():
    """DB health: per-collection counts/size/indexes."""
    return ok(mock.db_health() if settings.mock_mode else db_health(get_db()))


@app.get("/api/summary", tags=["owner"])
def summary(today: bool = True):
    if settings.mock_mode:
        return ok(mock.summary(today))
    since = start_of_today_utc() if today else None
    return ok(summary_cards(get_db(), STORE_ID, since))


@app.get("/api/timeline", tags=["owner"])
def timeline(limit: int = 20):
    if settings.mock_mode:
        return ok(mock.timeline(max(1, min(int(limit), 100))))
    return ok(audit_timeline(get_db(), STORE_ID, max(1, min(int(limit), 100))))  # clamp / DoS guard


@app.get("/api/evidence/{trace_id}", tags=["owner"])
def evidence(trace_id: str):
    if settings.mock_mode:
        return ok(mock.evidence(trace_id))
    ev = evidence_for_trace(get_db(), trace_id, STORE_ID)
    return ok(ev) if ev else JSONResponse({"error": "not found"}, status_code=404)


@app.get("/api/approvals", tags=["owner"])
def approvals():
    return ok(mock.approvals() if settings.mock_mode else pending_approvals(get_db()))


@app.post("/api/mcp-proof", tags=["mongodb"])
async def mcp_proof(body: ChatIn | None = None):
    """
    MongoDB MCP 서버로 실제 툴 호출을 한 번 돌려 'MCP가 라이브'임을 증명한다.
    Run one live call THROUGH the MongoDB MCP server to prove MCP is wired in-app.
    The tool calls are also written to agent_action_logs (visible in the Evidence Panel).
    """
    if settings.mock_mode:
        return ok(mock.mcp_proof(body.message if body else ""))
    from .agents.mcp_agent import run_mcp_query
    q = (body.message if body else None) or (
        "List the collections in the database, then count the products in the catalog.")
    try:
        # MCP(stdio) + Gemini 은 콜드스타트/무료티어로 느릴 수 있어 시간제한을 둔다.
        # MCP cold-start + free-tier Gemini can be slow → bound it.
        res = await asyncio.wait_for(run_mcp_query(q), timeout=settings.mcp_proof_timeout)
        return ok(res)
    except asyncio.TimeoutError:
        return JSONResponse(
            {"error": "MCP call timed out (cold start / rate limit) — retry in a moment",
             "via": "MongoDB MCP server", "tool_calls": []}, status_code=504)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(
            {"error": "MCP call failed", "detail": str(e)[:120],
             "via": "MongoDB MCP server", "tool_calls": []}, status_code=502)


@app.post("/api/vision/analyze", tags=["vision"])
async def vision_analyze(photo: UploadFile = File(...), owner_note: str = Form("")):
    """점주가 선반 사진 업로드 → Gemini Vision 분석 → 제안은 승인 인박스로.
    Owner uploads a shelf photo → Gemini Vision → suggestions land in the approval inbox."""
    if settings.mock_mode:
        return ok(mock.vision_analyze())
    from .agents.vision import analyze_shelf_photo
    if not (photo.content_type or "").startswith("image/"):
        return JSONResponse({"error": "please upload an image file"}, status_code=400)
    data = await photo.read()
    suffix = ".png" if (photo.content_type or "").endswith("png") else ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        path = f.name
    try:
        res = await asyncio.to_thread(analyze_shelf_photo, path, owner_note)
        return ok(res)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "vision analysis failed", "detail": str(e)[:80]}, status_code=502)
    finally:
        try:
            os.unlink(path)  # temp 파일 정리(누수 방지) / clean up temp file
        except OSError:
            pass


def _mock_ok(**extra):
    return ok({"ok": True, "mock": True, **extra})


@app.post("/api/approve/restock/{task_id}", tags=["owner"])
def do_approve_restock(task_id: str):
    if settings.mock_mode:
        return _mock_ok(task_id=task_id, status="approved")
    return ok(approve_restock(get_db(), task_id))


@app.post("/api/approve/suggestion/{suggestion_id}", tags=["owner"])
def do_approve_suggestion(suggestion_id: str):
    if settings.mock_mode:
        return _mock_ok(suggestion_id=suggestion_id, status="approved")
    return ok(approve_suggestion(get_db(), suggestion_id))


@app.post("/api/reject/restock/{task_id}", tags=["owner"])
def do_reject_restock(task_id: str):
    if settings.mock_mode:
        return _mock_ok(task_id=task_id, status="rejected")
    return ok(reject_restock(get_db(), task_id))


@app.post("/api/reject/suggestion/{suggestion_id}", tags=["owner"])
def do_reject_suggestion(suggestion_id: str):
    if settings.mock_mode:
        return _mock_ok(suggestion_id=suggestion_id, status="rejected")
    return ok(reject_suggestion(get_db(), suggestion_id))


@app.post("/api/reopen/{kind}/{item_id}", tags=["owner"])
def do_reopen(kind: str, item_id: str):
    """Undo — 방금 내린 승인/거절을 다시 pending 으로. Reopen a just-made decision."""
    if settings.mock_mode:
        return _mock_ok(kind=kind, id=item_id, status="pending")
    return ok(reopen_approval(get_db(), kind, item_id))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "오늘 매출 어때?"
    print(to_jsonable(asyncio.run(run_supervisor(q))))
