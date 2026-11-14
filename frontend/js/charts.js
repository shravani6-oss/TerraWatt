// Dependency-free SVG charts: responsive, themeable through CSS variables, keyboard-safe tooltips.
import { h, fmt } from './ui.js';
const NS = 'http://www.w3.org/2000/svg';
const s = (tag, attrs = {}, ...kids) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) (k === 'style' ? e.setAttribute('style', v) : e.setAttribute(k, v));
  e.append(...kids.flat().filter(Boolean)); return e;
};
export const PALETTE = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)'];

export function niceTicks(min, max, n = 5) {
  if (min === max) { max = min + 1; }
  const span = max - min, step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= step0);
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, out = [];
  for (let v = lo; v <= hi + step / 2; v += step) out.push(+v.toFixed(10));
  return out;
}

function mount(height, draw) {
  const wrap = h('div', { class: 'chart' });
  const tip = h('div', { class: 'tip', style: { display: 'none' } });
  const render = () => {
    const w = Math.max(wrap.clientWidth, 120);
    wrap.querySelector('svg')?.remove();
    const svg = s('svg', { viewBox: `0 0 ${w} ${height}`, height, role: 'img' });
    wrap.prepend(svg); draw(svg, w, height, tip, wrap);
  };
  wrap.append(tip);
  let t; const ro = new ResizeObserver(() => { clearTimeout(t); t = setTimeout(render, 60); });
  queueMicrotask(() => { if (wrap.isConnected) { render(); ro.observe(wrap); } else requestAnimationFrame(() => { render(); ro.observe(wrap); }); });
  wrap.cleanup = () => ro.disconnect();
  return wrap;
}
function showTip(tip, wrap, x, y, html) {
  tip.innerHTML = html; tip.style.display = 'block';
  const half = tip.offsetWidth / 2, w = wrap.clientWidth;
  tip.style.left = Math.min(Math.max(x, half + 4), w - half - 4) + 'px'; tip.style.top = y + 'px';
}
const hideTip = (tip) => { tip.style.display = 'none'; };
const E = (str) => String(str).replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

