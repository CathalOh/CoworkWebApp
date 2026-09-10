"""Sandbox runner: one hardened container per active run (or none in dev).

The interface is container-runtime agnostic so gVisor/Kata/Firecracker can drop in via `runtime=`.
Docker hardening baseline: cap-drop ALL, no-new-privileges, seccomp profile, read-only root + tmpfs, non-root,
CPU/mem/pids limits, only the workspace bind-mounted, egress via the allowlist proxy only.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings
from app.observability.logging import get_logger
from app.orchestration.base import RunConfig

log = get_logger("sandbox")
CONTAINER_WORKSPACE = "/ws"


@dataclass
class SandboxHandle:
    id: str
    backend: str
    workspace_path: str
    env: dict[str, str] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


class SandboxRunner(Protocol):
    async def start(self, run_id: str, cfg: RunConfig) -> SandboxHandle | None: ...
    async def stop(self, handle: SandboxHandle) -> None: ...
    async def health(self) -> dict[str, Any]: ...


class NoSandboxRunner:
    """Dev/test: the agent subprocess runs in the worker container with cwd=workspace and policy-only isolation."""

    async def start(self, run_id: str, cfg: RunConfig) -> SandboxHandle | None:
        Path(cfg.workspace_path).mkdir(parents=True, exist_ok=True)
        return SandboxHandle(id=f"local-{run_id}", backend="none", workspace_path=cfg.workspace_path)

    async def stop(self, handle: SandboxHandle) -> None:
        return None

    async def health(self) -> dict[str, Any]:
        return {"backend": "none", "ok": True}


class DockerSandboxRunner:
    """Sibling-container pattern: the worker talks to the Docker socket and runs the `claude` CLI inside a
    per-run hardened container. The SDK is pointed at that container by wrapping the CLI path with a
    `docker exec` shim (cli_path) so the subprocess, shell and workspace all live inside the sandbox."""

    def __init__(self) -> None:
        self.s = get_settings()
        self._active: dict[str, str] = {}

    async def _docker(self, *args: str) -> str:
        proc = await asyncio.create_subprocess_exec("docker", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"docker {' '.join(args[:2])} failed: {err.decode()[:500]}")
        return out.decode().strip()

    async def start(self, run_id: str, cfg: RunConfig) -> SandboxHandle | None:
        s = self.s
        Path(cfg.workspace_path).mkdir(parents=True, exist_ok=True)
        name = f"cw-sbx-{run_id[:12]}"
        seccomp = Path(__file__).resolve().parents[3] / "config" / "seccomp-sandbox.json"
        args = [
            "run", "-d", "--name", name, "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--read-only", "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m", "--tmpfs", "/home/agent:rw,nosuid,size=256m",
            "--user", "10001:10001", "--cpus", str(s.sandbox_cpu), "--memory", s.sandbox_memory, "--pids-limit", "512",
            "--network", "sandbox-egress" if s.sandbox_egress_proxy else "none",
            "-v", f"{os.path.abspath(cfg.workspace_path)}:{CONTAINER_WORKSPACE}:rw",
            "-w", CONTAINER_WORKSPACE, "-e", "HOME=/home/agent",
        ]
        if seccomp.exists():
            args += ["--security-opt", f"seccomp={seccomp}"]
        if s.sandbox_egress_proxy:
            args += ["-e", f"HTTPS_PROXY={s.sandbox_egress_proxy}", "-e", f"HTTP_PROXY={s.sandbox_egress_proxy}",
                     "-e", "NO_PROXY=localhost,127.0.0.1"]
        for k, v in cfg.env.items():  # provider env travels into the sandbox, never onto the host shell
            args += ["-e", f"{k}={v}"]
        args += [s.sandbox_image, "sleep", "infinity"]
        cid = await self._docker(*args)
        self._active[run_id] = name
        shim = Path("/tmp") / f"claude-shim-{run_id[:12]}"
        shim.write_text(f'#!/bin/sh\nexec docker exec -i {name} claude "$@"\n')
        shim.chmod(0o755)
        log.info("sandbox_started", run_id=run_id, container=name)
        return SandboxHandle(id=cid, backend="docker", workspace_path=cfg.workspace_path,
                             env={"CLAUDE_CLI_PATH": str(shim)}, meta={"name": name, "shim": str(shim)})

    async def stop(self, handle: SandboxHandle) -> None:
        name = handle.meta.get("name")
        if name:
            try:
                await self._docker("rm", "-f", name)
            finally:
                shim = handle.meta.get("shim")
                if shim and os.path.exists(shim):
                    os.unlink(shim)
        log.info("sandbox_stopped", container=name)

    async def health(self) -> dict[str, Any]:
        try:
            out = await self._docker("ps", "--filter", "name=cw-sbx-", "--format", "{{json .Names}}")
            n = len([line for line in out.splitlines() if line])
            return {"backend": "docker", "ok": True, "active": n, "max": self.s.max_concurrent_runs_global}
        except Exception as exc:
            return {"backend": "docker", "ok": False, "error": str(exc)}


_runner: SandboxRunner | None = None


def get_sandbox_runner() -> SandboxRunner:
    global _runner
    if _runner is None:
        s = get_settings()
        if s.sandbox_backend == "docker" and shutil.which("docker"):
            _runner = DockerSandboxRunner()
        else:
            _runner = NoSandboxRunner()
    return _runner


def egress_allowlist() -> list[str]:
    """Hosts the sandbox proxy may connect to: ILIAD always, plus configured extras and connector hosts."""
    s = get_settings()
    hosts = [h.strip() for h in s.sandbox_egress_allowlist.split(",") if h.strip()]
    if s.iliad_base_url:
        from urllib.parse import urlparse

        hosts.append(urlparse(s.iliad_base_url).hostname or "")
    return sorted({h for h in hosts if h})


def write_proxy_allowlist(path: str, extra_hosts: list[str] | None = None) -> None:
    hosts = sorted(set(egress_allowlist()) | set(extra_hosts or []))
    Path(path).write_text("\n".join(hosts) + "\n")
    log.info("egress_allowlist_written", path=path, count=len(hosts))


def sandbox_settings_json() -> str:
    return json.dumps({"cpu": get_settings().sandbox_cpu, "memory": get_settings().sandbox_memory,
                       "disk": get_settings().sandbox_disk, "backend": get_settings().sandbox_backend})
