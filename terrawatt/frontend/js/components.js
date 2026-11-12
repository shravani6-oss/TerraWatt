import { h, icon, fmt, delta, debounce, clear } from './ui.js';
import { state } from './state.js';
import { spark } from './charts.js';

export function pageHead(title, subtitle, ...actions) {
  return h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, title), subtitle && h('p', {}, subtitle)),
    actions.length ? h('div', { class: 'row wrap' }, ...actions) : null);
}
export function kpi({ label, value, unit, delta: d, series, hint }) {
  return h('div', { class: 'card kpi' }, h('div', { class: 'label' }, label),
    h('div', { class: 'value tnum' }, value, unit && h('small', {}, unit)),
    d ?? null, hint && h('div', { class: 'hint' }, hint),
    series ? spark(series) : null);
}
export const metricInfo = (key) => state.meta.metrics.find((m) => m.key === key);
export function metricSelect(value, onChange, filter = () => true, id = 'metric') {
  const sel = h('select', { class: 'input', id, 'aria-label': 'Metric', onchange: (e) => onChange(e.target.value) },
    state.meta.metrics.filter(filter).map((m) => h('option', { value: m.key, selected: m.key === value }, `${m.label}${m.derived ? ' ~' : ''}`)));
  return sel;
}
export function seg(options, value, onChange) {
  const box = h('div', { class: 'seg', role: 'group' });
  const draw = (v) => { clear(box).append(...options.map(([k, label]) => h('button', { 'aria-pressed': String(k === v), onclick: () => { draw(k); onChange(k); } }, label))); };
  draw(value); return box;
}
export function tabs(items, active, onChange) {
  const box = h('div', { class: 'tabs', role: 'tablist' });
  const draw = (v) => { clear(box).append(...items.map(([k, label]) => h('button', { role: 'tab', 'aria-selected': String(k === v), onclick: () => { draw(k); onChange(k); } }, label))); };
  draw(active); return box;
}
/** Typeahead country picker. onPick(country) */
export function countryPicker({ placeholder = 'Search countries…', onPick, clearOnPick = true, value = '' }) {
  const input = h('input', { class: 'input', placeholder, 'aria-label': placeholder, autocomplete: 'off', value });
  const wrap = h('div', { class: 'search', style: { maxWidth: 'none' } }, icon('search'), input);
  let pop = null, idx = 0, list = [];
  const close = () => { pop?.remove(); pop = null; };
  const pick = (c) => { close(); if (clearOnPick) input.value = ''; else input.value = c; onPick(c); };
  const open = () => {
    const q = input.value.trim().toLowerCase();
    list = state.meta.countries.filter((c) => c.toLowerCase().includes(q)).sort((a, b) => (a.toLowerCase().startsWith(q) ? 0 : 1) - (b.toLowerCase().startsWith(q) ? 0 : 1)).slice(0, 8);
    close(); if (!list.length) return;
    idx = 0;
    pop = h('div', { class: 'pop', role: 'listbox' }, list.map((c, i) => h('button', { role: 'option', class: i === 0 ? 'active' : '', onmousedown: (e) => { e.preventDefault(); pick(c); } }, c)));
    wrap.append(pop);
  };
  input.addEventListener('input', debounce(open, 80)); input.addEventListener('focus', open);
  input.addEventListener('blur', () => setTimeout(close, 120));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (!pop) return open(); idx = (idx + (e.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length; [...pop.children].forEach((b, i) => b.classList.toggle('active', i === idx)); }
    else if (e.key === 'Enter' && pop) { e.preventDefault(); pick(list[idx]); } else if (e.key === 'Escape') close();
  });
  return wrap;
}
export const sourceNote = (extra = '') => h('p', { class: 'hint' }, `Historical data, not a live feed: ${state.meta.provenance.source}. ${extra}`);
export const goCountry = (name) => { location.hash = `#/country/${encodeURIComponent(name)}`; };
export function labelFor(metric) { const m = metricInfo(metric); return m ? m.label : metric; }
export { delta, fmt, spark };
