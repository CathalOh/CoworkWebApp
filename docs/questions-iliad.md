# Questions for the ILIAD / gateway team (blocking Decision Gate A)

1. Does ILIAD expose the **Anthropic Messages API** (`POST /v1/messages`) with SSE streaming, tool use, extended
   (adaptive) thinking, prompt caching (`cache_control`, `cache_read_input_tokens` in usage), and files/PDF input?
   Or only an OpenAI-compatible surface (`/v1/chat/completions`)?
2. **Auth scheme**: Bearer token in `Authorization` (what the SDK sends via `ANTHROPIC_AUTH_TOKEN`), `x-api-key`, or a
   custom header (we can add via `ANTHROPIC_CUSTOM_HEADERS`)? Token lifetime / rotation?
3. Does it tolerate Anthropic **beta headers** (`anthropic-beta`) the SDK sends, or must we set
   `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1`?
4. Exact **model IDs** accepted (no client-side name translation; mismatches fail hard). Is `claude-opus-5` valid?
5. TLS: public CA or private (we need the CA bundle for `NODE_EXTRA_CA_CERTS`)? Any egress proxy requirements?
6. Rate limits and quotas per token/tenant; per-user attribution headers we should send for chargeback?
7. Does the response include `usage` (input/output/cache tokens) and any cost fields we can log?
8. Availability of `/v1/models`, `/v1/messages/count_tokens`, `/v1/files`, batches.
9. Latency expectations (TTFT) and max request duration / timeouts for long agentic turns.
10. If OpenAI-compatible only: does it support tool/function calling and streaming, and an `/v1/embeddings` endpoint?
