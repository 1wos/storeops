"""
Agent Runtime(Vertex AI agent_engines) 배포 스캐폴드 — '막판'에 실행.
Agent Runtime (Vertex AI agent_engines) deployment scaffold — run at the FINAL stage.

트랙 요건 "Built with Google Cloud Agent Builder" 의 증거 = ADK agent 를
Agent Runtime 에 올리는 것. (UI 에서 새로 만드는 게 아님.)
The track's "Built with Agent Builder" evidence = deploying our ADK agent to
Agent Runtime (not building something new in a UI).

사전 준비 / prerequisites:
  gcloud auth application-default login
  gcloud config set project $GCP_PROJECT
  pip install --upgrade "google-cloud-aiplatform[agent_engines,adk]>=1.112"

실행 / run:
  GCP_PROJECT=off-duty-rapidthon GCP_LOCATION=us-central1 \
  STAGING_BUCKET=gs://<bucket> MONGODB_URI=... python -m app.deploy_agent
"""
from __future__ import annotations

import os


def deploy():
    # 모든 값은 env 에서 — 하드코딩 금지. All values from env — no hardcoding.
    project = os.environ["GCP_PROJECT"]
    location = os.environ.get("GCP_LOCATION", "us-central1")
    staging_bucket = os.environ["STAGING_BUCKET"]          # gs://...
    mongodb_uri = os.environ["MONGODB_URI"]                # prod: Secret Manager 권장

    import vertexai
    from vertexai import agent_engines

    from .agents.supervisor import root_agent

    client = vertexai.Client(project=project, location=location)
    adk_app = agent_engines.AdkApp(agent=root_agent)

    remote = client.agent_engines.create(
        agent=adk_app,
        config={
            "requirements": [
                "google-cloud-aiplatform[agent_engines,adk]>=1.112",
                "google-adk>=2.1", "mcp>=1.0", "pymongo>=4.9", "pydantic-settings>=2.5",
            ],
            "staging_bucket": staging_bucket,
            "display_name": "Off-Duty Store Manager Agent",
            "env_vars": {
                "MONGODB_URI": mongodb_uri,
                "MONGODB_DB": os.environ.get("MONGODB_DB", "offduty"),
                "STORE_ID": os.environ.get("STORE_ID", "store_001"),
                "AGENT_MODEL": os.environ.get("AGENT_MODEL", "gemini-3-flash-preview"),
            },
        },
    )
    print("Deployed Agent Runtime resource:", remote.api_resource.name)
    return remote


if __name__ == "__main__":
    deploy()
