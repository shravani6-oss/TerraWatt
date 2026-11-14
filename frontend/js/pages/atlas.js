import { api, qs } from '../api.js';
import { h, fmt, load, delta, download, debounce, clear, icon, toast } from '../ui.js';
import { dotAtlas } from '../map.js';
import { pageHead, metricSelect, metricInfo, goCountry, sourceNote, tip } from '../components.js';
import { state } from '../state.js';

export default async function atlas({ query }) {
  const S = { metric: query.metric || 'renewable_elec_share', year: null, q: '', sort: 'desc', picked: new Set() };
  const mapBox = h('div', {}), tableBox = h('div', {}), availBox = h('div', {}), cmpBar = h('div', {}), ctl = h('div', {});
  const defaultYear = (m) => metricInfo(m).default_year;
  S.year = +query.year || defaultYear(S.metric);
  const drawControls = () => {
    const mi = metricInfo(S.metric);
    const slider = h('input', { type: 'range', min: mi.first_year ?? 2000, max: mi.latest_year, value: S.year, 'aria-label': 'Year', oninput: (e) => { yv.textContent = e.target.value; }, onchange: (e) => { S.year = +e.target.value; draw(); } });
    const yv = h('b', { class: 'tnum' }, S.year);
    clear(ctl).append(h('div', { class: 'grid g3', style: { alignItems: 'end' } },
      h('label', { class: 'field' }, 'Indicator', metricSelect(S.metric, (m) => { S.metric = m; S.year = defaultYear(m); drawControls(); draw(); })),
      h('label', { class: 'field' }, h('span', { class: 'row spread' }, h('span', {}, 'Year', tip('Each indicator has its own range of years. The slider only covers years the source reports.')), yv), slider),
      h('label', { class: 'field' }, 'Filter table', h('input', { class: 'input', placeholder: 'Filter countries…', 'aria-label': 'Filter countries', value: S.q, oninput: debounce((e) => { S.q = e.target.value; drawTable(); }, 200) }))));
  };
  const info = h('p', { class: 'sub' });
  const exportBtn = h('button', { class: 'btn', onclick: () => download('/api/export/rankings.csv?' + qs({ metric: S.metric, year: S.year, q: S.q, sort: S.sort })) }, icon('download'), 'CSV');
  const drawCmp = () => {
    clear(cmpBar);
    if (!S.picked.size) return;
    cmpBar.append(h('div', { class: 'card row wrap spread', style: { padding: '10px 14px' } }, h('span', {}, h('b', {}, S.picked.size), ` selected: ${[...S.picked].join(', ')}`),
      h('div', { class: 'row' }, h('button', { class: 'btn sm ghost', onclick: () => { S.picked.clear(); drawCmp(); drawTable(); } }, 'Clear'), h('a', { class: 'btn sm primary', href: `#/compare?${qs({ metric: S.metric, c: [...S.picked].join(',') })}` }, 'Compare selected'))));
  };
  async function draw() {
    const m = metricInfo(S.metric), ind = m;
    clear(info).append(`${m.description} Source: ${m.source}.`);
    await load(mapBox, async () => {
      const r = await api.get('/api/map?' + qs({ metric: S.metric, year: S.year }), { cache: true });
      const partial = S.year > m.default_year;
      const total = state.meta.countries.length;
      clear(availBox).append(h('div', { class: 'row wrap small' }, h('span', { class: 'chip green' }, `${r.points.length} of ${total} countries report ${m.label.toLowerCase()} in ${S.year}`),
        partial ? h('span', { class: 'chip amber' }, `${S.year} is a partial year`) : null, h('span', { class: 'muted' }, `Reported ${m.first_year}–${m.latest_year}`)));
      if (!r.points.length) return h('div', { class: 'state' }, h('h4', {}, 'No data for this indicator and year'), h('p', { class: 'muted' }, `Choose a year between ${m.first_year} and ${m.latest_year}.`));
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
        h('thead', {}, h('tr', {}, h('th', { class: 'sel-col' }, h('span', { class: 'sr' }, 'Select')), h('th', {}, '#'), h('th', {}, 'Country'), h('th', { class: 'sortable', onclick: () => { S.sort = S.sort === 'desc' ? 'asc' : 'desc'; drawTable(); } }, `${m.label} (${m.unit}) ${S.sort === 'desc' ? '▼' : '▲'}`), h('th', { class: 'r' }, 'Δ vs prior year'))),
        h('tbody', {}, r.rows.map((x) => h('tr', { class: 'link', tabindex: 0, onclick: (e) => { if (e.target.closest('input')) return; goCountry(x.country); }, onkeydown: (e) => e.key === 'Enter' && goCountry(x.country) },
          h('td', {}, h('input', { type: 'checkbox', 'aria-label': `Select ${x.country} for comparison`, checked: S.picked.has(x.country), onchange: (e) => { if (e.target.checked && S.picked.size >= 5) { e.target.checked = false; return toast('You can compare up to five countries'); } e.target.checked ? S.picked.add(x.country) : S.picked.delete(x.country); drawCmp(); } })),
          h('td', { class: 'muted tnum' }, x.rank), h('td', {}, h('b', {}, x.country)),
          h('td', {}, h('div', { class: 'bar-cell' }, h('span', { class: 'tnum', style: { width: '70px', fontWeight: 600 } }, fmt(x.value, 2)), h('i', { style: { width: (Math.abs(x.value) / max) * 100 + 'px', maxWidth: '140px' } }))),
          h('td', { class: 'r' }, delta(x.change, { good: m.higher_is_better === false ? 'down' : 'up', d: 2 })))))));
    }, { height: 300 });
  }
  drawControls(); draw();
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Atlas', 'Every country at its real coordinates. Dot size and colour show the selected indicator in the chosen year.', exportBtn),
    h('div', { class: 'card stack', style: { gap: '12px' } }, ctl, info, availBox, mapBox),
    cmpBar, tableBox, sourceNote());
}
