import { api, qs } from '../api.js';
import { h, fmt, load, clear, emptyState, signed } from '../ui.js';
import { lineChart, PALETTE } from '../charts.js';
import { pageHead, metricSelect, countryPicker, metricInfo, seg, sourceNote, tip } from '../components.js';

const QUICK = [['renewable_elec_share', 'Renewables %'], ['solar_twh', 'Solar'], ['wind_twh', 'Wind'], ['hydro_twh', 'Hydro'], ['co2_per_capita_t', 'CO₂ / person'], ['electricity_access', 'Access']];

export default async function compare({ query }) {
  const S = { metric: query.metric || 'renewable_elec_share', countries: (query.c || 'India,Germany,Brazil').split(',').filter(Boolean).slice(0, 5), from: +query.from || 2015 };
  const chips = h('div', { class: 'row wrap' }), out = h('div', {}), quick = h('div', {}), sel = h('div', {});
  const sync = () => { history.replaceState(null, '', `#/compare?${qs({ metric: S.metric, c: S.countries.join(','), from: S.from })}`); };
  const drawChips = () => clear(chips).append(...S.countries.map((c, i) => h('span', { class: 'chip', style: { border: `1.5px solid ${PALETTE[i]}` } }, c, h('button', { 'aria-label': `Remove ${c}`, onclick: () => { S.countries.splice(i, 1); drawChips(); run(); } }, '×'))),
    S.countries.length >= 5 ? h('span', { class: 'small muted' }, 'Maximum of five countries.') : null);
  const drawQuick = () => { clear(quick).append(seg(QUICK, QUICK.some(([k]) => k === S.metric) ? S.metric : '', (m) => { S.metric = m; drawSel(); run(); })); };
  const drawSel = () => { clear(sel).append(metricSelect(S.metric, (m) => { S.metric = m; drawQuick(); run(); })); };
  async function run() {
    sync();
    await load(out, async () => {
      if (!S.countries.length) return emptyState('Pick countries to compare', 'Add up to five countries with the search box above.');
      const r = await api.get('/api/compare?' + qs({ countries: S.countries.join(','), metric: S.metric }));
      const m = metricInfo(S.metric);
      const series = r.series.map((s, i) => ({ name: s.country, color: PALETTE[i], points: s.series.map((p) => ({ x: p.year, y: p.value })) }));
      if (r.world?.length) series.push({ name: 'World average', color: 'var(--ink-3)', dash: true, width: 1.8, points: r.world.map((p) => ({ x: p.year, y: p.value })) });
      if (!series.some((s) => s.points.length)) return emptyState('No data', `${m.label} is not reported for these countries.`);
      const rows = r.series.map((s) => {
        const l = s.series.at(-1), f = s.series.find((p) => p.year >= S.from), cagr = f && l && f.value > 0 && l.value > 0 && l.year > f.year ? (Math.pow(l.value / f.value, 1 / (l.year - f.year)) - 1) * 100 : null;
        return { c: s.country, v: l?.value, y: l?.year, d: f && l ? l.value - f.value : null, g: cagr, fy: f?.year };
      });
      const wl = r.world?.at(-1);
      return h('div', { class: 'stack' }, lineChart({ series, unit: m.unit, height: 360, ariaLabel: `${m.label} comparison` }),
        h('div', { class: 'legend' }, series.map((s) => h('span', { style: s.dash ? { color: 'var(--ink-3)' } : {} }, s.dash ? h('i', { class: 'dash' }) : h('i', { style: { background: s.color } }), s.name))),
        h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Country'), h('th', { class: 'r' }, 'Latest'), h('th', { class: 'r' }, 'Year'), h('th', { class: 'r' }, `Change since ${S.from}`), h('th', { class: 'r' }, 'Avg. growth / yr'))),
          h('tbody', {}, rows.map((r2) => h('tr', {}, h('td', {}, h('a', { href: `#/country/${encodeURIComponent(r2.c)}` }, r2.c)), h('td', { class: 'r tnum' }, r2.v == null ? 'no data' : fmt(r2.v, 2) + ' ' + m.unit), h('td', { class: 'r' }, r2.y ?? '–'), h('td', { class: 'r tnum' }, r2.d == null ? '–' : signed(r2.d, 2)), h('td', { class: 'r tnum' }, r2.g == null ? '–' : fmt(r2.g, 1) + '%'))),
            wl ? h('tr', { class: 'muted' }, h('td', {}, 'World average'), h('td', { class: 'r tnum' }, fmt(wl.value, 2) + ' ' + m.unit), h('td', { class: 'r' }, wl.year), h('td', { class: 'r' }, '–'), h('td', { class: 'r' }, '–')) : null))),
        h('p', { class: 'hint' }, `${m.description} `, r.world?.length ? r.world_note + '.' : 'Absolute quantities have no world average.', ' Growth rates are only shown where both end values are positive.'));
    }, { height: 380 });
  }
  drawChips(); drawQuick(); drawSel(); run();
  return h('div', { class: 'page stack', style: { gap: '20px' } }, pageHead('Compare countries', 'Overlay up to five countries on solar, wind, hydro, renewable share, CO₂ per person, electricity access and more.'),
    h('div', { class: 'card stack', style: { gap: '14px' } },
      h('div', { class: 'grid g2' }, h('label', { class: 'field' }, 'Add a country', countryPicker({ placeholder: 'Search…', onPick: (c) => { if (!S.countries.includes(c) && S.countries.length < 5) { S.countries.push(c); drawChips(); run(); } } })),
        h('label', { class: 'field' }, h('span', {}, 'Indicator', tip('Any indicator in the dataset. Quick picks above cover the common comparisons.')), sel)), quick, chips, out), sourceNote());
}
