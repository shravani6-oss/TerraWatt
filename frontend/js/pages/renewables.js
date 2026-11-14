import { api, qs } from '../api.js';
import { h, fmt, load, clear, compact, emptyState, signed } from '../ui.js';
import { lineChart, stackedArea, barH, PALETTE } from '../charts.js';
import { pageHead, seg, tabs, countryPicker, goCountry, sourceNote, tip } from '../components.js';
import { state } from '../state.js';

const SRC = [['solar_twh', 'Solar', 'var(--c2)'], ['wind_twh', 'Wind', 'var(--c3)'], ['hydro_twh', 'Hydropower', 'var(--c1)'], ['bioenergy_twh', 'Bioenergy', 'var(--c5)'], ['other_renew_twh', 'Geothermal & other', 'var(--c4)']];
const COLOR = Object.fromEntries(SRC.map(([k, , c]) => [k, c]));
const LABEL = Object.fromEntries(SRC.map(([k, l]) => [k, l]));

export default async function renewables({ query }) {
  const g = await api.get('/api/renewables/global', { cache: true });
  const tabsBox = h('div', {}), body = h('div', {});
  const views = { world: () => worldView(g), countries: () => rankingView(), compare: () => compareView(query), dominant: () => dominantView(), movers: () => moversView() };
  const show = (k) => { clear(body).append(views[k]()); };
  show('world');
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Renewable energy by source', `Electricity generation from solar, wind, hydropower, bioenergy and geothermal & other, ${g.sources[0] ? '2000–' + g.year : ''}.`),
    h('div', { class: 'callout green' }, h('b', {}, 'Generation is not the same as final energy. '), 'Everything on this page is electricity generation (TWh) and shares of electricity, from Ember. The “renewable share of final energy” used elsewhere (World Bank, includes traditional biomass and heat) is a different measure and ends in 2020.'),
    g.partial_year_note && h('div', { class: 'note-partial' }, g.partial_year_note),
    h('div', { class: 'card' }, tabs([['world', 'World'], ['countries', 'Country ranking'], ['compare', 'Compare countries'], ['dominant', 'Dominant source'], ['movers', 'Fastest change']], 'world', show), body),
    sourceNote('Geothermal is reported together with wave and tidal power as “other renewables”; it is not available separately.'));
}

/* ---------------------------------------------------------------- world */
function worldView(g) {
  const tr = g.trend.filter((r) => r.n_electricity > 0);
  const full = tr.filter((r) => !r.partial);
  const S = { pct: false };
  const mix = h('div', {});
  const drawMix = () => clear(mix).append(
    stackedArea({ rows: full.map((r) => ({ x: r.year, ...Object.fromEntries(SRC.map(([k]) => [k, r[k]])) })), keys: SRC.map(([key, name, color]) => ({ key, name, color })), percent: S.pct, unit: 'TWh', height: 300 }),
    h('div', { class: 'legend' }, SRC.map(([, n, c]) => h('span', {}, h('i', { style: { background: c } }), n))));
  drawMix();
  const index = (k) => { const b = full.find((r) => r.year === 2015)?.[k]; return full.filter((r) => r.year >= 2015).map((r) => ({ x: r.year, y: (r[k] / b) * 100 })); };
  return h('div', { class: 'stack', style: { gap: '22px' } },
    h('div', { class: 'grid g-main' },
      h('div', {}, h('div', { class: 'row spread wrap' }, h('h3', {}, 'Renewable electricity mix'), seg([['abs', 'TWh'], ['pct', '% of renewables']], 'abs', (v) => { S.pct = v === 'pct'; drawMix(); })), h('p', { class: 'sub' }, 'World total over reporting countries, full-coverage years'), h('div', { style: { marginTop: '10px' } }, mix)),
      h('div', {}, h('h3', {}, `Contribution in ${g.year}`), h('p', { class: 'sub' }, `World renewable generation: ${compact(g.sources.reduce((a, s) => a + s.twh, 0))} TWh`),
        h('div', { style: { marginTop: '12px' } }, barH({ rows: g.sources.map((s) => ({ label: s.label, value: s.share_of_renewables, color: COLOR[s.key] })), max: 100, format: (v) => fmt(v, 1) + '%' })),
        h('p', { class: 'hint' }, 'Share of renewable generation. Of all electricity: ' + g.sources.map((s) => `${s.label} ${fmt(s.share_of_electricity, 1)}%`).join(' · ')))),
    h('div', {}, h('h3', {}, 'Growth by source'), h('p', { class: 'sub' }, `${g.sources[0].first_year}→${g.year}`),
      h('div', { class: 'table-wrap', style: { marginTop: '10px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Source', `TWh ${g.sources[0].first_year}`, `TWh ${g.year}`, 'Change (5 yrs)', 'Avg. growth / yr', '% of renewables'].map((c, i) => h('th', { class: i ? 'r' : '' }, c)))),
        h('tbody', {}, g.sources.map((s) => h('tr', {}, h('td', {}, h('span', { class: 'sw', style: { background: COLOR[s.key] } }), s.label), h('td', { class: 'r tnum' }, fmt(s.twh_first, 0)), h('td', { class: 'r tnum' }, fmt(s.twh, 0)), h('td', { class: 'r tnum' }, signed(s.growth_5y, 0)), h('td', { class: 'r tnum' }, s.cagr == null ? '–' : fmt(s.cagr, 1) + '%'), h('td', { class: 'r tnum' }, fmt(s.share_of_renewables, 1) + '%'))))))),
    h('div', {}, h('div', { class: 'row' }, h('h3', {}, 'Solar versus wind'), tip('Generation indexed to 2015 = 100, so the two sources with very different sizes can be compared by growth rate. Absolute TWh are in the table above.')),
      h('p', { class: 'sub' }, 'World generation indexed to 2015 = 100'), h('div', { style: { marginTop: '10px' } }, lineChart({ series: [{ name: 'Solar', color: 'var(--c2)', points: index('solar_twh') }, { name: 'Wind', color: 'var(--c3)', points: index('wind_twh') }, { name: 'Hydropower', color: 'var(--c1)', points: index('hydro_twh') }], unit: '', yFormat: (v) => fmt(v, 0), decimals: 0, height: 280, ariaLabel: 'Solar, wind and hydro generation indexed to 2015' })),
      h('div', { class: 'legend' }, ['Solar', 'Wind', 'Hydropower'].map((n, i) => h('span', {}, h('i', { style: { background: ['var(--c2)', 'var(--c3)', 'var(--c1)'][i] } }), n)))));
}

