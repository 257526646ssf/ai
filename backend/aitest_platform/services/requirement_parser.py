from __future__ import annotations

import hashlib
import re
from typing import Any

from aitest_platform.services.file_formats import (
    UnsupportedFormatError,
    detect_import_format,
    detect_unsupported_import_format,
    normalize_format,
    unsupported_import_detail,
)
from aitest_platform.services.office_formats import parse_document_payload


PARSER_NAME = "markdown-text-rules-v1"
SUPPORTED_REQUIREMENT_IMPORT_FORMATS = {"markdown", "text", "docx", "pdf", "xlsx", "xmind"}
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def ensure_supported_requirement_source(*, document_name: str, source_type: str, source_file_name: str | None = None) -> None:
    unsupported_format = detect_unsupported_import_format(
        {"source_type": source_type, "name": document_name, "source_file_name": source_file_name}
    )
    if unsupported_format is not None:
        raise UnsupportedFormatError(
            unsupported_import_detail(
                unsupported_format,
                SUPPORTED_REQUIREMENT_IMPORT_FORMATS,
                error_code="unsupported_requirement_document_format",
            )
        )


def parse_requirement_blocks(
    content: str | None,
    *,
    document_id: int,
    document_name: str,
    source_type: str,
    source_file_name: str | None = None,
) -> list[dict[str, Any]]:
    ensure_supported_requirement_source(
        document_name=document_name,
        source_type=source_type,
        source_file_name=source_file_name,
    )
    fmt = (
        detect_import_format({"source_type": source_type, "name": document_name, "source_file_name": source_file_name})
        or normalize_format(source_type)
        or "text"
    )
    binary_fields: dict[str, Any] = {}
    if fmt in {"docx", "pdf", "xlsx", "xmind"} and isinstance(content, str) and content.strip():
        binary_fields = {"content_base64": content, "raw_content_base64": content}
    parsed = parse_document_payload(
        {
            "source_type": fmt,
            **binary_fields,
            "content": content,
            "raw_content": content,
            "source_file_name": source_file_name,
            "name": document_name,
        },
        source_type=fmt,
        filename=source_file_name or document_name,
        fallback_name=document_name,
    )
    if fmt == "pdf" and _ocr_only_pdf(parsed, document_name):
        return []

    blocks: list[dict[str, Any]] = []
    section_stack: list[str] = []
    line_no = 1

    def current_section_path() -> str | None:
        return " / ".join(section_stack) if section_stack else None

    for block in parsed.blocks:
        block_type = str(block.get("type") or "paragraph")
        if block_type == "heading":
            title = str(block.get("text") or "").strip()
            if not title:
                continue
            level = max(int(block.get("level") or 1), 1)
            section_stack = section_stack[: max(0, level - 1)]
            section_stack.append(title)
            _append_block(
                blocks,
                document_id=document_id,
                block_type="heading",
                raw_text=title,
                line_start=line_no,
                line_end=line_no,
                section_path=current_section_path(),
                source_type=fmt,
                metadata_extra={"heading_level": level, "source_format": parsed.format, "warnings": parsed.warnings or None},
            )
            line_no += 1
            continue
        if block_type == "table":
            rows = block.get("rows") if isinstance(block.get("rows"), list) else []
            for row_index, row in enumerate(rows, start=1):
                if not isinstance(row, list):
                    continue
                row_text = " | ".join(str(cell or "").strip() for cell in row).strip(" |")
                if not row_text:
                    continue
                _append_block(
                    blocks,
                    document_id=document_id,
                    block_type="table_row",
                    raw_text=row_text,
                    line_start=line_no,
                    line_end=line_no,
                    section_path=current_section_path(),
                    source_type=fmt,
                    metadata_extra={
                        "source_format": parsed.format,
                        "table_row_index": row_index,
                        "column_count": len(row),
                        "warnings": parsed.warnings or None,
                    },
                )
                line_no += 1
            continue
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        normalized_type = "list_item" if block_type == "list_item" else "paragraph"
        _append_block(
            blocks,
            document_id=document_id,
            block_type=normalized_type,
            raw_text=text,
            line_start=line_no,
            line_end=line_no,
            section_path=current_section_path(),
            source_type=fmt,
            metadata_extra={"source_format": parsed.format, "warnings": parsed.warnings or None},
        )
        line_no += 1

    if not blocks:
        _append_block(
            blocks,
            document_id=document_id,
            block_type="paragraph",
            raw_text=document_name,
            line_start=1,
            line_end=1,
            section_path=None,
            source_type=fmt,
        )
    return blocks


