const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v2';

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(message, { status, traceId, payload } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.traceId = traceId;
    this.payload = payload;
  }
}

export async function apiGet(path, options = {}) {
  return apiRequest(path, { ...options, method: 'GET' });
}

export async function apiPost(path, body, options = {}) {
  return apiRequest(path, { ...options, method: 'POST', body });
}

export async function apiRequest(path, { method = 'GET', body, params, timeoutMs = 8000, signal } = {}) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromParent = () => controller.abort();

  if (signal?.aborted) {
    controller.abort();
  } else if (signal) {
    signal.addEventListener('abort', abortFromParent, { once: true });
  }

  try {
    const response = await fetch(buildApiUrl(path, params), {
      method,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' })
      },
      body: body === undefined ? undefined : JSON.stringify(body)
    });

    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('application/json') ? await response.json() : await response.text();
    const unwrapped = unwrapEnvelope(payload);

    if (!response.ok) {
      throw new ApiError(readErrorMessage(payload, response.statusText), {
        status: response.status,
        traceId: payload?.trace_id,
        payload
      });
    }

    if (payload && typeof payload === 'object' && 'code' in payload && Number(payload.code) !== 0 && Number(payload.code) !== 200) {
      throw new ApiError(payload.message || 'API request failed', {
        status: response.status,
        traceId: payload.trace_id,
        payload
      });
    }

    return unwrapped;
  } catch (error) {
    if (error?.name === 'AbortError') {
      throw new ApiError('API request timeout', { status: 408 });
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener?.('abort', abortFromParent);
  }
}

export function pickList(payload) {
  if (Array.isArray(payload)) return payload;
  if (payload && Array.isArray(payload.list)) return payload.list;
  if (payload && Array.isArray(payload.items)) return payload.items;
  if (payload && Array.isArray(payload.records)) return payload.records;
  return [];
}

export function formatDateTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  });
}

export function downloadTextFile({ filename, content, mimeType }) {
  const blob = new Blob([content || ''], { type: mimeType || 'text/plain;charset=utf-8' });
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename || 'download.txt';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export function downloadBase64File({ filename, contentBase64, mimeType }) {
  const binary = window.atob(contentBase64 || '');
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  const blob = new Blob([bytes], { type: mimeType || 'application/octet-stream' });
  const href = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename || 'download.bin';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(href);
}

export function downloadExportedFile(payload, options = {}) {
  const file = normalizeDownloadPayload(payload, options);
  if (file.unsupported) {
    throw new ApiError(file.message, { status: file.status, payload });
  }

  if (file.contentBase64) {
    downloadBase64File({
      filename: file.filename,
      contentBase64: file.contentBase64,
      mimeType: file.mimeType
    });
    return file;
  }

  if (file.content !== undefined && file.content !== null && String(file.content).length > 0) {
    downloadTextFile({
      filename: file.filename,
      content: file.content,
      mimeType: file.mimeType
    });
    return file;
  }

  throw new ApiError('后端未返回可下载内容，已取消空文件下载。', { status: 502, payload });
}

export function formatDownloadError(error, fallback = '文件导出失败。') {
  const payload = error?.payload && typeof error.payload === 'object' ? error.payload : {};
  const parts = [error?.message || payload.message || payload.detail || fallback];
  const status = error?.status || payload.status || payload.status_code;
  const requestedFormat = payload.requested_format || payload.requestedFormat || payload.format;
  const supportedFormats = normalizeFormatList(
    payload.supported_formats || payload.supportedFormats || payload.available_formats || payload.availableFormats || payload.formats
  );

  if (status) parts.push(`HTTP ${status}`);
  if (requestedFormat) parts.push(`请求格式：${requestedFormat}`);
  if (supportedFormats.length) parts.push(`支持格式：${supportedFormats.join(' / ')}`);
  if (error?.traceId || payload.trace_id || payload.traceId) parts.push(`Trace：${error.traceId || payload.trace_id || payload.traceId}`);
  return parts.filter(Boolean).join('；');
}

function buildApiUrl(path, params) {
  const url = new URL(`${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`);
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.set(key, value);
    }
  });
  return url.toString();
}

function unwrapEnvelope(payload) {
  if (payload && typeof payload === 'object' && 'data' in payload && 'code' in payload && 'message' in payload) {
    return payload.data;
  }
  return payload;
}

