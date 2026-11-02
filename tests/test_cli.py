import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from change_to_words.cli import run
from change_to_words.transcriber import TextSegment, TranscriptionResult


class FakeTranscriber:
    def __init__(self, texts_by_path=None, fail_paths=()):
        self.texts_by_path = texts_by_path or {}
        self.fail_paths = {Path(p) for p in fail_paths}
        self.calls = []

    def transcribe(self, path, progress=None):
        path = Path(path)
        self.calls.append(path)
        if path in self.fail_paths:
            raise RuntimeError("decode failed")
        texts = self.texts_by_path.get(path, [" Hello world."])
        segments = [
            TextSegment(text=text, start=float(i), end=float(i + 1))
            for i, text in enumerate(texts)
        ]
        for segment in segments:
            if progress is not None:
                progress(segment, float(len(segments)))
        return TranscriptionResult(
            segments=tuple(segments),
            language="en",
            language_probability=0.99,
            duration=float(len(segments)),
        )


class Factory:
    def __init__(self, transcriber):
        self.transcriber = transcriber
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.transcriber


def make_audio(root, name="a.mp3"):
    path = Path(root) / name
    path.write_bytes(b"not really audio")
    return path


class CliTests(unittest.TestCase):
    def run_cli(self, argv, factory):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = run(argv, transcriber_factory=factory)
        return code, stderr.getvalue()

    def test_writes_txt_beside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            fake = FakeTranscriber()
            factory = Factory(fake)
            code, stderr = self.run_cli([str(audio)], factory)
            self.assertEqual(code, 0)
            self.assertEqual(
                (Path(tmp) / "a.txt").read_text(encoding="utf-8"),
                "Hello world.\n",
            )
            self.assertEqual(fake.calls, [audio])
            self.assertEqual(factory.calls[0]["model"], "small")
            self.assertIsNone(factory.calls[0]["language"])
            self.assertTrue(factory.calls[0]["vad_filter"])
            self.assertIsNone(factory.calls[0]["initial_prompt"])
            self.assertIn("已写入", stderr)

    def test_output_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "out"
            code, _ = self.run_cli(
                ["-o", str(out), str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                (out / "a.txt").read_text(encoding="utf-8"),
                "Hello world.\n",
            )

    def test_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.txt"
            code, _ = self.run_cli(
                ["-o", str(out), str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertEqual(out.read_text(encoding="utf-8"), "Hello world.\n")

    def test_srt_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.srt"
            code, _ = self.run_cli(
                ["--format", "srt", "-o", str(out), str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                out.read_text(encoding="utf-8"),
                "1\n00:00:00,000 --> 00:00:01,000\nHello world.\n",
            )

    def test_vtt_default_output_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, _ = self.run_cli(
                ["--format", "vtt", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            out = Path(tmp) / "a.vtt"
            self.assertTrue(out.exists())
            self.assertEqual(
                out.read_text(encoding="utf-8"),
                "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello world.\n",
            )

    def test_docx_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.docx"
            code, _ = self.run_cli(
                ["--format", "docx", "-o", str(out), str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 0)
            data = out.read_bytes()
            self.assertTrue(data.startswith(b"PK"))
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                document = archive.read("word/document.xml").decode("utf-8")
            self.assertIn("Hello world.", document)

    def test_docx_default_output_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, _ = self.run_cli(
                ["--format", "docx", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "a.docx").exists())

    def test_docx_output_extension_mismatch_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.txt"
            code, stderr = self.run_cli(
                ["--format", "docx", "-o", str(out), str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("扩展名", stderr)

    def test_skips_existing_docx_without_loading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            (Path(tmp) / "a.docx").write_bytes(b"old")
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                ["--format", "docx", str(audio)], factory
            )
            self.assertEqual(code, 0)
            self.assertEqual(factory.calls, [])
            self.assertEqual((Path(tmp) / "a.docx").read_bytes(), b"old")

    def test_markdown_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.md"
            fake = FakeTranscriber({audio: ["Hello world.", "Second line."]})
            code, _ = self.run_cli(
                ["--format", "md", "-o", str(out), str(audio)],
                Factory(fake),
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                out.read_text(encoding="utf-8"),
                "Hello world.\n\nSecond line.\n",
            )

    def test_markdown_default_output_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, _ = self.run_cli(
                ["--format", "md", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "a.md").exists())

    def test_output_extension_mismatch_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            out = Path(tmp) / "result.txt"
            code, stderr = self.run_cli(
                ["--format", "srt", "-o", str(out), str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("扩展名", stderr)

    def test_skips_existing_without_loading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            (Path(tmp) / "a.txt").write_text("old\n", encoding="utf-8")
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli([str(audio)], factory)
            self.assertEqual(code, 0)
            self.assertEqual(factory.calls, [])
            self.assertEqual(
                (Path(tmp) / "a.txt").read_text(encoding="utf-8"), "old\n"
            )

    def test_overwrite_replaces_existing(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            (Path(tmp) / "a.txt").write_text("old\n", encoding="utf-8")
            code, _ = self.run_cli(
                ["--overwrite", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                (Path(tmp) / "a.txt").read_text(encoding="utf-8"),
                "Hello world.\n",
            )

    def test_batch_continues_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = make_audio(tmp, "good.mp3")
            bad = make_audio(tmp, "bad.mp3")
            fake = FakeTranscriber(fail_paths=[bad])
            code, stderr = self.run_cli([str(good), str(bad)], Factory(fake))
            self.assertEqual(code, 1)
            self.assertTrue((Path(tmp) / "good.txt").exists())
            self.assertFalse((Path(tmp) / "bad.txt").exists())
            self.assertIn("失败", stderr)

    def test_missing_input_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self.run_cli(
                [str(Path(tmp) / "missing.mp3")],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)

    def test_empty_directory_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self.run_cli([tmp], Factory(FakeTranscriber()))
            self.assertEqual(code, 2)

    def test_duplicate_output_targets_return_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d1 = root / "d1"
            d2 = root / "d2"
            d1.mkdir()
            d2.mkdir()
            audio1 = make_audio(d1)
            audio2 = make_audio(d2)
            code, _ = self.run_cli(
                ["-o", str(root / "out"), str(audio1), str(audio2)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)

    def test_model_load_failure_returns_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)

            def broken_factory(**kwargs):
                raise RuntimeError("no network")

            code, stderr = self.run_cli([str(audio)], broken_factory)
            self.assertEqual(code, 1)
            self.assertIn("模型加载失败", stderr)

    def test_cli_options_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                [
                    "-m",
                    "tiny",
                    "-l",
                    "zh",
                    "--no-vad",
                    "--offline",
                    str(audio),
                ],
                factory,
            )
            self.assertEqual(code, 0)
            self.assertEqual(factory.calls[0]["model"], "tiny")
            self.assertEqual(factory.calls[0]["language"], "zh")
            self.assertFalse(factory.calls[0]["vad_filter"])
            self.assertTrue(factory.calls[0]["offline"])

    def test_batch_size_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                ["--batch-size", "8", str(audio)], factory
            )
            self.assertEqual(code, 0)
            self.assertEqual(factory.calls[0]["batch_size"], 8)

    def test_invalid_batch_size_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            for value in ("1", "20", "-1"):
                with self.subTest(value=value):
                    code, stderr = self.run_cli(
                        ["--batch-size", value, str(audio)],
                        Factory(FakeTranscriber()),
                    )
                    self.assertEqual(code, 2)
                    self.assertIn("batch-size", stderr)

    def test_batch_size_requires_vad_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["--batch-size", "8", "--no-vad", str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("静音过滤", stderr)

    def test_beam_size_and_cpu_threads_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                ["--beam-size", "1", "--cpu-threads", "4", str(audio)],
                factory,
            )
            self.assertEqual(code, 0)
            self.assertEqual(factory.calls[0]["beam_size"], 1)
            self.assertEqual(factory.calls[0]["cpu_threads"], 4)

    def test_invalid_beam_size_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["--beam-size", "0", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 2)
            self.assertIn("beam-size", stderr)

    def test_negative_cpu_threads_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["--cpu-threads", "-1", str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("cpu-threads", stderr)

    def test_anti_repeat_options_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                [
                    "--no-condition-on-previous-text",
                    "--no-repeat-ngram-size",
                    "3",
                    str(audio),
                ],
                factory,
            )
            self.assertEqual(code, 0)
            self.assertFalse(factory.calls[0]["condition_on_previous_text"])
            self.assertEqual(factory.calls[0]["no_repeat_ngram_size"], 3)

    def test_negative_no_repeat_ngram_size_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["--no-repeat-ngram-size", "-1", str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("no-repeat-ngram-size", stderr)

    def test_initial_prompt_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            factory = Factory(FakeTranscriber())
            code, _ = self.run_cli(
                ["--initial-prompt", "百度智能云，CTranslate2", str(audio)],
                factory,
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                factory.calls[0]["initial_prompt"], "百度智能云，CTranslate2"
            )

    def test_quiet_suppresses_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["-q", str(audio)], Factory(FakeTranscriber())
            )
            self.assertEqual(code, 0)
            self.assertEqual(stderr, "")

    def test_invalid_hf_endpoint_returns_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = make_audio(tmp)
            code, stderr = self.run_cli(
                ["--hf-endpoint", "ftp://example.com", str(audio)],
                Factory(FakeTranscriber()),
            )
            self.assertEqual(code, 2)
            self.assertIn("hf-endpoint", stderr)


if __name__ == "__main__":
    unittest.main()
