from __future__ import annotations

import re

from hive.models import Detector, InjectionEvent, RawDocument

PATTERNS: list[tuple[str, re.Pattern[str], float]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(?:all|previous|prior)(?:\s+\w+)?\s+instructions", re.I), 0.9),
    ("role_reassignment", re.compile(r"you\s+are\s+an?\s+(?:ai|assistant|language\s+model)", re.I), 0.7),
    ("system_prompt", re.compile(r"system\s+prompt", re.I), 0.6),
    ("report_that", re.compile(r"report\s+that", re.I), 0.5),
    ("respond_with", re.compile(r"respond\s+with", re.I), 0.5),
    ("do_not_tell", re.compile(r"do\s+not\s+tell", re.I), 0.6),
    ("html_comment_instruction", re.compile(
        r"<!--(?=[^>]*?\b(?:ignore|instruction|assistant|ai|model|respond|report|output|must|should)\b)(.*?)-->", re.I | re.S), 0.7),
    ("hidden_style", re.compile(
        r"display\s*:\s*none|visibility\s*:\s*hidden|color\s*:\s*(?:#fff(?:fff)?\b|white\b)", re.I), 0.4),
    ("base64_blob", re.compile(r"[A-Za-z0-9+/]{200,}={0,2}"), 0.3),
]

SNIPPET_CHARS = 160


def _snippet(text: str, start: int, end: int) -> str:
    pad = max(0, (SNIPPET_CHARS - (end - start)) // 2)
    lo = max(0, start - pad)
    return text[lo : lo + SNIPPET_CHARS].replace("\n", " ")


def detect(doc: RawDocument, swarm_id: str = "") -> list[InjectionEvent]:
    events: list[InjectionEvent] = []
    for name, rx, severity in PATTERNS:
        for m in rx.finditer(doc.text):
            events.append(
                InjectionEvent(
                    swarm_id=swarm_id,
                    doc_id=doc.doc_id,
                    source_id=doc.source_id,
                    detector=Detector.HEURISTIC,
                    pattern=name,
                    snippet=_snippet(doc.text, m.start(), m.end()),
                    severity=severity,
                )
            )
    return events


def canary_check(output: dict | None) -> bool:
    if not isinstance(output, dict):
        return False
    quote = output.get("injection_quote")
    return bool(output.get("injection_suspected")) or bool(quote and str(quote).strip())
