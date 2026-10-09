"""HTML -> (title, text). Keeps HTML comments and visually hidden text on purpose:
injection detection happens downstream, so the reader must see everything a page carries."""
from __future__ import annotations

import re

import lxml.html
from lxml import etree
from readability import Document

from hive.collectors._common import HTML_PARSER

_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0|opacity\s*:\s*0(?:\.0+)?\b"
    r"|color\s*:\s*(?:#fff(?:fff)?\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\)|transparent\b)"
    r"|left\s*:\s*-\d{3,}px|text-indent\s*:\s*-\d{3,}px|height\s*:\s*0|width\s*:\s*0",
    re.IGNORECASE,
)
_XML_DECL = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)
_WS = re.compile(r"[ \t\r\f\v]+")
_BLANKS = re.compile(r"\n\s*\n+")
_BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section", "article", "blockquote", "pre", "table"}


def _norm(s: str) -> str:
    s = _WS.sub(" ", s)
    s = "\n".join(line.strip() for line in s.splitlines())
    return _BLANKS.sub("\n\n", s).strip()


def _tree_text(el) -> str:
    parts: list[str] = []

    def walk(node):
        if isinstance(node, etree._Comment):
            return
        tag = node.tag if isinstance(node.tag, str) else ""
        if tag in ("script", "style", "noscript"):
            return
        if tag in _BLOCK_TAGS:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in _BLOCK_TAGS:
            parts.append("\n")

    walk(el)
    return _norm("".join(parts))


def _comments(root) -> list[str]:
    out = []
    for c in root.iter(etree.Comment):
        parent = c.getparent()
        if parent is not None and parent.tag in ("script", "style"):
            continue
        t = _norm(c.text or "")
        if t:
            out.append(t)
    return out


def _hidden_texts(root) -> list[str]:
    out = []
    for el in root.iter():
        if not isinstance(el.tag, str) or el.tag in ("script", "style", "head", "title", "meta"):
            continue
        style = el.get("style", "")
        if el.get("hidden") is not None or el.get("aria-hidden") == "true" or _HIDDEN_STYLE.search(style):
            t = _tree_text(el)
            if t:
                out.append(t)
    return out


def html_to_text(html: str) -> tuple[str, str]:
    if not html or not html.strip():
        return "", ""
    html = _XML_DECL.sub("", html, count=1)
    root = lxml.html.document_fromstring(html, parser=HTML_PARSER)

    title = ""
    main = ""
    try:
        doc = Document(html)
        title = (doc.short_title() or "").strip()
        main = _tree_text(lxml.html.fragment_fromstring(doc.summary(html_partial=True), parser=HTML_PARSER))
    except Exception:
        pass
    if not title:
        t = root.find(".//title")
        title = _norm(t.text_content()) if t is not None else ""
    if len(main) < 200:
        body = root.find(".//body")
        main = _tree_text(body if body is not None else root)

    extras: list[str] = []
    for h in _hidden_texts(root):
        if h not in main and h not in extras:
            extras.append(h)
    for c in _comments(root):
        extras.append(f"<!-- {c} -->")

    text = main
    if extras:
        text = f"{main}\n\n" + "\n\n".join(extras)
    return title, text.strip()
