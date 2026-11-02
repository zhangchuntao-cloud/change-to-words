import tempfile
import time
import unittest
from pathlib import Path

from change_to_words.transcriber import TextSegment, TranscriptionResult

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
        download = self.client.get(f"/api/jobs/{job_id}/download?fmt=md")
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

    def test_history_empty(self):
        self.assertEqual(self.client.get("/api/jobs").json()["jobs"], [])


if __name__ == "__main__":
    unittest.main()
