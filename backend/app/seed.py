"""Seed: roles, a demo team, demo users, an approved in-process connector (calc), a mock remote OAuth connector,
one org skill, one plugin, one bundle. Idempotent. Run: python -m app.seed"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.db import db_session
from app.models import Connector, Membership, Plugin, ProjectBundle, Role, Skill, Team, User
from app.models.identity import ROLE_NAMES

SKILL_BODY = """When asked for a board deck: read the latest metrics xlsx, extract KPIs, generate a 10-slide pptx via python-pptx
using the corporate template in assets/template.pptx, and write it to the workspace exports/ folder.
Never delete source files. See references/KPIS.md for definitions."""


async def seed() -> None:
    async with db_session() as db:
        roles = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
        for n in ROLE_NAMES:
            if n not in roles:
                roles[n] = Role(name=n)
                db.add(roles[n])
        await db.flush()
        team = (await db.execute(select(Team).where(Team.name == "Demo Team"))).scalar_one_or_none()
        if not team:
            team = Team(name="Demo Team")
            db.add(team)
            await db.flush()
        users = {
            "admin@example.com": ("Org Admin", ["org_admin", "developer"], "lead"),
            "lead@example.com": ("Team Lead", ["team_lead"], "lead"),
            "user@example.com": ("Demo User", ["user"], "member"),
            "auditor@example.com": ("Auditor", ["auditor"], "member"),
        }
        for email, (name, rnames, trole) in users.items():
            u = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
            if not u:
                u = User(ping_subject=f"dev:{email}", email=email, display_name=name, roles=[roles[r] for r in rnames])
                db.add(u)
                await db.flush()
                db.add(Membership(team_id=team.id, user_id=u.id, team_role=trole))
            else:
                u.roles = [roles[r] for r in rnames]
        admin = (await db.execute(select(User).where(User.email == "admin@example.com"))).scalar_one()
        for name, row in {
            "calc": dict(display_name="Calculator (in-process)", description="Backbone custom tools example", transport="sdk", auth_type="none",
                         risk_class="low", approved=True, allowed_tools=["mcp__calc__*"]),
            "backbone": dict(display_name="Backbone utilities", description="current_time and friends", transport="sdk", auth_type="none",
                             risk_class="low", approved=True, allowed_tools=["mcp__backbone__*"]),
            "mock-drive": dict(display_name="Mock Drive (remote, OAuth)", description="Mock remote MCP server with OAuth 2.1 + PKCE",
                               transport="http", url="http://mock-iliad:9100/mcp", auth_type="oauth",
                               oauth={"authorization_endpoint": "http://localhost:9100/oauth/authorize", "token_endpoint": "http://mock-iliad:9100/oauth/token",
                                      "client_id": "cowork-backbone", "resource": "http://mock-iliad:9100/mcp"},
                               required_scopes=["drive.read"], risk_class="medium", approved=True, allowed_tools=["mcp__mock-drive__*"],
                               egress_hosts=["mock-iliad"]),
            "fs-local": dict(display_name="Filesystem (local stdio)", description="Runs inside the session sandbox; gated by the local_mcp org toggle",
                             transport="stdio", command={"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/ws"]},
                             auth_type="none", risk_class="high", approved=True, allowed_tools=["mcp__fs-local__read_file", "mcp__fs-local__list_directory"]),
        }.items():
            c = (await db.execute(select(Connector).where(Connector.name == name))).scalar_one_or_none()
            if not c:
                db.add(Connector(name=name, **row))
        if not (await db.execute(select(Skill).where(Skill.name == "quarterly-board-deck"))).scalar_one_or_none():
            db.add(Skill(name="quarterly-board-deck", description="Build a board deck from a metrics workbook and a narrative doc.",
                         body=SKILL_BODY, allowed_tools=["Read", "Write", "Bash", "mcp__mock-drive__*"], scope="org", owner_id=admin.id))
        if not (await db.execute(select(Plugin).where(Plugin.name == "office-docs"))).scalar_one_or_none():
            db.add(Plugin(name="office-docs", version="0.1.0", scope="org", approved=True, manifest={
                "description": "docx/pptx/xlsx generation skills",
                "skills": [{"name": "docx-report", "description": "Generate a Word report with python-docx.",
                            "body": "Use python-docx to build the document; save to exports/."},
                           {"name": "xlsx-model", "description": "Build a spreadsheet model with openpyxl.",
                            "body": "Use openpyxl; keep formulas live; save to exports/."}]}))
        if not (await db.execute(select(ProjectBundle).where(ProjectBundle.name == "finance-ops"))).scalar_one_or_none():
            db.add(ProjectBundle(name="finance-ops", owner_id=admin.id, manifest={
                "system_prompt": "You are the Finance Ops assistant. Prefer spreadsheets for numeric deliverables; cite the source file for every KPI.",
                "skills": ["quarterly-board-deck"], "plugins": ["office-docs"], "connectors": [], "ui_slots": ["kpi-panel"],
                "permission_defaults": {"permission_mode": "default"}}))
        await db.commit()
    print("seeded")


if __name__ == "__main__":
    asyncio.run(seed())
