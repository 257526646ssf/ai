from __future__ import annotations

from pathlib import PurePath
from typing import Any, Iterable


UNSUPPORTED_EXPORT_BINARY_FORMATS = frozenset({"pdf", "word", "doc", "docx", "xmind"})
UNSUPPORTED_IMPORT_BINARY_FORMATS = frozenset({"pdf", "word", "doc", "docx", "xlsx", "xmind", "binary"})

_MIME_FORMATS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/octet-stream": "binary",
    "application/vnd.ms-excel": "xlsx",
    "application/vnd.ms-xmind": "xmind",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/x-xmind": "xmind",
}

_FORMAT_ALIASES = {
    "excel": "xlsx",
    "msword": "doc",
    "office": "binary",
    "wordprocessingml": "docx",
}

_EXPLICIT_FORMAT_KEYS = (
    "format",
    "file_type",
    "fileType",
    "source_type",
    "sourceType",
    "content_type",
    "contentType",
    "mime_type",
    "mimeType",
    "type",
)

_FILENAME_KEYS = (
    "filename",
    "file_name",
    "fileName",
    "source_file_name",
    "sourceFileName",
    "name",
)


class UnsupportedFormatError(ValueError):
    def __init__(self, detail: dict[str, Any], *, status_code: int = 415) -> None:
        self.detail = detail
        self.status_code = status_code
        super().__init__(str(detail.get("message") or "Unsupported format"))


def normalize_format(value: Any) -> str:
    text = str(value or "").strip().lower().lstrip(".")
    if not text:
        return ""
    media_type = text.split(";", 1)[0].strip()
    if media_type in _MIME_FORMATS:
        return _MIME_FORMATS[media_type]
    if "/" in media_type and media_type in _MIME_FORMATS:
        return _MIME_FORMATS[media_type]
    return _FORMAT_ALIASES.get(media_type, media_type.replace("-", "_"))


def file_extension(value: Any) -> str:
    text = str(value or "").strip().split("?", 1)[0].split("#", 1)[0]
    if not text:
        return ""
    suffix = PurePath(text.replace("\\", "/")).suffix
    return normalize_format(suffix)


def is_unsupported_export_format(value: Any) -> bool:
    return normalize_format(value) in UNSUPPORTED_EXPORT_BINARY_FORMATS


def is_unsupported_import_format(value: Any) -> bool:
    return normalize_format(value) in UNSUPPORTED_IMPORT_BINARY_FORMATS


def detect_unsupported_import_format(data: dict[str, Any], *, extra_filename: Any = None) -> str | None:
    for key in _EXPLICIT_FORMAT_KEYS:
        if key not in data:
            continue
        fmt = normalize_format(data.get(key))
        if fmt in UNSUPPORTED_IMPORT_BINARY_FORMATS:
            return fmt

    for key in _FILENAME_KEYS:
        fmt = file_extension(data.get(key))
        if fmt in UNSUPPORTED_IMPORT_BINARY_FORMATS:
            return fmt

    fmt = file_extension(extra_filename)
    if fmt in UNSUPPORTED_IMPORT_BINARY_FORMATS:
        return fmt
    return None


def unsupported_format_detail(
    fmt: Any,
    *,
    supported_formats: Iterable[str],
    alternatives: Iterable[str] | None = None,
    error_code: str,
    message: str | None = None,
) -> dict[str, Any]:
    normalized = normalize_format(fmt) or str(fmt or "unknown").strip().lower() or "unknown"
    supported = sorted({str(item) for item in supported_formats})
    alternative_formats = sorted({str(item) for item in (alternatives or supported)})
    return {
        "error_code": error_code,
        "message": message or f"Unsupported format '{normalized}'. Supported formats: {', '.join(supported)}.",
        "format": normalized,
        "supported_formats": supported,
        "alternatives": [{"format": item} for item in alternative_formats],
    }


def unsupported_export_detail(fmt: Any, supported_formats: Iterable[str], *, error_code: str = "unsupported_export_format") -> dict[str, Any]:
    normalized = normalize_format(fmt) or str(fmt or "unknown").strip().lower() or "unknown"
    return unsupported_format_detail(
        normalized,
        supported_formats=supported_formats,
        error_code=error_code,
        message=f"Export format '{normalized}' is not supported. Use one of: {', '.join(sorted(set(supported_formats)))}.",
    )


def unsupported_import_detail(fmt: Any, supported_formats: Iterable[str], *, error_code: str = "unsupported_import_format") -> dict[str, Any]:
    normalized = normalize_format(fmt) or str(fmt or "unknown").strip().lower() or "unknown"
    return unsupported_format_detail(
        normalized,
        supported_formats=supported_formats,
        error_code=error_code,
        message=(
            f"Import format '{normalized}' is a binary or unparsed document format. "
            f"Upload parsed text or use one of: {', '.join(sorted(set(supported_formats)))}."
        ),
    )
