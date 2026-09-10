"""Skills (SKILL.md) registry: rows in the DB, materialized per run into a session-scoped skills dir so the
agent loads them on demand via progressive disclosure (`.claude/skills/<name>/SKILL.md`)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Skill, User

_FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


def parse_skill_md(text: str) -> dict:
    m = _FM.match(text.strip())
    if not m:
        return {"name": None, "description": None, "allowed_tools": None, "body": text}
    fm, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in fm.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    tools = meta.get("allowed-tools")
    if tools:
        tools = [t.strip() for t in tools.strip("[]").split(",") if t.strip()]
    return {"name": meta.get("name"), "description": meta.get("description"), "allowed_tools": tools, "body": body.strip()}


def render_skill_md(s: Skill) -> str:
    lines = ["---", f"name: {s.name}", f"description: {s.description or ''}"]
    if s.allowed_tools:
        lines.append("allowed-tools: [" + ", ".join(s.allowed_tools) + "]")
    lines += ["---", s.body]
    return "\n".join(lines) + "\n"


async def visible_skills(db: AsyncSession, user: User) -> list[Skill]:
    team_ids = list(user.team_ids)
    q = select(Skill).where(Skill.enabled.is_(True)).where(
        or_(Skill.scope == "org", Skill.owner_id == user.id, Skill.team_id.in_(team_ids) if team_ids else False))
    return list((await db.execute(q)).scalars().all())


def materialize(skills: list[Skill], session_dir: Path) -> tuple[Path, list[str]]:
    """Write SKILL.md files as a session-local *plugin* (<session_dir>/.plugins/session-skills/skills/<name>/SKILL.md).

    Plugins are loaded explicitly via ClaudeAgentOptions.plugins, so skills reach the agent even with
    setting_sources=[] (which we keep for multi-tenant safety). Returns (plugin_dir, allowed_tools)."""
    import json

    root = session_dir / ".plugins" / "session-skills"
    (root / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (root / ".claude-plugin" / "plugin.json").write_text(json.dumps({"name": "session-skills", "version": "1.0.0",
                                                                      "description": "Skills selected for this session"}))
    tools: list[str] = []
    for s in skills:
        d = root / "skills" / re.sub(r"[^a-zA-Z0-9_-]", "-", s.name)
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(render_skill_md(s))
        tools.extend(s.allowed_tools or [])
    return root, sorted(set(tools))


async def get_skill_for(db: AsyncSession, skill_id: uuid.UUID, user: User) -> Skill | None:
    s = await db.get(Skill, skill_id)
    if not s:
        return None
    if s.scope == "org" or s.owner_id == user.id or (s.team_id and s.team_id in user.team_ids):
        return s
    return None
