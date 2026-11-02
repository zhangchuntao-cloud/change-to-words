from __future__ import annotations

import argparse
import atexit
import mimetypes
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from . import __version__
from .jobs import MEDIA_EXTENSIONS
from .subtitle import segments_to_srt, segments_to_vtt
from .text import segments_to_text
from .transcriber import TextSegment, Transcriber, load_model, wrap_model

MODEL_CHOICES = ("tiny", "base", "small", "medium", "large-v3")
VIDEO_EXTENSIONS = frozenset(
    {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".flv", ".mpeg", ".mpg", ".wmv", ".ts"}
)


@dataclass
class WebJob:
    id: str
    filename: str
    source: Path
    model: str
    language: Optional[str]
    vad_filter: bool
    initial_prompt: Optional[str]
    status: str = "queued"
    progress: float = 0.0
    processed: float = 0.0
    duration: Optional[float] = None
    language_detected: Optional[str] = None
    language_probability: Optional[float] = None
    segments: List[TextSegment] = field(default_factory=list)
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None


class ModelPool:
    """按模型名缓存底层 WhisperModel；切换模型时释放旧模型以控制内存。"""

    def __init__(
        self,
        *,
        download_root: Optional[str] = None,
        offline: bool = False,
    ) -> None:
        self._download_root = download_root
        self._offline = offline
        self._models: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, model: str) -> Any:
        with self._lock:
            if model not in self._models:
                self._models.clear()
                self._models[model] = load_model(
                    model,
                    download_root=self._download_root,
                    offline=self._offline,
                )
            return self._models[model]


TranscriberFactory = Callable[..., Transcriber]


