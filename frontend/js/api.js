// Fetch wrapper: CSRF header, JSON errors normalised to ApiError, small GET cache for public data.
export class ApiError extends Error {
  constructor(status, code, message, details) { super(message); this.status = status; this.code = code; this.details = details; }
}
const cache = new Map();
async function request(method, url, body) {
  const opts = { method, headers: { 'X-Requested-With': 'TerraWatt' }, credentials: 'same-origin' };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  let res;
  try { res = await fetch(url, opts); } catch { throw new ApiError(0, 'network', 'Cannot reach the server. Check your connection.'); }
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json() : null;
  if (!res.ok) {
    const e = data?.error || {};
    throw new ApiError(res.status, e.code || 'error', e.message || `Request failed (${res.status})`, e.details);
  }
  return data;
}
export const api = {
  get(url, { cache: useCache = false } = {}) {
    if (useCache && cache.has(url)) return cache.get(url);
    const p = request('GET', url); if (useCache) { cache.set(url, p); p.catch(() => cache.delete(url)); } return p;
  },
  post: (u, b = {}) => request('POST', u, b), put: (u, b = {}) => request('PUT', u, b),
  patch: (u, b = {}) => request('PATCH', u, b), del: (u) => request('DELETE', u),
};
export const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)).toString();
