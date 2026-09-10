# ADR-005: Per-run hardened Docker sandbox now; microVM/gVisor before untrusted multi-tenancy

**Status:** accepted · **Date:** 2026-09-10

## Decision
`SandboxRunner` protocol with `NoSandboxRunner` (dev: policy-only isolation, cwd = workspace) and `DockerSandboxRunner`
(one container per run: cap-drop ALL, no-new-privileges, seccomp allowlist, read-only rootfs + tmpfs, non-root, CPU/mem/pid
limits, only the workspace bind-mounted, egress only through the tinyproxy allowlist — ILIAD + catalog hosts). The SDK's
CLI subprocess is executed inside the container through a `docker exec` shim (`cli_path`), so the shell, working
directory and transcripts live in the sandbox. Provider credentials are passed as container env, never on the host shell.

## Consequences
Shared-kernel runc is acceptable on a single trusted host only. The runner interface is runtime-agnostic: gVisor
(`--runtime=runsc`), Kata or Firecracker drop in. The proxy allowlists hosts but does not inspect TLS → connector tokens
must be least-privilege. Deletion protection and secret-path blocks are enforced in the host policy regardless of sandbox.
