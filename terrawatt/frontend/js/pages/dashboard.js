import { api } from '../api.js';
import { h, fmt, delta, load, emptyState, icon, compact } from '../ui.js';
import { lineChart, stackedArea, barH, spark } from '../charts.js';
import { kpi, pageHead, seg, goCountry, sourceNote } from '../components.js';
import { state } from '../state.js';

export default async function dashboard() {
  const [ov, trend] = await Promise.all([api.get('/api/overview', { cache: true }), api.get('/api/trend/global', { cache: true })]);
  const k = ov.kpis, t = trend.series;
  const sp = (key) => t.map((r) => r[key]);
  const page = h('div', { class: 'page stack', style: { gap: '22px' } },
    pageHead('Global overview', `Where the world stands in ${ov.year}, the latest year with broad renewable-share coverage.`,
      h('span', { class: 'chip green' }, 'Historical data · ' + ov.year)),
    h('div', { class: 'grid g4 kpi-row' },
      kpi({ label: 'Renewable share of electricity', value: fmt(k.global_renewable_electricity_share, 1), unit: '%', delta: delta(k.global_renewable_electricity_share - k.global_renewable_electricity_share_prev, { unit: ' pts', suffix: 'vs ' + (ov.year - 1) }), series: sp('renewable_elec_share') }),
      kpi({ label: 'Renewable generation', value: compact(k.renewable_twh), unit: 'TWh', delta: delta((k.renewable_twh / k.renewable_twh_prev - 1) * 100, { unit: '%', suffix: 'vs ' + (ov.year - 1) }), series: sp('renewable_twh') }),
      kpi({ label: 'Avg. electricity access', value: fmt(k.avg_electricity_access, 1), unit: '%', delta: delta(k.avg_electricity_access - k.avg_electricity_access_prev, { unit: ' pts', suffix: 'vs ' + (ov.year - 1) }), series: sp('electricity_access') }),
      kpi({ label: `CO₂ emissions (${k.co2_year})`, value: fmt(k.co2_mt / 1000, 1), unit: 'Gt', delta: delta((k.co2_mt / k.co2_mt_prev - 1) * 100, { unit: '%', good: 'down', suffix: 'vs prior year' }), series: sp('co2_mt') })),
    h('div', { class: 'grid g-main' },
      h('div', { class: 'card' }, h('h3', {}, 'World electricity mix'), h('p', { class: 'sub' }, 'Share of generation by source, all reporting countries'),
        h('div', { style: { marginTop: '12px' } }, stackedArea({ rows: t.filter((r) => r.fossil_twh != null).map((r) => ({ x: r.year, Fossil: r.fossil_twh, Nuclear: r.nuclear_twh, Renewable: r.renewable_twh })), keys: [{ key: 'Fossil', name: 'Fossil', color: 'var(--c4)' }, { key: 'Nuclear', name: 'Nuclear', color: 'var(--c5)' }, { key: 'Renewable', name: 'Renewable', color: 'var(--c1)' }], percent: true, unit: 'TWh', height: 290 })),
        h('div', { class: 'legend' }, [['Fossil', '--c4'], ['Nuclear', '--c5'], ['Renewable', '--c1']].map(([n, c]) => h('span', {}, h('i', { style: { background: `var(${c})` } }), n)))),
      h('div', { class: 'card' }, h('h3', {}, 'Renewables in the electricity mix'), h('p', { class: 'sub' }, 'Generation-weighted global share, %'),
        h('div', { style: { marginTop: '12px' } }, lineChart({ series: [{ name: 'Global', points: t.filter((r) => r.renewable_elec_share != null).map((r) => ({ x: r.year, y: r.renewable_elec_share })), area: true }], unit: '%', yMin: 0, height: 290, ariaLabel: 'Global renewable electricity share over time' })))),
    h('div', { class: 'grid g3' }, leaderCard(), moversCard('gainers', ov), moversCard('decliners', ov)),
    state.user ? watchlistCard() : h('div', { class: 'card callout green row spread wrap' }, h('div', {}, h('b', {}, 'Make it yours. '), 'Create a free account to watch countries, set threshold alerts and log your own carbon footprint.'), h('a', { class: 'btn primary', href: '#/register' }, 'Create account')),
    sourceNote('Leaders by share of final energy are often low-income countries that rely on traditional biomass; compare with the electricity-based view.'));
  return page;
}

function leaderCard() {
  const body = h('div', {});
  const card = h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('h3', {}, 'Leaders'),
    seg([['renewable_elec_share', 'Electricity'], ['renewable_share', 'Final energy']], 'renewable_elec_share', (m) => draw(m))), h('p', { class: 'sub' }, 'Top 8 countries, % renewable'), h('div', { style: { marginTop: '12px' } }, body));
  const draw = (m) => load(body, async () => {
    const r = await api.get(`/api/rankings?metric=${m}&limit=8`, { cache: true });
    return barH({ rows: r.rows.map((x) => ({ label: x.country, value: x.value, onClick: () => goCountry(x.country) })), max: 100, format: (v) => fmt(v, 1) + '%' });
  }, { height: 260 });
  draw('renewable_elec_share'); return card;
}
function moversCard(kind, ov) {
  const rows = ov.movers[kind], [a, b] = ov.movers.window, good = kind === 'gainers';
  return h('div', { class: 'card' }, h('h3', {}, good ? 'Biggest gainers' : 'Biggest decliners'), h('p', { class: 'sub' }, `Renewable share of final energy, ${a}→${b} (points)`),
    h('div', { style: { marginTop: '12px' } }, barH({ rows: rows.map((x) => ({ label: x.country, value: x.delta, color: good ? 'var(--c1)' : 'var(--c4)', onClick: () => goCountry(x.country) })), format: (v) => (v > 0 ? '+' : '') + fmt(v, 1) })));
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
