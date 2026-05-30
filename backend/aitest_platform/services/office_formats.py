from __future__ import annotations

import base64
import io
import json
import re
import zlib
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

from aitest_platform.services.file_formats import file_extension, normalize_format


DOCX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
PDF_MIME_TYPE = "application/pdf"
XMIND_MIME_TYPE = "application/vnd.xmind.workbook"
XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ZIP_ENTRY_LIMIT = 200
ZIP_ENTRY_SIZE_LIMIT = 8 * 1024 * 1024
ZIP_TOTAL_SIZE_LIMIT = 32 * 1024 * 1024

_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_REL_NS = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
_SHEET_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
_XMIND_XML_NS = {
    "xmap": "urn:xmind:xmap:xmlns:content:2.0",
    "fo": "http://www.w3.org/1999/XSL/Format",
}

_BLOCK_TYPES = {"heading", "paragraph", "list_item", "table"}
_BINARY_TEXT_FIELDS = (
    "content_base64",
    "contentBase64",
    "raw_content_base64",
    "rawContentBase64",
    "file_base64",
    "fileBase64",
    "base64",
)
_TEXT_FIELDS = (
    "raw_content",
    "rawContent",
    "content",
    "text",
    "raw_text",
    "document",
)
_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)\b(?:authorization|x-api-key|api[_-]?key|token|cookie|password|secret)(\s*[:=]\s*|\s+)(?:Bearer\s+)?[^\s,;}\]\"']+"
)
_PDF_STREAM_RE = re.compile(rb"<<(?P<dict>.*?)>>\s*stream\r?\n(?P<data>.*?)\r?\nendstream", re.S)
_PDF_TEXT_RE = re.compile(rb"(?P<literal>\((?:\\.|[^\\()])*\)|<[^<>]+>)\s*(?:Tj|TJ|'|\")")
_PDF_ARRAY_RE = re.compile(rb"\[(?P<body>.*?)\]\s*TJ", re.S)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")


class OfficeFormatError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedDocument:
    format: str
    text: str
    blocks: list[dict[str, Any]]
    tables: list[dict[str, Any]]
    outline: list[dict[str, Any]]
    warnings: list[str]
    metadata: dict[str, Any]


def parse_document_payload(
    payload: Any,
    *,
    source_type: Any = None,
    filename: Any = None,
    fallback_name: str | None = None,
) -> ParsedDocument:
    data = payload if isinstance(payload, dict) else {"content": payload}
    raw_bytes = _extract_payload_bytes(data)
    normalized_source = normalize_format(source_type)
    normalized_name = file_extension(filename) or file_extension(data.get("source_file_name")) or file_extension(data.get("name"))
    sniffed = _sniff_format(raw_bytes) if raw_bytes else ""
    fmt = normalized_source or normalized_name or sniffed or "text"
    plain_text = _extract_payload_text(data, fallback_name=fallback_name)

    if fmt == "docx":
        return _parse_docx_document(raw_bytes, plain_text, fallback_name or str(filename or data.get("name") or "document"))
    if fmt == "xlsx":
        return _parse_xlsx_document(raw_bytes, plain_text, fallback_name or str(filename or data.get("name") or "workbook"))
    if fmt == "xmind":
        return _parse_xmind_document(raw_bytes, plain_text, fallback_name or str(filename or data.get("name") or "mindmap"))
    if fmt == "pdf":
        return _parse_pdf_document(raw_bytes, plain_text, fallback_name or str(filename or data.get("name") or "document"))
    return _plain_text_document(plain_text or fallback_name or "", fmt=fmt)


def markdown_to_blocks(markdown: str) -> list[dict[str, Any]]:
    lines = (markdown or "").splitlines()
    blocks: list[dict[str, Any]] = []
    paragraph: list[str] = []
    table_lines: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        blocks.append({"type": "paragraph", "text": " ".join(part.strip() for part in paragraph if part.strip()).strip()})
        paragraph.clear()

    def flush_table() -> None:
        if not table_lines:
            return
        rows = [_split_markdown_table_row(line) for line in table_lines]
        body_rows = rows[2:] if len(rows) >= 2 and all(set(cell) <= {"-"} for cell in rows[1]) else rows[1:]
        blocks.append({"type": "table", "rows": [rows[0], *body_rows] if rows else []})
        table_lines.clear()

    for raw_line in lines:
        line = raw_line.rstrip()
        if line.startswith("| "):
            flush_paragraph()
            table_lines.append(line)
            continue
        flush_table()
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            continue
        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_paragraph()
            blocks.append({"type": "heading", "text": heading.group(2).strip(), "level": len(heading.group(1))})
            continue
        list_item = _LIST_RE.match(stripped)
        if list_item:
            flush_paragraph()
            blocks.append({"type": "list_item", "text": list_item.group(1).strip(), "level": 1})
            continue
        paragraph.append(stripped)

    flush_table()
    flush_paragraph()
    return [block for block in blocks if block.get("type") in _BLOCK_TYPES and _block_has_content(block)]


