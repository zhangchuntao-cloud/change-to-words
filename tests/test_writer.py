import tempfile
import unittest
from pathlib import Path

from change_to_words.writer import write_text


class WriteTextTests(unittest.TestCase):
    def test_creates_utf8_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            self.assertTrue(write_text(target, "你好\nworld\n"))
            self.assertEqual(target.read_text(encoding="utf-8"), "你好\nworld\n")

    def test_skips_existing_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("old", encoding="utf-8")
            self.assertFalse(write_text(target, "new"))
            self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_overwrites_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a.txt"
            target.write_text("old", encoding="utf-8")
            self.assertTrue(write_text(target, "new", overwrite=True))
            self.assertEqual(target.read_text(encoding="utf-8"), "new")

    def test_creates_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "a.txt"
            self.assertTrue(write_text(target, "hello\n"))
            self.assertEqual(target.read_text(encoding="utf-8"), "hello\n")

    def test_no_temp_files_left(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_text(root / "a.txt", "hello\n")
            self.assertEqual([p.name for p in root.iterdir()], ["a.txt"])


if __name__ == "__main__":
    unittest.main()
