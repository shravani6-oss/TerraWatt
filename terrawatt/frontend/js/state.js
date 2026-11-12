// Shared, minimal app state (no framework): user, metadata, theme.
export const state = { user: null, meta: null, notifications: { unread: 0, items: [] } };
const listeners = new Set();
export const onState = (fn) => (listeners.add(fn), () => listeners.delete(fn));
export const emit = () => listeners.forEach((f) => f(state));
export function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem('tw-theme', t); } catch { /* storage unavailable */ }
}
export function initialTheme() {
  let t = null; try { t = localStorage.getItem('tw-theme'); } catch { /* ignore */ }
  return t || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
