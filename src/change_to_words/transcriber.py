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
        batch_size: int = 0,
        beam_size: int = 5,
        condition_on_previous_text: bool = True,
        no_repeat_ngram_size: int = 0,
    ) -> None:
        self._model = model
        self._language = language
        self._vad_filter = vad_filter
        self._initial_prompt = initial_prompt
        self._beam_size = max(1, int(beam_size))
        self._batch_size = max(0, int(batch_size))
        self._condition_on_previous_text = condition_on_previous_text
        self._no_repeat_ngram_size = max(0, int(no_repeat_ngram_size))
        self._pipeline = None
        if self._batch_size > 1:
            if not vad_filter:
                raise ValueError("批量推理需要开启静音过滤（VAD）")
            # 延迟导入：不使用批量推理时不加载额外模块。
            from faster_whisper import BatchedInferencePipeline

            self._pipeline = BatchedInferencePipeline(model)

    def transcribe(
        self, path: Path, progress: Optional[ProgressCallback] = None
    ) -> TranscriptionResult:
        options = {
            "language": self._language,
            "task": "transcribe",
            "vad_filter": self._vad_filter,
            "initial_prompt": self._initial_prompt,
            "beam_size": self._beam_size,
            "condition_on_previous_text": self._condition_on_previous_text,
            "no_repeat_ngram_size": self._no_repeat_ngram_size,
        }
        if self._pipeline is not None:
            segments, info = self._pipeline.transcribe(
                str(path), batch_size=self._batch_size, **options
            )
        else:
            segments, info = self._model.transcribe(str(path), **options)

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
    cpu_threads: int = 0,
) -> Any:
    """加载并返回底层 WhisperModel，供 CLI 和 Web 复用。"""
    # 延迟导入：--help、参数错误等场景不需要加载较重的依赖。
    from faster_whisper import WhisperModel

    return WhisperModel(
        model,
        device="cpu",
        compute_type=compute_type,
        cpu_threads=max(0, int(cpu_threads)),
        download_root=download_root,
        local_files_only=offline,
    )


def wrap_model(
    model: Any,
    *,
    language: Optional[str] = None,
    vad_filter: bool = True,
    initial_prompt: Optional[str] = None,
    batch_size: int = 0,
    beam_size: int = 5,
    condition_on_previous_text: bool = True,
    no_repeat_ngram_size: int = 0,
) -> FasterWhisperTranscriber:
    """在已加载的模型上绑定本次任务的参数。"""
    return FasterWhisperTranscriber(
        model,
        language=language,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
        batch_size=batch_size,
        beam_size=beam_size,
        condition_on_previous_text=condition_on_previous_text,
        no_repeat_ngram_size=no_repeat_ngram_size,
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
    batch_size: int = 0,
    beam_size: int = 5,
    cpu_threads: int = 0,
    condition_on_previous_text: bool = True,
    no_repeat_ngram_size: int = 0,
) -> FasterWhisperTranscriber:
    whisper_model = load_model(
        model,
        download_root=download_root,
        offline=offline,
        compute_type=compute_type,
        cpu_threads=cpu_threads,
    )
    return wrap_model(
        whisper_model,
        language=language,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
        batch_size=batch_size,
        beam_size=beam_size,
        condition_on_previous_text=condition_on_previous_text,
        no_repeat_ngram_size=no_repeat_ngram_size,
    )
