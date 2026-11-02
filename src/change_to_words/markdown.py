from __future__ import annotations

from collections.abc import Iterable

from .text import segments_to_lines


def segments_to_markdown(texts: Iterable[str]) -> str:
    """把分段文本拼成 Markdown：每段一个段落，段间空一行。"""
    lines = segments_to_lines(texts)
    if not lines:
        return ""
    return "\n\n".join(lines) + "\n"
