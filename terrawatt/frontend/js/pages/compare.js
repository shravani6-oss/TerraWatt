import { api, qs } from '../api.js';
import { h, fmt, load, clear, emptyState, download, icon } from '../ui.js';
import { lineChart, PALETTE } from '../charts.js';
import { pageHead, metricSelect, countryPicker, metricInfo, sourceNote } from '../components.js';

export default async function compare({ query }) {
  const S = { metric: query.metric || 'renewable_share', countries: (query.c || 'India,Germany,Brazil').split(',').filter(Boolean).slice(0, 5) };
  const chips = h('div', { class: 'row wrap' }), out = h('div', {});
  const sync = () => { history.replaceState(null, '', `#/compare?${qs({ metric: S.metric, c: S.countries.join(',') })}`); };
  const drawChips = () => { clear(chips).append(...S.countries.map((c, i) => h('span', { class: 'chip', style: { border: `1.5px solid ${PALETTE[i]}` } }, c, h('button', { 'aria-label': `Remove ${c}`, onclick: () => { S.countries.splice(i, 1); drawChips(); run(); } }, '×')))); };
  async function run() {
    sync();
    await load(out, async () => {
      if (!S.countries.length) return emptyState('Pick countries to compare', 'Add up to five countries with the search box above.');
      const r = await api.get('/api/compare?' + qs({ countries: S.countries.join(','), metric: S.metric }));
      const m = metricInfo(S.metric);
      const series = r.series.map((s, i) => ({ name: s.country, color: PALETTE[i], points: s.series.map((p) => ({ x: p.year, y: p.value })) }));
      const rows = r.series.map((s) => { const l = s.series.at(-1), f = s.series[0]; return [s.country, l?.value, l?.year, f && l ? l.value - f.value : null]; });
      return h('div', { class: 'stack' }, lineChart({ series, unit: m.unit, height: 360, ariaLabel: `${m.label} comparison` }),
        h('div', { class: 'legend' }, series.map((s) => h('span', {}, h('i', { style: { background: s.color } }), s.name))),
        h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Country'), h('th', { class: 'r' }, 'Latest'), h('th', { class: 'r' }, 'Year'), h('th', { class: 'r' }, 'Change since first year'))),
          h('tbody', {}, rows.map((r2) => h('tr', {}, h('td', {}, h('a', { href: `#/country/${encodeURIComponent(r2[0])}` }, r2[0])), h('td', { class: 'r tnum' }, fmt(r2[1], 2) + ' ' + m.unit), h('td', { class: 'r' }, r2[2] ?? '–'), h('td', { class: 'r tnum' }, r2[3] == null ? '–' : (r2[3] > 0 ? '+' : '') + fmt(r2[3], 2))))))));
    }, { height: 380 });
  }
  drawChips(); run();
  return h('div', { class: 'page stack', style: { gap: '20px' } }, pageHead('Compare countries', 'Overlay up to five countries on any indicator.'),
    h('div', { class: 'card stack', style: { gap: '14px' } },
      h('div', { class: 'grid g2' }, h('label', { class: 'field' }, 'Add a country', countryPicker({ placeholder: 'Search…', onPick: (c) => { if (!S.countries.includes(c) && S.countries.length < 5) { S.countries.push(c); drawChips(); run(); } } })),
        h('label', { class: 'field' }, 'Indicator', metricSelect(S.metric, (m) => { S.metric = m; run(); }))), chips, out), sourceNote());
}
