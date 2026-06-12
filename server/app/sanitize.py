from __future__ import annotations

from html import escape
import re

import nh3


ALLOWED_TAGS = {
    "a",
    "article",
    "blockquote",
    "body",
    "br",
    "button",
    "caption",
    "code",
    "div",
    "em",
    "footer",
    "head",
    "h1",
    "h2",
    "h3",
    "header",
    "html",
    "li",
    "main",
    "meta",
    "ol",
    "p",
    "pre",
    "section",
    "span",
    "strong",
    "style",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "time",
    "title",
    "tr",
    "ul",
}

ALLOWED_ATTRIBUTES = {
    "*": {"aria-label", "class", "data-action", "data-payload", "data-role"},
    "a": {"rel", "title"},
    "button": {"type", "data-action", "data-payload", "aria-label", "class"},
    "html": {"lang"},
    "meta": {"charset", "name", "content"},
}


def sanitize_generated_html(html: str) -> str:
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        clean_content_tags=set(),
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=set(),
        link_rel=None,
        strip_comments=True,
    )
    cleaned = re.sub(r"\s+on[a-z]+\s*=", " data-stripped=", cleaned, flags=re.IGNORECASE)
    cleaned = strip_external_css(cleaned)
    return cleaned


def strip_external_css(html: str) -> str:
    cleaned = re.sub(r"@import\s+[^;]+;", "", html, flags=re.IGNORECASE)
    cleaned = re.sub(r"url\(\s*(['\"])?[^)]*?\1\s*\)", "none", cleaned, flags=re.IGNORECASE)
    return cleaned


def page_document(title: str, body: str) -> str:
    safe_title = escape(" ".join(title.strip().lower().split()) or "untitled", quote=True)
    document = (
        '<article class="hermes-page">'
        '<header class="meta">built by hermes · local · 1 source</header>'
        f"<h1>{safe_title}</h1>"
        f"{body}"
        '<footer class="sources">sources: hermes home fallback agent</footer>'
        "</article>"
    )
    return sanitize_generated_html(document)
