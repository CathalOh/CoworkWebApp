from __future__ import annotations

import asyncio
import json

from app.tasks.queue import wait_inline
from tests.conftest import login


async def read_sse(client, run_id: str, after: int = 0, max_events: int = 200) -> list[dict]:
    events = []
    async with client.stream("GET", f"/v1/runs/{run_id}/events", headers={"Last-Event-ID": str(after)}, timeout=20) as r:
        assert r.status_code == 200
        buf = ""
        async for chunk in r.aiter_text():
            buf += chunk.replace("\r\n", "\n")
            while "\n\n" in buf:
                frame, buf = buf.split("\n\n", 1)
                data = [line[5:].strip() for line in frame.splitlines() if line.startswith("data:")]
                if data:
                    ev = json.loads(data[0])
                    events.append(ev)
                    if ev["type"] in ("result", "error", "interrupted") or (ev["type"] == "status" and ev["data"].get("kind") == "closed"):
                        return events
            if len(events) >= max_events:
                break
    return events


async def test_meta_and_auth_flow(client):
    r = await client.get("/v1/meta")
    assert r.status_code == 200 and r.json()["dev_login"] is True
    r = await client.get("/v1/users/me")
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    me = await login(client)
    assert "user" in me["roles"] and me["csrf_token"]
    r = await client.get("/v1/users/me")
    assert r.status_code == 200
    # CSRF required on mutating calls
    bad = client.headers.pop("X-CSRF-Token")
    r = await client.post("/v1/conversations", json={})
    assert r.status_code == 403
    client.headers["X-CSRF-Token"] = bad
    r = await client.post("/v1/auth/logout")
    assert r.status_code == 204
    r = await client.get("/v1/users/me")
    assert r.status_code == 401


async def test_chat_stream_resume_and_persistence(user_client):
    c = user_client
    r = await c.post("/v1/conversations", json={"title": "t1"})
    assert r.status_code == 201, r.text
    conv = r.json()
    r = await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "hello there slow"})
    assert r.status_code == 202, r.text
    run = r.json()
    events = await read_sse(c, run["id"])
    types = [e["type"] for e in events]
    assert types[0] == "run_started" and types[-1] == "result"
    assert any(e["type"] == "assistant_text" for e in events)
    seqs = [e["seq"] for e in events]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
    # resume from the middle: no duplicates, no restart
    mid = seqs[len(seqs) // 2]
    await wait_inline()
    resumed = await read_sse(c, run["id"], after=mid)
    assert all(e["seq"] > mid for e in resumed) and resumed[-1]["type"] == "result"
    # persisted messages + run status + cost
    r = await c.get(f"/v1/conversations/{conv['id']}/messages")
    msgs = r.json()
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert msgs[1]["blocks"][0]["content"]["text"].startswith("Echo from mock runtime")
    r = await c.get(f"/v1/runs/{run['id']}")
    assert r.json()["status"] == "succeeded" and r.json()["total_cost_usd"] is not None
    # concurrent run on same conversation rejected while active? (already finished -> allowed)
    r = await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "second"})
    assert r.status_code == 202
    await read_sse(c, r.json()["id"])
    await wait_inline()


async def test_approval_flow_allow_and_deny_and_timeout_audit(user_client, admin_client):
    c = user_client
    conv = (await c.post("/v1/conversations", json={"title": "approvals", "permission_mode": "acceptEdits"})).json()
    # deletion always prompts even in acceptEdits
    run = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "please delete the old file"})).json()

    async def approver():
        for _ in range(100):
            await asyncio.sleep(0.05)
            aps = (await c.get(f"/v1/runs/{run['id']}/approvals")).json()
            pending = [a for a in aps if a["decision"] is None]
            if pending:
                rr = await c.post(f"/v1/runs/{run['id']}/approvals", json={"tool_use_id": pending[0]["tool_use_id"], "decision": "allow"})
                assert rr.status_code == 202
                return pending[0]
        raise AssertionError("no approval request appeared")

    task = asyncio.create_task(approver())
    events = await read_sse(c, run["id"])
    pending = await task
    assert pending["tool_name"] == "Bash"
    req = next(e for e in events if e["type"] == "approval_request")
    assert req["data"]["category"] == "delete"
    await wait_inline()
    assert any(e["type"] == "approval_decided" and e["data"]["decision"] == "allow" for e in events)
    r = await c.get(f"/v1/runs/{run['id']}/approvals")
    aps = r.json()
    assert len(aps) == 1 and aps[0]["decision"] == "allow" and aps[0]["tool_name"] == "Bash"
    # audit rows exist for request + decision (admin view)
    r = await admin_client.get("/v1/admin/audit", params={"entity_id": run["id"]})
    actions = {i["action"] for i in r.json()["items"]}
    assert {"tool.approval_requested", "tool.approved", "run.created", "run.succeeded"} <= actions
    # timeout => deny
    run2 = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "write a file please"})).json()
    ev2 = await read_sse(c, run2["id"])
    # acceptEdits auto-allows Write (no approval) -> tool_result ok
    assert any(e["type"] == "tool_result" and not e["data"].get("is_error") for e in ev2)
    await wait_inline()
    conv2 = (await c.post("/v1/conversations", json={"title": "manual"})).json()
    run3 = (await c.post(f"/v1/conversations/{conv2['id']}/messages", json={"content": "write a file please"})).json()
    ev3 = await read_sse(c, run3["id"])  # nobody answers; 5s timeout -> deny
    await wait_inline()
    assert any(e["type"] == "approval_decided" and e["data"]["decision"] == "deny" for e in ev3)
    r = await admin_client.get("/v1/admin/audit", params={"entity_id": run3["id"], "action": "tool.denied"})
    assert r.json()["items"] and r.json()["items"][0]["after"]["reason"] == "timeout"


