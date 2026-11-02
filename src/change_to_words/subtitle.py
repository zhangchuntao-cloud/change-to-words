from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from .transcriber import TextSegment


def _clean(text: str) -> str:
    return " ".join(text.split())


def _timestamp(seconds: float, *, separator: str) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"
        f"{separator}{milliseconds:03d}"
    )


def _cue(segment: TextSegment) -> Optional[Tuple[str, float, float]]:
    text = _clean(segment.text)
    if not text:
        return None
    start = max(0.0, float(segment.start))
    end = max(start + 0.001, float(segment.end))
    return text, start, end


def segments_to_srt(segments: Iterable[TextSegment]) -> str:
    """生成 SRT 字幕，时间戳格式为 HH:MM:SS,mmm。"""
    blocks: List[str] = []
    for segment in segments:
        cue = _cue(segment)
        if cue is None:
            continue
        text, start, end = cue
        blocks.append(
            f"{len(blocks) + 1}\n"
            f"{_timestamp(start, separator=',')} --> "
            f"{_timestamp(end, separator=',')}\n"
            f"{text}"
        )
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def segments_to_vtt(segments: Iterable[TextSegment]) -> str:
    """生成 WebVTT 字幕，时间戳格式为 HH:MM:SS.mmm。"""
    blocks: List[str] = []
    for segment in segments:
        cue = _cue(segment)
        if cue is None:
            continue
        text, start, end = cue
        blocks.append(
            f"{_timestamp(start, separator='.')} --> "
            f"{_timestamp(end, separator='.')}\n"
            f"{text}"
        )
    if not blocks:
        return "WEBVTT\n"
    return "WEBVTT\n\n" + "\n\n".join(blocks) + "\n"
