import io
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path

from change_to_words.transcriber import TextSegment, TranscriptionResult
from change_to_words.word import DOCX_MEDIA_TYPE

try:
    from fastapi.testclient import TestClient
    from change_to_words.web import JobManager, create_app
except ImportError:  # Web 依赖未安装时跳过整个模块
    TestClient = None
    JobManager = None
    create_app = None


class FakeTranscriber:
    def __init__(self):
        self.segments = (
            TextSegment(" Hello world.", 0.0, 1.0),
            TextSegment(" Second line.", 1.0, 2.0),
        )

    def transcribe(self, path, progress=None):
        for segment in self.segments:
            if progress is not None:
                progress(segment, 2.0)
        return TranscriptionResult(
            segments=self.segments,
            language="en",
            language_probability=0.99,
            duration=2.0,
        )


class FakeModelPool:
    def get(self, model):
        return "fake-model"


class RecordingFactory:
    def __init__(self):
        self.calls = []

    def __call__(self, model_obj, **kwargs):
        self.calls.append(kwargs)
        return FakeTranscriber()


class BlockingTranscriber:
    def __init__(self, started):
        self.started = started

    def transcribe(self, path, progress=None):
        self.started.set()
        for index in range(500):
            time.sleep(0.01)
            if progress is not None:
                progress(
                    TextSegment("Working.", float(index), float(index + 1)),
                    500.0,
                )
        return TranscriptionResult(
            segments=(TextSegment("Working.", 0.0, 500.0),),
            language="en",
            language_probability=0.99,
            duration=500.0,
        )


