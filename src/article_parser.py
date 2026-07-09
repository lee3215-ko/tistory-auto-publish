"""원고 파일에서 제목·본문·해시태그 분리."""

from __future__ import annotations

import re
from dataclasses import dataclass

HASHTAG_TOKEN_RE = re.compile(r"#([^\s#,]+)")


@dataclass(frozen=True)
class ArticleParts:
    title: str
    body: str
    tags: list[str]


def parse_article(text: str) -> ArticleParts:
    """첫 줄=제목, 맨 아래 #해시태그 줄=태그(본문에서 제거)."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if not lines:
        return ArticleParts(title="무제", body="", tags=[])

    title = lines[0].strip() or "무제"
    body_lines = lines[1:]

    while body_lines and not body_lines[-1].strip():
        body_lines.pop()

    tags: list[str] = []
    while body_lines:
        last_line = body_lines[-1].strip()
        tokens = [token for token in re.split(r"[\s,]+", last_line) if token]
        if not tokens or not all(token.startswith("#") for token in tokens):
            break
        line_tags = HASHTAG_TOKEN_RE.findall(last_line)
        if not line_tags:
            break
        tags = line_tags + tags
        body_lines.pop()
        while body_lines and not body_lines[-1].strip():
            body_lines.pop()

    deduped_tags: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped_tags.append(tag)

    body = "\n".join(body_lines).strip()
    return ArticleParts(title=title, body=body, tags=deduped_tags)
