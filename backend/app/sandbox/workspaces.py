"""Workspace directory management: each Workspace maps to a host directory under WORKSPACES_ROOT."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.config import get_settings


def workspace_dir(workspace_id: uuid.UUID | str) -> Path:
    root = Path(get_settings().workspaces_root).resolve()
    p = (root / str(workspace_id)).resolve()
    if root not in p.parents and p != root:
        raise ValueError("workspace path escapes root")
    p.mkdir(parents=True, exist_ok=True)
    return p


def scratch_dir(conversation_id: uuid.UUID | str) -> Path:
    root = Path(get_settings().workspaces_root).resolve() / "_scratch"
    p = root / str(conversation_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def dir_size(path: Path) -> int:
    total = 0
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            try:
                total += (Path(dp) / fn).stat().st_size
            except OSError:
                pass
    return total


def safe_join(root: Path, rel: str) -> Path:
    p = (root / rel.lstrip("/")).resolve()
    if root.resolve() not in p.parents and p != root.resolve():
        raise ValueError("path escapes workspace")
    return p