def render_docx_document(title: str, blocks: list[dict[str, Any]]) -> bytes:
    body_parts = [_docx_paragraph(title, style="Title")]
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            level = min(max(int(block.get("level") or 1), 1), 3)
            body_parts.append(_docx_paragraph(str(block.get("text") or ""), style=f"Heading{level}"))
        elif block_type == "list_item":
            body_parts.append(_docx_paragraph(f"- {block.get('text') or ''}"))
        elif block_type == "table":
            rows = _normalize_table_rows(block.get("rows"))
            if rows:
                body_parts.append(_docx_table(rows))
        else:
            body_parts.append(_docx_paragraph(str(block.get("text") or "")))
    body_parts.append('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>')

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
        'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
        'xmlns:o="urn:schemas-microsoft-com:office:office" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        'xmlns:v="urn:schemas-microsoft-com:vml" '
        'xmlns:wp14="http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing" '
        'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
        'xmlns:w10="urn:schemas-microsoft-com:office:word" '
        'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
        'xmlns:wpg="http://schemas.microsoft.com/office/word/2010/wordprocessingGroup" '
        'xmlns:wpi="http://schemas.microsoft.com/office/word/2010/wordprocessingInk" '
        'xmlns:wne="http://schemas.microsoft.com/office/2006/wordml" '
        'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
        'mc:Ignorable="w14 wp14"><w:body>'
        + "".join(body_parts)
        + "</w:body></w:document>"
    )

    created = _ooxml_timestamp()
    styles_xml = _docx_styles_xml()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _docx_content_types())
        archive.writestr("_rels/.rels", _docx_root_relationships())
        archive.writestr("docProps/app.xml", _docx_app_props())
        archive.writestr("docProps/core.xml", _docx_core_props(created))
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("word/_rels/document.xml.rels", _docx_document_relationships())
    return buffer.getvalue()


def render_pdf_document(title: str, blocks: list[dict[str, Any]]) -> bytes:
    lines = _pdf_lines(title, blocks)
    if not lines:
        lines = [title]
    pages = _paginate_lines(lines, max_lines=44)

    objects: list[bytes] = [b""]

    def add_object(value: bytes | str) -> int:
        payload = value.encode("utf-8") if isinstance(value, str) else value
        objects.append(payload)
        return len(objects) - 1

    font_id = add_object(
        b"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H "
        b"/DescendantFonts [<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>] >>"
    )
    content_ids: list[int] = []
    page_ids: list[int] = []
    pages_id = add_object(b"<< /Type /Pages /Count 0 /Kids [] >>")
    for page_lines in pages:
        stream = _pdf_content_stream(page_lines)
        content_id = add_object(
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"
        )
        page_id = add_object(
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {content_id} 0 R >>"
        )
        content_ids.append(content_id)
        page_ids.append(page_id)
    objects[pages_id] = f"<< /Type /Pages /Count {len(page_ids)} /Kids [{' '.join(f'{page_id} 0 R' for page_id in page_ids)}] >>".encode("utf-8")
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    result = io.BytesIO()
    result.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index in range(1, len(objects)):
        offsets.append(result.tell())
        result.write(f"{index} 0 obj\n".encode("ascii"))
        result.write(objects[index])
        result.write(b"\nendobj\n")
    xref_offset = result.tell()
    result.write(f"xref\n0 {len(objects)}\n".encode("ascii"))
    result.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.write(
        f"trailer\n<< /Size {len(objects)} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii")
    )
    return result.getvalue()


def render_xmind_document(title: str, blocks: list[dict[str, Any]]) -> bytes:
    root = blocks_to_xmind_topic(title or "Document", blocks)
    sheet_id = uuid4().hex
    content = [
        {
            "id": sheet_id,
            "title": title or "Document",
            "rootTopic": root,
        }
    ]
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    metadata = {
        "creator": {"name": "AI Test Platform"},
        "created": created,
        "modified": created,
        "title": title or "Document",
    }
    manifest = {"file-entries": {"content.json": {}, "metadata.json": {}}}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        archive.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buffer.getvalue()


