from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from xml.sax.saxutils import escape

from .text import segments_to_lines
from .transcriber import TextSegment

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

# zipfile 允许的最小时间戳，保证同样输入生成相同字节。
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _strip_illegal_xml_chars(text: str) -> str:
    """去掉 XML 1.0 不允许的控制字符和孤立代理项。

    文本已经过 normalize_line 处理，不会包含制表符或换行。
    """
    return "".join(
        char
        for char in text
        if 0x20 <= ord(char) <= 0xD7FF
        or 0xE000 <= ord(char) <= 0xFFFD
        or 0x10000 <= ord(char) <= 0x10FFFF
    )

_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.'
    'wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_RELS_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)

_DOCUMENT_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
    "<w:body>%s"
    '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
    'w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    "</w:body></w:document>"
)

_PARAGRAPH_XML = '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
_EMPTY_PARAGRAPH_XML = "<w:p/>"


def segments_to_docx(segments: Iterable[TextSegment]) -> bytes:
    """把转写片段生成最小 OOXML 文档（.docx），一段文字一个段落。"""
    paragraphs = []
    for line in segments_to_lines(segment.text for segment in segments):
        clean = _strip_illegal_xml_chars(line)
        if clean:
            paragraphs.append(_PARAGRAPH_XML % escape(clean))

    body = "".join(paragraphs) or _EMPTY_PARAGRAPH_XML
    return _build_zip(_DOCUMENT_XML % body)


def _build_zip(document_xml: str) -> bytes:
    parts = (
        ("[Content_Types].xml", _CONTENT_TYPES_XML),
        ("_rels/.rels", _RELS_XML),
        ("word/document.xml", document_xml),
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts:
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, content.encode("utf-8"))
    return buffer.getvalue()
