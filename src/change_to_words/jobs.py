from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

MEDIA_EXTENSIONS = frozenset(
    {
        # 音频
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
        ".aiff",
        ".aif",
        ".caf",
        ".amr",
        # 视频
        ".mp4",
        ".mov",
        ".m4v",
        ".mkv",
        ".webm",
        ".avi",
        ".flv",
        ".mpeg",
        ".mpg",
        ".wmv",
        ".ts",
    }
)

OUTPUT_EXTENSIONS = frozenset({".txt", ".srt", ".vtt", ".docx", ".md"})


class JobError(Exception):
    """输入或输出规划错误。"""


@dataclass(frozen=True)
class Source:
    path: Path
    relpath: Path


@dataclass(frozen=True)
class Job:
    source: Path
    target: Path


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTENSIONS


def collect_sources(
    inputs: Iterable[str], recursive: bool, warnings: List[str]
) -> List[Source]:
    """展开输入参数，返回去重后的音视频文件列表。"""
    sources: List[Source] = []
    seen: Set[Path] = set()

    for raw in inputs:
        path = Path(raw).expanduser()
        if not path.exists():
            raise JobError(f"输入不存在: {path}")

        if path.is_file():
            # 显式指定的文件不检查扩展名，交给解码器判断。
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                sources.append(Source(path=path, relpath=Path(path.name)))
            continue

        if not path.is_dir():
            raise JobError(f"不是文件或目录: {path}")

        candidates: List[Path] = []
        if recursive:
            for root, dirs, files in os.walk(str(path), followlinks=False):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for name in sorted(files):
                    if name.startswith("."):
                        continue
                    candidate = Path(root) / name
                    if is_media_file(candidate):
                        candidates.append(candidate)
        else:
            try:
                entries = sorted(path.iterdir())
            except OSError as exc:
                raise JobError(f"无法读取目录 {path}: {exc}") from exc
            for candidate in entries:
                if candidate.name.startswith(".") or not candidate.is_file():
                    continue
                if is_media_file(candidate):
                    candidates.append(candidate)

        if not candidates:
            warnings.append(f"目录中没有找到音视频文件: {path}")

        for candidate in candidates:
            key = candidate.resolve()
            if key in seen:
                continue
            seen.add(key)
            sources.append(Source(path=candidate, relpath=candidate.relative_to(path)))

    return sources


def plan_jobs(
    sources: List[Source], output: Optional[Path], extension: str = ".txt"
) -> List[Job]:
    """计算每个输入对应的输出路径，并做冲突和覆盖检查。"""
    if not sources:
        raise JobError("没有可处理的音视频文件")
    if extension not in OUTPUT_EXTENSIONS:
        raise ValueError(f"不支持输出扩展名: {extension}")

    jobs: List[Job] = []

    if output is not None:
        output = Path(output).expanduser()
        output_is_file = output.exists() and output.is_file()
        if not output.exists() and output.suffix.lower() in OUTPUT_EXTENSIONS:
            output_is_file = True

        if output_is_file:
            if len(sources) != 1:
                raise JobError("-o 指向具体文件时只能处理一个输入文件")
            if output.suffix.lower() != extension:
                raise JobError(
                    f"输出文件扩展名应为 {extension}，当前为 "
                    f"{output.suffix or '无扩展名'}: {output}"
                )
            jobs.append(Job(source=sources[0].path, target=output))
        else:
            for source in sources:
                target = output / source.relpath.with_suffix(extension)
                jobs.append(Job(source=source.path, target=target))
    else:
        for source in sources:
            jobs.append(Job(source=source.path, target=source.path.with_suffix(extension)))

    source_paths: Set[Path] = {job.source.resolve() for job in jobs}
    targets: Set[Path] = set()
    for job in jobs:
        target = job.target.resolve()
        if target in source_paths:
            raise JobError(f"输出文件会覆盖输入文件: {job.target}")
        if target in targets:
            raise JobError(f"多个输入会写入同一个输出文件: {job.target}")
        targets.add(target)

    return jobs