def blocks_to_xmind_topic(title: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    root = _xmind_topic(title or "Document")
    stack: list[tuple[int, dict[str, Any]]] = [(0, root)]
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            level = min(max(int(block.get("level") or 1), 1), 6)
            topic = _xmind_topic(str(block.get("text") or "Untitled"))
            while stack and stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1] if stack else root
            _xmind_attach(parent, topic)
            stack.append((level, topic))
            continue
        parent = stack[-1][1] if stack else root
        if block_type == "table":
            rows = _normalize_table_rows(block.get("rows"))
            if not rows:
                continue
            headers = rows[0]
            table_topic = _xmind_topic("Table")
            _xmind_attach(parent, table_topic)
            for row in rows[1:] if len(rows) > 1 else rows:
                row_title = next((cell for cell in row if cell), "Row")
                row_topic = _xmind_topic(row_title)
                for index, cell in enumerate(row):
                    if index >= len(headers):
                        break
                    header = headers[index] or f"Column {index + 1}"
                    if header == row_title and index == 0:
                        continue
                    if cell:
                        _xmind_attach(row_topic, _xmind_topic(f"{header}: {cell}"))
                _xmind_attach(table_topic, row_topic)
            continue
        text = str(block.get("text") or "").strip()
        if text:
            _xmind_attach(parent, _xmind_topic(text))
    return root


def _plain_text_document(text: str, *, fmt: str = "text", warning: str | None = None) -> ParsedDocument:
    blocks = markdown_to_blocks(text)
    if not blocks:
        blocks = [{"type": "paragraph", "text": _sanitize_text(text or "")}]
    sanitized_blocks = [_sanitize_block(block) for block in blocks if _block_has_content(block)]
    warnings = [warning] if warning else []
    return ParsedDocument(
        format=fmt,
        text=_sanitize_text(text or ""),
        blocks=sanitized_blocks,
        tables=[block for block in sanitized_blocks if block.get("type") == "table"],
        outline=[],
        warnings=warnings,
        metadata={"plain_text": True},
    )