/** series: [{name,color,points:[{x,y}],dash?,band?:[{x,lo,hi}],area?}] */
export function lineChart({ series, height = 300, unit = '', yMin, yMax, yFormat = (v) => fmt(v, 1), xFormat = (v) => v, decimals = 1, zeroBase = false, markX, ariaLabel }) {
  return mount(height, (svg, W, H, tip, wrap) => {
    svg.setAttribute('aria-label', ariaLabel || 'Line chart');
    const m = { t: 12, r: 14, b: 26, l: 46 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    const all = series.flatMap((d) => [...d.points.map((p) => p.y), ...(d.band || []).flatMap((b) => [b.lo, b.hi])]).filter((v) => v != null);
    const xs = series.flatMap((d) => d.points.map((p) => p.x));
    if (!all.length) { svg.append(s('text', { x: W / 2, y: H / 2, 'text-anchor': 'middle', class: 'ax' }, 'No data')); return; }
    let lo = yMin ?? Math.min(...all), hi = yMax ?? Math.max(...all);
    if (zeroBase) lo = Math.min(0, lo);
    const ticks = niceTicks(lo, hi, Math.max(3, Math.floor(ih / 55)));
    lo = yMin ?? ticks[0]; hi = yMax ?? ticks[ticks.length - 1];
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * iw, Y = (v) => m.t + ih - ((v - lo) / (hi - lo || 1)) * ih;
    const g = s('g', { class: 'grid' }), ax = s('g', { class: 'ax' });
    ticks.filter((t) => t >= lo && t <= hi).forEach((t) => {
      g.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }));
      ax.append(s('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end' }, yFormat(t)));
    });
    const step = Math.max(1, Math.ceil((x1 - x0) / Math.max(2, Math.floor(iw / 62))));
    for (let v = x0; v <= x1; v += step) ax.append(s('text', { x: X(v), y: H - 6, 'text-anchor': v === x0 ? 'start' : 'middle' }, xFormat(v)));
    svg.append(g, ax);
    if (markX != null && markX >= x0 && markX <= x1) svg.append(s('line', { x1: X(markX), x2: X(markX), y1: m.t, y2: m.t + ih, style: 'stroke:var(--ink-3);stroke-dasharray:2 4' }));
    series.forEach((d, i) => {
      const col = d.color || PALETTE[i % 5];
      if (d.band?.length) svg.append(s('path', { d: 'M' + d.band.map((b) => `${X(b.x)},${Y(b.hi)}`).join('L') + 'L' + [...d.band].reverse().map((b) => `${X(b.x)},${Y(b.lo)}`).join('L') + 'Z', style: `fill:${col};opacity:.16` }));
      const pts = d.points.filter((p) => p.y != null);
      if (!pts.length) return;
      const path = 'M' + pts.map((p) => `${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join('L');
      if (d.area) svg.append(s('path', { d: `${path}L${X(pts.at(-1).x)},${Y(lo)}L${X(pts[0].x)},${Y(lo)}Z`, style: `fill:${col};opacity:.12` }));
      svg.append(s('path', { d: path, fill: 'none', style: `stroke:${col};stroke-width:${d.width || 2.4};stroke-linejoin:round;stroke-linecap:round;${d.dash ? 'stroke-dasharray:6 5' : ''}` }));
      if (pts.length < 40 && !d.dash) pts.forEach((p) => svg.append(s('circle', { cx: X(p.x), cy: Y(p.y), r: 2.6, style: `fill:var(--surface);stroke:${col};stroke-width:1.6` })));
    });
    // hover crosshair
    const cross = s('line', { y1: m.t, y2: m.t + ih, style: 'stroke:var(--ink-3);stroke-width:1;display:none' });
    const dots = series.map((d, i) => s('circle', { r: 4.5, style: `fill:${d.color || PALETTE[i % 5]};stroke:var(--surface);stroke-width:2;display:none` }));
    svg.append(cross, ...dots);
    const overlay = s('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent', tabindex: 0 });
    const move = (clientX) => {
      const r = svg.getBoundingClientRect(), px = clientX - r.left, xv = x0 + ((px - m.l) / iw) * (x1 - x0);
      const nearest = xs.reduce((a, b) => (Math.abs(b - xv) < Math.abs(a - xv) ? b : a));
      cross.setAttribute('x1', X(nearest)); cross.setAttribute('x2', X(nearest)); cross.style.display = '';
      const lines = [];
      series.forEach((d, i) => {
        const p = d.points.find((q) => q.x === nearest);
        if (p && p.y != null) {
          dots[i].setAttribute('cx', X(p.x)); dots[i].setAttribute('cy', Y(p.y)); dots[i].style.display = '';
          const b = d.band?.find((q) => q.x === nearest);
          lines.push(`<span style="color:${'#fff'}">${E(d.name)}: <b style="display:inline">${fmt(p.y, decimals)}${unit ? ' ' + E(unit) : ''}</b>${b ? ` <span style="opacity:.7">(${fmt(b.lo, decimals)}–${fmt(b.hi, decimals)})</span>` : ''}${d.dash ? ' <i style="opacity:.7">forecast</i>' : ''}</span>`);
        } else dots[i].style.display = 'none';
      });
      showTip(tip, wrap, X(nearest), m.t + 6, `<b>${xFormat(nearest)}</b>${lines.join('<br>')}`);
    };
    overlay.addEventListener('pointermove', (e) => move(e.clientX));
    overlay.addEventListener('pointerleave', () => { hideTip(tip); cross.style.display = 'none'; dots.forEach((d) => (d.style.display = 'none')); });
    svg.append(overlay);
  });
}

/** rows:[{x, a:..,b:..}] keys:[{key,name,color}] — stacked area in absolute units */
export function stackedArea({ rows, keys, height = 280, unit = '', percent = false, xFormat = (v) => v }) {
  return mount(height, (svg, W, H, tip, wrap) => {
    svg.setAttribute('aria-label', 'Stacked area chart');
    const m = { t: 10, r: 14, b: 26, l: 46 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    if (!rows.length) return;
    const tot = rows.map((r) => keys.reduce((a, k) => a + (r[k.key] || 0), 0));
    const max = percent ? 100 : Math.max(...tot), ticks = niceTicks(0, max, 4), top = ticks.at(-1);
    const x0 = rows[0].x, x1 = rows.at(-1).x;
    const X = (v) => m.l + ((v - x0) / (x1 - x0 || 1)) * iw, Y = (v) => m.t + ih - (v / top) * ih;
    const ax = s('g', { class: 'ax' }), g = s('g', { class: 'grid' });
    ticks.forEach((t) => { g.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) })); ax.append(s('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end' }, percent ? t + '%' : fmt(t, 0))); });
    const step = Math.max(1, Math.ceil((x1 - x0) / Math.max(2, Math.floor(iw / 62))));
    for (let v = x0; v <= x1; v += step) ax.append(s('text', { x: X(v), y: H - 6, 'text-anchor': v === x0 ? 'start' : 'middle' }, xFormat(v)));
    svg.append(g, ax);
    const base = rows.map(() => 0);
    keys.forEach((k) => {
      const lower = [...base];
      rows.forEach((r, i) => { base[i] += percent ? ((r[k.key] || 0) / (tot[i] || 1)) * 100 : r[k.key] || 0; });
      const d = 'M' + rows.map((r, i) => `${X(r.x)},${Y(base[i])}`).join('L') + 'L' + rows.map((r, i) => `${X(r.x)},${Y(lower[i])}`).reverse().join('L') + 'Z';
      svg.append(s('path', { d, style: `fill:${k.color};opacity:.88` }));
    });
    const cross = s('line', { y1: m.t, y2: m.t + ih, style: 'stroke:var(--ink);stroke-width:1;display:none' });
    const overlay = s('rect', { x: m.l, y: m.t, width: iw, height: ih, fill: 'transparent' });
    overlay.addEventListener('pointermove', (e) => {
      const r = svg.getBoundingClientRect(), xv = x0 + ((e.clientX - r.left - m.l) / iw) * (x1 - x0);
      const row = rows.reduce((a, b) => (Math.abs(b.x - xv) < Math.abs(a.x - xv) ? b : a)), t = keys.reduce((a, k) => a + (row[k.key] || 0), 0);
      cross.setAttribute('x1', X(row.x)); cross.setAttribute('x2', X(row.x)); cross.style.display = '';
      showTip(tip, wrap, X(row.x), m.t + 6, `<b>${xFormat(row.x)}</b>` + keys.map((k) => `${E(k.name)}: <b style="display:inline">${fmt(row[k.key] || 0, 1)} ${unit}</b> (${fmt(((row[k.key] || 0) / (t || 1)) * 100, 0)}%)`).join('<br>'));
    });
    overlay.addEventListener('pointerleave', () => { hideTip(tip); cross.style.display = 'none'; });
    svg.append(cross, overlay);
  });
}

/** Horizontal bars: rows [{label,value,color?,onClick?,sub?}] */
export function barH({ rows, format = (v) => fmt(v, 1), color = 'var(--c1)', max, rowH = 30 }) {
  const top = max ?? Math.max(...rows.map((r) => Math.abs(r.value)), 1), hasNeg = rows.some((r) => r.value < 0);
  return h('div', { class: 'stack', style: { gap: '6px' } }, rows.map((r) => {
    const pct = (Math.abs(r.value) / top) * 100;
    return h('div', { class: 'row', style: { gap: '10px', minHeight: rowH + 'px', cursor: r.onClick ? 'pointer' : 'default' }, onclick: r.onClick, title: r.sub || '' },
      h('div', { style: { width: '38%', minWidth: '96px', fontSize: '13.5px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, r.label),
      h('div', { class: 'grow', style: { background: 'var(--surface-2)', borderRadius: '5px', height: '10px', position: 'relative' } },
        h('i', { style: { position: 'absolute', left: 0, top: 0, bottom: 0, width: pct + '%', borderRadius: '5px', background: r.color || (hasNeg && r.value < 0 ? 'var(--c4)' : color), transition: 'width .6s cubic-bezier(.2,.8,.2,1)' } })),
      h('div', { class: 'tnum', style: { width: '64px', textAlign: 'right', fontWeight: 600, fontSize: '13.5px' } }, format(r.value)));
  }));
}

export function donut({ parts, size = 150, thickness = 22, center }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1, r = (size - thickness) / 2, C = 2 * Math.PI * r;
  let off = 0; const svg = s('svg', { viewBox: `0 0 ${size} ${size}`, width: size, height: size, role: 'img', 'aria-label': 'Donut chart' });
  svg.append(s('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', style: `stroke:var(--surface-2);stroke-width:${thickness}` }));
  parts.forEach((p) => {
    const len = (p.value / total) * C;
    svg.append(s('circle', { cx: size / 2, cy: size / 2, r, fill: 'none', transform: `rotate(-90 ${size / 2} ${size / 2})`, style: `stroke:${p.color};stroke-width:${thickness};stroke-dasharray:${len} ${C - len};stroke-dashoffset:${-off}` }, s('title', {}, `${p.label}: ${fmt(p.value, 1)}`)));
    off += len;
  });
  if (center) svg.append(s('text', { x: size / 2, y: size / 2 + 6, 'text-anchor': 'middle', style: 'font:600 20px var(--serif);fill:var(--ink)' }, center));
  return h('div', { class: 'row', style: { gap: '20px', alignItems: 'center' } }, svg,
    h('div', { class: 'legend', style: { flexDirection: 'column', gap: '8px' } }, parts.map((p) => h('span', {}, h('i', { style: { background: p.color } }), `${p.label} · ${fmt((p.value / total) * 100, 0)}%`))));
}

export function spark(values, { w = 96, hgt = 34, color = 'var(--c1)' } = {}) {
  const v = values.filter((x) => x != null); if (v.length < 2) return h('span');
  const lo = Math.min(...v), hi = Math.max(...v), X = (i) => (i / (v.length - 1)) * (w - 4) + 2, Y = (x) => hgt - 3 - ((x - lo) / (hi - lo || 1)) * (hgt - 6);
  const d = 'M' + v.map((x, i) => `${X(i)},${Y(x)}`).join('L');
  return s('svg', { viewBox: `0 0 ${w} ${hgt}`, width: w, height: hgt, 'aria-hidden': 'true', class: 'spark' },
    s('path', { d: `${d}L${X(v.length - 1)},${hgt}L${X(0)},${hgt}Z`, style: `fill:${color};opacity:.14` }),
    s('path', { d, fill: 'none', style: `stroke:${color};stroke-width:2;stroke-linecap:round;stroke-linejoin:round` }),
    s('circle', { cx: X(v.length - 1), cy: Y(v.at(-1)), r: 2.8, style: `fill:${color}` }));
}

/** points:[{x,y,color,label,onClick}] */
export function scatter({ points, height = 360, xLabel = '', yLabel = '' }) {
  return mount(height, (svg, W, H, tip, wrap) => {
    svg.setAttribute('aria-label', 'Scatter plot');
    const m = { t: 10, r: 14, b: 34, l: 40 }, iw = W - m.l - m.r, ih = H - m.t - m.b;
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const xt = niceTicks(Math.min(...xs), Math.max(...xs), 6), yt = niceTicks(Math.min(...ys), Math.max(...ys), 5);
    const X = (v) => m.l + ((v - xt[0]) / (xt.at(-1) - xt[0])) * iw, Y = (v) => m.t + ih - ((v - yt[0]) / (yt.at(-1) - yt[0])) * ih;
    const g = s('g', { class: 'grid' }), ax = s('g', { class: 'ax' });
    yt.forEach((t) => { g.append(s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) })); ax.append(s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, fmt(t, 1))); });
    xt.forEach((t) => ax.append(s('text', { x: X(t), y: H - 16, 'text-anchor': 'middle' }, fmt(t, 1))));
    ax.append(s('text', { x: W / 2, y: H - 2, 'text-anchor': 'middle' }, xLabel), s('text', { x: m.l + 8, y: m.t + 14, 'text-anchor': 'start' }, yLabel));
    svg.append(g, ax);
    points.forEach((p) => {
      const c = s('circle', { cx: X(p.x), cy: Y(p.y), r: 5, style: `fill:${p.color};opacity:.78;stroke:var(--surface);stroke-width:1;cursor:${p.onClick ? 'pointer' : 'default'}` });
      c.addEventListener('pointerenter', () => { c.setAttribute('r', 8); showTip(tip, wrap, X(p.x), Y(p.y) - 6, p.label); });
      c.addEventListener('pointerleave', () => { c.setAttribute('r', 5); hideTip(tip); });
      if (p.onClick) c.addEventListener('click', p.onClick);
      svg.append(c);
    });
  });
}
