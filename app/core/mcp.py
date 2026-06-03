"""
MongoDB MCP 툴셋 팩토리 — 읽기/집계는 MCP로(트랙 요건), 쓰기는 도메인 툴로.
MongoDB MCP toolset factory — reads/aggregation via MCP (track requirement),
writes via curated domain tools (least privilege).

지연 임포트(lazy import): 모듈을 불러오는 것만으로 npx 프로세스가 뜨지 않게
팩토리 안에서 ADK MCP 클래스를 임포트한다.
Lazy import: ADK MCP classes are imported inside the factory so merely importing
this module never spawns an npx process.
"""
from __future__ import annotations

from ..config import settings

# 읽기 전용으로 노출할 도구만 화이트리스트 (안전성).
# Whitelist only the read-only tools we expose (safety).
READ_ONLY_TOOLS = ["list-collections", "find", "count", "aggregate", "collection-schema", "explain"]


def build_mongo_mcp_toolset(read_only: bool = True):
    """
    Atlas 를 가리키는 MongoDB MCP 서버를 stdio 로 띄우는 ADK 툴셋을 만든다.
    Build an ADK toolset that launches the MongoDB MCP server (stdio) → Atlas.

    주의(prod): 요청마다 npx 스폰은 금지 — 이미지에 베이크하거나 롱리빙 세션으로.
    Note (prod): do NOT spawn npx per request — bake into the image / long-lived session.
    """
    import os

    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    args = [a for a in settings.mcp_args.split(",") if a]
    server_args = list(args)
    if read_only:
        server_args.append("--readOnly")

    # 연결 문자열은 env 로 전달(공식 권장). --connectionString 는 deprecated.
    # Pass the connection string via env (official, non-deprecated path).
    env = {**os.environ, "MDB_MCP_CONNECTION_STRING": settings.mongodb_uri}

    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=settings.mcp_command, args=server_args, env=env,
            ),
            # 바깥 /api/mcp-proof 의 wait_for(=mcp_proof_timeout) 가 권위적 데드라인이 되도록
            # stdio 타임아웃을 그보다 크게 둔다(콜드스타트가 502 대신 우아한 504로). margin +15s.
            # Keep stdio timeout >= the outer wait_for so the calibrated 504 (not a raw 502) wins on cold start.
            timeout=settings.mcp_proof_timeout + 15,
        ),
        tool_filter=READ_ONLY_TOOLS if read_only else None,
    )
