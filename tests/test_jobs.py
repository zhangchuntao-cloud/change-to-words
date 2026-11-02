import tempfile
import unittest
from pathlib import Path

from change_to_words.jobs import JobError, Source, collect_sources, plan_jobs


class CollectSourcesTests(unittest.TestCase):
    def test_explicit_file_accepts_any_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "a.bin"
            audio.write_bytes(b"x")
            warnings = []
            sources = collect_sources([str(audio)], False, warnings)
            self.assertEqual([s.path for s in sources], [audio])
            self.assertEqual(sources[0].relpath, Path("a.bin"))
            self.assertEqual(warnings, [])

    def test_directory_filters_media_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.mp3").write_bytes(b"x")
            (root / "b.txt").write_text("x")
            (root / ".hidden.mp3").write_bytes(b"x")
            sources = collect_sources([str(root)], False, [])
            self.assertEqual([s.path.name for s in sources], ["a.mp3"])

    def test_recursive_scan_finds_nested_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "sub"
            sub.mkdir()
            (sub / "c.mp4").write_bytes(b"x")
            sources = collect_sources([str(root)], True, [])
            self.assertEqual([s.relpath for s in sources], [Path("sub/c.mp4")])

    def test_deduplicates_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "a.mp3"
            audio.write_bytes(b"x")
            sources = collect_sources([str(audio), str(root)], False, [])
            self.assertEqual(len(sources), 1)

    def test_missing_input_raises(self):
        with self.assertRaises(JobError):
            collect_sources(["/definitely/not/here.mp3"], False, [])

    def test_empty_directory_warns(self):
        with tempfile.TemporaryDirectory() as tmp:
            warnings = []
            sources = collect_sources([tmp], False, warnings)
            self.assertEqual(sources, [])
            self.assertEqual(len(warnings), 1)


class PlanJobsTests(unittest.TestCase):
    def test_default_output_beside_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.mp3", relpath=Path("a.mp3"))
            jobs = plan_jobs([source], None)
            self.assertEqual(jobs[0].target, root / "a.txt")

    def test_output_extension_can_be_srt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.mp3", relpath=Path("a.mp3"))
            jobs = plan_jobs([source], None, ".srt")
            self.assertEqual(jobs[0].target, root / "a.srt")

    def test_output_directory_preserves_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(
                path=root / "in" / "sub" / "a.mp3",
                relpath=Path("sub/a.mp3"),
            )
            jobs = plan_jobs([source], root / "out", ".vtt")
            self.assertEqual(jobs[0].target, root / "out" / "sub" / "a.vtt")

    def test_output_txt_file_for_single_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.mp3", relpath=Path("a.mp3"))
            jobs = plan_jobs([source], root / "result.txt")
            self.assertEqual(jobs[0].target, root / "result.txt")

    def test_output_file_extension_must_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.mp3", relpath=Path("a.mp3"))
            with self.assertRaises(JobError):
                plan_jobs([source], root / "result.txt", ".srt")

    def test_output_file_with_multiple_sources_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [
                Source(path=root / "a.mp3", relpath=Path("a.mp3")),
                Source(path=root / "b.mp3", relpath=Path("b.mp3")),
            ]
            with self.assertRaises(JobError):
                plan_jobs(sources, root / "result.txt")

    def test_duplicate_targets_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [
                Source(path=root / "x" / "a.mp3", relpath=Path("a.mp3")),
                Source(path=root / "y" / "a.mp3", relpath=Path("a.mp3")),
            ]
            with self.assertRaises(JobError):
                plan_jobs(sources, root / "out")

    def test_target_overwriting_another_source_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [
                Source(path=root / "a.mp3", relpath=Path("a.mp3")),
                Source(path=root / "out" / "a.txt", relpath=Path("out/a.txt")),
            ]
            with self.assertRaises(JobError):
                plan_jobs(sources, root / "out", ".txt")

    def test_target_equal_to_source_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.txt", relpath=Path("a.txt"))
            with self.assertRaises(JobError):
                plan_jobs([source], None)

    def test_no_sources_raises(self):
        with self.assertRaises(JobError):
            plan_jobs([], None)

    def test_invalid_extension_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = Source(path=root / "a.mp3", relpath=Path("a.mp3"))
            with self.assertRaises(ValueError):
                plan_jobs([source], None, ".md")


if __name__ == "__main__":
    unittest.main()
