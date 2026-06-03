"""
견고성(robustness) 체크 — 같은 의도를 여러 표현으로 던져 라우팅 일관성 검증.
Robustness checks — same intent phrased many ways must route to the same agent.

'특정 프롬프트에만 동작하면 안 된다'를 증명: 실제 supervisor 를 통해 delegation_path 확인.
Proves the agent is not prompt-brittle: routes by intent through the REAL supervisor.

    python scripts/run_robustness_checks.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.main import run_supervisor  # noqa: E402

# (expected_agent, [paraphrases of the same intent])
PARAPHRASES = [
    ("owner_agent", [
        "how's today going?",
        "give me a quick rundown of the shop",
        "what happened while I was out?",
    ]),
    ("ordering_agent", [
        "what do you have?",
        "anything cold to drink?",
        "recommend me something sweet please",
    ]),
]


async def _route_with_retry(prompt, expected, n, tries=3):
    """429(쿼터)면 백오프 후 재시도. Back off + retry on 429 (free-tier quota)."""
    delay = 35.0
    for attempt in range(tries):
        try:
            out = await run_supervisor(prompt, session_id=f"rob{n}_{attempt}")
            path = out.get("delegation_path") or []
            return path, expected in path
        except Exception as e:  # noqa: BLE001
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < tries - 1:
                await asyncio.sleep(delay)
                delay *= 1.5
                continue
            return [f"error: {str(e)[:60]}"], False
    return ["error: retries exhausted"], False


async def main():
    print("Off-Duty — routing robustness (same intent, different wording)")
    print("=" * 60)
    passed = total = 0
    for i, (expected, prompts) in enumerate(PARAPHRASES):
        for p in prompts:
            total += 1
            path, hit = await _route_with_retry(p, expected, total)
            passed += bool(hit)
            print(f"[{'PASS' if hit else 'FAIL'}] \"{p}\"\n        -> {path}  (expected {expected})")
            # 무료티어 5 req/분 한도 — 콜 사이 간격. Free tier is 5 req/min; pace the calls.
            await asyncio.sleep(float(os.environ.get("ROB_DELAY", "20")))
    print("=" * 60)
    print(f"Routing robustness: {passed}/{total} paraphrases routed correctly")


if __name__ == "__main__":
    asyncio.run(main())
