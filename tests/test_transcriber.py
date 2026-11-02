import unittest
from pathlib import Path

from change_to_words.transcriber import FasterWhisperTranscriber


class FakeInfo:
    duration = 1.0
    language = "en"
    language_probability = 0.9


class FakeModel:
    def __init__(self):
        self.kwargs = None

    def transcribe(self, path, **kwargs):
        self.kwargs = kwargs
        return iter(()), FakeInfo()


class BatchOptionsTests(unittest.TestCase):
    def test_batch_requires_vad(self):
        with self.assertRaises(ValueError):
            FasterWhisperTranscriber(object(), vad_filter=False, batch_size=8)

    def test_single_batch_is_treated_as_disabled(self):
        transcriber = FasterWhisperTranscriber(object(), batch_size=1)
        self.assertIsNone(transcriber._pipeline)

    def test_zero_batch_is_disabled(self):
        transcriber = FasterWhisperTranscriber(object(), batch_size=0)
        self.assertIsNone(transcriber._pipeline)

    def test_beam_size_forwarded_to_model(self):
        model = FakeModel()
        transcriber = FasterWhisperTranscriber(
            model,
            beam_size=1,
            condition_on_previous_text=False,
            no_repeat_ngram_size=3,
        )
        result = transcriber.transcribe(Path("audio.mp3"))
        self.assertEqual(model.kwargs["beam_size"], 1)
        self.assertFalse(model.kwargs["condition_on_previous_text"])
        self.assertEqual(model.kwargs["no_repeat_ngram_size"], 3)
        self.assertEqual(result.segments, ())
        self.assertEqual(result.language, "en")


if __name__ == "__main__":
    unittest.main()
