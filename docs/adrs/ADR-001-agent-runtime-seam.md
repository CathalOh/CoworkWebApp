# ADR-001: Orchestration behind an `AgentRuntime` seam

**Status:** accepted · **Date:** 2026-09-10

## Context
The Claude Agent SDK is the reference runtime (Cowork is built on it) but its viability depends on ILIAD exposing the
Anthropic Messages API. LangChain Deep Agents is a credible fallback with a similar shape (filesystem tools, subagents,
interrupts, checkpointers).

## Decision
All orchestration goes through `app/orchestration/base.py` (`RunConfig` → `AgentRuntime.run(cfg, hooks)` → `AgentEvent`
stream + result dict). Three implementations: `AgentSdkRuntime` (primary), `DeepAgentsRuntime` (fallback), `MockRuntime`
(tests). The host (`RunHost`) owns approvals, elicitation, event persistence, cost accounting and audit, so runtimes stay
thin. `RunConfig.tools` (availability) is separate from `RunConfig.allowed_tools` (pre-approved) so permission semantics are
runtime-independent.

## Consequences
Switching runtime is `AGENT_RUNTIME=deep_agents` (+ provider). Feature code never imports an SDK. Runtime-specific
capabilities (e.g. SDK session resume) are carried opaquely (`resume_session_id`).
