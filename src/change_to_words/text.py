from __future__ import annotations

from collections.abc import Iterable


def normalize_line(raw: str) -> str:
    """把一行文本中的连续空白折叠为单个空格。"""
    # split() 只按空白切分，不会在中文之间插入空格。
    return " ".join(raw.split())


def segments_to_lines(texts: Iterable[str]) -> list[str]:
    """清理分段文本，按顺序返回非空行。"""
    lines: list[str] = []
    for raw in texts:
        line = normalize_line(raw)
        if line:
            lines.append(line)
    return lines


def segments_to_text(texts: Iterable[str]) -> str:
    """把分段文本拼成纯文本：一段一行，去掉时间戳和多余空白。"""
    lines = segments_to_lines(texts)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"
