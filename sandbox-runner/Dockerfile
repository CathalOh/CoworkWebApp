# Per-session sandbox image: hosts the `claude` CLI subprocess and any Bash/execute tool calls.
# Hardening flags (cap-drop ALL, no-new-privileges, seccomp, read-only rootfs, tmpfs, non-root, limits, no host mounts
# except the workspace) are applied at `docker run` time by app/sandbox/runner.py.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HOME=/home/agent
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git ripgrep jq \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
# Document-generation toolchain available to the agent (docx/pptx/xlsx/pdf per PRD §7.7)
RUN pip install python-docx python-pptx openpyxl XlsxWriter reportlab pypdf pandas matplotlib pillow
# The Claude Code CLI (same binary the Agent SDK bundles). Version pin: keep in sync with backend claude-agent-sdk.
RUN npm install -g @anthropic-ai/claude-code@latest && npm cache clean --force
RUN useradd -u 10001 -m agent && mkdir -p /ws /home/agent && chown -R agent:agent /ws /home/agent
USER agent
WORKDIR /ws
CMD ["sleep", "infinity"]
