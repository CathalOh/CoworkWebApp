# Runbook: Decision Gate A — ILIAD compatibility spike

1. Get from the ILIAD team (see `docs/questions-iliad.md`): base URL, service token, custom headers, CA cert, exact model IDs.
2. `ILIAD_BASE_URL=… ILIAD_AUTH_TOKEN=… CLAUDE_AGENT_MODEL=… [ILIAD_CUSTOM_HEADERS=… ILIAD_CA_CERT_PATH=…] backend/.venv/bin/python scripts/iliad_spike.py`
3. Read `docs/spike-results.json`. The script retries with `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` automatically if the
   first attempt is rejected (then set `ILIAD_DISABLE_EXPERIMENTAL_BETAS=true`).
4. **PASS** (streaming + tool use + model ID + auth + TTFT < 5 s): keep `MODEL_PROVIDER=iliad_anthropic`,
   `AGENT_RUNTIME=agent_sdk`. Record thinking/caching/structured-output results in the ADR-002 notes.
5. **FAIL**: `MODEL_PROVIDER=iliad_openai_compat AGENT_RUNTIME=deep_agents`, fill `config/litellm.yaml`, run
   `docker compose --profile litellm up`, install the extras `uv pip install -e ".[deepagents]"`. Do not relitigate.
6. Commit `docs/spike-results.json` with the decision.
