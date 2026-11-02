import unittest

from change_to_words.markdown import segments_to_markdown


class MarkdownTests(unittest.TestCase):
    def test_one_paragraph_per_segment(self):
        self.assertEqual(
            segments_to_markdown([" Hello  world. ", "", "Second line."]),
            "Hello world.\n\nSecond line.\n",
        )

    def test_empty_input_returns_empty_string(self):
        self.assertEqual(segments_to_markdown([]), "")
        self.assertEqual(segments_to_markdown(["", "   "]), "")

    def test_matches_txt_cleanup(self):
        texts = [" 你好，世界 ", "Hello   world.", "  ", "多行\t文本"]
        self.assertEqual(
            segments_to_markdown(texts),
            "你好，世界\n\nHello world.\n\n多行 文本\n",
        )


if __name__ == "__main__":
    unittest.main()
