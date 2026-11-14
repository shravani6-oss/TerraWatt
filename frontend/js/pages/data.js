import { api, qs } from '../api.js';
import { h, fmt, load, debounce, download, icon } from '../ui.js';
import { pageHead, sourceNote, goCountry, metricInfo } from '../components.js';

function catalogCard() {
  const ind = state.meta.provenance.indicators, total = state.meta.countries.length;
  const rows = state.meta.metrics.filter((m) => ind[m.key]);
  return h('details', { class: 'more' }, h('summary', {}, `Indicator catalog · source, unit and coverage of ${rows.length} indicators`),
    h('div', { class: 'table-wrap', style: { maxHeight: '420px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Indicator', 'Unit', 'Years', 'Latest year', 'Countries (latest)', 'Source'].map((c, i) => h('th', { class: i > 1 && i < 5 ? 'r' : '' }, c)))),
      h('tbody', {}, rows.map((m) => { const i = ind[m.key]; return h('tr', {}, h('td', { title: m.description }, m.label), h('td', {}, m.unit), h('td', { class: 'r tnum' }, `${i.first_year}–${i.latest_year}`), h('td', { class: 'r tnum' }, i.latest_year === i.broad_year ? i.latest_year : h('span', {}, i.broad_year, h('span', { class: 'year-chip partial', title: `${i.latest_year} exists but only ${i.n_latest} countries report` }, `${i.latest_year} partial`))), h('td', { class: 'r tnum' }, `${i.n_countries} of ${total} (${i.n_latest})`), h('td', { class: 'small muted' }, i.source)); })))),
    h('p', { class: 'hint', style: { margin: 0 } }, '“Latest year” is the latest year with broad coverage (at least half of the best-covered year). Later years that exist for fewer countries are marked partial. Values are never carried forward: an empty cell means the source did not report it.'));
}
import { state } from '../state.js';

const LABEL = { country: 'Country', year: 'Year', renewable_share: 'Renewables, final energy (%)', renewable_elec_share: 'Renewables, electricity (%)', solar_twh: 'Solar (TWh)', wind_twh: 'Wind (TWh)', hydro_twh: 'Hydro (TWh)', electricity_access: 'Electricity access (%)', clean_cooking_access: 'Clean cooking (%)', co2_per_capita_t: 'CO₂ per person (t)', grid_intensity: 'Grid intensity (g/kWh)' };

export default async function data() {
  const S = { q: '', year: '', sort: 'country', order: 'asc', page: 1 };
  const box = h('div', {});
  const yearSel = h('select', { class: 'input', 'aria-label': 'Year', onchange: (e) => { S.year = e.target.value; S.page = 1; draw(); } }, h('option', { value: '' }, 'All years'),
    ...Array.from({ length: state.meta.years[1] - state.meta.years[0] + 1 }, (_, i) => state.meta.years[1] - i).map((y) => h('option', { value: y }, y)));
  const search = h('input', { class: 'input', placeholder: 'Search country…', 'aria-label': 'Search country', oninput: debounce((e) => { S.q = e.target.value; S.page = 1; draw(); }, 250) });
  async function draw() {
    await load(box, async () => {
      const r = await api.get('/api/records?' + qs({ ...S, per_page: 25 }));
      if (!r.rows.length) return h('div', { class: 'state' }, h('h4', {}, 'No records match'), h('p', { class: 'muted' }, 'Try a different search or year.'));
      const pages = Math.ceil(r.total / r.per_page);
      return h('div', {}, h('div', { class: 'table-wrap' }, h('table', {},
        h('thead', {}, h('tr', {}, r.columns.map((c) => h('th', { class: 'sortable' + (c === 'country' ? '' : ' r'), 'aria-sort': S.sort === c ? (S.order === 'asc' ? 'ascending' : 'descending') : 'none', tabindex: 0,
          onclick: () => { S.order = S.sort === c && S.order === 'asc' ? 'desc' : 'asc'; S.sort = c; draw(); } }, LABEL[c] || c, S.sort === c ? (S.order === 'asc' ? ' ▲' : ' ▼') : '')))),
        h('tbody', {}, r.rows.map((row) => h('tr', {}, r.columns.map((c) => c === 'country' ? h('td', {}, h('a', { href: `#/country/${encodeURIComponent(row[c])}` }, row[c])) : h('td', { class: 'r tnum' }, c === 'year' ? row[c] : fmt(row[c], 2)))))))),
        h('div', { class: 'pager' }, h('span', { class: 'muted small' }, `${fmt(r.total, 0)} records · page ${r.page} of ${pages}`),
          h('button', { class: 'btn sm', disabled: S.page <= 1, onclick: () => { S.page--; draw(); } }, '‹ Prev'), h('button', { class: 'btn sm', disabled: S.page >= pages, onclick: () => { S.page++; draw(); } }, 'Next ›')));
    }, { height: 420 });
  }
  draw();
  return h('div', { class: 'page stack', style: { gap: '20px' } }, pageHead('Dataset explorer', `${fmt(state.meta.provenance.rows, 0)} country-year records. Search, filter, sort, and export.`),
    catalogCard(),
    h('div', { class: 'card row wrap' }, h('div', { class: 'grow', style: { minWidth: '200px' } }, search), h('div', { style: { width: '160px' } }, yearSel),
      h('p', { class: 'hint', style: { margin: 0 } }, 'Export a country from its page, or a ranking from the Atlas.')), box, sourceNote('Empty cells mean the source did not report a value.'));
}