@unittest.skipIf(TestClient is None, "Web 依赖未安装")
class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.factory = RecordingFactory()
        self.manager = JobManager(
            upload_dir=Path(self.tmp.name) / "uploads",
            model_pool=FakeModelPool(),
            transcriber_factory=self.factory,
        )
        self.app = create_app(default_model="small", job_manager=self.manager)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.manager.shutdown()
        self.tmp.cleanup()

    def upload(self, name="a.mp3", content=b"fake audio bytes", **overrides):
        data = {
            "model": "small",
            "language": "en",
            "initial_prompt": "",
            "vad": "true",
            "batch_size": "0",
            "beam_size": "5",
            "condition_on_previous_text": "true",
            "no_repeat_ngram_size": "0",
        }
        data.update(overrides)
        return self.client.post(
            "/api/jobs",
            files={"file": (name, content, "application/octet-stream")},
            data=data,
        )

    def wait_done(self, job_id, timeout=5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            detail = self.client.get(f"/api/jobs/{job_id}").json()
            if detail.get("status") in ("done", "error"):
                return detail
            time.sleep(0.02)
        self.fail("任务未在限定时间内结束")

    def test_health(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("small", data["models"])
        self.assertEqual(data["default_model"], "small")

    def test_index_page(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("change-to-words", response.text)
        self.assertIn("开始转写", response.text)
        self.assertIn(">DOCX<", response.text)
        self.assertIn(">MD<", response.text)
        self.assertIn("cancelBtn", response.text)

    def test_upload_transcribe_and_download(self):
        content = b"fake audio bytes"
        response = self.upload(content=content)
        self.assertEqual(response.status_code, 202)
        job_id = response.json()["id"]

        detail = self.wait_done(job_id)
        self.assertEqual(detail["status"], "done", detail.get("error"))
        self.assertEqual(detail["segment_count"], 2)
        self.assertEqual(detail["language_detected"], "en")
        self.assertEqual(detail["segments"][0]["text"], " Hello world.")
        self.assertEqual(self.factory.calls[0]["language"], "en")
        self.assertTrue(self.factory.calls[0]["vad_filter"])

        txt = self.client.get(f"/api/jobs/{job_id}/download?fmt=txt")
        self.assertEqual(txt.status_code, 200)
        self.assertEqual(txt.text, "Hello world.\nSecond line.\n")
        self.assertIn("attachment", txt.headers["content-disposition"])

        srt = self.client.get(f"/api/jobs/{job_id}/download?fmt=srt")
        self.assertEqual(srt.status_code, 200)
        self.assertIn("00:00:00,000 --> 00:00:01,000", srt.text)
        self.assertIn("00:00:01,000 --> 00:00:02,000", srt.text)

        vtt = self.client.get(f"/api/jobs/{job_id}/download?fmt=vtt")
        self.assertEqual(vtt.status_code, 200)
        self.assertTrue(vtt.text.startswith("WEBVTT\n\n"))

        md = self.client.get(f"/api/jobs/{job_id}/download?fmt=md")
        self.assertEqual(md.status_code, 200)
        self.assertTrue(md.headers["content-type"].startswith("text/markdown"))
        self.assertEqual(md.text, "Hello world.\n\nSecond line.\n")
        self.assertIn(".md", md.headers["content-disposition"])

        docx = self.client.get(f"/api/jobs/{job_id}/download?fmt=docx")
        self.assertEqual(docx.status_code, 200)
        self.assertEqual(docx.headers["content-type"], DOCX_MEDIA_TYPE)
        self.assertTrue(docx.content.startswith(b"PK"))
        self.assertIn(".docx", docx.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(docx.content)) as archive:
            document = archive.read("word/document.xml").decode("utf-8")
        self.assertIn("Hello world.", document)
        self.assertIn("Second line.", document)

        media = self.client.get(f"/api/jobs/{job_id}/media")
        self.assertEqual(media.status_code, 200)
        self.assertEqual(media.content, content)

        jobs = self.client.get("/api/jobs").json()["jobs"]
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["id"], job_id)

    def test_auto_language_becomes_none(self):
        response = self.upload(language="auto")
        job_id = response.json()["id"]
        self.wait_done(job_id)
        self.assertIsNone(self.factory.calls[0]["language"])

    def test_initial_prompt_forwarded(self):
        response = self.upload(initial_prompt="  百度智能云  ")
        job_id = response.json()["id"]
        self.wait_done(job_id)
        self.assertEqual(self.factory.calls[0]["initial_prompt"], "百度智能云")

    def test_rejects_unsupported_extension(self):
        response = self.upload(name="a.txt")
        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持的文件类型", response.json()["detail"])

    def test_rejects_unknown_model(self):
        response = self.upload(model="evil-model")
        self.assertEqual(response.status_code, 400)
        self.assertIn("不支持的模型", response.json()["detail"])

    def test_unknown_job_returns_404(self):
        self.assertEqual(self.client.get("/api/jobs/nope").status_code, 404)
        self.assertEqual(
            self.client.get("/api/jobs/nope/download?fmt=txt").status_code, 404
        )
        self.assertEqual(self.client.delete("/api/jobs/nope").status_code, 404)

    def test_invalid_download_format(self):
        response = self.upload()
        job_id = response.json()["id"]
        self.wait_done(job_id)
        download = self.client.get(f"/api/jobs/{job_id}/download?fmt=pdf")
        self.assertEqual(download.status_code, 400)

    def test_delete_done_job(self):
        response = self.upload()
        job_id = response.json()["id"]
        self.wait_done(job_id)
        deleted = self.client.delete(f"/api/jobs/{job_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/jobs").json()["jobs"], [])

    def test_empty_upload_rejected(self):
        response = self.upload(content=b"")
        self.assertEqual(response.status_code, 400)
        self.assertIn("文件为空", response.json()["detail"])

    def test_batch_size_forwarded(self):
        response = self.upload(batch_size="8")
        job_id = response.json()["id"]
        self.wait_done(job_id)
        self.assertEqual(self.factory.calls[0]["batch_size"], 8)

    def test_invalid_batch_size_rejected(self):
        for value in ("1", "20", "-1"):
            with self.subTest(value=value):
                response = self.upload(batch_size=value)
                self.assertEqual(response.status_code, 400, value)

    def test_batch_size_requires_vad(self):
        response = self.upload(batch_size="8", vad="false")
        self.assertEqual(response.status_code, 400)
        self.assertIn("静音过滤", response.json()["detail"])

    def test_beam_size_forwarded(self):
        response = self.upload(beam_size="1")
        job_id = response.json()["id"]
        self.wait_done(job_id)
        self.assertEqual(self.factory.calls[0]["beam_size"], 1)

    def test_invalid_beam_size_rejected(self):
        for value in ("0", "11"):
            with self.subTest(value=value):
                response = self.upload(beam_size=value)
                self.assertEqual(response.status_code, 400, value)

    def test_anti_repeat_options_forwarded(self):
        response = self.upload(
            condition_on_previous_text="false",
            no_repeat_ngram_size="3",
        )
        job_id = response.json()["id"]
        self.wait_done(job_id)
        self.assertFalse(self.factory.calls[0]["condition_on_previous_text"])
        self.assertEqual(self.factory.calls[0]["no_repeat_ngram_size"], 3)

    def test_invalid_no_repeat_ngram_size_rejected(self):
        response = self.upload(no_repeat_ngram_size="-1")
        self.assertEqual(response.status_code, 400)

    def test_cancel_unknown_job_returns_404(self):
        self.assertEqual(
            self.client.post("/api/jobs/nope/cancel").status_code, 404
        )

    def test_cancel_finished_job_returns_finished(self):
        response = self.upload()
        job_id = response.json()["id"]
        self.wait_done(job_id)
        cancel = self.client.post(f"/api/jobs/{job_id}/cancel")
        self.assertEqual(cancel.status_code, 200)
        self.assertEqual(cancel.json()["status"], "finished")

    def test_cancel_running_job(self):
        started = threading.Event()
        manager = JobManager(
            upload_dir=Path(self.tmp.name) / "cancel-uploads",
            model_pool=FakeModelPool(),
            transcriber_factory=lambda model_obj, **kwargs: BlockingTranscriber(
                started
            ),
        )
        client = TestClient(create_app(job_manager=manager))
        try:
            response = client.post(
                "/api/jobs",
                files={"file": ("a.mp3", b"fake", "application/octet-stream")},
                data={
                    "model": "small",
                    "language": "en",
                    "initial_prompt": "",
                    "vad": "true",
                    "batch_size": "0",
                },
            )
            self.assertEqual(response.status_code, 202)
            job_id = response.json()["id"]
            self.assertTrue(started.wait(2))

            cancel = client.post(f"/api/jobs/{job_id}/cancel")
            self.assertEqual(cancel.status_code, 200)
            self.assertEqual(cancel.json()["status"], "cancelling")

            detail = {"status": None}
            deadline = time.time() + 5
            while time.time() < deadline:
                detail = client.get(f"/api/jobs/{job_id}").json()
                if detail["status"] == "cancelled":
                    break
                time.sleep(0.02)
            self.assertEqual(detail["status"], "cancelled")
            self.assertEqual(
                client.delete(f"/api/jobs/{job_id}").status_code, 200
            )
        finally:
            client.close()
            manager.shutdown()

    def test_job_history_is_capped(self):
        manager = JobManager(
            upload_dir=Path(self.tmp.name) / "cap-uploads",
            model_pool=FakeModelPool(),
            transcriber_factory=RecordingFactory(),
            max_jobs=2,
        )
        try:
            sources = []
            for index in range(3):
                source = Path(self.tmp.name) / "cap-uploads" / f"{index}.mp3"
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_bytes(b"x")
                sources.append(source)
                manager.create(
                    filename=f"{index}.mp3",
                    source=source,
                    model="small",
                    language=None,
                    vad_filter=True,
                    initial_prompt=None,
                )
                deadline = time.time() + 2
                while time.time() < deadline:
                    summaries = manager.summaries()
                    if summaries and summaries[0]["status"] == "done":
                        break
                    time.sleep(0.02)
                self.assertEqual(manager.summaries()[0]["status"], "done")

            self.assertEqual(len(manager.summaries()), 2)
            self.assertFalse(sources[0].exists())
        finally:
            manager.shutdown()

    def test_history_empty(self):
        self.assertEqual(self.client.get("/api/jobs").json()["jobs"], [])


if __name__ == "__main__":
    unittest.main()
