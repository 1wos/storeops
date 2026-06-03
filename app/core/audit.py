"""
Audit / Evidence trail — 모든 의미있는 행동을 한 줄씩 기록한다.
Audit / Evidence trail — every meaningful action appends one line.

이 통합 제품의 신뢰(trust) 핵심: 에이전트가 무엇을 보고/말하고/썼는지
trace_id 로 묶어 점주가 추적할 수 있게 한다.
The trust centerpiece: what the agent saw / said / wrote, tied together by a
trace_id so the owner can audit the whole chain (PRD §10.3).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pymongo.database import Database


def new_trace() -> str:
    """한 고객 요청 = 하나의 trace. One customer request = one trace."""
    ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return f"trace_{ms}_{uuid.uuid4().hex[:8]}"


def log_action(
    db: Database,
    *,
    store_id: str,
    trace_id: str,
    action_type: str,        # read | write | recommend
    tool_name: str,
    input_refs: list | None = None,
    output_refs: list | None = None,
    result: str = "success",
    summary: str = "",
) -> dict:
    doc = {
        "store_id": store_id,
        "action_type": action_type,
        "tool_name": tool_name,
        "input_refs": input_refs or [],      # 무엇을 보고 / what it read
        "output_refs": output_refs or [],    # 무엇을 만들었나 / what it wrote
        "result": result,
        "summary": summary,
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc),
    }
    db.agent_action_logs.insert_one(doc)
    return doc


def instrument(db: Database, tool_name: str, action_type: str, fn):
    """
    도구 함수를 감싸 호출마다 자동 로깅한다(계측). 오케스트레이션과 거버넌스가
    한 코드 경로를 공유 — 에이전트가 도구를 쓰면 그 사용이 곧 타임라인에 남는다.
    Wrap a tool so each call is auto-logged. Orchestration and governance share
    one path: using a tool is, itself, recorded in the timeline it later exposes.

    내부 fn 은 {"result", "input_refs"?, "output_refs"?, "summary"?} 를 반환.
    The inner fn returns {"result", "input_refs"?, "output_refs"?, "summary"?}.
    """

    def wrapped(ctx: dict, **args):
        store_id, trace_id = ctx["store_id"], ctx["trace_id"]
        try:
            res = fn(ctx, **args)
            log_action(
                db, store_id=store_id, trace_id=trace_id, action_type=action_type,
                tool_name=tool_name, input_refs=res.get("input_refs", []),
                output_refs=res.get("output_refs", []), summary=res.get("summary", ""),
            )
            return res.get("result")
        except Exception as err:  # noqa: BLE001 — 로깅 후 재전파 / log then re-raise
            log_action(
                db, store_id=store_id, trace_id=trace_id, action_type=action_type,
                tool_name=tool_name, result="error", summary=str(err),
            )
            raise

    return wrapped