async def test_interrupt(user_client):
    c = user_client
    conv = (await c.post("/v1/conversations", json={"title": "int"})).json()
    run = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "slow " + "word " * 30})).json()
    await asyncio.sleep(0.3)
    r = await c.post(f"/v1/runs/{run['id']}/interrupt")
    assert r.status_code == 202
    ev = await read_sse(c, run["id"])
    await wait_inline()
    assert ev[-1]["type"] == "interrupted"
    r = await c.get(f"/v1/runs/{run['id']}")
    assert r.json()["status"] == "cancelled"


async def test_rbac_and_admin_endpoints(user_client, admin_client):
    r = await user_client.get("/v1/admin/audit")
    assert r.status_code == 403
    r = await admin_client.get("/v1/admin/audit/verify")
    assert r.status_code == 200 and r.json()["ok"] is True
    r = await admin_client.get("/v1/admin/usage", params={"group_by": "user"})
    assert r.status_code == 200
    r = await admin_client.post("/v1/admin/capabilities", json={"key": "new_runs", "enabled": False, "reason": "drain"})
    assert r.status_code == 200
    conv = (await user_client.post("/v1/conversations", json={"title": "drained"})).json()
    r = await user_client.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "hi"})
    assert r.status_code == 503
    await admin_client.post("/v1/admin/capabilities", json={"key": "new_runs", "enabled": True})
    r = await user_client.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "hi"})
    assert r.status_code == 202
    await read_sse(user_client, r.json()["id"])
    await wait_inline()
    r = await admin_client.get("/v1/admin/llm-logs")
    assert r.status_code == 200 and r.json()["items"]


async def test_projects_files_sharing_and_context_manifest(user_client, admin_client):
    c = user_client
    me = (await c.get("/v1/users/me")).json()
    team_id = me["teams"][0]
    p = (await c.post("/v1/projects", json={"name": "P1", "instructions": "Always answer in bullet points."})).json()
    files = {"file": ("notes.txt", b"quarterly numbers", "text/plain")}
    r = await c.post(f"/v1/projects/{p['id']}/files", files=files)
    assert r.status_code == 201, r.text
    r = await c.post(f"/v1/projects/{p['id']}/files", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415
    r = await c.post(f"/v1/projects/{p['id']}/shares", json={"team_id": team_id, "access": "read"})
    assert r.status_code == 204
    conv = (await c.post("/v1/conversations", json={"title": "in project", "project_id": p["id"]})).json()
    run = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "summarize"})).json()
    await read_sse(c, run["id"])
    await wait_inline()
    r = await admin_client.get("/v1/admin/runs")
    assert any(x["id"] == run["id"] for x in r.json())
    # the lead (same team) can read the shared project
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=c._transport.app), base_url="http://test") as lead:
        await login(lead, "lead@example.com", ["team_lead"])
        r = await lead.get(f"/v1/projects/{p['id']}")
        assert r.status_code == 200
        r = await lead.patch(f"/v1/projects/{p['id']}", json={"name": "renamed"})
        assert r.status_code == 403  # read-only share
    async with AsyncClient(transport=ASGITransport(app=c._transport.app), base_url="http://test") as other:
        await login(other, "stranger@example.com", ["user"])
        r = await other.get(f"/v1/projects/{p['id']}")
        assert r.status_code == 403
        r = await other.get(f"/v1/conversations/{conv['id']}")
        assert r.status_code == 403


async def test_connectors_catalog_and_mcp_status(user_client):
    c = user_client
    r = await c.get("/v1/connectors")
    cat = {x["name"]: x for x in r.json()}
    assert cat["mock-drive"]["status"] == "needs-auth" and cat["calc"]["status"] == "connected"
    conv = (await c.post("/v1/conversations", json={"title": "mcp", "connector_ids": [cat["mock-drive"]["id"], cat["calc"]["id"]]})).json()
    run = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "list files"})).json()
    await read_sse(c, run["id"])
    await wait_inline()
    r = await c.get(f"/v1/runs/{run['id']}")
    assert r.json()["status"] == "succeeded"
    # run continued without the un-authorized connector; manifest records needs-auth
    import uuid

    from app.db import db_session
    from app.models import Run

    async with db_session() as db:
        row = await db.get(Run, uuid.UUID(run["id"]))
        st = {s["name"]: s["status"] for s in row.config["context_manifest"]["connectors"]}
        assert st["mock-drive"] == "needs-auth" and st["calc"] == "connected"
        assert "mock-drive" not in row.config["mcp_servers"] and "calc" in row.config["mcp_servers"]


