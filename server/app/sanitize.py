from __future__ import annotations

import re

import nh3


ALLOWED_TAGS = {
    "a",
    "article",
    "blockquote",
    "button",
    "code",
    "div",
    "em",
    "footer",
    "h1",
    "h2",
    "h3",
    "header",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "time",
    "tr",
    "ul",
}

ALLOWED_ATTRIBUTES = {
    "*": {"aria-label", "class", "data-action", "data-payload", "data-role"},
    "a": {"href", "rel", "title"},
    "button": {"type", "data-action", "data-payload", "aria-label", "class"},
}


def sanitize_generated_html(html: str) -> str:
    cleaned = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={"https"},
        link_rel=None,
        strip_comments=True,
    )
    cleaned = re.sub(r"\s+on[a-z]+\s*=", " data-stripped=", cleaned, flags=re.IGNORECASE)
    return cleaned


def page_document(title: str, body: str) -> str:
    safe_body = sanitize_generated_html(body)
    return (
        '<article class="hermes-page">'
        '<header class="meta">built by hermes · local · 1 source</header>'
        f"<h1>{title.lower()}</h1>"
        f"{safe_body}"
        '<footer class="sources">sources: hermes home fallback agent</footer>'
        "</article>"
    )
