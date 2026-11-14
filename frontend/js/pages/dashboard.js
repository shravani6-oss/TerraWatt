import { api } from '../api.js';
import { h, fmt, delta, load, emptyState, compact } from '../ui.js';
import { lineChart, barH, spark } from '../charts.js';
import { dotAtlas } from '../map.js';
import { kpi, pageHead, seg, goCountry, sourceNote, metricInfo } from '../components.js';
import { state } from '../state.js';

const MAP_METRICS = [['renewable_elec_share', 'Renewables in electricity'], ['grid_intensity', 'Grid carbon intensity'], ['co2_per_capita_t', 'CO₂ per person'], ['electricity_access', 'Electricity access']];
const PTS = (v) => delta(v, { unit: ' pts', d: 1 });

export default async function dashboard() {
  const ov = await api.get('/api/overview', { cache: true });
  const k = ov.kpis;
  const tw = (key) => compact(k[key].value);
  const pct = (x) => (x.value != null && x.prev ? ((x.value - x.prev) / x.prev) * 100 : null);
  return h('div', { class: 'page stack', style: { gap: '22px' } },
    pageHead('Global overview', `Renewable electricity and related indicators. Every figure carries its own reporting year, because indicators are published on different schedules.`),
    ov.partial_year_note && h('div', { class: 'note-partial' }, ov.partial_year_note),
    h('div', { class: 'grid g3 kpi-row' },
      kpi({ label: 'Renewable share of electricity', year: k.renewable_elec_share.year, value: fmt(k.renewable_elec_share.value, 1), unit: '%', delta: PTS(k.renewable_elec_share.change), hint: `${k.renewable_elec_share.n} countries · change vs ${k.renewable_elec_share.year - 1}, same countries` }),
      kpi({ label: 'Renewable generation', year: k.renewable_twh.year, value: tw('renewable_twh'), unit: 'TWh', delta: delta(pct(k.renewable_twh), { unit: '%' }), hint: `Solar ${tw('solar_twh')} · Wind ${tw('wind_twh')} · Hydro ${tw('hydro_twh')} TWh` }),
      kpi({ label: 'Grid carbon intensity', year: k.grid_intensity.year, value: fmt(k.grid_intensity.value, 0), unit: 'g CO₂e/kWh', delta: delta(k.grid_intensity.change, { good: 'down', d: 0, unit: ' g' }), hint: 'Generation-weighted, lifecycle' }),
      kpi({ label: 'Fossil CO₂ emissions', year: k.co2_mt.year, value: fmt(k.co2_mt.value / 1000, 1), unit: 'Gt', delta: delta(pct(k.co2_mt), { good: 'down', unit: '%' }), hint: `${k.co2_mt.n} countries · territorial` }),
      kpi({ label: 'Access to electricity', year: k.electricity_access.year, value: fmt(k.electricity_access.value, 1), unit: '%', delta: PTS(k.electricity_access.change), hint: 'Population-weighted · World Bank series ends in 2020' }),
      kpi({ label: 'Renewables in final energy', year: k.renewable_share.year, value: fmt(k.renewable_share.value, 1), unit: '%', delta: PTS(k.renewable_share.change), hint: 'Median country · includes traditional biomass' })),
    h('div', { class: 'grid g-main' }, mapCard(), leadersCard()),
    h('div', { class: 'grid g-main' }, trendCard(ov), sourcesCard()),
    state.user ? watchlistCard() : h('div', { class: 'card callout green row spread wrap' }, h('div', {}, h('b', {}, 'Make it yours. '), 'Create a free account to watch countries, set alerts, and track your household carbon footprint and goals.'), h('a', { class: 'btn primary', href: '#/register' }, 'Create account')),
    sourceNote());
}

function mapCard() {
  const S = { metric: 'renewable_elec_share' };
  const body = h('div', {}), title = h('div', { class: 'sub' });
  const draw = () => {
    const mi = metricInfo(S.metric);
    const year = mi.default_year;
    title.textContent = `${mi.label} (${mi.unit}) · ${year}${mi.latest_year > year ? ` · ${mi.latest_year} is partial` : ''}`;
    load(body, async () => {
      const r = await api.get(`/api/map?metric=${S.metric}&year=${year}`, { cache: true });
      if (!r.points.length) return emptyState('No data', 'This indicator has no reports for that year.');
      return dotAtlas({ points: r.points, vmin: r.min, vmax: r.max, unit: mi.unit, label: mi.label, reverse: mi.higher_is_better === false, onSelect: goCountry });
    }, { height: 420 });
  };
  const card = h('div', { class: 'card' }, h('div', { class: 'row spread wrap' }, h('h3', {}, 'World map'), seg(MAP_METRICS, S.metric, (m) => { S.metric = m; draw(); })), title, h('div', { style: { marginTop: '10px' } }, body));
  draw(); return card;
}

