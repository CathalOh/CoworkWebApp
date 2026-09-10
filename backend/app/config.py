"""Application settings.

Everything is environment-driven so the same image runs under docker-compose today and
Kubernetes later. Settings are grouped by concern; see config/.env.example for docs.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app -------------------------------------------------------------------------------
    app_name: str = "cowork-backbone"
    env: Literal["dev", "test", "prod"] = "dev"
    debug: bool = False
    public_base_url: str = "http://localhost:8000"
    frontend_origin: str = "http://localhost:5173"
    secret_key: str = Field(default="dev-only-change-me-0123456789abcdef", min_length=16)
    session_cookie_name: str = "cw_session"
    session_ttl_seconds: int = 60 * 60 * 12
    csrf_header_name: str = "X-CSRF-Token"
    cookie_secure: bool = False  # set true behind TLS

    # --- storage ---------------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    redis_url: str = "redis://localhost:6379/0"
    object_store_path: str = "./data/objects"
    workspaces_root: str = "./data/workspaces"
    skills_root: str = "./data/skills"

    # --- identity (PingID / OIDC) ----------------------------------------------------------
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_redirect_uri: str = "http://localhost:8000/v1/auth/callback"
    oidc_scopes: str = "openid profile email groups"
    oidc_groups_claim: str = "groups"
    oidc_token_validation: Literal["jwks", "introspection"] = "jwks"
    oidc_introspection_endpoint: str | None = None
    auth_dev_bypass: bool = True  # local dev login without PingID (disabled when env=prod)
    role_group_map_json: str = (
        '{"cw-org-admins":"org_admin","cw-workspace-admins":"workspace_admin",'
        '"cw-team-leads":"team_lead","cw-auditors":"auditor","cw-developers":"developer"}'
    )

    # --- model provider (ILIAD) ------------------------------------------------------------
    model_provider: Literal["iliad_anthropic", "iliad_openai_compat", "mock"] = "mock"
    iliad_base_url: str | None = None  # ANTHROPIC_BASE_URL root, e.g. https://iliad.internal
    iliad_auth_token: str | None = None
    iliad_custom_headers: str | None = None  # "k: v,k2: v2"
    iliad_disable_experimental_betas: bool = False
    iliad_ca_cert_path: str | None = None
    claude_agent_model: str = "claude-opus-5"
    litellm_base_url: str | None = None
    litellm_api_key: str | None = None

    # --- orchestration ---------------------------------------------------------------------
    agent_runtime: Literal["agent_sdk", "deep_agents", "mock"] = "agent_sdk"
    default_permission_mode: Literal["default", "plan", "acceptEdits", "dontAsk"] = "default"
    max_concurrent_runs_global: int = 8
    max_concurrent_runs_per_user: int = 2
    default_max_budget_usd: float = 2.0
    approval_timeout_seconds: int = 60 * 30
    event_retention_seconds: int = 60 * 60 * 24

    # --- sandbox ---------------------------------------------------------------------------
    sandbox_backend: Literal["none", "docker"] = "none"
    sandbox_image: str = "cowork-sandbox:latest"
    sandbox_cpu: float = 1.0
    sandbox_memory: str = "1g"
    sandbox_disk: str = "5g"
    sandbox_egress_proxy: str | None = None  # http://egress-proxy:3128
    sandbox_egress_allowlist: str = ""  # comma-separated hosts, ILIAD always allowed

    # --- security --------------------------------------------------------------------------
    kms_master_key_b64: str | None = None  # 32-byte base64; envelope encryption root
    audit_hmac_key_b64: str | None = None
    rate_limit_per_minute: int = 240
    embeddings_dim: int = 1536
    embedding_provider: Literal["hash", "openai_compat"] = "hash"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def dev_login_enabled(self) -> bool:
        return self.auth_dev_bypass and not self.is_prod


@lru_cache
def get_settings() -> Settings:
    return Settings()
