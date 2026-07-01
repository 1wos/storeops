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
from datetime import datetime, timezone

import json

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import mockdata as mock
from .config import bootstrap_genai_env, settings
from .core.serial import to_jsonable
from .db import STORE_ID, ensure_indexes, get_db, start_of_today_utc
from .flows.owner_read import (
    approve_restock, approve_suggestion, audit_timeline, daily_ops_report, db_health,
    evidence_for_trace, explain_summary, impact_metrics, morning_digest, ops_metrics,
    pending_approvals, reconcile, reject_restock, reject_suggestion, reopen_approval, summary_cards,
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


# 에이전트 이름 → 점주에게 보여줄 단계 문구. agent name → owner-facing step label.
_AGENT_LABEL = {
    "off_duty_supervisor": "Routing to the right agent",
    "owner_agent": "Reading sales & store data",
    "inventory_agent": "Checking inventory levels",
    "ordering_agent": "Looking up the menu & availability",
    "vision_agent": "Analyzing the photo",
}


def _agent_label(name: str) -> str:
    return _AGENT_LABEL.get(name, f"Working ({name})")


def _latest_grounding(since=None) -> dict:
    """이번 턴(since 이후)에 기록된 최신 trace 만 근거 영수증으로 집어온다 — 직전 무관한 trace 오인 방지.
    Only grab a trace logged in THIS turn (timestamp >= since), so the evidence link never points
    at a previous, unrelated request. Returns trace_tools too for the receipt fallback."""
    try:
        db = get_db()
        q = {"store_id": STORE_ID}
        if since is not None:
            q["timestamp"] = {"$gte": since}
        latest = list(db.agent_action_logs.find(q).sort("timestamp", -1).limit(1))
        if latest:
            tid = latest[0]["trace_id"]
            rows = list(db.agent_action_logs.find({"store_id": STORE_ID, "trace_id": tid}))
            names = list(dict.fromkeys(r.get("tool_name") for r in rows if r.get("tool_name")))
            return {"trace_id": tid, "grounded_docs": len(rows), "trace_tools": names}
    except Exception:  # noqa: BLE001 — 근거는 best-effort / grounding is best-effort
        pass
    return {"trace_id": None, "grounded_docs": 0, "trace_tools": []}


async def stream_supervisor(query: str, user_id: str = "demo", session_id: str = "s1"):
    """SSE 제너레이터 — 에이전트/도구 이벤트를 실시간으로 흘리고, 끝에 최종 답 + 근거를 보낸다.
    SSE generator — stream agent/tool events live, end with the final answer + grounding."""
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    from .agents.supervisor import root_agent

    def sse(obj):
        return f"data: {json.dumps(obj)}\n\n"

    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=sessions)

    # supervisor 단계를 미리 한 번 흘려 즉각 피드백을 주고, path 에 심어 루프가 중복 emit 하지 않게 한다.
    # Pre-emit the supervisor step for instant feedback; seed path so the loop won't duplicate it.
    started = datetime.now(timezone.utc)   # 이번 턴 경계 — 근거 trace 를 이 시점 이후로 한정 / turn boundary for grounding
    path, tools, answer = ["off_duty_supervisor"], [], ""
    yield sse({"type": "step", "agent": "off_duty_supervisor", "label": _agent_label("off_duty_supervisor")})
    try:
        async for ev in runner.run_async(
            user_id=user_id, session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=query)]),
        ):
            author = getattr(ev, "author", None)
            if author and (not path or path[-1] != author):
                path.append(author)
                yield sse({"type": "step", "agent": author, "label": _agent_label(author)})
            try:
                for fc in (ev.get_function_calls() or []):
                    nm = getattr(fc, "name", None)
                    # transfer_to_agent 은 ADK 내부 위임 제어 도구 — 근거(데이터) 도구가 아니라 제외.
                    # transfer_to_agent is ADK's internal delegation control, not a data tool — skip it.
                    if nm and nm not in tools and nm != "transfer_to_agent":
                        tools.append(nm)
                        yield sse({"type": "tool", "name": nm})
            except Exception:  # noqa: BLE001 — 도구 추출 실패해도 흐름 유지 / keep streaming
                pass
            if ev.is_final_response() and ev.content:
                answer = "".join(p.text for p in ev.content.parts if getattr(p, "text", None))
    except Exception as e:  # noqa: BLE001
        busy = "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e)
        msg = ("The assistant is busy right now (rate limit) — please try again in a moment."
               if busy else "Sorry, I had trouble with that. Could you rephrase?")
        yield sse({"type": "answer", "answer": msg, "delegation_path": path, "tools": tools, "error": str(e)[:100]})
        return
    g = _latest_grounding(started)
    # 이벤트에서 도구를 못 잡았으면 trace 에 기록된 도구명으로 영수증을 채운다.
    # If the event stream didn't expose tool calls, fall back to the trace's logged tool names.
    if not tools:
        tools = g.get("trace_tools", [])
    yield sse({"type": "answer", "answer": answer, "delegation_path": path, "tools": tools,
               "trace_id": g.get("trace_id"), "grounded_docs": g.get("grounded_docs", 0)})


