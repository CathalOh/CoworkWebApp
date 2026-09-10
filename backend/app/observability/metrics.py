"""Minimal in-process metrics registry (counters/histograms) exposed at /metrics in Prometheus text format.
OpenTelemetry exporters can be attached later without touching call sites."""
from __future__ import annotations

import threading
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
_hist: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = defaultdict(list)


def inc(name: str, value: float = 1.0, **labels: str) -> None:
    with _lock:
        _counters[(name, tuple(sorted(labels.items())))] += value


def observe(name: str, value: float, **labels: str) -> None:
    with _lock:
        h = _hist[(name, tuple(sorted(labels.items())))]
        h.append(value)
        if len(h) > 5000:
            del h[: len(h) - 5000]


def render_prometheus() -> str:
    lines: list[str] = []
    with _lock:
        for (name, labels), v in _counters.items():
            lbl = ",".join(f'{k}="{val}"' for k, val in labels)
            lines.append(f"{name}{{{lbl}}} {v}")
        for (name, labels), vals in _hist.items():
            lbl = ",".join(f'{k}="{val}"' for k, val in labels)
            if vals:
                s = sorted(vals)
                lines.append(f"{name}_count{{{lbl}}} {len(s)}")
                lines.append(f"{name}_sum{{{lbl}}} {sum(s)}")
                lines.append(f'{name}_p50{{{lbl}}} {s[len(s)//2]}')
                lines.append(f'{name}_p95{{{lbl}}} {s[int(len(s)*0.95)-1 if len(s)>1 else 0]}')
    return "\n".join(lines) + "\n"
