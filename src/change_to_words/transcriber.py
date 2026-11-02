from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional, Protocol, Tuple


@dataclass(frozen=True)
class TextSegment:
    text: str
    start: float
    end: float


@dataclass(frozen=True)
class TranscriptionResult:
    segments: Tuple[TextSegment, ...] = field(default_factory=tuple)
    language: Optional[str] = None
    language_probability: Optional[float] = None
    duration: Optional[float] = None


ProgressCallback = Callable[[TextSegment, Optional[float]], None]


class Transcriber(Protocol):
    def transcribe(
        self, path: Path, progress: Optional[ProgressCallback] = None
    ) -> TranscriptionResult:
        ...


class FasterWhisperTranscriber:
    def __init__(
        self,
        model: Any,
        *,
        language: Optional[str] = None,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
    ) -> None:
        self._model = model
        self._language = language
        self._vad_filter = vad_filter
        self._initial_prompt = initial_prompt

    def transcribe(
        self, path: Path, progress: Optional[ProgressCallback] = None
    ) -> TranscriptionResult:
        segments, info = self._model.transcribe(
            str(path),
            language=self._language,
            task="transcribe",
            vad_filter=self._vad_filter,
            initial_prompt=self._initial_prompt,
        )

        collected: List[TextSegment] = []
        for segment in segments:
            item = TextSegment(
                text=segment.text,
                start=float(segment.start),
                end=float(segment.end),
            )
            collected.append(item)
            if progress is not None:
                duration = float(info.duration) if info.duration else None
                progress(item, duration)

        return TranscriptionResult(
            segments=tuple(collected),
            language=getattr(info, "language", None),
            language_probability=getattr(info, "language_probability", None),
            duration=getattr(info, "duration", None),
        )


def load_model(
    model: str,
    *,
    download_root: Optional[str] = None,
    offline: bool = False,
    compute_type: str = "int8",
) -> Any:
    """加载并返回底层 WhisperModel，供 CLI 和 Web 复用。"""
    # 延迟导入：--help、参数错误等场景不需要加载较重的依赖。
    from faster_whisper import WhisperModel

    return WhisperModel(
        model,
        device="cpu",
        compute_type=compute_type,
        download_root=download_root,
        local_files_only=offline,
    )


def wrap_model(
    model: Any,
    *,
    language: Optional[str] = None,
    vad_filter: bool = True,
    initial_prompt: Optional[str] = None,
) -> FasterWhisperTranscriber:
    """在已加载的模型上绑定本次任务的参数。"""
    return FasterWhisperTranscriber(
        model,
        language=language,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
    )


def create_transcriber(
    *,
    model: str,
    language: Optional[str],
    vad_filter: bool,
    download_root: Optional[str] = None,
    offline: bool = False,
    compute_type: str = "int8",
    initial_prompt: Optional[str] = None,
) -> FasterWhisperTranscriber:
    whisper_model = load_model(
        model,
        download_root=download_root,
        offline=offline,
        compute_type=compute_type,
    )
    return wrap_model(
        whisper_model,
        language=language,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
    )