def build_requirement_item_payloads(document_name: str, blocks: list[Any]) -> list[dict[str, Any]]:
    candidates = [block for block in blocks if getattr(block, "block_type", "") != "heading" and _block_text(block)]
    if not candidates:
        candidates = [block for block in blocks if _block_text(block)]

    items: list[dict[str, Any]] = []
    for block in candidates:
        text = _block_text(block)
        title = _title_from_text(text, getattr(block, "section_path", None), document_name)
        items.append(
            {
                "title": title,
                "summary": text[:800],
                "module": _module_from_section(getattr(block, "section_path", None)),
                "goal": text[:500],
                "priority": "P2",
                "confidence": 0.68,
                "granularity_flag": estimate_granularity_flag(text),
                "source_anchor_ids": [getattr(block, "block_key")],
            }
        )
    return items


def estimate_granularity_flag(text: str | None) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) < 20:
        return "too_small"
    separators = sum(normalized.count(marker) for marker in (";", " and ", " or ", "以及", "或者", "并且"))
    if len(normalized) > 450 or separators >= 4:
        return "too_coarse"
    return "normal"


def content_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _append_block(
    blocks: list[dict[str, Any]],
    *,
    document_id: int,
    block_type: str,
    raw_text: str,
    line_start: int,
    line_end: int,
    section_path: str | None,
    source_type: str,
    normalized_text: str | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> None:
    normalized = " ".join((normalized_text if normalized_text is not None else raw_text).split())
    digest = content_hash(f"{block_type}\n{section_path or ''}\n{line_start}\n{normalized}")[:12]
    order_no = len(blocks) + 1
    block_key = f"doc-{document_id}-b{order_no:04d}-{digest}"
    metadata = {
        "line_start": line_start,
        "line_end": line_end,
        "parser": PARSER_NAME,
        "hash": digest,
        "anchor": block_key,
        "source_type": source_type,
    }
    if metadata_extra:
        metadata.update(metadata_extra)
    blocks.append(
        {
            "block_key": block_key,
            "block_type": block_type,
            "raw_text": raw_text,
            "normalized_text": normalized,
            "order_no": order_no,
            "section_path": section_path,
            "metadata_json": metadata,
        }
    )


def _block_text(block: Any) -> str:
    return " ".join(str(getattr(block, "normalized_text", None) or getattr(block, "raw_text", "") or "").split())


def _title_from_text(text: str, section_path: str | None, document_name: str) -> str:
    cleaned = _LIST_PREFIX_RE.sub("", text).strip(" -\t")
    first_sentence = re.split(r"[。.!?\n]", cleaned, maxsplit=1)[0].strip()
    title = first_sentence or section_path or document_name
    if section_path and title != section_path:
        title = f"{section_path}: {title}"
    return title[:120]


def _module_from_section(section_path: str | None) -> str | None:
    if not section_path:
        return None
    return section_path.split(" / ")[0][:128]


def _ocr_only_pdf(parsed: Any, document_name: str) -> bool:
    warnings = [str(item).lower() for item in getattr(parsed, "warnings", [])]
    if not any("ocr" in item for item in warnings):
        return False
    blocks = getattr(parsed, "blocks", []) or []
    visible_texts = [str(block.get("text") or "").strip() for block in blocks if isinstance(block, dict) and str(block.get("text") or "").strip()]
    return not visible_texts or all(text == document_name for text in visible_texts)
