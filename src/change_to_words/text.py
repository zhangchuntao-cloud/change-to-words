from __future__ import annotations

from collections.abc import Iterable


def segments_to_text(texts: Iterable[str]) -> str:
    """把分段文本拼成纯文本：一段一行，去掉时间戳和多余空白。"""
    lines: list[str] = []
    for raw in texts:
        # split() 只按空白切分，不会在中文之间插入空格。
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
