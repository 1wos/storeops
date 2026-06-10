"""
설정(Configuration) — 모든 값은 환경변수/.env 에서 온다. 하드코딩 절대 금지.
Configuration — every value comes from env/.env. No hardcoding, ever.

시니어 원칙 / Senior principle:
  모델명·연결문자열·키·임계값은 코드 리터럴이 아니라 설정으로 주입한다.
  Model names, connection strings, keys, thresholds are injected as config,
  never written as code literals — so we can swap them per environment.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 는 실행 위치(CWD)가 아니라 이 패키지 기준으로 찾는다(CWD 독립).
# Resolve .env relative to this package, not the CWD (CWD-independent).
_ENV_PATH = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_PATH), extra="ignore")

    # MongoDB (shared Atlas) / 공유 Atlas 연결
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "offduty"
    store_id: str = "store_001"

    # Gemini / LLM. 모델명은 설정으로 — 기본은 트랙 요건인 Gemini 3.
    # Model name is config-driven; default is Gemini 3 (the track requirement).
    gemini_api_key: str = ""
    agent_model: str = "gemini-3-flash-preview"      # supervisor + 추론 sub-agent
    router_model: str = "gemini-3-flash-preview"     # 라우팅용(향후 더 싼 모델로 교체 가능)
    # 폴백 모델(선택). 기본은 비활성("") → 레포를 100% Gemini 3 로 유지.
    # 굳이 GA 안전망을 쓰려면 .env 에서 AGENT_MODEL_FALLBACK 만 지정하면 됨(코드/레포엔 비-3 문자열 없음).
    # Optional fallback model. Empty by default → the repo stays 100% Gemini 3.
    # Set AGENT_MODEL_FALLBACK in .env if you want a GA safety net (no non-3 string lives in the repo).
    agent_model_fallback: str = ""

    # Runtime: Vertex AI(권장 — free-tier rate limit 없음 + 'Built on Google Cloud' 트랙 크레딧
    # + Agent Engine 배포 경로와 동일) vs AI Studio API 키. gemini-3-flash-preview 는 Vertex
    # 'global' 리전에서 동작 확인됨.
    # Vertex AI runtime (no free-tier rate limit, on-track GCP credibility, same deploy path)
    # vs AI Studio API key. gemini-3-flash-preview is verified on Vertex location 'global'.
    use_vertex: bool = True
    gcp_project: str = "off-duty-rapidthon"
    gcp_location: str = "global"

    # MOCK 모드 — Atlas/Vertex 없이 가짜 데이터로 전체 UI/흐름 구동(팀원 로컬 데모/논의용).
    # Mock mode — run the whole UI/flow on canned data with NO Atlas/Vertex (for local team demos).
    mock_mode: bool = False

    # MongoDB MCP. 읽기는 read-only MCP, 쓰기는 큐레이트된 도메인 툴.
    # Reads via read-only MCP; writes via curated domain tools (least privilege).
    mcp_command: str = "npx"
    mcp_args: str = "-y,mongodb-mcp-server"          # 콤마구분 / comma-separated
    mcp_proof_timeout: float = 90.0                  # /api/mcp-proof 상한(초) / cap (cold start + free tier)
    chat_timeout: float = 60.0                       # /api/chat 한 턴 상한(초) — Vertex gemini-3 툴턴이 ~40s / per-turn cap
    review_scan_limit: int = 5                        # 한 번에 스캔할 리뷰 수(각 ~Gemini 1콜) / reviews per scan
    review_match_confidence: float = 0.9              # 리뷰 상품매칭 confidence(하드코딩 금지) / product-match confidence

    # Atlas Search + Vector Search (vision/product matching).
    # 임베딩 모델은 트랙 규칙상 Google(Gemini) 또는 MongoDB(Voyage) 제공만.
    # Embedding model must be Google(Gemini) or MongoDB(Voyage) per track rules.
    embed_model: str = "gemini-embedding-001"
    embed_dim: int = 768
    product_search_index: str = "product_text"       # Atlas Search 인덱스명
    product_vector_index: str = "product_vector"     # Vector Search 인덱스명
    match_candidates: int = 3
    vision_low_conf: float = 0.5
    # 매칭 튜닝값(하드코딩 금지 → 설정). Matching tunables (config, not literals).
    match_ambiguity_ratio: float = 0.85      # 1위 대비 2위가 이 비율 넘으면 모호 / runner-up too close
    match_hybrid_boost: float = 0.1          # (legacy) 미사용 / superseded by RRF
    rrf_k: int = 60                          # Reciprocal Rank Fusion 상수(스케일프리 하이브리드) / RRF constant
    vector_num_candidates_floor: int = 50    # $vectorSearch numCandidates 하한
    vision_temperature: float = 0.1          # 비전 추출 온도(낮게=결정적) / low = deterministic
    # 임팩트 추정용 — 점주가 수동으로 했다면 액션당 걸렸을 평균 시간(초). 데모 추정치 라벨.
    # Impact estimate — assumed seconds an owner would spend per action done manually (labeled demo estimate).
    impact_seconds_per_action: float = 45.0
    # 재입고 승인 시 임계치의 몇 배까지 채울지 — 승인이 실제로 재고를 복구해 low 루프를 닫음.
    # On restock approval, refill on_hand to this multiple of threshold (so approval actually closes the low loop).
    restock_to_multiple: float = 2.0

    port: int = 8080


settings = Settings()


def bootstrap_genai_env() -> None:
    """
    ADK/google-genai 가 기대하는 환경변수를 설정값으로부터 채운다(API 키 모드).
    Populate the env vars ADK/google-genai expect, from settings (API-key mode).
    """
    if settings.use_vertex:
        # Vertex 모드: ADC(gcloud auth)로 인증, 프로젝트/리전만 지정. API 키 불필요.
        # Vertex mode: auth via ADC (gcloud), set project/location; no API key needed.
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.gcp_project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.gcp_location)
        return
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")
    if settings.gemini_api_key and not os.environ.get("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = settings.gemini_api_key
        os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)


def resolve_agent_model() -> str:
    """
    기본(preview) 모델에 접근 가능한지 한 번 확인하고, NOT_FOUND/404 면 GA 폴백으로 전환.
    settings.agent_model 을 제자리에서 갱신해 이후 빌드되는 에이전트가 같은 값을 쓰게 한다.
    Probe the primary (preview) model once; on NOT_FOUND/404 switch to the GA fallback and
    update settings.agent_model in place so agents built afterwards pick up the resolved name.
    (Other errors — e.g. rate limit — keep the primary; we only fall back on 'model missing'.)
    """
    bootstrap_genai_env()
    primary, fallback = settings.agent_model, settings.agent_model_fallback
    if not settings.use_vertex and not settings.gemini_api_key and not os.environ.get("GOOGLE_API_KEY"):
        return primary  # API-키 모드인데 키가 없으면 판단 불가 / can't probe without a key
    try:
        # 최소 호출(1토큰)로 '모델 사용 가능' 확인. Vertex 에선 models.get 이 불안정해 generate 로 검증.
        # Tiny 1-token call to confirm the model is usable (models.get is flaky on Vertex).
        from google import genai
        from google.genai import types
        client = genai.Client()   # 변수로 유지 — 인라인이면 GC 되어 transport 가 닫힘 / keep alive; inline temporary gets GC'd mid-call
        client.models.generate_content(
            model=primary, contents="ping",
            config=types.GenerateContentConfig(max_output_tokens=1))
        return primary
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).upper()
        # '모델 없음'(404/NOT_FOUND)일 때만 폴백. 403/권한/쿼터는 폴백하지 않고 그대로 알린다
        # (일시적 IAM/토큰 문제로 Gemini 3 능력을 조용히 강등시키지 않도록).
        # Fall back ONLY on 'model missing' (404/NOT_FOUND). Do NOT silently downgrade on
        # 403/permission/quota — those are transient/auth and shouldn't mask Gemini 3.
        is_missing = "NOT_FOUND" in msg or "404" in msg or "WAS NOT FOUND" in msg
        if is_missing and fallback and fallback != primary:
            settings.agent_model = fallback
            print(f"[model] primary '{primary}' not found → fallback '{fallback}'")
            return fallback
        if not is_missing:
            print(f"[model] probe non-fatal error (keeping '{primary}'): {str(exc)[:80]}")
        return primary
