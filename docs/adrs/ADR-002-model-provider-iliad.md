# ADR-002: ILIAD behind a `ModelProvider` seam, gated by a spike

**Status:** accepted · **Date:** 2026-09-10

## Context
ILIAD's API shape (Anthropic-native vs OpenAI-compatible), auth header, beta-header tolerance, model IDs and TLS are
unknown. The SDK honours `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN` with no name translation and no silent fallback.

## Decision
`ModelProvider.env()` produces the environment injected into the agent subprocess (or the LangChain model). Primary:
`IliadAnthropicProvider`; fallback: `IliadOpenAICompatProvider` (LiteLLM). `scripts/iliad_spike.py` is Decision Gate A and
writes `docs/spike-results.json` with PASS/FAIL per criterion (streaming, tool use, model ID, auth/beta headers, latency,
thinking, caching, structured output). The model ID is pinned via `CLAUDE_AGENT_MODEL`.

## Consequences
The gate can be re-run any time; flipping the provider + runtime is configuration. Cost accounting reads
`ResultMessage.total_cost_usd`/`usage` on the Anthropic path and LangChain `usage_metadata` on the fallback path.