function readErrorMessage(payload, fallback) {
  if (payload && typeof payload === 'object') {
    return payload.message || payload.detail || fallback || 'API request failed';
  }
  return fallback || 'API request failed';
}

function normalizeDownloadPayload(payload, options = {}) {
  const format = String(options.format || payload?.format || '').toLowerCase();
  const record = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
  const unsupported = isUnsupportedDownloadPayload(record);
  const fallbackMime = options.defaultMimeType || mimeTypeForFormat(format);
  const filename = firstText(
    record.filename,
    record.file_name,
    record.name,
    options.defaultFilename,
    `download${extensionForFormat(format)}`
  );
  const mimeType = firstText(record.mime_type, record.mimeType, record.content_type, record.contentType, fallbackMime);
  const contentBase64 = firstText(
    record.content_base64,
    record.contentBase64,
    record.file_base64,
    record.fileBase64,
    record.base64
  );

  let content;
  if (typeof payload === 'string') {
    content = payload;
  } else if (payload !== null && payload !== undefined && !Array.isArray(payload) && typeof payload !== 'object') {
    content = String(payload);
  } else if (record.content !== undefined && record.content !== null) {
    content = stringifyDownloadContent(record.content);
  } else if (record.text !== undefined && record.text !== null) {
    content = stringifyDownloadContent(record.text);
  } else if (record.body !== undefined && record.body !== null) {
    content = stringifyDownloadContent(record.body);
  } else if (record.json !== undefined && record.json !== null) {
    content = stringifyDownloadContent(record.json, true);
  } else if (format === 'json' && payload && typeof payload === 'object') {
    content = stringifyDownloadContent(payload, true);
  }

  return {
    filename,
    mimeType,
    content,
    contentBase64,
    unsupported,
    status: record.status_code || record.statusCode || record.status || 415,
    message: readDownloadPayloadMessage(record, format)
  };
}

function isUnsupportedDownloadPayload(record) {
  if (!record || typeof record !== 'object') return false;
  const statusText = String(record.status || record.code || record.error_code || '').toLowerCase();
  return (
    record.unsupported === true ||
    record.supported === false ||
    record.available === false ||
    ['unsupported', 'not_supported', 'format_unsupported', 'unsupported_format'].includes(statusText)
  );
}

function readDownloadPayloadMessage(record, format) {
  const supportedFormats = normalizeFormatList(
    record.supported_formats || record.supportedFormats || record.available_formats || record.availableFormats || record.formats
  );
  const formatText = format ? `${format.toUpperCase()} ` : '';
  const supportText = supportedFormats.length ? `支持格式：${supportedFormats.join(' / ')}` : '请改用已开放格式。';
  return record.message || record.detail || `${formatText}导出未开放，${supportText}`;
}

function stringifyDownloadContent(value, prettyJson = false) {
  if (typeof value === 'string') return value;
  if (value instanceof Blob) return value;
  if (value instanceof ArrayBuffer) return value;
  if (ArrayBuffer.isView(value)) return value;
  if (prettyJson || typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function normalizeFormatList(value) {
  if (Array.isArray(value)) return value.map(item => String(item).toUpperCase()).filter(Boolean);
  if (typeof value === 'string') return value.split(/[,\s/]+/).map(item => item.trim().toUpperCase()).filter(Boolean);
  return [];
}

function firstText(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return '';
}

function extensionForFormat(format) {
  const extensions = {
    csv: '.csv',
    markdown: '.md',
    md: '.md',
    json: '.json',
    html: '.html',
    xlsx: '.xlsx',
    word: '.docx',
    docx: '.docx',
    pdf: '.pdf',
    xmind: '.xmind',
    zip: '.zip'
  };
  return extensions[format] || '.txt';
}

function mimeTypeForFormat(format) {
  const mimeTypes = {
    csv: 'text/csv;charset=utf-8',
    markdown: 'text/markdown;charset=utf-8',
    md: 'text/markdown;charset=utf-8',
    json: 'application/json;charset=utf-8',
    html: 'text/html;charset=utf-8',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    word: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    pdf: 'application/pdf',
    xmind: 'application/octet-stream',
    zip: 'application/zip'
  };
  return mimeTypes[format] || 'application/octet-stream';
}