async def stream_mock(query: str):
    """MOCK_MODE 스트리밍 — 단계 몇 개 흘리고 canned 답을 보낸다. Mock streaming for dev."""
    m = mock.chat(query)

    def sse(obj):
        return f"data: {json.dumps(obj)}\n\n"

    yield sse({"type": "step", "agent": "off_duty_supervisor", "label": _agent_label("off_duty_supervisor")})
    for a in (m.get("delegation_path") or [])[1:]:
        await asyncio.sleep(0.4)
        yield sse({"type": "step", "agent": a, "label": _agent_label(a)})
    await asyncio.sleep(0.3)
    yield sse({"type": "answer", **m, "tools": ["get_owner_summary"],
               "trace_id": "trace_mock_chat", "grounded_docs": 3})


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


# 정적 HTML 캐시 금지 — 심사위원/팀이 늘 최신 UI(영문 등)를 받게. No HTML caching so everyone gets the latest UI.
_NO_CACHE = {"Cache-Control": "no-store, must-revalidate"}


@app.get("/", include_in_schema=False)
def console():
    """Owner Ops Console (다크 운영비서 UI). Owner Ops Console (dark ops-assistant UI)."""
    return FileResponse(os.path.join(_STATIC, "console.html"), headers=_NO_CACHE)


@app.get("/counter", include_in_schema=False)
def counter():
    """Customer Counter — 고객이 에이전트와 주문하는 화면. Customer ordering screen."""
    return FileResponse(os.path.join(_STATIC, "counter.html"), headers=_NO_CACHE)


@app.get("/layout", include_in_schema=False)
def layout():
    """Store Layout Advisor — merchandising / planogram placement tool. Runs standalone (no DB)."""
    return FileResponse(os.path.join(_STATIC, "layout.html"), headers=_NO_CACHE)


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


@app.post("/api/chat/stream", tags=["agent"])
async def chat_stream(body: ChatIn):
    """채팅 + 실시간 에이전트 trace(SSE). 기존 /api/chat 은 폴백으로 그대로 둔다.
    Streaming chat with live agent trace (SSE). /api/chat stays as the fallback."""
    gen = stream_mock(body.message) if settings.mock_mode else stream_supervisor(body.message)
    return StreamingResponse(gen, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                                      "Connection": "keep-alive"})


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


@app.get("/api/daily-report", tags=["owner"])
def daily_report():
    """End-of-day report: what the agent handled while the owner was off-duty (+ 3-sentence summary)."""
    return ok(mock.daily_report() if settings.mock_mode else daily_ops_report(get_db()))


@app.get("/api/reconciliation", tags=["owner"])
def reconciliation():
    """Ops health: data-integrity checks on the agent's actions (orders↔events, stock, refs…)."""
    return ok(mock.reconciliation() if settings.mock_mode else reconcile(get_db()))


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


# ── Review-to-Action: 리뷰(디지털 신호) → 운영 액션 / reviews → store ops ──
@app.get("/api/reviews", tags=["reviews"])
def reviews_list():
    if settings.mock_mode:
        return ok(mock.reviews_list())
    from .flows.review_to_action import list_reviews
    return ok({"reviews": list_reviews(get_db())})


@app.post("/api/reviews/scan", tags=["reviews"])
async def reviews_scan():
    """새 리뷰를 분석→매칭→재고확인→reply 초안→(필요시) Needs You 라우팅. Bounded for the demo."""
    if settings.mock_mode:
        return ok(mock.reviews_scan())
    from .flows.review_to_action import scan_reviews
    lim = settings.review_scan_limit
    try:
        # 한도(기본 5)에 비례한 예산. 각 리뷰는 자체 trace 로 즉시 커밋되므로 부분 완료도 안전.
        # Budget proportional to the limit; each review commits under its own trace, so a partial scan is safe.
        res = await asyncio.wait_for(
            asyncio.to_thread(scan_reviews, get_db(), STORE_ID, lim),
            timeout=settings.chat_timeout * (lim + 1))
        return ok(res)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "review scan timed out — try again", "processed": []}, status_code=504)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "review scan failed", "detail": str(e)[:120], "processed": []}, status_code=502)


@app.post("/api/approve/review/{action_id}", tags=["reviews"])
def do_approve_review(action_id: str):
    if settings.mock_mode:
        return _mock_ok(action_id=action_id, status="approved")
    from .flows.review_to_action import resolve_review_action
    return ok(resolve_review_action(get_db(), action_id, "approve"))


@app.post("/api/reject/review/{action_id}", tags=["reviews"])
def do_reject_review(action_id: str):
    if settings.mock_mode:
        return _mock_ok(action_id=action_id, status="rejected")
    from .flows.review_to_action import resolve_review_action
    return ok(resolve_review_action(get_db(), action_id, "reject"))


@app.post("/api/reopen/{kind}/{item_id}", tags=["owner"])
def do_reopen(kind: str, item_id: str):
    """Undo — 방금 내린 승인/거절을 다시 pending 으로. Reopen a just-made decision."""
    if settings.mock_mode:
        return _mock_ok(kind=kind, id=item_id, status="pending")
    return ok(reopen_approval(get_db(), kind, item_id))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "오늘 매출 어때?"
    print(to_jsonable(asyncio.run(run_supervisor(q))))
