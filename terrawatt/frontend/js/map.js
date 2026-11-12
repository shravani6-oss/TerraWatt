// Dot atlas: every country in the dataset plotted at its real latitude/longitude (equirectangular).
// Honest by design - no country polygons are bundled, so values are encoded as colour + area of a dot.
import { h, fmt } from './ui.js';
const NS = 'http://www.w3.org/2000/svg';
const el = (t, a = {}) => { const e = document.createElementNS(NS, t); for (const [k, v] of Object.entries(a)) e.setAttribute(k, v); return e; };

export function lerpColor(stops, t) {
  t = Math.min(1, Math.max(0, t)); const n = stops.length - 1, i = Math.min(n - 1, Math.floor(t * n)), f = t * n - i;
  const a = stops[i], b = stops[i + 1];
  return `rgb(${a.map((x, k) => Math.round(x + (b[k] - x) * f)).join(',')})`;
}
export const RAMP = [[222, 240, 214], [140, 205, 130], [28, 150, 100], [6, 70, 52]];
export const RAMP_BAD = [[255, 236, 200], [244, 176, 90], [214, 92, 70], [120, 28, 40]];

export function dotAtlas({ points, vmin, vmax, unit = '', onSelect, highlight, reverse = false, height = 460, label = '' }) {
  const wrap = h('div', { class: 'map-wrap' }), W = 1000, H = 500, tip = h('div', { class: 'chart' });
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': `World dot map of ${label}` });
  const X = (lon) => ((lon + 180) / 360) * W, Y = (lat) => ((90 - lat) / 180) * H * 0.9 + H * 0.02;
  const gr = el('g', { style: 'stroke:var(--grid);stroke-width:1' });
  for (let lon = -150; lon <= 180; lon += 30) gr.append(Object.assign(el('line', { x1: X(lon), x2: X(lon), y1: 0, y2: H }), {}));
  for (let lat = -60; lat <= 60; lat += 30) gr.append(el('line', { x1: 0, x2: W, y1: Y(lat), y2: Y(lat) }));
  gr.append(el('line', { x1: 0, x2: W, y1: Y(0), y2: Y(0), style: 'stroke:var(--line-2);stroke-dasharray:3 5' }));
  svg.append(gr);
  const ramp = reverse ? RAMP_BAD : RAMP, tipEl = h('div', { class: 'tip', style: { display: 'none', position: 'absolute' } });
  [...points].sort((a, b) => b.value - a.value).forEach((p) => {
    const t = (p.value - vmin) / (vmax - vmin || 1), r = 5 + Math.sqrt(Math.max(t, 0)) * 7;
    const c = el('circle', { cx: X(p.lon), cy: Y(p.lat), r, tabindex: 0, role: 'button', 'aria-label': `${p.country}: ${fmt(p.value)} ${unit}`,
      style: `fill:${lerpColor(ramp, t)};opacity:.9;stroke:${p.country === highlight ? 'var(--accent)' : 'var(--surface)'};stroke-width:${p.country === highlight ? 3 : 1.2}` });
    const show = () => {
      c.setAttribute('r', r + 3);
      const box = wrap.getBoundingClientRect(), pt = c.getBoundingClientRect();
      tipEl.innerHTML = `<b>${p.country.replace(/</g, '&lt;')}</b>${fmt(p.value)} ${unit}`; tipEl.style.display = 'block';
      tipEl.style.left = pt.left - box.left + pt.width / 2 + 'px'; tipEl.style.top = pt.top - box.top + 'px';
    };
    c.addEventListener('pointerenter', show); c.addEventListener('focus', show);
    c.addEventListener('pointerleave', () => { c.setAttribute('r', r); tipEl.style.display = 'none'; });
    c.addEventListener('blur', () => { tipEl.style.display = 'none'; });
    c.addEventListener('click', () => onSelect?.(p.country));
    c.addEventListener('keydown', (e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onSelect?.(p.country)));
    svg.append(c);
  });
  wrap.append(svg, tipEl);
  const [a, b, c2, d] = [0, 1, 2, 3].map((i) => `rgb(${ramp[i].join(',')})`);
  wrap.style.setProperty('--g0', a); wrap.style.setProperty('--g1', b); wrap.style.setProperty('--g2', c2); wrap.style.setProperty('--g3', d);
  const legend = h('div', { style: { padding: '10px 16px 14px' } },
    h('div', { class: 'gradient-legend' }),
    h('div', { class: 'row spread small muted', style: { marginTop: '4px' } }, h('span', {}, fmt(vmin) + ' ' + unit), h('span', {}, 'dot size & colour = value'), h('span', {}, fmt(vmax) + ' ' + unit)));
  wrap.append(legend);
  return wrap;
}

/** Hero artwork: decorative dot map built from the real country coordinates (colour = renewable share). */
const HERO_RAMP = [[150, 214, 140], [70, 176, 110], [16, 132, 90], [6, 80, 56]];
export function heroDots(points) {
  const svg = el('svg', { viewBox: '0 0 1000 500', 'aria-hidden': 'true', class: 'world' });
  const X = (lon) => ((lon + 180) / 360) * 1000, Y = (lat) => ((78 - lat) / 140) * 470 + 14;
  points.forEach((p, i) => {
    const t = Math.min(1, Math.max(0, p.value / 100));
    svg.append(el('circle', { cx: X(p.lon), cy: Y(p.lat), r: 7 + t * 5, style: `fill:${lerpColor(HERO_RAMP, t)};animation:pulse 4s ${(i % 17) * 0.23}s ease-in-out infinite` }));
  });
  return svg;
}
