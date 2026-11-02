import unittest

from change_to_words.text import segments_to_text


class SegmentsToTextTests(unittest.TestCase):
    def test_joins_segments_one_per_line(self):
        self.assertEqual(
            segments_to_text([" Hello world.", " This is a test. "]),
            "Hello world.\nThis is a test.\n",
        )

    def test_chinese_keeps_original_spacing(self):
        self.assertEqual(
            segments_to_text(["你好，", "这是一个测试。"]),
            "你好，\n这是一个测试。\n",
        )

    def test_skips_empty_segments(self):
        self.assertEqual(segments_to_text(["", "   ", "hello"]), "hello\n")

    def test_empty_input(self):
        self.assertEqual(segments_to_text([]), "")

    def test_collapses_internal_whitespace(self):
        self.assertEqual(segments_to_text(["  hello \n world  "]), "hello world\n")


if __name__ == "__main__":
    unittest.main()
