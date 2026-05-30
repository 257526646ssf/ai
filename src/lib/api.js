const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000/api/v2';

const JSON_CONTENT_TYPE = 'application/json';
const DOWNLOAD_ACCEPT = 'application/json, text/plain, */*';
const RFC5987_PREFIX = "utf-8''";

const MIME_TYPE_TO_FORMAT = {
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/msword': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.ms-excel': 'xlsx',
  'application/xmind': 'xmind',
  'application/vnd.xmind': 'xmind'
};

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

export async function apiRequest(
  path,
  {
    method = 'GET',
    body,
    params,
    timeoutMs = 8000,
    signal,
    headers,
    accept = JSON_CONTENT_TYPE,
    responseType = 'auto'
  } = {}
) {
  const response = await executeFetch(path, { method, body, params, timeoutMs, signal, headers, accept });
  const payload = await readResponsePayload(response, responseType);

  if (!response.ok) {
    throw buildApiError(payload, response.status, response.statusText);
  }

  if (isEnvelopeError(payload)) {
    throw new ApiError(payload.message || 'API request failed', {
      status: response.status,
      traceId: payload.trace_id,
      payload
    });
  }

  return unwrapEnvelope(payload);
}

export async function apiDownload(
  path,
  {
    method = 'GET',
    body,
    params,
    timeoutMs = 15000,
    signal,
    headers,
    format,
    defaultFilename,
    defaultMimeType
  } = {}
) {
  const response = await executeFetch(path, {
    method,
    body,
    params,
    timeoutMs,
    signal,
    headers,
    accept: DOWNLOAD_ACCEPT
  });

  const contentType = (response.headers.get('content-type') || '').toLowerCase();
  const contentDisposition = response.headers.get('content-disposition') || '';

  if (looksLikeJsonResponse(contentType)) {
    const payload = await readResponsePayload(response, 'json');
    if (!response.ok) {
      throw buildApiError(payload, response.status, response.statusText);
    }
    if (isEnvelopeError(payload)) {
      throw new ApiError(payload.message || 'File download failed', {
        status: response.status,
        traceId: payload.trace_id,
        payload
      });
    }

    const normalizedPayload = unwrapEnvelope(payload);
    if (contentDisposition) {
      const filename = parseFilenameFromDisposition(contentDisposition);
      if (filename && normalizedPayload && typeof normalizedPayload === 'object' && !Array.isArray(normalizedPayload)) {
        normalizedPayload.filename = normalizedPayload.filename || normalizedPayload.file_name || filename;
      }
    }
    return downloadExportedFile(normalizedPayload, { format, defaultFilename, defaultMimeType });
  }

  if (!response.ok) {
    const errorText = await readResponsePayload(response, 'text');
    throw buildApiError(errorText, response.status, response.statusText);
  }

  const filename = parseFilenameFromDisposition(contentDisposition);
  const blob = await response.blob();
  return downloadExportedFile(
    {
      blob,
      filename,
      mime_type: contentType || defaultMimeType,
      format
    },
    { format, defaultFilename, defaultMimeType }
  );
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
  return downloadBlobFile({ filename, blob });
}

export function downloadBase64File({ filename, contentBase64, mimeType }) {
  const blob = base64ToBlob(contentBase64 || '', mimeType || 'application/octet-stream');
  return downloadBlobFile({ filename, blob });
}

