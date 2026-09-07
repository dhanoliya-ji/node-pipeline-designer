// api/client.js
// Every call to the backend goes through here.
//
// Centralising them means one place defines the base URL, one place turns a
// failed fetch into a message a user can act on, and the components never
// touch `fetch` directly.
// --------------------------------------------------

import { toApiPayload } from '../lib/serialize';

export const API_BASE_URL =
  process.env.REACT_APP_API_URL || 'http://localhost:8000';

export class ApiError extends Error {
  constructor(message, { status = null, unreachable = false } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.unreachable = unreachable;
  }
}

const UNREACHABLE = `Couldn't reach the backend at ${API_BASE_URL}. Start it with "python -m uvicorn app.main:app --reload" in the backend folder.`;

const request = async (path, { method = 'GET', body, signal } = {}) => {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (error) {
    // fetch rejects with a TypeError when the server is not listening; an
    // aborted request is the caller's own doing and is re-thrown as-is.
    if (error.name === 'AbortError') throw error;
    throw new ApiError(UNREACHABLE, { unreachable: true });
  }

  if (!response.ok) {
    // FastAPI puts a human-readable reason in `detail` when it has one.
    let detail = `The server responded with ${response.status}.`;
    try {
      const payload = await response.json();
      if (payload?.detail) detail = String(payload.detail);
    } catch (error) {
      /* keep the status-code message */
    }
    throw new ApiError(detail, { status: response.status });
  }

  return response.json();
};

export const parsePipeline = (nodes, edges, options) =>
  request('/pipelines/parse', {
    method: 'POST',
    body: toApiPayload(nodes, edges),
    ...options,
  });

export const validatePipeline = (nodes, edges, options) =>
  request('/pipelines/validate', {
    method: 'POST',
    body: toApiPayload(nodes, edges),
    ...options,
  });

export const executePipeline = (nodes, edges, { strict = true, ...options } = {}) =>
  request(`/pipelines/execute?strict=${strict}`, {
    method: 'POST',
    body: toApiPayload(nodes, edges),
    ...options,
  });

export const fetchHealth = (options) => request('/health', options);

export const fetchNodeCatalogue = (options) => request('/nodes', options);