/* ---------------------------------------------------------------- ranking */
function rankingView() {
  const S = { src: 'solar_twh', by: 'twh' }, out = h('div', {});
  const draw = () => load(out, async () => {
    const r = await api.get('/api/renewables/ranking?' + qs({ source: S.src, by: S.by, limit: 15 }));
    if (!r.rows.length) return emptyState('No data', 'No country reports this source for the selected year.');
    return h('div', { class: 'stack' }, h('p', { class: 'sub', style: { margin: 0 } }, `${r.label} · ${r.year} · ${r.n} countries reporting · world total ${compact(r.global_twh)} TWh`),
      barH({ rows: r.rows.map((x) => ({ label: x.country, value: x.value, onClick: () => goCountry(x.country), sub: `${fmt(x.twh, 1)} TWh · ${fmt(x.share_of_global, 1)}% of world` })), max: S.by === 'share' ? 100 : undefined, format: (v) => (S.by === 'share' ? fmt(v, 1) + '%' : compact(v) + ' TWh'), color: COLOR[S.src] || 'var(--c1)' }),
      h('p', { class: 'hint' }, S.by === 'share' ? 'Share of the country’s own electricity generation. Small systems can score high with little absolute generation.' : 'Absolute generation. Hover a row for the share of world generation.'));
  }, { height: 380 });
  const card = h('div', { class: 'stack' }, h('div', { class: 'row wrap spread' }, seg([...SRC.map(([k, l]) => [k, l])], S.src, (v) => { S.src = v; draw(); }), seg([['twh', 'Generation'], ['share', 'Share of electricity']], S.by, (v) => { S.by = v; draw(); })), out);
  draw(); return card;
}