function leadersCard() {
  const S = { m: 'renewable_elec_share' }, body = h('div', {}), sub = h('p', { class: 'sub' });
  const draw = () => load(body, async () => {
    const r = await api.get(`/api/rankings?metric=${S.m}&limit=10`, { cache: true });
    const mi = metricInfo(S.m);
    sub.textContent = `Top 10 · ${r.year} · ${r.total} countries reporting`;
    const max = S.m === 'renewable_elec_share' ? 100 : undefined;
    return barH({ rows: r.rows.map((x) => ({ label: x.country, value: x.value, onClick: () => goCountry(x.country) })), max, format: (v) => (S.m === 'renewable_elec_share' ? fmt(v, 1) + '%' : compact(v)) });
  }, { height: 300 });
  const card = h('div', { class: 'card' }, h('div', { class: 'row spread wrap' }, h('h3', {}, 'Top countries'), seg([['renewable_elec_share', 'Share'], ['elec_renewable_twh', 'TWh']], S.m, (m) => { S.m = m; draw(); })), sub, h('div', { style: { marginTop: '12px' } }, body));
  draw(); return card;
}

function trendCard(ov) {
  const body = h('div', {});
  const card = h('div', { class: 'card' }, h('h3', {}, 'Renewable share of electricity, 2000 onward'), h('p', { class: 'sub' }, 'World total over reporting countries. Dashed = partial latest year.'), h('div', { style: { marginTop: '12px' } }, body));
  load(body, async () => {
    const t = (await api.get('/api/trend/global', { cache: true })).series.filter((r) => r.renewable_elec_share != null);
    const full = t.filter((r) => !r.partial), part = t.filter((r) => r.partial);
    const series = [{ name: 'Reporting countries', color: 'var(--c1)', area: true, points: full.map((r) => ({ x: r.year, y: r.renewable_elec_share })) }];
    if (part.length) series.push({ name: `Partial year (${part[0].n_electricity} countries)`, color: 'var(--c2)', dash: true, points: [{ x: full.at(-1).year, y: full.at(-1).renewable_elec_share }, ...part.map((r) => ({ x: r.year, y: r.renewable_elec_share }))] });
    return h('div', {}, lineChart({ series, unit: '%', yMin: 0, height: 300, ariaLabel: 'Global renewable share of electricity over time' }),
      h('div', { class: 'legend' }, h('span', {}, h('i', { style: { background: 'var(--c1)' } }), 'Full coverage'), part.length ? h('span', { style: { color: 'var(--c2)' } }, h('i', { class: 'dash' }), 'Partial year') : null));
  }, { height: 300 });
  return card;
}

function sourcesCard() {
  const body = h('div', {});
  const card = h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('h3', {}, 'What renewables are made of'), h('a', { class: 'btn sm', href: '#/renewables' }, 'Source analysis')), h('p', { class: 'sub' }, 'Share of renewable generation by source'), h('div', { style: { marginTop: '12px' } }, body));
  load(body, async () => {
    const g = await api.get('/api/renewables/global', { cache: true });
    return h('div', { class: 'stack', style: { gap: '10px' } },
      barH({ rows: g.sources.map((s) => ({ label: s.label, value: s.share_of_renewables, color: ({ solar_twh: 'var(--c2)', wind_twh: 'var(--c3)', hydro_twh: 'var(--c1)', bioenergy_twh: 'var(--c5)', other_renew_twh: 'var(--c4)' })[s.key] })), max: 100, format: (v) => fmt(v, 1) + '%' }),
      h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, `Solar growth ${g.year - 5}→${g.year}`), h('b', {}, '+' + compact(g.sources.find((s) => s.key === 'solar_twh').growth_5y) + ' TWh')),
      h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, `Wind growth ${g.year - 5}→${g.year}`), h('b', {}, '+' + compact(g.sources.find((s) => s.key === 'wind_twh').growth_5y) + ' TWh')),
      h('p', { class: 'hint', style: { margin: 0 } }, `${g.year} generation (Ember). This is electricity, not final energy.`));
  }, { height: 260 });
  return card;
}

function watchlistCard() {
  const body = h('div', {});
  const card = h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('h3', {}, 'Your watchlist'), h('a', { class: 'btn sm', href: '#/alerts' }, 'Manage')), h('div', { style: { marginTop: '12px' } }, body));
  load(body, async () => {
    const { items } = await api.get('/api/watchlist');
    if (!items.length) return emptyState('Nothing watched yet', 'Open any country and press “Watch” to follow it here.');
    return h('div', { class: 'grid g3' }, items.map((i) => h('div', { class: 'card', style: { cursor: 'pointer', boxShadow: 'none' }, onclick: () => goCountry(i.country) },
      h('div', { class: 'row spread' }, h('b', {}, i.country), spark(i.series.map((p) => p.value), { w: 80 })),
      h('div', { class: 'big-num tnum', style: { fontSize: '30px', marginTop: '6px' } }, fmt(i.value, 1), h('small', { class: 'muted', style: { fontSize: '14px', fontFamily: 'var(--sans)' } }, '% · ' + i.year)))));
  }, { height: 90 });
  return card;
}
