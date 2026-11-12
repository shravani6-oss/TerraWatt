// Tiny DOM + UI toolkit: hyperscript helper, icons, formatting, toasts, modal, states.
export function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;            // only used with trusted, static strings
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
export const $ = (sel, root = document) => root.querySelector(sel);
export const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };

const P = {
  home: 'M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18',
  trend: 'M3 17l6-6 4 4 8-9M15 6h6v6',
  flask: 'M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2.2h12.4a1.5 1.5 0 0 0 1.3-2.2L14 9V3',
  leaf: 'M5 21c0-9 5-15 15-16 0 10-6 15-14 15M5 21c2-5 5-8 9-10',
  bell: 'M6 9a6 6 0 1 1 12 0c0 6 2 7 2 7H4s2-1 2-7M10 20a2 2 0 0 0 4 0',
  table: 'M3 5h18v14H3zM3 10h18M9 5v14',
  cpu: 'M7 7h10v10H7zM4 9h3M4 15h3M17 9h3M17 15h3M9 4v3M15 4v3M9 17v3M15 17v3',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4',
  moon: 'M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z',
  menu: 'M4 6h16M4 12h16M4 18h16',
  download: 'M12 3v12M7 10l5 5 5-5M4 21h16',
  plus: 'M12 5v14M5 12h14',
  x: 'M6 6l12 12M18 6L6 18',
  star: 'M12 3l2.8 5.8 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.3l1.1-6.2L3 9.7l6.2-.9z',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  alert: 'M12 3l10 18H2zM12 10v5M12 18v.01',
  bolt: 'M13 2L4 14h7l-1 8 9-12h-7z',
  logout: 'M9 4H5v16h4M16 8l4 4-4 4M20 12H9',
  inbox: 'M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5',
  file: 'M6 3h8l4 4v14H6zM14 3v5h4',
  scale: 'M12 4v16M5 20h14M5 8l-3 7a3.5 3.5 0 0 0 6 0zM19 8l-3 7a3.5 3.5 0 0 0 6 0zM5 8h14',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 8v.01',
  check: 'M5 12.5l4.5 4.5L19 7',
};
export function icon(name) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor');
  s.setAttribute('stroke-width', '1.8'); s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
  s.setAttribute('aria-hidden', 'true');
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', P[name] || P.info);
  s.append(p); return s;
}
export function logoMark() {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 32 32'); s.setAttribute('class', 'mark'); s.setAttribute('aria-hidden', 'true');
  s.innerHTML = '<rect width="32" height="32" rx="9" fill="var(--brand)"/><path d="M8 22c0-8 5-13 15-14 0 9-5 14-13 14" fill="none" stroke="var(--brand-ink)" stroke-width="2.2" stroke-linecap="round"/><path d="M8 24c3-4 6-7 11-9" fill="none" stroke="var(--brand-ink)" stroke-width="2.2" stroke-linecap="round"/>';
  return s;
}

// ---------- formatting
export const fmt = (v, d = 1) => v == null || Number.isNaN(v) ? '–' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: 0 });
export const compact = (v) => v == null ? '–' : Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(v);
export function signed(v, d = 1, unit = '') { if (v == null) return '–'; const s = v > 0 ? '+' : v < 0 ? '−' : ''; return s + fmt(Math.abs(v), d) + unit; }
export function delta(v, { unit = '', good = 'up', d = 1, suffix = '' } = {}) {
  if (v == null) return h('span', { class: 'delta flat' }, '–');
  const dir = Math.abs(v) < 0.05 ? 'flat' : v > 0 ? 'up' : 'down';
  const isGood = dir === 'flat' ? null : (dir === 'up') === (good === 'up');
  const cls = dir === 'flat' ? 'flat' : isGood ? 'up' : 'down';
  return h('span', { class: `delta ${cls}` }, dir === 'up' ? '▲' : dir === 'down' ? '▼' : '■', ' ', fmt(Math.abs(v), d) + unit, suffix && h('span', { class: 'muted', style: { fontWeight: 500 } }, ' ' + suffix));
}
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// ---------- toasts / modal / states
let toastBox;
export function toast(msg, kind = '') {
  if (!toastBox) { toastBox = h('div', { class: 'toasts', role: 'status', 'aria-live': 'polite' }); document.body.append(toastBox); }
  const t = h('div', { class: `toast ${kind}` }, msg); toastBox.append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 6000 : 3500);
}
export function modal(title, body, actions = []) {
  return new Promise((resolve) => {
    const close = (v) => { bg.remove(); document.removeEventListener('keydown', onKey); resolve(v); };
    const onKey = (e) => e.key === 'Escape' && close(false);
    const bg = h('div', { class: 'modal-bg', onclick: (e) => e.target === bg && close(false) },
      h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
        h('h3', { style: { fontSize: '20px', marginBottom: '10px' } }, title), body,
        h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '20px' } },
          ...actions.map((a) => h('button', { class: `btn ${a.class || ''}`, onclick: () => close(a.value) }, a.label)))));
    document.addEventListener('keydown', onKey); document.body.append(bg);
    bg.querySelector('button')?.focus();
  });
}
export const confirmBox = (title, text, okLabel = 'Delete') =>
  modal(title, h('p', { class: 'muted', style: { margin: 0 } }, text), [{ label: 'Cancel', value: false }, { label: okLabel, value: true, class: 'danger' }]);

export const skeleton = (height = 200) => h('div', { class: 'skeleton', style: { height: height + 'px' }, 'aria-busy': 'true' });
export function emptyState(title, text, action) {
  return h('div', { class: 'state' }, icon('inbox'), h('h4', {}, title), h('p', { class: 'muted', style: { margin: 0, maxWidth: '42ch' } }, text), action);
}
export function errorState(err, retry) {
  return h('div', { class: 'state' }, icon('alert'), h('h4', {}, 'Something went wrong'),
    h('p', { class: 'muted', style: { margin: 0 } }, err?.message || 'Unexpected error'),
    retry && h('button', { class: 'btn', onclick: retry }, 'Try again'));
}
/** Render async content into a container with skeleton → content/error lifecycle. */
export async function load(container, fn, { height = 200 } = {}) {
  clear(container).append(skeleton(height));
  try { const node = await fn(); clear(container).append(node); }
  catch (e) { console.error(e); clear(container).append(errorState(e, () => load(container, fn, { height }))); }
}
export function debounce(fn, ms = 250) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
export function download(url) { const a = h('a', { href: url, download: '' }); document.body.append(a); a.click(); a.remove(); }
export const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
