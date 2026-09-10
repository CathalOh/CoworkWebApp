from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin


class Connector(UUIDMixin, TimestampMixin, Base):
    """Org-approved MCP connector catalog entry."""

    __tablename__ = "connectors"
    name: Mapped[str] = mapped_column(String(64), unique=True)  # used as the MCP server name => mcp__<name>__<tool>
    display_name: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    transport: Mapped[str] = mapped_column(String(16))  # http|sse|stdio|sdk
    url: Mapped[str | None] = mapped_column(Text)
    command: Mapped[dict[str, Any] | None] = mapped_column()  # {"command": ..., "args": [...], "env": {...}}
    auth_type: Mapped[str] = mapped_column(String(16), default="none")  # none|oauth|static_header
    oauth: Mapped[dict[str, Any] | None] = mapped_column()  # {authorization_endpoint, token_endpoint, client_id, scopes[], resource, dcr}
    required_scopes: Mapped[list[Any] | None] = mapped_column()
    risk_class: Mapped[str] = mapped_column(String(16), default="medium")  # low|medium|high
    allowed_tools: Mapped[list[Any] | None] = mapped_column()  # ["mcp__x__*"]
    denied_tools: Mapped[list[Any] | None] = mapped_column()
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    team_ids: Mapped[list[Any] | None] = mapped_column()  # null => org-wide
    egress_hosts: Mapped[list[Any] | None] = mapped_column()


class ConnectorCredential(UUIDMixin, TimestampMixin, Base):
    """Per-user token, envelope encrypted (DEK wrapped by master key)."""

    __tablename__ = "connector_credentials"
    __table_args__ = (UniqueConstraint("user_id", "connector_id", name="uq_connector_credentials_user_connector"),)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connector_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("connectors.id", ondelete="CASCADE"), index=True)
    enc_token: Mapped[bytes] = mapped_column(LargeBinary)
    enc_refresh_token: Mapped[bytes | None] = mapped_column(LargeBinary)
    enc_dek: Mapped[bytes] = mapped_column(LargeBinary)
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    token_type: Mapped[str] = mapped_column(String(32), default="Bearer")
    scopes: Mapped[list[Any] | None] = mapped_column()
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="connected")  # connected|needs-auth|revoked


class OAuthState(UUIDMixin, TimestampMixin, Base):
    """Pending OAuth 2.1 + PKCE authorization (server-side; the SDK will not run this flow)."""

    __tablename__ = "oauth_states"
    state: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    connector_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("connectors.id", ondelete="CASCADE"))
    code_verifier: Mapped[str] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(Text)
    resource: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
