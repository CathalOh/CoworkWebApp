from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin, UUIDMixin

ROLE_NAMES = ("user", "team_lead", "workspace_admin", "org_admin", "auditor", "developer")


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    ping_subject: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="active")

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")
    memberships: Mapped[list[Membership]] = relationship(back_populates="user", lazy="selectin")

    @property
    def role_names(self) -> set[str]:
        return {r.name for r in self.roles} | {"user"}

    @property
    def team_ids(self) -> set[uuid.UUID]:
        return {m.team_id for m in self.memberships}


class Role(UUIDMixin, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(64), unique=True)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)


class Team(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(Text)
    members: Mapped[list[Membership]] = relationship(back_populates="team", lazy="selectin")


class Membership(Base):
    __tablename__ = "memberships"
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    team_role: Mapped[str] = mapped_column(String(32), default="member")  # member|lead
    team: Mapped[Team] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")
