"""End-to-end tests for the mock ILIAD / MCP / OAuth / OIDC server, run in-process against the ASGI app.

    pip install -r requirements.txt && pytest -q
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
import pytest
from jose import jwt

import oauth_as
import oidc
from server import app

BASE = "http://localhost:9100"
AUTH = {"Authorization": "Bearer mock", "anthropic-version": "2023-06-01"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    oauth_as.reset()
    oidc.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as c:
        yield c


def pkce() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def msg(text: str, **extra) -> dict:
    return {"model": "claude-opus-5", "max_tokens": 256, "messages": [{"role": "user", "content": text}], **extra}


CALC_TOOL = {"name": "mcp__calc__add", "description": "add", "input_schema": {"type": "object", "properties": {
    "a": {"type": "number"}, "b": {"type": "number"}}}}
WRITE_TOOL = {"name": "Write", "description": "write", "input_schema": {"type": "object", "properties": {
    "file_path": {"type": "string"}, "content": {"type": "string"}}}}


# ------------------------------------------------------------------------------------------------ Anthropic API
@pytest.mark.anyio
async def test_models_and_auth(client):
    r = await client.get("/v1/models")  # open: used as the compose/backend health probe
    assert r.status_code == 200
    assert [m["id"] for m in r.json()["data"]] == ["claude-opus-5", "claude-sonnet-5"]
    assert (await client.post("/v1/messages", json=msg("hi"))).status_code == 401
    assert (await client.post("/v1/messages", json=msg("hi"), headers={"x-api-key": "k"})).status_code == 200


@pytest.mark.anyio
async def test_messages_non_streaming(client):
    r = await client.post("/v1/messages", json=msg("Hello there", system="You are helpful", metadata={"user_id": "u1"},
                                                    unknown_field=1), headers={**AUTH, "anthropic-beta": "prompt-caching-2024-07-31"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["type"] == "message" and m["role"] == "assistant" and m["model"] == "claude-opus-5"
    assert m["id"].startswith("msg_mock_")
    assert m["content"] == [{"type": "text", "text": "Mock ILIAD reply: Hello there"}]
    assert m["stop_reason"] == "end_turn" and m["stop_sequence"] is None
    assert set(m["usage"]) == {"input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"}
    assert m["usage"]["output_tokens"] == 5 and m["usage"]["input_tokens"] > 0


@pytest.mark.anyio
async def test_messages_streaming(client):
    r = await client.post("/v1/messages", json=msg("Hello streaming world, how are you today", stream=True), headers=AUTH)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "message_start" and names[1] == "ping"
    assert names[2] == "content_block_start" and names[-3] == "content_block_stop"
    assert names[-2] == "message_delta" and names[-1] == "message_stop"
    assert all(e == "content_block_delta" for e in names[3:-3]) and len(names[3:-3]) >= 2
    start = events[0][1]
    assert start["message"]["role"] == "assistant" and start["message"]["content"] == []
    assert events[2][1]["content_block"] == {"type": "text", "text": ""}
    text = "".join(d["delta"]["text"] for e, d in events if e == "content_block_delta")
    assert text == "Mock ILIAD reply: Hello streaming world, how are you today"
    delta = events[-2][1]
    assert delta["delta"] == {"stop_reason": "end_turn", "stop_sequence": None}
    assert delta["usage"]["output_tokens"] == len(text.split())
    for e, d in events:
        assert d["type"] == e


@pytest.mark.anyio
async def test_tool_use_round_trip_streaming(client):
    body = msg("Please use the calculator to add 2 and 3", tools=[CALC_TOOL], stream=True)
    events = parse_sse((await client.post("/v1/messages", json=body, headers=AUTH)).text)
    starts = [d for e, d in events if e == "content_block_start"]
    assert starts[0]["content_block"]["type"] == "tool_use" and starts[0]["content_block"]["name"] == "mcp__calc__add"
    partial = "".join(d["delta"]["partial_json"] for e, d in events if e == "content_block_delta")
    assert json.loads(partial) == {"a": 2, "b": 3}
    assert [d for e, d in events if e == "message_delta"][0]["delta"]["stop_reason"] == "tool_use"
    tool_use_id = starts[0]["content_block"]["id"]

    # second turn: feed the tool result back
    body["messages"] += [
        {"role": "assistant", "content": [{"type": "tool_use", "id": tool_use_id, "name": "mcp__calc__add", "input": {"a": 2, "b": 3}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": [{"type": "text", "text": "5"}]}]},
    ]
    body["stream"] = False
    m = (await client.post("/v1/messages", json=body, headers=AUTH)).json()
    assert m["content"] == [{"type": "text", "text": "The result is 5"}] and m["stop_reason"] == "end_turn"


@pytest.mark.anyio
async def test_write_file_and_thinking(client):
    body = msg("Now think hard and write a file for me", tools=[WRITE_TOOL], system="Working directory: /ws/session-1\n")
    m = (await client.post("/v1/messages", json=body, headers=AUTH)).json()
    assert m["content"][0]["type"] == "thinking" and m["content"][0]["thinking"] == "Let me think..."
    assert m["content"][1] == {"type": "tool_use", "id": m["content"][1]["id"], "name": "Write",
                               "input": {"file_path": "/ws/session-1/notes.md", "content": "hello from mock"}}
    assert m["stop_reason"] == "tool_use"
    body["messages"] += [{"role": "assistant", "content": m["content"]},
                         {"role": "user", "content": [{"type": "tool_result", "tool_use_id": m["content"][1]["id"], "content": "ok"}]}]
    m2 = (await client.post("/v1/messages", json=body, headers=AUTH)).json()
    assert m2["content"] == [{"type": "text", "text": "Wrote the file."}]

    # streamed thinking uses thinking_delta then signature_delta
    events = parse_sse((await client.post("/v1/messages", json=msg("think about it", stream=True), headers=AUTH)).text)
    kinds = [d["delta"]["type"] for e, d in events if e == "content_block_delta"]
    assert kinds[0] == "thinking_delta" and "signature_delta" in kinds and kinds[-1] == "text_delta"


@pytest.mark.anyio
async def test_error_scenarios(client):
    r = await client.post("/v1/messages", json=msg("please error500"), headers=AUTH)
    assert r.status_code == 500 and r.json() == {"type": "error", "error": {"type": "api_error", "message": "mock outage"}}
    r = await client.post("/v1/messages", json=msg("ratelimit me", stream=True), headers=AUTH)
    assert r.status_code == 429 and r.headers["retry-after"] == "1" and r.json()["error"]["type"] == "rate_limit_error"


# ------------------------------------------------------------------------------------------------ MCP + OAuth
def rpc(id_, method, params=None):
    return {"jsonrpc": "2.0", "id": id_, "method": method, **({"params": params} if params is not None else {})}


async def oauth_login(client, *, client_id: str, redirect_uri: str, resource: str | None = "http://localhost:9100/mcp") -> dict:
    verifier, challenge = pkce()
    state = secrets.token_urlsafe(8)
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": redirect_uri, "state": state, "scope": "drive.read",
         "code_challenge": challenge, "code_challenge_method": "S256", "auto_approve": "1"}
    if resource:
        q["resource"] = resource
    r = await client.get("/oauth/authorize", params=q)
    assert r.status_code == 302, r.text
    loc = urlparse(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == redirect_uri
    qs = parse_qs(loc.query)
    assert qs["state"] == [state] and "error" not in qs
    data = {"grant_type": "authorization_code", "code": qs["code"][0], "redirect_uri": redirect_uri, "client_id": client_id,
            "code_verifier": verifier}
    if resource:
        data["resource"] = resource
    r = await client.post("/oauth/token", data=data, headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.anyio
async def test_mcp_requires_oauth_then_full_pkce_dance(client):
    # 1. unauthenticated -> 401 pointing at the protected-resource metadata
    r = await client.post("/mcp", json=rpc(1, "initialize"))
    assert r.status_code == 401
    assert 'resource_metadata="http://localhost:9100/.well-known/oauth-protected-resource/mcp"' in r.headers["www-authenticate"]
    assert (await client.get("/mcp")).status_code == 405

    # 2. RFC 9728 -> RFC 8414 discovery (same path as backend/app/mcp_host/oauth.discover)
    prm = (await client.get("/.well-known/oauth-protected-resource/mcp")).json()
    assert prm == {**prm, "resource": "http://localhost:9100/mcp", "authorization_servers": ["http://localhost:9100"]}
    assert (await client.get("/.well-known/oauth-protected-resource")).json()["resource"] == prm["resource"]
    meta = (await client.get("/.well-known/oauth-authorization-server")).json()
    assert meta["code_challenge_methods_supported"] == ["S256"]
    assert "authorization_code" in meta["grant_types_supported"] and meta["response_types_supported"] == ["code"]
    for k in ("authorization_endpoint", "token_endpoint", "registration_endpoint"):
        assert meta[k].startswith("http://localhost:9100/oauth/")

    # 3. dynamic client registration (payload identical to oauth.register_client)
    redirect_uri = "http://localhost:8000/v1/connectors/oauth/callback"
    r = await client.post(meta["registration_endpoint"], json={
        "client_name": "Cowork backbone (mock-drive)", "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"], "token_endpoint_auth_method": "none"})
    assert r.status_code == 201, r.text
    client_id = r.json()["client_id"]

    # 4. authorize (auto_approve) + token exchange
    tok = await oauth_login(client, client_id=client_id, redirect_uri=redirect_uri)
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 3600 and tok["scope"] == "drive.read"
    assert tok["access_token"] and tok["refresh_token"]

    # 5. refresh rotates both tokens; the old refresh token is dead
    r = await client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"],
                                                "client_id": client_id, "resource": "http://localhost:9100/mcp"})
    assert r.status_code == 200, r.text
    tok2 = r.json()
    assert tok2["access_token"] != tok["access_token"] and tok2["refresh_token"] != tok["refresh_token"]
    r = await client.post("/oauth/token", data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": client_id})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
    old = {"Authorization": f"Bearer {tok['access_token']}"}
    assert (await client.post("/mcp", json=rpc(1, "initialize"), headers=old)).status_code == 401

    # 6. MCP session with the fresh token
    h = {"Authorization": f"Bearer {tok2['access_token']}", "Accept": "application/json, text/event-stream"}
    r = await client.post("/mcp", json=rpc(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                                            "clientInfo": {"name": "test", "version": "0"}}), headers=h)
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/json")
    res = r.json()["result"]
    assert res["protocolVersion"] == "2025-06-18" and res["capabilities"] == {"tools": {}} and res["serverInfo"]["name"] == "mock-drive"
    r = await client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}, headers=h)
    assert r.status_code == 202 and r.content == b""

    tools = (await client.post("/mcp", json=rpc(2, "tools/list"), headers=h)).json()["result"]["tools"]
    assert [t["name"] for t in tools] == ["list_files", "read_file"]
    assert tools[1]["inputSchema"]["properties"]["path"]["type"] == "string"

    r = (await client.post("/mcp", json=rpc(3, "tools/call", {"name": "list_files", "arguments": {}}), headers=h)).json()
    assert r["id"] == 3 and r["result"]["content"][0]["text"].split("\n") == ["metrics.xlsx", "narrative.docx"]
    r = (await client.post("/mcp", json=rpc(4, "tools/call", {"name": "read_file", "arguments": {"path": "metrics.xlsx"}}), headers=h)).json()
    assert r["result"]["content"] == [{"type": "text", "text": "contents of metrics.xlsx"}] and r["result"]["isError"] is False
    r = (await client.post("/mcp", json=rpc(5, "tools/call", {"name": "nope", "arguments": {}}), headers=h)).json()
    assert r["error"]["code"] == -32602 and "result" not in r
    r = (await client.post("/mcp", json=rpc(6, "resources/list"), headers=h)).json()
    assert r["error"]["code"] == -32601


@pytest.mark.anyio
async def test_oauth_seeded_client_consent_page_and_validation(client):
    """The seed row uses the pre-registered client `cowork-backbone` with the compose-internal resource URL."""
    redirect_uri = "http://localhost:8000/v1/connectors/oauth/callback"
    tok = await oauth_login(client, client_id="cowork-backbone", redirect_uri=redirect_uri, resource="http://mock-iliad:9100/mcp")
    assert tok["access_token"]

    # consent page: Approve form + Deny link
    verifier, challenge = pkce()
    q = {"response_type": "code", "client_id": "cowork-backbone", "redirect_uri": redirect_uri, "state": "s1",
         "scope": "drive.read", "code_challenge": challenge, "code_challenge_method": "S256"}
    r = await client.get("/oauth/authorize", params=q)
    assert r.status_code == 200 and "Approve" in r.text and "Deny" in r.text
    req_id = r.text.split("name='req_id' value='")[1].split("'")[0]
    r = await client.post("/oauth/authorize/decision", data={"req_id": req_id, "decision": "approve"})
    assert r.status_code == 302
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    # wrong verifier -> invalid_grant, and the code is single-use
    r = await client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                                "client_id": "cowork-backbone", "code_verifier": "wrong" * 10})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
    r = await client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                                "client_id": "cowork-backbone", "code_verifier": verifier})
    assert r.status_code == 400

    # deny -> access_denied
    r = await client.get("/oauth/authorize", params={**q, "state": "s2"})
    req_id = r.text.split("name='req_id' value='")[1].split("'")[0]
    r = await client.get("/oauth/authorize/decision", params={"req_id": req_id, "decision": "deny"})
    assert r.status_code == 302 and parse_qs(urlparse(r.headers["location"]).query) == {"error": ["access_denied"], "state": ["s2"]}

    # unknown client / missing PKCE
    assert (await client.get("/oauth/authorize", params={**q, "client_id": "nobody"})).status_code == 400
    r = await client.get("/oauth/authorize", params={k: v for k, v in q.items() if k != "code_challenge"})
    assert r.status_code == 302 and "error=invalid_request" in r.headers["location"]


# ------------------------------------------------------------------------------------------------ OIDC
@pytest.mark.anyio
async def test_oidc_discovery_pkce_login_and_id_token(client):
    doc = (await client.get("/oidc/.well-known/openid-configuration")).json()
    assert doc["issuer"] == "http://localhost:9100/oidc"
    for k in ("authorization_endpoint", "token_endpoint", "jwks_uri", "end_session_endpoint", "introspection_endpoint"):
        assert doc[k].startswith(doc["issuer"] + "/")
    assert doc["code_challenge_methods_supported"] == ["S256"]
    jwks = (await client.get(doc["jwks_uri"])).json()
    assert jwks["keys"][0]["kid"] == "mock-1" and jwks["keys"][0]["kty"] == "RSA"

    verifier, challenge = pkce()
    nonce, state = secrets.token_urlsafe(8), secrets.token_urlsafe(8)
    redirect_uri = "http://localhost:8000/v1/auth/callback"
    q = {"response_type": "code", "client_id": "cowork-backbone", "redirect_uri": redirect_uri, "scope": "openid profile email groups",
         "state": state, "nonce": nonce, "code_challenge": challenge, "code_challenge_method": "S256"}
    # login form renders...
    r = await client.get(doc["authorization_endpoint"], params=q)
    assert r.status_code == 200 and "name='email'" in r.text and "cw-org-admins" in r.text
    # ...and the auto shortcut skips it
    r = await client.get(doc["authorization_endpoint"], params={**q, "auto": "1", "email": "lead@example.com", "groups": "cw-team-leads, cw-developers"})
    assert r.status_code == 302
    qs = parse_qs(urlparse(r.headers["location"]).query)
    assert qs["state"] == [state]

    r = await client.post(doc["token_endpoint"], data={"grant_type": "authorization_code", "code": qs["code"][0], "redirect_uri": redirect_uri,
                                                       "client_id": "cowork-backbone", "code_verifier": verifier})
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok["token_type"] == "Bearer" and tok["expires_in"] == 3600 and tok["refresh_token"]

    # same validation as backend/app/auth/oidc.validate_id_token
    header = jwt.get_unverified_header(tok["id_token"])
    assert header["kid"] == "mock-1" and header["alg"] == "RS256"
    key = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
    claims = jwt.decode(tok["id_token"], key, algorithms=["RS256"], audience="cowork-backbone", issuer=doc["issuer"])
    assert claims["sub"] == "mock|lead@example.com" and claims["email"] == "lead@example.com"
    assert claims["groups"] == ["cw-team-leads", "cw-developers"] and claims["nonce"] == nonce
    assert claims["exp"] - claims["iat"] == 3600 and claims["name"] == "Lead"

    intro = (await client.post(doc["introspection_endpoint"], data={"token": tok["access_token"]},
                               auth=("cowork-backbone", ""))).json()
    assert intro["active"] is True and intro["sub"] == claims["sub"] and intro["groups"] == claims["groups"]
    assert (await client.post(doc["introspection_endpoint"], data={"token": "bogus"})).json() == {"active": False}
    ui = (await client.get(doc["userinfo_endpoint"], headers={"Authorization": f"Bearer {tok['access_token']}"})).json()
    assert ui["email"] == "lead@example.com"

    # refresh rotates and issues a fresh id_token; the old refresh token is dead
    r = await client.post(doc["token_endpoint"], data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"]},
                          auth=("cowork-backbone", "secret"))
    assert r.status_code == 200 and r.json()["access_token"] != tok["access_token"]
    assert jwt.decode(r.json()["id_token"], jwks, algorithms=["RS256"], audience="cowork-backbone")["email"] == "lead@example.com"
    r = await client.post(doc["token_endpoint"], data={"grant_type": "refresh_token", "refresh_token": tok["refresh_token"], "client_id": "cowork-backbone"})
    assert r.status_code == 400

    # PKCE is enforced when a challenge was supplied
    r = await client.get(doc["authorization_endpoint"], params={**q, "auto": "1"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    r = await client.post(doc["token_endpoint"], data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
                                                       "client_id": "cowork-backbone", "code_verifier": "not-the-verifier"})
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"

    # RP-initiated logout
    r = await client.get(doc["end_session_endpoint"], params={"post_logout_redirect_uri": "http://localhost:5173/", "client_id": "cowork-backbone",
                                                              "id_token_hint": tok["id_token"]})
    assert r.status_code == 302 and r.headers["location"].startswith("http://localhost:5173/")


@pytest.mark.anyio
async def test_index_and_health(client):
    assert (await client.get("/healthz")).json() == {"ok": True}
    idx = (await client.get("/")).json()
    assert "/v1/messages" in idx["anthropic"] and "/mcp" in idx["mcp"]
