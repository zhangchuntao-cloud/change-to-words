import unittest

from change_to_words.subtitle import segments_to_srt, segments_to_vtt
from change_to_words.transcriber import TextSegment


class SubtitleTests(unittest.TestCase):
    def test_srt_formats_cues(self):
        segments = [
            TextSegment(text=" Hello world.", start=0.0, end=1.234),
            TextSegment(text=" Second line.", start=1.5, end=3.0),
        ]
        self.assertEqual(
            segments_to_srt(segments),
            "1\n00:00:00,000 --> 00:00:01,234\nHello world.\n\n"
            "2\n00:00:01,500 --> 00:00:03,000\nSecond line.\n",
        )

    def test_srt_skips_empty_segments_and_numbers_contiguously(self):
        segments = [
            TextSegment(text="   ", start=0.0, end=1.0),
            TextSegment(text=" First.", start=1.0, end=2.0),
        ]
        self.assertEqual(
            segments_to_srt(segments),
            "1\n00:00:01,000 --> 00:00:02,000\nFirst.\n",
        )

    def test_srt_end_is_not_before_start(self):
        segments = [TextSegment(text="x", start=2.0, end=2.0)]
        self.assertIn("00:00:02,000 --> 00:00:02,001", segments_to_srt(segments))

    def test_srt_clamps_negative_start(self):
        segments = [TextSegment(text="x", start=-1.0, end=0.5)]
        self.assertIn("00:00:00,000 --> 00:00:00,500", segments_to_srt(segments))

    def test_srt_empty(self):
        self.assertEqual(segments_to_srt([]), "")

    def test_vtt_has_header_and_dot_timestamps(self):
        segments = [TextSegment(text=" Hello.", start=0.0, end=1.234)]
        self.assertEqual(
            segments_to_vtt(segments),
            "WEBVTT\n\n00:00:00.000 --> 00:00:01.234\nHello.\n",
        )

    def test_vtt_empty_still_has_header(self):
        self.assertEqual(segments_to_vtt([]), "WEBVTT\n")

    def test_long_timestamp_rolls_over_hours(self):
        segments = [TextSegment(text="x", start=3661.5, end=3662.0)]
        self.assertIn("01:01:01,500 --> 01:01:02,000", segments_to_srt(segments))


if __name__ == "__main__":
    unittest.main()
