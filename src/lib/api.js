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