class JobManager:
    def __init__(
        self,
        *,
        upload_dir: Path,
        model_pool: Any,
        max_workers: int = 1,
        transcriber_factory: Optional[TranscriberFactory] = None,
    ) -> None:
        self._upload_dir = Path(upload_dir)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._model_pool = model_pool
        self._factory: TranscriberFactory = transcriber_factory or (
            lambda model_obj, **kwargs: wrap_model(model_obj, **kwargs)
        )
        self._jobs: Dict[str, WebJob] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="ctw-job"
        )

    def create(
        self,
        *,
        filename: str,
        source: Path,
        model: str,
        language: Optional[str],
        vad_filter: bool,
        initial_prompt: Optional[str],
    ) -> WebJob:
        job = WebJob(
            id=uuid.uuid4().hex,
            filename=filename,
            source=Path(source),
            model=model,
            language=language,
            vad_filter=vad_filter,
            initial_prompt=initial_prompt,
        )
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job)
        return job

    def _run(self, job: WebJob) -> None:
        try:
            with self._lock:
                job.status = "loading"
            model_obj = self._model_pool.get(job.model)
            transcriber = self._factory(
                model_obj,
                language=job.language,
                vad_filter=job.vad_filter,
                initial_prompt=job.initial_prompt,
            )
            with self._lock:
                job.status = "running"

            def on_progress(segment: TextSegment, duration: Optional[float]) -> None:
                with self._lock:
                    job.segments.append(segment)
                    job.processed = segment.end
                    if duration and duration > 0:
                        job.duration = duration
                        job.progress = min(100.0, max(0.0, segment.end / duration * 100.0))

            result = transcriber.transcribe(job.source, progress=on_progress)
            with self._lock:
                job.segments = list(result.segments)
                job.duration = result.duration
                job.language_detected = result.language
                job.language_probability = result.language_probability
                job.progress = 100.0
                job.status = "done"
                job.finished_at = time.time()
        except Exception as exc:
            with self._lock:
                job.status = "error"
                job.error = str(exc) or exc.__class__.__name__
                job.finished_at = time.time()

    def get(self, job_id: str) -> Optional[WebJob]:
        with self._lock:
            return self._jobs.get(job_id)

    def summaries(self) -> List[Dict[str, Any]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [self._summary(job) for job in jobs[:50]]

    def detail(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                **self._summary(job),
                "language": job.language,
                "language_probability": job.language_probability,
                "initial_prompt": job.initial_prompt,
                "segments": [
                    {"start": segment.start, "end": segment.end, "text": segment.text}
                    for segment in job.segments
                ],
            }

    def snapshot(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return {
                "filename": job.filename,
                "status": job.status,
                "segments": list(job.segments),
            }

    def delete(self, job_id: str) -> str:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return "missing"
            if job.status in ("queued", "loading", "running"):
                return "busy"
            self._jobs.pop(job_id, None)
            source = job.source
        source.unlink(missing_ok=True)
        return "deleted"

    def shutdown(self) -> None:
        self._executor.shutdown(wait=True)

    @staticmethod
    def _summary(job: WebJob) -> Dict[str, Any]:
        return {
            "id": job.id,
            "filename": job.filename,
            "model": job.model,
            "status": job.status,
            "progress": round(job.progress, 1),
            "processed": round(job.processed, 2),
            "duration": job.duration,
            "language_detected": job.language_detected,
            "segment_count": len(job.segments),
            "error": job.error,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
        }


def create_app(
    *,
    default_model: str = "small",
    download_root: Optional[str] = None,
    offline: bool = False,
    max_upload_mb: int = 2048,
    job_manager: Optional[JobManager] = None,
) -> FastAPI:
    if job_manager is None:
        upload_dir = Path(tempfile.mkdtemp(prefix="ctw-web-"))
        atexit.register(shutil.rmtree, upload_dir, ignore_errors=True)
        job_manager = JobManager(
            upload_dir=upload_dir,
            model_pool=ModelPool(download_root=download_root, offline=offline),
        )
        atexit.register(job_manager.shutdown)

    manager = job_manager
    max_upload_bytes = max(1, max_upload_mb) * 1024 * 1024
    index_path = Path(__file__).with_name("web") / "index.html"
    allowed_models = set(MODEL_CHOICES) | {default_model}

    app = FastAPI(
        title="change-to-words",
        version=__version__,
        description="本地离线音频/视频转文字",
    )
    app.state.manager = manager

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        if not index_path.exists():
            raise HTTPException(status_code=500, detail="Web 页面文件缺失")
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        return {
            "status": "ok",
            "version": __version__,
            "default_model": default_model,
            "models": list(MODEL_CHOICES),
        }

    @app.get("/api/jobs")
    def list_jobs() -> Dict[str, Any]:
        return {"jobs": manager.summaries()}

    @app.post("/api/jobs", status_code=202)
    async def create_job(
        file: UploadFile = File(...),
        model: str = Form(default_model),
        language: str = Form("auto"),
        initial_prompt: str = Form(""),
        vad: bool = Form(True),
    ) -> Dict[str, Any]:
        filename = Path(file.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="缺少文件名")
        suffix = Path(filename).suffix.lower()
        if suffix not in MEDIA_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {suffix or '无扩展名'}",
            )

        model = (model or default_model).strip()
        if model not in allowed_models:
            raise HTTPException(status_code=400, detail=f"不支持的模型: {model}")

        language_value = language.strip()
        language_value = (
            None
            if language_value.lower() in ("", "auto")
            else language_value
        )
        prompt = initial_prompt.strip()[:1000] or None

        job_id = uuid.uuid4().hex
        destination = manager._upload_dir / f"{job_id}{suffix}"
        total = 0
        try:
            with destination.open("wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"文件超过 {max_upload_mb} MB 限制",
                        )
                    handle.write(chunk)
        except HTTPException:
            destination.unlink(missing_ok=True)
            raise
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"保存文件失败: {exc}") from exc
        finally:
            await file.close()

        if total == 0:
            destination.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="文件为空")

        job = manager.create(
            filename=filename,
            source=destination,
            model=model,
            language=language_value,
            vad_filter=bool(vad),
            initial_prompt=prompt,
        )
        return {"id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    def job_detail(job_id: str) -> Dict[str, Any]:
        detail = manager.detail(job_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        return detail

    @app.get("/api/jobs/{job_id}/media")
    def job_media(job_id: str) -> FileResponse:
        job = manager.get(job_id)
        if job is None or not job.source.exists():
            raise HTTPException(status_code=404, detail="任务或文件不存在")
        media_type = mimetypes.guess_type(job.filename)[0] or "application/octet-stream"
        return FileResponse(job.source, media_type=media_type)

    @app.get("/api/jobs/{job_id}/download")
    def job_download(job_id: str, fmt: str = "txt") -> Response:
        snapshot = manager.snapshot(job_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        if snapshot["status"] != "done":
            raise HTTPException(status_code=409, detail="任务尚未完成")

        segments = snapshot["segments"]
        if fmt == "txt":
            content = segments_to_text(segment.text for segment in segments)
            media_type = "text/plain"
        elif fmt == "srt":
            content = segments_to_srt(segments)
            media_type = "application/x-subrip"
        elif fmt == "vtt":
            content = segments_to_vtt(segments)
            media_type = "text/vtt"
        else:
            raise HTTPException(status_code=400, detail="fmt 只能是 txt、srt 或 vtt")

        stem = Path(snapshot["filename"]).stem or "transcript"
        download_name = f"{stem}.{fmt}"
        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(download_name)}"
        }
        return Response(
            content=content.encode("utf-8"),
            media_type=f"{media_type}; charset=utf-8",
            headers=headers,
        )

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> Dict[str, Any]:
        result = manager.delete(job_id)
        if result == "missing":
            raise HTTPException(status_code=404, detail="任务不存在")
        if result == "busy":
            raise HTTPException(status_code=409, detail="任务仍在进行中，无法删除")
        return {"deleted": True}

    return app


def serve_main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ctw serve",
        description="启动本地 Web 界面（拖拽上传、录音、进度、字幕下载）",
    )
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认仅本机")
    parser.add_argument("--port", type=int, default=8000, help="端口，默认 8000")
    parser.add_argument(
        "-m",
        "--model",
        default="small",
        help="默认模型，默认 small",
    )
    parser.add_argument("--download-root", type=Path, default=None, help="模型缓存目录")
    parser.add_argument("--offline", action="store_true", help="只使用已缓存模型")
    parser.add_argument(
        "--max-upload-mb",
        type=int,
        default=2048,
        help="单个上传文件大小上限（MB），默认 2048",
    )
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args(argv)

    app = create_app(
        default_model=args.model,
        download_root=(
            str(args.download_root) if args.download_root is not None else None
        ),
        offline=args.offline,
        max_upload_mb=args.max_upload_mb,
    )

    display_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{display_host}:{args.port}"
    print(f"change-to-words Web 界面: {url}")
    print("按 Ctrl-C 停止。")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "警告: 当前监听地址允许局域网访问，请确认你信任所在网络。",
            file=sys.stderr,
        )

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