def _parse_docx_document(raw_bytes: bytes | None, plain_text: str | None, fallback_name: str) -> ParsedDocument:
    if not raw_bytes:
        return _plain_text_document(plain_text or fallback_name, fmt="docx", warning="DOCX payload missing binary data; used plain text fallback.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            document_xml = _read_zip_entry(archive, "word/document.xml")
        root = ElementTree.fromstring(document_xml)
    except Exception:
        if plain_text:
            return _plain_text_document(plain_text, fmt="docx", warning="DOCX payload was not a valid OOXML document; used plain text fallback.")
        raise OfficeFormatError("DOCX payload is not a valid OOXML document")

    body = root.find("w:body", _WORD_NS)
    blocks: list[dict[str, Any]] = []
    tables: list[dict[str, Any]] = []
    outline: list[dict[str, Any]] = []
    if body is None:
        return _plain_text_document(plain_text or fallback_name, fmt="docx")

    outline_stack: list[tuple[int, dict[str, Any]]] = []
    for child in body:
        tag = _local_name(child.tag)
        if tag == "p":
            text = _sanitize_text(_word_paragraph_text(child))
            if not text:
                continue
            style = _word_paragraph_style(child)
            if style.startswith("Heading"):
                level = _word_heading_level(style)
                block = {"type": "heading", "text": text, "level": level}
                blocks.append(block)
                node = {"title": text, "children": []}
                while outline_stack and outline_stack[-1][0] >= level:
                    outline_stack.pop()
                if outline_stack:
                    outline_stack[-1][1]["children"].append(node)
                else:
                    outline.append(node)
                outline_stack.append((level, node))
            else:
                blocks.append({"type": "paragraph", "text": text})
        elif tag == "tbl":
            rows = _word_table_rows(child)
            if rows:
                table = {"rows": rows}
                tables.append(table)
                blocks.append({"type": "table", "rows": rows})

    text = "\n".join(_block_text_for_output(block) for block in blocks if _block_text_for_output(block))
    return ParsedDocument(
        format="docx",
        text=text,
        blocks=[_sanitize_block(block) for block in blocks if _block_has_content(block)],
        tables=tables,
        outline=outline,
        warnings=[],
        metadata={"table_count": len(tables), "block_count": len(blocks)},
    )


def _parse_xlsx_document(raw_bytes: bytes | None, plain_text: str | None, fallback_name: str) -> ParsedDocument:
    if not raw_bytes:
        return _plain_text_document(plain_text or fallback_name, fmt="xlsx", warning="XLSX payload missing binary data; used plain text fallback.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            shared_strings = _xlsx_shared_strings(archive)
            sheet_refs = _xlsx_sheet_refs(archive)
            blocks: list[dict[str, Any]] = []
            tables: list[dict[str, Any]] = []
            outline: list[dict[str, Any]] = []
            text_parts: list[str] = []
            for sheet_name, sheet_path in sheet_refs:
                xml_bytes = _read_zip_entry(archive, sheet_path)
                rows = _xlsx_rows(xml_bytes, shared_strings)
                if not rows:
                    continue
                heading = _sanitize_text(sheet_name)
                blocks.append({"type": "heading", "text": heading, "level": 1})
                blocks.append({"type": "table", "rows": rows})
                tables.append({"name": heading, "rows": rows})
                outline.append({"title": heading, "children": []})
                text_parts.append(f"# {heading}")
                for row in rows:
                    text_parts.append(" | ".join(cell for cell in row if cell))
            if not blocks and plain_text:
                return _plain_text_document(plain_text, fmt="xlsx", warning="XLSX workbook contained no readable sheets; used plain text fallback.")
    except Exception:
        if plain_text:
            return _plain_text_document(plain_text, fmt="xlsx", warning="XLSX payload was not a valid workbook; used plain text fallback.")
        raise OfficeFormatError("XLSX payload is not a valid workbook")

    return ParsedDocument(
        format="xlsx",
        text=_sanitize_text("\n".join(part for part in text_parts if part)),
        blocks=[_sanitize_block(block) for block in blocks if _block_has_content(block)],
        tables=tables,
        outline=outline,
        warnings=[],
        metadata={"sheet_count": len(tables)},
    )


def _parse_xmind_document(raw_bytes: bytes | None, plain_text: str | None, fallback_name: str) -> ParsedDocument:
    if not raw_bytes:
        return _plain_text_document(plain_text or fallback_name, fmt="xmind", warning="XMind payload missing binary data; used plain text fallback.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            content_json = _optional_zip_entry(archive, "content.json")
            if content_json is not None:
                content = json.loads(content_json.decode("utf-8"))
                sheets = content if isinstance(content, list) else [content]
                outline = []
                blocks: list[dict[str, Any]] = []
                text_parts: list[str] = []
                for sheet in sheets:
                    root_topic = sheet.get("rootTopic") if isinstance(sheet, dict) else None
                    if not isinstance(root_topic, dict):
                        continue
                    root_outline = _xmind_json_outline(root_topic)
                    if root_outline:
                        outline.append(root_outline)
                        _outline_to_blocks(root_outline, blocks, text_parts, depth=1)
            else:
                content_xml = _read_zip_entry(archive, "content.xml")
                outline = _xmind_xml_outline(content_xml)
                blocks = []
                text_parts = []
                for node in outline:
                    _outline_to_blocks(node, blocks, text_parts, depth=1)
    except Exception:
        if plain_text:
            return _plain_text_document(plain_text, fmt="xmind", warning="XMind payload was not a valid workbook; used plain text fallback.")
        raise OfficeFormatError("XMind payload is not a valid workbook")

    sanitized_blocks = [_sanitize_block(block) for block in blocks if _block_has_content(block)]
    text = _sanitize_text("\n".join(text_parts))
    return ParsedDocument(
        format="xmind",
        text=text,
        blocks=sanitized_blocks,
        tables=[],
        outline=outline,
        warnings=[],
        metadata={"sheet_count": len(outline)},
    )


def _parse_pdf_document(raw_bytes: bytes | None, plain_text: str | None, fallback_name: str) -> ParsedDocument:
    if not raw_bytes:
        return _plain_text_document(
            plain_text or fallback_name,
            fmt="pdf",
            warning="PDF payload missing binary data; OCR is required before reliable parsing.",
        )
    warnings: list[str] = []
    extracted_text = _pdf_extract_text(raw_bytes)
    if not extracted_text.strip() and plain_text:
        return _plain_text_document(
            plain_text,
            fmt="pdf",
            warning="PDF text extraction produced no text; OCR is required before reliable parsing.",
        )
    if not extracted_text.strip():
        warnings.append("PDF text extraction found little or no text. The file may require OCR.")
        extracted_text = "PDF text extraction found little or no text. OCR is required before reliable requirement/API extraction."
    blocks = markdown_to_blocks(extracted_text)
    if not blocks:
        blocks = [{"type": "paragraph", "text": _sanitize_text(extracted_text)}]
    return ParsedDocument(
        format="pdf",
        text=_sanitize_text(extracted_text),
        blocks=[_sanitize_block(block) for block in blocks if _block_has_content(block)],
        tables=[],
        outline=[],
        warnings=warnings,
        metadata={
            "page_count": max(1, len(re.findall(rb"/Type\s*/Page\b", raw_bytes))),
            "contains_images": b"/Subtype /Image" in raw_bytes,
        },
    )


def _extract_payload_bytes(data: dict[str, Any]) -> bytes | None:
    for key in _BINARY_TEXT_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            decoded = _decode_base64_value(value)
            if decoded is not None:
                return decoded
    for key in ("content", "raw_content", "document", "file"):
        value = data.get(key)
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
    return None


def _extract_payload_text(data: dict[str, Any], *, fallback_name: str | None = None) -> str:
    for key in _TEXT_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            decoded = _decode_base64_value(value)
            if decoded is not None and _looks_like_binary(decoded):
                continue
            return value
    return fallback_name or ""


def _decode_base64_value(value: str) -> bytes | None:
    text = value.strip()
    if not text:
        return None
    if text.startswith("data:") and "," in text:
        _, _, text = text.partition(",")
    normalized = re.sub(r"\s+", "", text)
    if len(normalized) < 16 or len(normalized) % 4 != 0 or re.search(r"[^A-Za-z0-9+/=]", normalized):
        return None
    try:
        return base64.b64decode(normalized, validate=True)
    except Exception:
        return None


def _sniff_format(raw_bytes: bytes | None) -> str:
    if not raw_bytes:
        return ""
    if raw_bytes.startswith(b"%PDF-"):
        return "pdf"
    if raw_bytes.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
                names = set(archive.namelist())
        except Exception:
            return ""
        if "word/document.xml" in names:
            return "docx"
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "content.json" in names or "content.xml" in names:
            return "xmind"
    return ""


def _looks_like_binary(raw_bytes: bytes) -> bool:
    if not raw_bytes:
        return False
    if raw_bytes.startswith((b"PK", b"%PDF-")):
        return True
    sample = raw_bytes[:64]
    return any(byte == 0 for byte in sample)


def _read_zip_entry(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > ZIP_ENTRY_SIZE_LIMIT:
        raise OfficeFormatError(f"Zip entry '{name}' exceeds safe size limit")
    total = sum(item.file_size for item in archive.infolist())
    if len(archive.infolist()) > ZIP_ENTRY_LIMIT or total > ZIP_TOTAL_SIZE_LIMIT:
        raise OfficeFormatError("Zip payload exceeds safe size limits")
    return archive.read(info)


def _optional_zip_entry(archive: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        return _read_zip_entry(archive, name)
    except KeyError:
        return None


def _word_paragraph_text(node: ElementTree.Element) -> str:
    parts: list[str] = []
    for text_node in node.findall(".//w:t", _WORD_NS):
        if text_node.text:
            parts.append(text_node.text)
    return "".join(parts).strip()


def _word_paragraph_style(node: ElementTree.Element) -> str:
    style = node.find("./w:pPr/w:pStyle", _WORD_NS)
    if style is None:
        return ""
    return str(style.attrib.get(f"{{{_WORD_NS['w']}}}val") or style.attrib.get("val") or "")


def _word_heading_level(style: str) -> int:
    match = re.search(r"(\d+)$", style)
    if match:
        return max(1, min(int(match.group(1)), 6))
    return 1


def _word_table_rows(node: ElementTree.Element) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in node.findall("./w:tr", _WORD_NS):
        values: list[str] = []
        for cell in row.findall("./w:tc", _WORD_NS):
            parts = [
                _word_paragraph_text(paragraph)
                for paragraph in cell.findall("./w:p", _WORD_NS)
            ]
            values.append(_sanitize_text("\n".join(part for part in parts if part)))
        if any(values):
            rows.append(values)
    return rows


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    xml_bytes = _optional_zip_entry(archive, "xl/sharedStrings.xml")
    if xml_bytes is None:
        return []
    root = ElementTree.fromstring(xml_bytes)
    values: list[str] = []
    for item in root.findall(".//main:si", _SHEET_NS):
        text = "".join(node.text or "" for node in item.findall(".//main:t", _SHEET_NS))
        values.append(_sanitize_text(text))
    return values


def _xlsx_sheet_refs(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(_read_zip_entry(archive, "xl/workbook.xml"))
    relationships = ElementTree.fromstring(_read_zip_entry(archive, "xl/_rels/workbook.xml.rels"))
    rel_map = {
        relation.attrib.get("Id"): relation.attrib.get("Target")
        for relation in relationships.findall(".//r:Relationship", _REL_NS)
    }
    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall(".//main:sheets/main:sheet", _SHEET_NS):
        rel_id = sheet.attrib.get(f"{{{_SHEET_NS['rel']}}}id")
        target = rel_map.get(rel_id)
        if not target:
            continue
        normalized = _safe_zip_member(f"xl/{target.lstrip('/')}")
        sheets.append((sheet.attrib.get("name") or "Sheet", normalized))
    return sheets


def _xlsx_rows(xml_bytes: bytes, shared_strings: list[str]) -> list[list[str]]:
    root = ElementTree.fromstring(xml_bytes)
    rows: list[list[str]] = []
    max_columns = 0
    for row in root.findall(".//main:sheetData/main:row", _SHEET_NS):
        values: dict[int, str] = {}
        for cell in row.findall("./main:c", _SHEET_NS):
            ref = cell.attrib.get("r") or ""
            column_index = _excel_ref_to_index(ref)
            if column_index < 0:
                continue
            values[column_index] = _xlsx_cell_value(cell, shared_strings)
            max_columns = max(max_columns, column_index + 1)
        if values:
            rows.append([values.get(index, "") for index in range(max_columns)])
    return _trim_trailing_empty_columns(rows)


def _xlsx_cell_value(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        text = "".join(node.text or "" for node in cell.findall(".//main:t", _SHEET_NS))
        return _sanitize_text(text)
    value_node = cell.find("./main:v", _SHEET_NS)
    raw_value = value_node.text if value_node is not None and value_node.text is not None else ""
    if cell_type == "s":
        try:
            return shared_strings[int(raw_value)]
        except Exception:
            return ""
    if cell_type == "b":
        return "TRUE" if raw_value == "1" else "FALSE"
    return _sanitize_text(raw_value)


def _xmind_json_outline(topic: dict[str, Any]) -> dict[str, Any]:
    node = {
        "title": _sanitize_text(str(topic.get("title") or "Untitled")),
        "children": [],
    }
    children = topic.get("children")
    attached = []
    if isinstance(children, dict):
        attached = children.get("attached") or children.get("topics") or []
    elif isinstance(topic.get("topics"), list):
        attached = topic.get("topics") or []
    if isinstance(attached, list):
        for child in attached:
            if isinstance(child, dict):
                node["children"].append(_xmind_json_outline(child))
    return node


def _xmind_xml_outline(xml_bytes: bytes) -> list[dict[str, Any]]:
    root = ElementTree.fromstring(xml_bytes)
    outlines: list[dict[str, Any]] = []
    for topic in root.findall(".//xmap:sheet/xmap:topic", _XMIND_XML_NS):
        outlines.append(_xmind_xml_topic(topic))
    return outlines


def _xmind_xml_topic(node: ElementTree.Element) -> dict[str, Any]:
    title = node.findtext("./xmap:title", default="Untitled", namespaces=_XMIND_XML_NS)
    result = {"title": _sanitize_text(title), "children": []}
    for child in node.findall("./xmap:children/xmap:topics/xmap:topic", _XMIND_XML_NS):
        result["children"].append(_xmind_xml_topic(child))
    return result


def _outline_to_blocks(
    node: dict[str, Any],
    blocks: list[dict[str, Any]],
    text_parts: list[str],
    *,
    depth: int,
) -> None:
    title = _sanitize_text(str(node.get("title") or "Untitled"))
    if not title:
        return
    if depth <= 3:
        blocks.append({"type": "heading", "text": title, "level": depth})
        text_parts.append(f"{'#' * depth} {title}")
    else:
        blocks.append({"type": "list_item", "text": title, "level": depth - 3})
        text_parts.append(f"- {title}")
    for child in node.get("children") or []:
        if isinstance(child, dict):
            _outline_to_blocks(child, blocks, text_parts, depth=depth + 1)


def _pdf_extract_text(raw_bytes: bytes) -> str:
    text_parts: list[str] = []
    for match in _PDF_STREAM_RE.finditer(raw_bytes):
        stream_dict = match.group("dict")
        stream = match.group("data")
        if b"/FlateDecode" in stream_dict:
            try:
                stream = zlib.decompress(stream)
            except Exception:
                continue
        if b"BT" not in stream and b"Tj" not in stream and b"TJ" not in stream:
            continue
        text_parts.extend(_pdf_stream_strings(stream))
    text = _normalize_pdf_text(text_parts)
    if text.strip():
        return text
    decoded = raw_bytes.decode("latin-1", errors="ignore")
    literals = [match.group(1) for match in re.finditer(r"\(([^()]{2,200})\)", decoded)]
    return _sanitize_text("\n".join(literals[:200]))


def _pdf_stream_strings(stream: bytes) -> list[str]:
    values: list[str] = []
    for array_match in _PDF_ARRAY_RE.finditer(stream):
        body = array_match.group("body")
        for token in re.finditer(rb"\((?:\\.|[^\\()])*\)|<[^<>]+>", body):
            decoded = _decode_pdf_token(token.group(0))
            if decoded:
                values.append(decoded)
    for token_match in _PDF_TEXT_RE.finditer(stream):
        decoded = _decode_pdf_token(token_match.group("literal"))
        if decoded:
            values.append(decoded)
    return values


def _decode_pdf_token(token: bytes) -> str:
    if token.startswith(b"(") and token.endswith(b")"):
        data = token[1:-1]
        result = bytearray()
        index = 0
        while index < len(data):
            char = data[index]
            if char != 92:
                result.append(char)
                index += 1
                continue
            index += 1
            if index >= len(data):
                break
            escaped = data[index]
            if escaped in b"nrtbf":
                mapping = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
                result.append(mapping.get(escaped, escaped))
                index += 1
                continue
            if 48 <= escaped <= 55:
                octal = bytes([escaped])
                index += 1
                for _ in range(2):
                    if index < len(data) and 48 <= data[index] <= 55:
                        octal += bytes([data[index]])
                        index += 1
                    else:
                        break
                result.append(int(octal, 8))
                continue
            result.append(escaped)
            index += 1
        return _decode_pdf_text_bytes(bytes(result))
    if token.startswith(b"<") and token.endswith(b">"):
        hex_value = re.sub(rb"\s+", b"", token[1:-1])
        if len(hex_value) % 2:
            hex_value += b"0"
        try:
            return _decode_pdf_text_bytes(bytes.fromhex(hex_value.decode("ascii")))
        except Exception:
            return ""
    return ""


def _decode_pdf_text_bytes(data: bytes) -> str:
    if not data:
        return ""
    for encoding in ("utf-16-be", "utf-8", "gb18030", "latin-1"):
        try:
            text = data.decode(encoding)
        except Exception:
            continue
        cleaned = _sanitize_text(text)
        if cleaned:
            return cleaned
    return ""


def _normalize_pdf_text(parts: list[str]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for item in parts:
        cleaned = _sanitize_text(item)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        lines.append(cleaned)
    return "\n".join(lines)


def _docx_paragraph(text: str, *, style: str | None = None) -> str:
    escaped = _xml_text(text)
    style_xml = f'<w:pPr><w:pStyle w:val="{_xml_attr(style)}"/></w:pPr>' if style else ""
    return f"<w:p>{style_xml}<w:r><w:t xml:space=\"preserve\">{escaped}</w:t></w:r></w:p>"


def _docx_table(rows: list[list[str]]) -> str:
    row_xml: list[str] = []
    for row in rows:
        cells = "".join(
            f"<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr><w:p><w:r><w:t xml:space=\"preserve\">{_xml_text(cell)}</w:t></w:r></w:p></w:tc>"
            for cell in row
        )
        row_xml.append(f"<w:tr>{cells}</w:tr>")
    return (
        "<w:tbl>"
        "<w:tblPr><w:tblBorders>"
        "<w:top w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:left w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:right w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:insideH w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "<w:insideV w:val=\"single\" w:sz=\"4\" w:space=\"0\" w:color=\"auto\"/>"
        "</w:tblBorders></w:tblPr>"
        + "".join(row_xml)
        + "</w:tbl>"
    )


def _docx_content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""


def _docx_root_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def _docx_document_relationships() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""


def _docx_app_props() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>AI Test Platform</Application>
</Properties>"""


def _docx_core_props(created: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>AI Test Platform</dc:creator>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>"""


def _docx_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
    <w:qFormat/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="32"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading3">
    <w:name w:val="heading 3"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="22"/></w:rPr>
  </w:style>
</w:styles>"""


def _pdf_lines(title: str, blocks: list[dict[str, Any]]) -> list[str]:
    lines = [title, ""]
    for block in blocks:
        block_type = block.get("type")
        if block_type == "heading":
            level = max(int(block.get("level") or 1), 1)
            lines.append(f"{'#' * min(level, 3)} {block.get('text') or ''}")
        elif block_type == "list_item":
            lines.append(f"- {block.get('text') or ''}")
        elif block_type == "table":
            rows = _normalize_table_rows(block.get("rows"))
            for row in rows:
                lines.append(" | ".join(row))
        else:
            lines.extend(_wrap_pdf_line(str(block.get("text") or "")))
        lines.append("")
    return [_sanitize_text(line)[:160] for line in lines if line is not None]


def _wrap_pdf_line(text: str, *, width: int = 56) -> list[str]:
    clean = _sanitize_text(text)
    if len(clean) <= width:
        return [clean]
    words = re.split(r"(\s+)", clean)
    if len(words) == 1:
        return [clean[index : index + width] for index in range(0, len(clean), width)]
    lines: list[str] = []
    current = ""
    for token in words:
        if len(current) + len(token) <= width:
            current += token
            continue
        if current.strip():
            lines.append(current.strip())
        current = token.strip()
    if current.strip():
        lines.append(current.strip())
    return lines or [clean]


def _paginate_lines(lines: list[str], *, max_lines: int) -> list[list[str]]:
    pages: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if len(current) >= max_lines:
            pages.append(current)
            current = []
        current.append(line)
    if current:
        pages.append(current)
    return pages or [[""]]


def _pdf_content_stream(lines: list[str]) -> bytes:
    commands = [b"BT", b"/F1 11 Tf", b"1 0 0 1 50 790 Tm"]
    first = True
    for line in lines:
        if not first:
            commands.append(b"0 -16 Td")
        first = False
        commands.append(f"<{_pdf_hex(line)}> Tj".encode("ascii"))
    commands.append(b"ET")
    return b"\n".join(commands)


def _pdf_hex(text: str) -> str:
    return text.encode("utf-16-be", errors="ignore").hex().upper()


def _xmind_topic(title: str) -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "title": _sanitize_text(title or "Untitled"),
        "children": {"attached": []},
    }


def _xmind_attach(parent: dict[str, Any], child: dict[str, Any]) -> None:
    children = parent.setdefault("children", {})
    attached = children.setdefault("attached", [])
    attached.append(child)


def _split_markdown_table_row(line: str) -> list[str]:
    raw = line.strip().strip("|")
    return [_sanitize_text(cell.strip().replace("\\|", "|")) for cell in raw.split("|")]


def _normalize_table_rows(value: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    if not isinstance(value, list):
        return rows
    for row in value:
        if not isinstance(row, list):
            continue
        rows.append([_sanitize_text("" if cell is None else str(cell)) for cell in row])
    return rows


def _trim_trailing_empty_columns(rows: list[list[str]]) -> list[list[str]]:
    max_index = -1
    for row in rows:
        for index in range(len(row) - 1, -1, -1):
            if row[index]:
                max_index = max(max_index, index)
                break
    if max_index < 0:
        return rows
    return [row[: max_index + 1] for row in rows]


def _excel_ref_to_index(reference: str) -> int:
    letters = "".join(ch for ch in reference if ch.isalpha()).upper()
    if not letters:
        return -1
    value = 0
    for letter in letters:
        value = value * 26 + (ord(letter) - 64)
    return value - 1


def _safe_zip_member(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    parts = [part for part in path.parts if part not in {"", ".", ".."} and ":" not in part]
    clean = "/".join(parts).lstrip("/")
    if not clean:
        raise OfficeFormatError("Unsafe zip member path")
    return clean


def _ooxml_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sanitize_block(block: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {"type": block.get("type")}
    if "level" in block:
        clean["level"] = int(block.get("level") or 1)
    if "text" in block:
        clean["text"] = _sanitize_text(str(block.get("text") or ""))
    if "rows" in block:
        clean["rows"] = _normalize_table_rows(block.get("rows"))
    return clean


def _block_has_content(block: dict[str, Any]) -> bool:
    if block.get("type") == "table":
        return any(any(cell for cell in row) for row in _normalize_table_rows(block.get("rows")))
    return bool(str(block.get("text") or "").strip())


def _block_text_for_output(block: dict[str, Any]) -> str:
    if block.get("type") == "table":
        rows = _normalize_table_rows(block.get("rows"))
        return "\n".join(" | ".join(row) for row in rows)
    return _sanitize_text(str(block.get("text") or ""))


def _sanitize_text(value: str) -> str:
    text = _strip_invalid_xml_chars(str(value or ""))
    text = text.replace("\u00a0", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return _SENSITIVE_VALUE_RE.sub(lambda match: match.group(0).split(match.group(1), 1)[0] + match.group(1) + "***", text).strip()


def _strip_invalid_xml_chars(value: str) -> str:
    return "".join(ch for ch in value if ch in "\t\n\r" or ord(ch) >= 32)


def _xml_text(value: Any) -> str:
    return xml_escape(_strip_invalid_xml_chars(str(value or "")), {'"': "&quot;"})


def _xml_attr(value: Any) -> str:
    return _xml_text(value)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
