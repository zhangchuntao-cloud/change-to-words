from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional, TextIO

from . import __version__
from .jobs import Job, JobError, collect_sources, plan_jobs
from .markdown import segments_to_markdown
from .subtitle import segments_to_srt, segments_to_vtt
from .text import segments_to_text
from .transcriber import (
    ProgressCallback,
    TextSegment,
    Transcriber,
    create_transcriber,
)
from .word import segments_to_docx
from .writer import write_bytes, write_text

TranscriberFactory = Callable[..., Transcriber]


def build_transcriber(
    *,
    model: str,
    language: Optional[str],
    vad_filter: bool,
    download_root: Optional[str],
    offline: bool,
    initial_prompt: Optional[str] = None,
    batch_size: int = 0,
    beam_size: int = 5,
    cpu_threads: int = 0,
    condition_on_previous_text: bool = True,
    no_repeat_ngram_size: int = 0,
) -> Transcriber:
    return create_transcriber(
        model=model,
        language=language,
        vad_filter=vad_filter,
        download_root=download_root,
        offline=offline,
        initial_prompt=initial_prompt,
        batch_size=batch_size,
        beam_size=beam_size,
        cpu_threads=cpu_threads,
        condition_on_previous_text=condition_on_previous_text,
        no_repeat_ngram_size=no_repeat_ngram_size,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="change-to-words",
        description="本地离线音频/视频转文字（faster-whisper）",
        epilog="启动 Web 界面: change-to-words serve --port 8000",
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="INPUT",
        help="音频/视频文件或目录，可指定多个",
    )

    model_group = parser.add_mutually_exclusive_group()
    model_group.add_argument(
        "-m",
        "--model",
        default=None,
        help="模型名或 Hugging Face 仓库 ID，默认 small；可选 tiny/base/small/medium/large-v3",
    )
    model_group.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="本地 CTranslate2 模型目录（与 --model 二选一）",
    )

    parser.add_argument(
        "-l",
        "--language",
        default="auto",
        help="语言代码，如 zh、en、ja；默认 auto 自动识别",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("txt", "srt", "vtt", "docx", "md"),
        default="txt",
        help="输出格式，默认 txt；也可以选 srt、vtt、docx 或 md",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="输出文件（仅单输入，扩展名需与 --format 一致）或输出目录；默认写在源文件旁",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="递归扫描目录",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="覆盖已存在的输出文件",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="关闭静音过滤（默认开启）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="批量推理大小，0 表示关闭；建议 4-16，需要开启静音过滤",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
        help="解码束宽，默认 5；1 最快但准确率略低，越大越准也越慢",
    )
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=0,
        help="CPU 线程数，0 表示自动（默认）",
    )
    parser.add_argument(
        "--condition-on-previous-text",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否使用前一段文本作为上下文；长音频出现重复时用 --no-condition-on-previous-text 关闭",
    )
    parser.add_argument(
        "--no-repeat-ngram-size",
        type=int,
        default=0,
        help="禁止重复的 n-gram 大小，0 表示关闭；出现重复时可设为 3",
    )
    parser.add_argument(
        "--initial-prompt",
        default=None,
        help="术语提示，用于提高人名、专有名词、行业词汇的识别准确率",
    )
    parser.add_argument(
        "--download-root",
        type=Path,
        default=None,
        help="模型缓存目录",
    )
    parser.add_argument(
        "--hf-endpoint",
        default=None,
        help="Hugging Face 镜像，如 https://hf-mirror.com",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="只使用已缓存或本地模型，不联网下载",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="不显示进度和状态信息（错误仍会输出）",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def run(
    argv: Optional[List[str]] = None,
    *,
    transcriber_factory: TranscriberFactory = build_transcriber,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    err = sys.stderr
    extension = f".{args.output_format}"

    if args.batch_size < 0 or args.batch_size == 1 or args.batch_size > 16:
        print("错误: --batch-size 必须是 0（关闭）或 2-16", file=err)
        return 2
    if args.batch_size > 0 and args.no_vad:
        print(
            "错误: 批量推理需要开启静音过滤，不能同时使用 --no-vad",
            file=err,
        )
        return 2
    if args.beam_size < 1 or args.beam_size > 10:
        print("错误: --beam-size 必须在 1-10 之间", file=err)
        return 2
    if args.cpu_threads < 0:
        print("错误: --cpu-threads 不能为负数", file=err)
        return 2
    if args.no_repeat_ngram_size < 0:
        print("错误: --no-repeat-ngram-size 不能为负数", file=err)
        return 2

    try:
        if args.model_path is not None and not args.model_path.is_dir():
            raise JobError(f"本地模型目录不存在: {args.model_path}")
        warnings: List[str] = []
        sources = collect_sources(args.inputs, args.recursive, warnings)
        for warning in warnings:
            if not args.quiet:
                print(f"警告: {warning}", file=err)
        jobs = plan_jobs(sources, args.output, extension)
    except JobError as exc:
        print(f"错误: {exc}", file=err)
        return 2

    if args.hf_endpoint:
        endpoint = args.hf_endpoint.strip()
        if not endpoint.startswith(("http://", "https://")):
            print("错误: --hf-endpoint 必须是 http(s) URL", file=err)
            return 2
        os.environ["HF_ENDPOINT"] = endpoint.rstrip("/")
        # 部分镜像不支持 Xet 传输，强制走普通 HTTP 下载。
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        if not args.quiet:
            print(f"使用 Hugging Face 镜像: {os.environ['HF_ENDPOINT']}", file=err)

    pending: List[Job] = []
    skipped: List[Job] = []
    for job in jobs:
        if job.target.exists() and not args.overwrite:
            skipped.append(job)
            if not args.quiet:
                print(f"跳过（已存在）: {job.target}", file=err)
        else:
            pending.append(job)

    if not pending:
        if not args.quiet:
            print(f"完成：0 个写入，{len(skipped)} 个跳过", file=err)
        return 0

    model_ref = (
        str(args.model_path)
        if args.model_path is not None
        else (args.model or "small")
    )
    language = (
        None
        if args.language.strip().lower() in ("", "auto")
        else args.language.strip()
    )

    if not args.quiet:
        print(f"加载模型: {model_ref}（首次使用会自动下载）", file=err)

    try:
        transcriber = transcriber_factory(
            model=model_ref,
            language=language,
            vad_filter=not args.no_vad,
            download_root=(
                str(args.download_root) if args.download_root is not None else None
            ),
            offline=args.offline,
            initial_prompt=args.initial_prompt,
            batch_size=args.batch_size,
            beam_size=args.beam_size,
            cpu_threads=args.cpu_threads,
            condition_on_previous_text=args.condition_on_previous_text,
            no_repeat_ngram_size=args.no_repeat_ngram_size,
        )
    except KeyboardInterrupt:
        print("\n已取消", file=err)
        return 130
    except Exception as exc:
        print(f"错误: 模型加载失败: {exc}", file=err)
        print(
            "提示: 国内网络可加 --hf-endpoint https://hf-mirror.com，"
            "或用 --model-path 指定本地模型。",
            file=err,
        )
        return 1

    written = 0
    failed = 0
    total = len(pending)
    progress_enabled = not args.quiet and _is_tty(err)

    for index, job in enumerate(pending, start=1):
        if not args.quiet:
            print(f"[{index}/{total}] 转写: {job.source}", file=err)
        progress = _make_progress(err) if progress_enabled else None

        try:
            result = transcriber.transcribe(job.source, progress=progress)
            if progress_enabled:
                err.write("\r\033[K")
                err.flush()

            if args.output_format == "docx":
                wrote = write_bytes(
                    job.target,
                    segments_to_docx(result.segments),
                    overwrite=args.overwrite,
                )
            else:
                if args.output_format == "srt":
                    content = segments_to_srt(result.segments)
                elif args.output_format == "vtt":
                    content = segments_to_vtt(result.segments)
                elif args.output_format == "md":
                    content = segments_to_markdown(
                        segment.text for segment in result.segments
                    )
                else:
                    content = segments_to_text(
                        segment.text for segment in result.segments
                    )

                wrote = write_text(job.target, content, overwrite=args.overwrite)

            if not wrote:
                skipped.append(job)
                if not args.quiet:
                    print(f"    跳过（已存在）: {job.target}", file=err)
                continue

            written += 1
            if not args.quiet:
                details = f"{len(result.segments)} 段"
                if result.language:
                    details += f"，语言 {result.language}"
                    if result.language_probability is not None:
                        details += f"（{result.language_probability:.0%}）"
                print(f"    已写入: {job.target}（{details}）", file=err)
                has_speech = any(
                    segment.text.strip() for segment in result.segments
                )
                if not has_speech:
                    print("    警告: 未识别到语音内容，已写入空结果", file=err)
        except KeyboardInterrupt:
            if progress_enabled:
                err.write("\n")
            print("\n已取消", file=err)
            return 130
        except Exception as exc:
            if progress_enabled:
                err.write("\r\033[K")
                err.flush()
            failed += 1
            print(f"    失败: {exc}", file=err)

    if not args.quiet:
        print(
            f"完成：{written} 个写入，{len(skipped)} 个跳过，{failed} 个失败",
            file=err,
        )
    return 1 if failed else 0


def _is_tty(stream: TextIO) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, OSError):
        return False


def _format_time(seconds: float) -> str:
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _make_progress(err: TextIO) -> ProgressCallback:
    def on_progress(segment: TextSegment, duration: Optional[float]) -> None:
        if duration and duration > 0:
            percent = min(100.0, max(0.0, segment.end / duration * 100.0))
            err.write(
                f"\r    进度 {percent:5.1f}%  "
                f"{_format_time(segment.end)}/{_format_time(duration)}"
            )
        else:
            err.write(f"\r    已处理 {_format_time(segment.end)}")
        err.flush()

    return on_progress


def _serve(argv: List[str]) -> int:
    try:
        from .web import serve_main
    except ImportError as exc:
        print(f"错误: 无法加载 Web 界面: {exc}", file=sys.stderr)
        print(
            "提示: 请先安装依赖，例如 python -m pip install -e .",
            file=sys.stderr,
        )
        return 1
    return serve_main(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "serve":
        return _serve(args[1:])
    return run(args)