/* ---------------------------------------------------------------- compare */
function compareView(query) {
  const S = { countries: (query.c || 'India,China,Germany,Brazil').split(',').filter(Boolean).slice(0, 5), mode: 'share' };
  const chips = h('div', { class: 'row wrap' }), out = h('div', {});
  const drawChips = () => clear(chips).append(...S.countries.map((c, i) => h('span', { class: 'chip', style: { border: `1.5px solid ${PALETTE[i]}` } }, c, h('button', { 'aria-label': `Remove ${c}`, onclick: () => { S.countries.splice(i, 1); drawChips(); run(); } }, '×'))));
  const run = () => load(out, async () => {
    if (!S.countries.length) return emptyState('Pick countries', 'Add up to five countries to compare their renewable sources.');
    const rs = await Promise.all(S.countries.map((c) => api.get('/api/renewables/country/' + encodeURIComponent(c))));
    const rows = rs.map((r) => ({ c: r.country, year: r.latest_year, latest: r.latest || [], none: r.sources_without_data }));
    const key = S.mode === 'share' ? 'share_of_electricity' : 'twh';
    const max = Math.max(...rows.flatMap((r) => r.latest.map((x) => x[key] || 0)), 1);
    return h('div', { class: 'stack', style: { gap: '18px' } },
      rows.map((r) => h('div', {}, h('div', { class: 'row spread' }, h('b', {}, r.c), h('span', { class: 'small muted' }, r.year ? `${r.year} generation` : 'no generation data')),
        r.latest.length ? h('div', { class: 'bar-compare' }, r.latest.flatMap((x) => [h('span', {}, h('i', { class: 'sw', style: { background: COLOR[x.key] } }), x.label), h('div', { class: 'progress', style: { height: '10px' } }, h('i', { style: { width: ((x[key] || 0) / max) * 100 + '%', background: COLOR[x.key] } })), h('span', { class: 'tnum' }, x[key] == null ? 'n/a' : S.mode === 'share' ? fmt(x[key], 1) + '%' : fmt(x[key], 1) + ' TWh')])) : emptyState('No generation data', 'This country has no Ember generation records.'),
        r.none.length ? h('p', { class: 'hint', style: { margin: '4px 0 0' } }, `Not reported: ${r.none.join(', ')}.`) : null)),
      h('p', { class: 'hint' }, S.mode === 'share' ? 'Each bar is a source’s share of that country’s total electricity generation.' : 'Absolute generation. Bars are scaled to the largest value shown.'));
  }, { height: 300 });
  drawChips(); run();
  return h('div', { class: 'stack' }, h('div', { class: 'row wrap spread' }, h('div', { style: { width: 'min(320px,100%)' } }, countryPicker({ placeholder: 'Add a country (max 5)…', onPick: (c) => { if (!S.countries.includes(c) && S.countries.length < 5) { S.countries.push(c); drawChips(); run(); } } })), seg([['share', '% of electricity'], ['twh', 'TWh']], S.mode, (v) => { S.mode = v; run(); })), chips, out);
}

/* ---------------------------------------------------------------- dominant */
function dominantView() {
  const S = { q: '', src: '' }, out = h('div', {});
  load(out, async () => {
    const d = await api.get('/api/renewables/dominant');
    const draw = () => {
      const rows = d.rows.filter((r) => (!S.src || r.key === S.src) && r.country.toLowerCase().includes(S.q.toLowerCase())).sort((a, b) => b.renewable_twh - a.renewable_twh);
      clear(box).append(h('div', { class: 'table-wrap', style: { maxHeight: '440px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Country', 'Dominant renewable source', 'Share of its renewables', 'Renewable TWh'].map((c, i) => h('th', { class: i > 1 ? 'r' : '' }, c)))),
        h('tbody', {}, rows.map((r) => h('tr', { class: 'link', tabindex: 0, onclick: () => goCountry(r.country), onkeydown: (e) => e.key === 'Enter' && goCountry(r.country) }, h('td', {}, h('b', {}, r.country)), h('td', {}, h('span', { class: 'sw', style: { background: COLOR[r.key] } }), r.source), h('td', { class: 'r tnum' }, fmt(r.share_of_renewables, 0) + '%'), h('td', { class: 'r tnum' }, fmt(r.renewable_twh, 1))))))));
    };
    const box = h('div', {});
    const counts = Object.entries(d.counts).sort((a, b) => b[1] - a[1]);
    const res = h('div', { class: 'stack' }, h('p', { class: 'sub', style: { margin: 0 } }, `${d.rows.length} countries with renewable generation in ${d.year}. The dominant source is the one with the most generation.`),
      h('div', { class: 'row wrap' }, h('button', { class: 'chip', style: { border: 0, cursor: 'pointer' }, onclick: () => { S.src = ''; draw(); } }, 'All'), ...counts.map(([n, c]) => { const k = Object.keys(LABEL).find((x) => LABEL[x] === n); return h('button', { class: 'chip', style: { border: 0, cursor: 'pointer', boxShadow: `inset 0 0 0 1.5px ${COLOR[k]}` }, onclick: () => { S.src = k; draw(); } }, `${n}: ${c}`); }),
        h('input', { class: 'input', style: { maxWidth: '220px' }, placeholder: 'Filter countries…', 'aria-label': 'Filter countries', oninput: (e) => { S.q = e.target.value; draw(); } })), box);
    draw(); return res;
  }, { height: 380 }).then(() => {});
  return out;
}

/* ---------------------------------------------------------------- movers */
function moversView() {
  const out = h('div', {});
  load(out, async () => {
    const ov = await api.get('/api/overview', { cache: true });
    const m = ov.movers, [a, b] = m.window;
    const col = (rows, good) => h('div', {}, h('h3', {}, good ? 'Biggest gainers' : 'Biggest decliners'), h('p', { class: 'sub' }, `Renewable share of electricity, ${a}→${b}, percentage points`),
      h('div', { style: { marginTop: '10px' } }, barH({ rows: rows.map((x) => ({ label: x.country, value: x.delta, color: good ? 'var(--c1)' : 'var(--c4)', onClick: () => goCountry(x.country), sub: `now ${fmt(x.value, 1)}%` })), format: (v) => signed(v, 1) })));
    return h('div', { class: 'grid g2' }, col(m.gainers, true), col(m.decliners, false));
  }, { height: 320 });
  return out;
}
