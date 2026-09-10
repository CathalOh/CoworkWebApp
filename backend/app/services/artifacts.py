from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Artifact, ArtifactVersion

MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
KINDS = ("html", "react", "markdown", "svg", "mermaid", "code")


async def create_artifact(db: AsyncSession, owner_id: uuid.UUID, conversation_id: uuid.UUID | None, kind: str, title: str,
                          content: str, live_source: dict | None = None) -> Artifact:
    if kind not in KINDS:
        raise ValueError("unsupported artifact kind")
    if len(content.encode()) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds 20 MB")
    a = Artifact(owner_id=owner_id, conversation_id=conversation_id, kind=kind, title=title, latest_version=1, live_source=live_source)
    db.add(a)
    await db.flush()
    db.add(ArtifactVersion(artifact_id=a.id, version=1, content=content, storage={"bytes": len(content.encode())}))
    return a


async def add_version(db: AsyncSession, a: Artifact, content: str) -> ArtifactVersion:
    if len(content.encode()) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact exceeds 20 MB")
    a.latest_version += 1
    v = ArtifactVersion(artifact_id=a.id, version=a.latest_version, content=content, storage={"bytes": len(content.encode())})
    db.add(v)
    await db.flush()
    return v


async def get_version(db: AsyncSession, artifact_id: uuid.UUID, version: int | None) -> ArtifactVersion | None:
    q = select(ArtifactVersion).where(ArtifactVersion.artifact_id == artifact_id)
    q = q.where(ArtifactVersion.version == version) if version else q.order_by(ArtifactVersion.version.desc())
    return (await db.execute(q.limit(1))).scalar_one_or_none()


def render_document(kind: str, content: str) -> str:
    """Wrap artifact content in a minimal document for the sandboxed srcdoc iframe. Scripts are only
    allowed from the CDN allowlist enforced by the preview CSP."""
    if kind == "html":
        return content
    if kind == "svg":
        return f"<!doctype html><html><body style='margin:0'>{content}</body></html>"
    if kind == "markdown":
        import html

        return ("<!doctype html><html><head><script src='https://cdnjs.cloudflare.com/ajax/libs/marked/12.0.2/marked.min.js'></script>"
                "</head><body><div id='c'></div><script>document.getElementById('c').innerHTML=marked.parse(document.getElementById('src').textContent)</script>"
                f"<script id='src' type='text/plain'>{html.escape(content)}</script></body></html>")
    if kind == "mermaid":
        import html

        return ("<!doctype html><html><body><pre class='mermaid'>" + html.escape(content) + "</pre>"
                "<script src='https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js'></script>"
                "<script>mermaid.initialize({startOnLoad:true})</script></body></html>")
    if kind == "react":
        import html

        return ("<!doctype html><html><head>"
                "<script src='https://cdnjs.cloudflare.com/ajax/libs/react/18.3.1/umd/react.production.min.js'></script>"
                "<script src='https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.3.1/umd/react-dom.production.min.js'></script>"
                "<script src='https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.24.7/babel.min.js'></script>"
                "</head><body><div id='root'></div><script type='text/babel' data-presets='react'>" + content +
                "\n;(function(){var C=(typeof App!=='undefined')?App:(typeof exports!=='undefined'&&exports.default);"
                "if(C){ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(C));}})();</script></body></html>")
    import html

    return f"<!doctype html><html><body><pre style='font-family:monospace;white-space:pre-wrap'>{html.escape(content)}</pre></body></html>"
