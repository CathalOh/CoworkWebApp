# sandbox-runner

Hardened per-session container image. One container per active run; created by `app/sandbox/runner.py`
(`DockerSandboxRunner`) and destroyed on completion.

Runtime hardening applied by the runner (Anthropic "Securely deploying AI agents" baseline):

| Control | Flag |
|---|---|
| Drop all capabilities | `--cap-drop ALL` |
| No privilege escalation | `--security-opt no-new-privileges` |
| Syscall filter | `--security-opt seccomp=config/seccomp-sandbox.json` |
| Immutable root FS | `--read-only` + `--tmpfs /tmp:rw,noexec,nosuid` |
| Non-root | `--user 10001:10001` |
| Resource caps | `--cpus 1 --memory 1g --pids-limit 512` (start values from PRD) |
| Mounts | only the session workspace at `/ws` |
| Network | `--network sandbox-egress` (allowlist proxy) or `--network none` |

Egress: the container has no direct route out; `HTTPS_PROXY` points at the `egress-proxy` service (tinyproxy) whose
allowlist is generated from ILIAD + the connector catalog (`config/egress-allowlist.txt`). The proxy allowlists
hostnames and does **not** inspect TLS, so connector tokens must be least-privilege.

Upgrade path: the `SandboxRunner` protocol is runtime-agnostic; swap `docker run` for `--runtime=runsc` (gVisor),
Kata, or a Firecracker microVM driver without touching the orchestration layer.
