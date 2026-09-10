from __future__ import annotations

import uuid

from sqlalchemy import select

from app.db import db_session
from app.models import AuditEvent
from app.security.audit import compute_row_hash, record_audit, verify_chain


async def test_audit_chain_verifies_and_detects_tamper(_schema):
    async with db_session() as db:
        a = await record_audit(db, action="test.one", actor_id=uuid.uuid4(), after={"x": 1})
        b = await record_audit(db, action="test.two", actor_id=None, actor_type="system", after={"y": [1, 2]})
        await db.commit()
        assert b.prev_hash == a.row_hash
        res = await verify_chain(db, a.stream_key)
        assert res["ok"] and res["checked"] >= 2
    async with db_session() as db:
        if db.bind.dialect.name == "postgresql":
            # DB-level append-only: the BEFORE UPDATE OR DELETE trigger rejects any mutation
            import pytest
            from sqlalchemy.exc import DBAPIError

            row = (await db.execute(select(AuditEvent).where(AuditEvent.id == b.id))).scalar_one()
            row.after = {"y": [9]}
            with pytest.raises(DBAPIError, match="append-only"):
                await db.commit()
            await db.rollback()
            res = await verify_chain(db, a.stream_key)
            assert res["ok"]
            return
        # sqlite has no trigger: tamper directly and expect the chain verification to catch it
        row = (await db.execute(select(AuditEvent).where(AuditEvent.id == b.id))).scalar_one()
        row.after = {"y": [9]}
        await db.commit()
    async with db_session() as db:
        res = await verify_chain(db, a.stream_key)
        assert not res["ok"]
        assert res["streams"][a.stream_key]["first_bad_id"] == b.id
        # repair for later tests
        row = (await db.execute(select(AuditEvent).where(AuditEvent.id == b.id))).scalar_one()
        row.after = {"y": [1, 2]}
        await db.commit()


def test_row_hash_is_deterministic():
    f = {"a": 1, "b": "x"}
    assert compute_row_hash(b"p", f) == compute_row_hash(b"p", dict(reversed(list(f.items()))))
    assert compute_row_hash(b"p", f) != compute_row_hash(b"q", f)
