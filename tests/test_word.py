import io
import unittest
import zipfile
import xml.etree.ElementTree as ET

from change_to_words.text import segments_to_text
from change_to_words.transcriber import TextSegment
from change_to_words.word import DOCX_MEDIA_TYPE, segments_to_docx

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CT = "{http://schemas.openxmlformats.org/package/2006/content-types}"
REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def read_part(data, name):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(name)


def paragraphs(data):
    root = ET.fromstring(read_part(data, "word/document.xml"))
    result = []
    for paragraph in root.findall(f".//{W}p"):
        result.append("".join(node.text or "" for node in paragraph.iter(f"{W}t")))
    return result


def segments(*texts):
    return [
        TextSegment(text=text, start=float(index), end=float(index + 1))
        for index, text in enumerate(texts)
    ]


class DocxTests(unittest.TestCase):
    def test_package_contains_required_parts(self):
        data = segments_to_docx(segments("Hello world."))
        self.assertTrue(data.startswith(b"PK"))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        self.assertEqual(
            names,
            {"[Content_Types].xml", "_rels/.rels", "word/document.xml"},
        )

    def test_content_types_declares_main_document(self):
        root = ET.fromstring(read_part(segments_to_docx(segments("x")), "[Content_Types].xml"))
        override = root.find(f"{CT}Override")
        self.assertIsNotNone(override)
        self.assertEqual(override.get("PartName"), "/word/document.xml")
        self.assertEqual(
            override.get("ContentType"),
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document.main+xml",
        )

    def test_relationship_targets_document(self):
        root = ET.fromstring(read_part(segments_to_docx(segments("x")), "_rels/.rels"))
        relationship = root.find(f"{REL}Relationship")
        self.assertIsNotNone(relationship)
        self.assertTrue(relationship.get("Type").endswith("/officeDocument"))
        self.assertEqual(relationship.get("Target"), "word/document.xml")

    def test_one_paragraph_per_non_empty_segment(self):
        data = segments_to_docx(segments(" First  line. ", "", "   ", "Second."))
        self.assertEqual(paragraphs(data), ["First line.", "Second."])

    def test_matches_txt_cleanup(self):
        texts = [" 你好，世界 ", "Hello   world.", "  ", "多行\t文本"]
        data = segments_to_docx(segments(*texts))
        self.assertEqual(
            paragraphs(data),
            segments_to_text(iter(texts)).splitlines(),
        )

    def test_escapes_xml_special_characters(self):
        text = 'A & B < C > D "E" \'F\''
        data = segments_to_docx(segments(text))
        self.assertEqual(paragraphs(data), [text])

    def test_removes_illegal_control_characters(self):
        text = "a" + chr(0) + "b" + chr(1) + "c" + chr(0xD800) + "d"
        data = segments_to_docx(segments(text))
        self.assertEqual(paragraphs(data), ["abcd"])
        ET.fromstring(read_part(data, "word/document.xml"))

    def test_empty_transcript_has_one_empty_paragraph(self):
        data = segments_to_docx([])
        self.assertEqual(paragraphs(data), [""])
        ET.fromstring(read_part(data, "word/document.xml"))

    def test_all_blank_segments_have_one_empty_paragraph(self):
        data = segments_to_docx(segments("", "   "))
        self.assertEqual(paragraphs(data), [""])

    def test_output_is_deterministic(self):
        data = segments_to_docx(segments("Hello", "World"))
        self.assertEqual(data, segments_to_docx(segments("Hello", "World")))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))

    def test_media_type_constant(self):
        self.assertEqual(
            DOCX_MEDIA_TYPE,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


if __name__ == "__main__":
    unittest.main()
