import { api, qs } from '../api.js';
import { h, fmt, load, delta, download, debounce, clear, icon } from '../ui.js';
import { dotAtlas } from '../map.js';
import { pageHead, metricSelect, metricInfo, goCountry, sourceNote } from '../components.js';
import { state } from '../state.js';

export default async function atlas({ query }) {
  const S = { metric: query.metric || 'renewable_share', year: +query.year || state.meta.headline_year, q: '', sort: 'desc' };
  const [y0, y1] = state.meta.years;
  const mapBox = h('div', {}), tableBox = h('div', {}), yearLabel = h('b', { class: 'tnum' }, S.year);
  const slider = h('input', { type: 'range', min: y0, max: y1, value: S.year, 'aria-label': 'Year', oninput: (e) => { yearLabel.textContent = e.target.value; }, onchange: (e) => { S.year = +e.target.value; draw(); } });
  const mSel = metricSelect(S.metric, (m) => { S.metric = m; draw(); }, () => true);
  const search = h('input', { class: 'input', placeholder: 'Filter table…', 'aria-label': 'Filter countries', oninput: debounce((e) => { S.q = e.target.value; drawTable(); }, 200) });
  const info = h('p', { class: 'sub' });
  const exportBtn = h('button', { class: 'btn', onclick: () => download('/api/export/rankings.csv?' + qs({ metric: S.metric, year: S.year, q: S.q, sort: S.sort })) }, icon('download'), 'CSV');
  async function draw() {
    const m = metricInfo(S.metric); clear(info).append(`${m.description}${m.derived ? ' (derived by TerraWatt, approximate)' : ''}`);
    await load(mapBox, async () => {
      const r = await api.get('/api/map?' + qs({ metric: S.metric, year: S.year }), { cache: true });
      if (!r.points.length) return h('div', { class: 'state' }, h('h4', {}, 'No data for this metric and year'), h('p', { class: 'muted' }, 'Try an earlier year; some indicators stop before 2020.'));
      return dotAtlas({ points: r.points, vmin: r.min, vmax: r.max, unit: m.unit, label: m.label, reverse: m.higher_is_better === false, onSelect: goCountry });
    }, { height: 420 });
    drawTable();
  }
  async function drawTable() {
    const m = metricInfo(S.metric);
    await load(tableBox, async () => {
      const r = await api.get('/api/rankings?' + qs({ metric: S.metric, year: S.year, q: S.q, sort: S.sort }));
      if (!r.rows.length) return h('div', { class: 'state' }, h('h4', {}, 'No countries match'), h('p', { class: 'muted' }, 'Clear the filter or choose another year.'));
      const max = Math.max(...r.rows.map((x) => Math.abs(x.value)));
      return h('div', { class: 'table-wrap', style: { maxHeight: '520px' } }, h('table', {},
        h('thead', {}, h('tr', {}, h('th', {}, '#'), h('th', {}, 'Country'), h('th', { class: 'sortable', onclick: () => { S.sort = S.sort === 'desc' ? 'asc' : 'desc'; drawTable(); } }, `${m.label} (${m.unit}) ${S.sort === 'desc' ? '▼' : '▲'}`), h('th', { class: 'r' }, 'Δ vs prior year'))),
        h('tbody', {}, r.rows.map((x) => h('tr', { class: 'link', tabindex: 0, onclick: () => goCountry(x.country), onkeydown: (e) => e.key === 'Enter' && goCountry(x.country) },
          h('td', { class: 'muted tnum' }, x.rank), h('td', {}, h('b', {}, x.country)),
          h('td', {}, h('div', { class: 'bar-cell' }, h('span', { class: 'tnum', style: { width: '70px', fontWeight: 600 } }, fmt(x.value)), h('i', { style: { width: (Math.abs(x.value) / max) * 100 + 'px', maxWidth: '140px' } }))),
          h('td', { class: 'r' }, delta(x.change, { good: m.higher_is_better === false ? 'down' : 'up', d: 2 })))))));
    }, { height: 300 });
  }
  draw();
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Atlas', 'Every country at its real coordinates. Dot size and colour show the selected indicator.', exportBtn),
    h('div', { class: 'card stack', style: { gap: '12px' } },
      h('div', { class: 'grid g3', style: { alignItems: 'end' } }, h('label', { class: 'field' }, 'Indicator', mSel),
        h('label', { class: 'field' }, h('span', { class: 'row spread' }, 'Year', yearLabel), slider), h('label', { class: 'field' }, 'Filter table', search)),
      info, mapBox),
    tableBox, sourceNote());
}
