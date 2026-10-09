from __future__ import annotations

import re

from hive.models import Detector, InjectionEvent, RawDocument

CUE_WINDOW = 300
SNIPPET_CHARS = 160
HIDDEN_SCAN_CHARS = 600

STRONG_CUE = re.compile(
    r"\b(?:ignore|disregard)\b(?:\W+\w+){0,4}?\W+(?:instructions?|prompts?|rules|guidelines)\b"
    r"|\b(?:previous|prior)\s+instructions\b|\bsystem\s+prompt\b"
    r"|\byou\s+are\s+an?\s+(?:ai|assistant|(?:large\s+)?(?:language\s+)?model)\b",
    re.I,
)
COMMENT_CUE = re.compile(
    r"\b(?:ignore|disregard|respond|override|must)\b|\b(?:previous|prior)\s+instructions\b|\bsystem\s+prompt\b"
    r"|\byou\s+are\s+an?\s+(?:ai|assistant|model)\b|\breport\s+that\b|\bdo\s+not\s+tell\b",
    re.I,
)
ADDRESSEE = re.compile(
    r"\byou(?:r|rs|rself)?\b|\b(?:ai|assistants?|models?|llms?|agents?|chatbots?|automated\s+readers?)\b", re.I
)
BENIGN_COMMENT_PREFIXES = ("<!-- #", "<!-- /", "<!-- wp:", "<!-- /wp:", "<!--[if", "<!-- google tag")

_COMMENT = re.compile(r"<!--(.*?)-->", re.S)
_HIDDEN = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0(?:px|pt|em|rem)?\b"
    r"|color\s*:\s*(?:#fff(?:fff)?\b|white\b)[^\"'>]*background(?:-color)?\s*:\s*(?:#fff(?:fff)?\b|white\b)"
    r"|(?:height|font-size)\s*:\s*1px[^\"'>]*overflow\s*:\s*hidden",
    re.I,
)
_TAG_END = re.compile(r"[\"']?\s*>")

SIMPLE: list[tuple[str, re.Pattern[str], float]] = [
    ("ignore_instructions", re.compile(r"ignore\s+(?:all|previous|prior)(?:\s+\w+)?\s+instructions", re.I), 0.9),
    ("role_reassignment", re.compile(r"you\s+are\s+an?\s+(?:ai|assistant|language\s+model)", re.I), 0.7),
    ("system_prompt", re.compile(r"system\s+prompt", re.I), 0.6),
    ("do_not_tell", re.compile(r"do\s+not\s+tell", re.I), 0.6),
]
CUED: list[tuple[str, re.Pattern[str]]] = [
    ("report_that", re.compile(r"report\s+that", re.I)),
    ("respond_with", re.compile(r"respond\s+with", re.I)),
]
CUED_LOW, CUED_HIGH = 0.25, 0.6
COMMENT_SEVERITY = 0.7
HIDDEN_LOW, HIDDEN_HIGH = 0.3, 0.8
BASE64_SEVERITY = 0.15
_BASE64 = re.compile(r"[A-Za-z0-9+/]{200,}={0,2}")


def _snippet(text: str, start: int, end: int) -> str:
    pad = max(0, (SNIPPET_CHARS - (end - start)) // 2)
    lo = max(0, start - pad)
    return text[lo : lo + SNIPPET_CHARS].replace("\n", " ")


def _benign_comment(body: str) -> bool:
    raw = body.lstrip().lower()
    return ("<!--" + body.lower()).startswith(BENIGN_COMMENT_PREFIXES) or ("<!-- " + raw).startswith(BENIGN_COMMENT_PREFIXES)


def _window(text: str, start: int, end: int) -> str:
    half = CUE_WINDOW // 2
    return text[max(0, start - half) : end + half]


def _hits(text: str) -> list[tuple[str, int, int, float]]:
    hits: list[tuple[str, int, int, float]] = []
    for name, rx, severity in SIMPLE:
        hits.extend((name, m.start(), m.end(), severity) for m in rx.finditer(text))
    for name, rx in CUED:
        for m in rx.finditer(text):
            cued = STRONG_CUE.search(_window(text, m.start(), m.end()))
            hits.append((name, m.start(), m.end(), CUED_HIGH if cued else CUED_LOW))
    for m in _COMMENT.finditer(text):
        body = m.group(1)
        if _benign_comment(body):
            continue
        if COMMENT_CUE.search(body) and ADDRESSEE.search(body):
            hits.append(("html_comment_instruction", m.start(), m.end(), COMMENT_SEVERITY))
    for m in _HIDDEN.finditer(text):
        tag_end = _TAG_END.search(text, m.end())
        lo = tag_end.end() if tag_end else m.end()
        hidden = re.sub(r"<[^>]+>", " ", text[lo : lo + HIDDEN_SCAN_CHARS].split("</", 1)[0])
        severity = HIDDEN_HIGH if STRONG_CUE.search(hidden) else HIDDEN_LOW
        hits.append(("hidden_text", m.start(), lo + len(hidden), severity))
    blob = _BASE64.search(text)
    if blob:
        hits.append(("base64_blob", blob.start(), blob.end(), BASE64_SEVERITY))
    return hits


def detect(doc: RawDocument, swarm_id: str = "") -> list[InjectionEvent]:
    best: dict[str, tuple[int, int, float]] = {}
    for name, start, end, severity in _hits(doc.text):
        if name not in best or severity > best[name][2]:
            best[name] = (start, end, severity)
    return [
        InjectionEvent(
            swarm_id=swarm_id,
            doc_id=doc.doc_id,
            source_id=doc.source_id,
            detector=Detector.HEURISTIC,
            pattern=name,
            snippet=_snippet(doc.text, start, end),
            severity=severity,
        )
        for name, (start, end, severity) in best.items()
    ]


def canary_check(output: dict | None) -> bool:
    if not isinstance(output, dict):
        return False
    quote = output.get("injection_quote")
    return bool(output.get("injection_suspected")) or bool(quote and str(quote).strip())
