# Off-Duty web app (FastAPI + ADK on Vertex) for Cloud Run.
# Python + Node (Node is needed so the MongoDB MCP server can run via /api/mcp-proof).
FROM python:3.12-slim

# Node 20 + the MongoDB MCP server (global, so the MCP call is fast on a cold start).
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g mongodb-mcp-server \
 && apt-get purge -y curl gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY app/requirements.txt ./app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app/ ./app/
COPY scripts/ ./scripts/

ENV PORT=8080
# Cloud Run sets $PORT; bind to it.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