export function downloadExportedFile(payload, options = {}) {
  const file = normalizeDownloadPayload(payload, options);
  if (file.unsupported) {
    throw new ApiError(file.message, { status: file.status, payload });
  }

  if (file.blob) {
    if (file.blob.size <= 0) {
      throw new ApiError('后端没有返回可下载的文件内容。', { status: 502, payload });
    }
    downloadBlobFile({
      filename: file.filename,
      blob: file.blob,
      mimeType: file.mimeType
    });
    return file;
  }

  if (file.contentBase64) {
    downloadBase64File({
      filename: file.filename,
      contentBase64: file.contentBase64,
      mimeType: file.mimeType
    });
    return file;
  }

  if (isBinaryLike(file.content)) {
    downloadBlobFile({
      filename: file.filename,
      blob: new Blob([file.content], { type: file.mimeType || 'application/octet-stream' })
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

  throw new ApiError('后端没有返回可下载的文件内容。', { status: 502, payload });
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
  if (requestedFormat) parts.push(`请求格式: ${requestedFormat}`);
  if (supportedFormats.length) parts.push(`支持格式: ${supportedFormats.join(' / ')}`);
  if (error?.traceId || payload.trace_id || payload.traceId) parts.push(`Trace: ${error.traceId || payload.trace_id || payload.traceId}`);
  return parts.filter(Boolean).join('；');
}

export function inferFileFormat(fileOrName, mimeType = '') {
  const name = typeof fileOrName === 'string' ? fileOrName : fileOrName?.name || '';
  const normalizedMimeType = String(mimeType || fileOrName?.type || '').toLowerCase();
  const extension = name.includes('.') ? name.split('.').pop().toLowerCase() : '';

  if (extension) {
    return normalizeFormatAlias(extension);
  }

  return MIME_TYPE_TO_FORMAT[normalizedMimeType] || '';
}

export async function readFileAsBase64(file) {
  if (!(file instanceof Blob)) {
    throw new Error('No file selected.');
  }

  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error('Failed to read file.'));
    reader.onload = () => {
      const result = String(reader.result || '');
      const base64 = result.includes(',') ? result.split(',').pop() : result;
      resolve(base64 || '');
    };
    reader.readAsDataURL(file);
  });
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

async function executeFetch(path, { method, body, params, timeoutMs, signal, headers, accept }) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromParent = () => controller.abort();

  if (signal?.aborted) {
    controller.abort();
  } else if (signal) {
    signal.addEventListener('abort', abortFromParent, { once: true });
  }

  try {
    return await fetch(buildApiUrl(path, params), {
      method,
      signal: controller.signal,
      headers: buildRequestHeaders({ body, headers, accept }),
      body: serializeRequestBody(body)
    });
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

function buildRequestHeaders({ body, headers, accept }) {
  const normalizedHeaders = new Headers(headers || {});

  if (accept && !normalizedHeaders.has('Accept')) {
    normalizedHeaders.set('Accept', accept);
  }

  if (body === undefined || body === null) {
    return normalizedHeaders;
  }

  if (body instanceof FormData || body instanceof URLSearchParams || body instanceof Blob || typeof body === 'string') {
    return normalizedHeaders;
  }

  if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) {
    if (!normalizedHeaders.has('Content-Type')) {
      normalizedHeaders.set('Content-Type', 'application/octet-stream');
    }
    return normalizedHeaders;
  }

  if (!normalizedHeaders.has('Content-Type')) {
    normalizedHeaders.set('Content-Type', JSON_CONTENT_TYPE);
  }

  return normalizedHeaders;
}

function serializeRequestBody(body) {
  if (body === undefined || body === null) return undefined;
  if (body instanceof FormData || body instanceof URLSearchParams || body instanceof Blob || typeof body === 'string') return body;
  if (body instanceof ArrayBuffer || ArrayBuffer.isView(body)) return body;
  return JSON.stringify(body);
}

async function readResponsePayload(response, responseType = 'auto') {
  if (response.status === 204) {
    return null;
  }

  const contentType = (response.headers.get('content-type') || '').toLowerCase();

  if (responseType === 'blob') {
    return response.blob();
  }

  if (responseType === 'text') {
    return response.text();
  }

  if (responseType === 'json') {
    return readJsonResponse(response);
  }

  if (looksLikeJsonResponse(contentType)) {
    return readJsonResponse(response);
  }

  return response.text();
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function buildApiError(payload, status, fallbackMessage) {
  return new ApiError(readErrorMessage(payload, fallbackMessage), {
    status,
    traceId: payload?.trace_id,
    payload
  });
}

function unwrapEnvelope(payload) {
  if (payload && typeof payload === 'object' && 'data' in payload && 'code' in payload && 'message' in payload) {
    return payload.data;
  }
  return payload;
}

function isEnvelopeError(payload) {
  return payload && typeof payload === 'object' && 'code' in payload && Number(payload.code) !== 0 && Number(payload.code) !== 200;
}

function readErrorMessage(payload, fallback) {
  if (payload && typeof payload === 'object') {
    return payload.message || payload.detail || fallback || 'API request failed';
  }
  if (typeof payload === 'string' && payload.trim()) {
    return payload.trim();
  }
  return fallback || 'API request failed';
}

function looksLikeJsonResponse(contentType) {
  return contentType.includes('/json') || contentType.includes('+json');
}

function downloadBlobFile({ filename, blob, mimeType }) {
  const nextBlob = blob instanceof Blob ? blob : new Blob([blob], { type: mimeType || 'application/octet-stream' });
  const href = URL.createObjectURL(nextBlob);
  const link = document.createElement('a');
  link.href = href;
  link.download = filename || 'download.bin';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(href), 0);
}

function base64ToBlob(contentBase64, mimeType) {
  const binary = window.atob(contentBase64 || '');
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new Blob([bytes], { type: mimeType || 'application/octet-stream' });
}

function normalizeDownloadPayload(payload, options = {}) {
  const record = payload && typeof payload === 'object' && !Array.isArray(payload) ? payload : {};
  const format = normalizeFormatAlias(String(options.format || record.format || '').toLowerCase());
  const fallbackMime = options.defaultMimeType || mimeTypeForFormat(format);
  const contentBase64 = firstText(
    record.content_base64,
    record.contentBase64,
    record.file_base64,
    record.fileBase64,
    record.base64
  );
  const filename = firstText(
    record.filename,
    record.file_name,
    record.name,
    options.defaultFilename,
    `download${extensionForFormat(format)}`
  );
  const mimeType = firstText(record.mime_type, record.mimeType, record.content_type, record.contentType, fallbackMime);

  let blob = null;
  if (record.blob instanceof Blob) {
    blob = record.blob;
  } else if (record.file instanceof Blob) {
    blob = record.file;
  } else if (isBinaryLike(record.bytes || record.array_buffer || record.arrayBuffer || record.binary)) {
    blob = new Blob([record.bytes || record.array_buffer || record.arrayBuffer || record.binary], {
      type: mimeType || 'application/octet-stream'
    });
  }

  let content;
  if (blob) {
    content = blob;
  } else if (typeof payload === 'string') {
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

  if (!blob && isBinaryLike(content)) {
    blob = new Blob([content], { type: mimeType || 'application/octet-stream' });
  }

  return {
    filename,
    mimeType,
    content,
    contentBase64,
    blob,
    unsupported: isUnsupportedDownloadPayload(record),
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
  const supportText = supportedFormats.length ? `支持格式: ${supportedFormats.join(' / ')}` : '请改用后端已开放的格式。';
  return record.message || record.detail || `${formatText}导出暂不可用，${supportText}`;
}

function stringifyDownloadContent(value, prettyJson = false) {
  if (typeof value === 'string') return value;
  if (isBinaryLike(value)) return value;
  if (prettyJson || typeof value === 'object') return JSON.stringify(value, null, 2);
  return String(value);
}

function normalizeFormatList(value) {
  if (Array.isArray(value)) return value.map((item) => normalizeFormatAlias(String(item))).filter(Boolean).map((item) => item.toUpperCase());
  if (typeof value === 'string') {
    return value
      .split(/[,\s/]+/)
      .map((item) => normalizeFormatAlias(item.trim()))
      .filter(Boolean)
      .map((item) => item.toUpperCase());
  }
  return [];
}

function normalizeFormatAlias(value) {
  const normalized = String(value || '').toLowerCase();
  if (normalized === 'doc') return 'docx';
  if (normalized === 'word') return 'word';
  if (normalized === 'xls') return 'xlsx';
  return normalized;
}

function firstText(...values) {
  for (const value of values) {
    if (value !== undefined && value !== null && value !== '') return String(value);
  }
  return '';
}

function isBinaryLike(value) {
  return value instanceof Blob || value instanceof ArrayBuffer || ArrayBuffer.isView(value);
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
  return extensions[normalizeFormatAlias(format)] || '.txt';
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
  return mimeTypes[normalizeFormatAlias(format)] || 'application/octet-stream';
}

function parseFilenameFromDisposition(contentDisposition) {
  if (!contentDisposition) return '';

  const parts = contentDisposition.split(';').map((part) => part.trim());
  const filenameStarPart = parts.find((part) => part.toLowerCase().startsWith('filename*='));
  if (filenameStarPart) {
    const rawValue = filenameStarPart.slice(filenameStarPart.indexOf('=') + 1).trim().replace(/^"(.*)"$/, '$1');
    const normalizedValue = rawValue.toLowerCase().startsWith(RFC5987_PREFIX) ? rawValue.slice(RFC5987_PREFIX.length) : rawValue;
    try {
      return decodeURIComponent(normalizedValue);
    } catch {
      return normalizedValue;
    }
  }

  const filenamePart = parts.find((part) => part.toLowerCase().startsWith('filename='));
  if (!filenamePart) return '';
  return filenamePart.slice(filenamePart.indexOf('=') + 1).trim().replace(/^"(.*)"$/, '$1');
}