async def test_skills_tasks_schedules_artifacts_memory_search(user_client, admin_client):
    c = user_client
    skill_md = "---\nname: my-skill\ndescription: test skill\nallowed-tools: [Read, mcp__calc__*]\n---\nDo the thing."
    r = await c.post("/v1/skills/import", json={"skill_md": skill_md, "scope": "user"})
    assert r.status_code == 201 and r.json()["allowed_tools"] == ["Read", "mcp__calc__*"]
    r = await c.get("/v1/skills")
    assert {s["name"] for s in r.json()} >= {"my-skill", "quarterly-board-deck"}
    t = (await c.post("/v1/tasks", json={"name": "nightly", "prompt": "write a file report", "config": {"permission_mode": "acceptEdits"}})).json()
    r = await c.post("/v1/schedules", json={"task_id": t["id"], "cron": "0 3 * * *", "timezone": "Europe/Dublin"})
    assert r.status_code == 201 and r.json()["next_run"]
    r = await c.post("/v1/schedules", json={"task_id": t["id"], "cron": "bad cron"})
    assert r.status_code == 400
    r = await c.post(f"/v1/tasks/{t['id']}/run")
    assert r.status_code == 202
    run_id = r.json()["run_id"]
    ev = await read_sse(c, run_id)
    await wait_inline()
    assert ev[-1]["type"] == "result"
    r = await c.get(f"/v1/tasks/{t['id']}/runs")
    assert r.json()[0]["status"] == "succeeded"
    # scheduler fires due schedules
    import uuid as _u
    from datetime import timedelta

    from app.db import db_session
    from app.models import Schedule
    from app.models.base import utcnow
    from app.tasks.worker import scheduler_tick

    async with db_session() as db:
        for s in (await db.execute(__import__("sqlalchemy").select(Schedule).where(Schedule.task_id == _u.UUID(t["id"])))).scalars().all():
            s.next_run = utcnow() - timedelta(seconds=1)
        await db.commit()
    n = await scheduler_tick({})
    assert n >= 1
    await wait_inline()
    r = await c.get(f"/v1/tasks/{t['id']}/runs")
    assert len(r.json()) >= 2
    # artifacts
    a = (await c.post("/v1/artifacts", json={"kind": "html", "title": "hello", "content": "<h1>hi</h1>"})).json()
    r = await c.get(f"/v1/artifacts/{a['id']}/render")
    assert r.status_code == 200 and "frame-ancestors" in r.headers["content-security-policy"] and "<h1>hi</h1>" in r.text
    r = await c.post(f"/v1/artifacts/{a['id']}/versions", json={"content": "<h1>v2</h1>"})
    assert r.json()["version"] == 2
    r = await c.post("/v1/artifacts", json={"kind": "html", "title": "big", "content": "x" * (20 * 1024 * 1024 + 1)})
    assert r.status_code == 413
    live = (await c.post("/v1/artifacts", json={"kind": "html", "title": "live", "content": "<div id=x></div>",
                                                "live_source": {"tool": "calc.add", "args": {"a": 1, "b": 2}}})).json()
    r = await c.post(f"/v1/artifacts/{live['id']}/refresh")
    assert r.status_code == 200 and "__LIVE_DATA__" in r.json()["content"] and "3.0" in r.json()["content"]
    # memory + search
    r = await c.post("/v1/memory", json={"content": "I prefer spreadsheets over slide decks"})
    assert r.status_code == 201
    conv = (await c.post("/v1/conversations", json={"title": "memtest"})).json()
    run = (await c.post(f"/v1/conversations/{conv['id']}/messages", json={"content": "Remember that our team uses Europe/Dublin timezone"})).json()
    await read_sse(c, run["id"])
    await wait_inline()
    r = await c.get("/v1/search", params={"q": "Dublin timezone"})
    assert r.status_code == 200 and r.json()["items"]
    r = await c.get("/v1/memory")
    assert any("Dublin" in m["content"] for m in r.json())


async def test_bypass_permissions_rejected(user_client):
    c = user_client
    r = await c.post("/v1/conversations", json={"title": "x", "permission_mode": "bypassPermissions"})
    assert r.status_code == 422
    r = await c.post("/v1/tasks", json={"name": "t", "prompt": "p", "config": {"permission_mode": "bypassPermissions"}})
    assert r.status_code == 400


async def test_readyz_and_metrics(client):
    r = await client.get("/readyz")
    assert r.status_code == 200 and r.json()["ready"]
    r = await client.get("/metrics")
    assert r.status_code == 200
    r = await client.get("/healthz")
    assert "content-security-policy" in r.headers and r.headers["x-frame-options"] == "DENY"
