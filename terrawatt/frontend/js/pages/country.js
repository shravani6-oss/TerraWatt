import { api, qs } from '../api.js';
import { h, fmt, delta, load, icon, toast, download, signed, clear, emptyState } from '../ui.js';
import { lineChart, stackedArea, donut, spark } from '../charts.js';
import { kpi, pageHead, tabs, metricInfo, goCountry, sourceNote } from '../components.js';
import { state } from '../state.js';

const CARDS = ['renewable_share', 'renewable_elec_share', 'electricity_access', 'clean_cooking_access', 'co2_per_capita_t', 'grid_intensity'];

export default async function country({ params }) {
  const name = params.name;
  const p = await api.get(`/api/countries/${encodeURIComponent(name)}`);
  const c = p.info.country;
  document.title = `${c} · TerraWatt`;
  let watched = false;
  if (state.user) { try { watched = (await api.get('/api/watchlist')).items.some((i) => i.country === c); } catch {} }
  const watchBtn = h('button', { class: 'btn' });
  const paintWatch = () => { clear(watchBtn).append(icon('star'), watched ? 'Watching' : 'Watch'); watchBtn.classList.toggle('primary', watched); };
  paintWatch();
  watchBtn.onclick = async () => {
    if (!state.user) { toast('Sign in to watch countries'); return (location.hash = '#/login?next=' + encodeURIComponent(location.hash.slice(1))); }
    try { watched ? await api.del(`/api/watchlist/${encodeURIComponent(c)}`) : await api.post('/api/watchlist', { country: c }); watched = !watched; paintWatch(); toast(watched ? `Watching ${c}` : `Stopped watching ${c}`, 'ok'); } catch (e) { toast(e.message, 'err'); }
  };
  const cardOf = (m) => p.cards.find((x) => x.metric === m);
  const cl = p.cluster;
  const body = h('div', {});
  const view = {
    forecast: () => forecastView(c),
    mix: () => mixView(p),
    access: () => lines(p, [['electricity_access', 'Electricity access', 'var(--c1)'], ['clean_cooking_access', 'Clean cooking access', 'var(--c2)']], '%', 0, 100),
    emissions: () => h('div', { class: 'grid g2' }, lines(p, [['co2_per_capita_t', 'CO₂ per person (t)', 'var(--c4)']], ' t'), lines(p, [['grid_intensity', 'Grid intensity (g/kWh, est.)', 'var(--c3)']], ' g')),
  };
  const show = (k) => { clear(body).append(view[k]()); };
  show('forecast');
  return h('div', { class: 'page stack', style: { gap: '22px' } },
    pageHead(c, `Latest indicators, trends and a model-based outlook. Data ${p.info.first_year}–${p.info.last_year}.`,
      watchBtn, h('button', { class: 'btn', onclick: () => download(`/api/export/country/${encodeURIComponent(c)}.pdf`) }, icon('file'), 'PDF report'),
      h('button', { class: 'btn', onclick: () => download(`/api/export/country/${encodeURIComponent(c)}.csv`) }, icon('download'), 'CSV'),
      h('a', { class: 'btn', href: `#/lab?country=${encodeURIComponent(c)}` }, icon('flask'), 'What-if')),
    h('div', { class: 'row wrap' },
      cl && h('span', { class: 'chip green', title: 'K-Means peer group on 7 indicators (latest 5 years). The label describes the group average, individual countries can differ.' }, 'Peer group · ' + cl.label.toLowerCase()),
      cl && h('span', { class: 'chip amber', title: 'Average percentile deficit across five indicators (higher = bigger gap)' }, `Intervention priority ${fmt(cl.priority * 100, 0)}/100`),
      p.peers.length ? h('span', { class: 'small muted' }, 'Similar countries:') : null,
      ...p.peers.slice(0, 5).map((x) => h('button', { class: 'chip', style: { border: 0, cursor: 'pointer' }, onclick: () => goCountry(x) }, x))),
    h('div', { class: 'grid g3 kpi-row' }, CARDS.map((m) => {
      const cd = cardOf(m), mi = metricInfo(m); if (!cd || cd.value == null) return kpi({ label: mi.label, value: '–', hint: 'No data reported' });
      const good = mi.higher_is_better === false ? 'down' : 'up';
      return kpi({ label: mi.label + (mi.derived ? ' ~' : ''), value: fmt(cd.value, cd.value > 1000 ? 0 : 1), unit: mi.unit.replace('% of population', '%'),
        delta: delta(cd.change_5y, { unit: ' ' + (mi.unit.startsWith('%') || mi.unit === '%' ? 'pts' : ''), good, suffix: 'over 5 yrs' }), hint: `#${cd.rank} of ${cd.of} in ${cd.year}`, series: p.series[m]?.map((x) => x.value) });
    })),
    h('div', { class: 'card' }, tabs([['forecast', 'Trend & forecast'], ['mix', 'Electricity mix'], ['access', 'Access'], ['emissions', 'Emissions']], 'forecast', show), body),
    h('div', { class: 'card' }, h('h3', {}, 'Recommendations'), h('p', { class: 'sub' }, 'Rule-based, each one quotes the numbers that triggered it.'),
      h('div', { style: { marginTop: '14px' } }, p.recommendations.map((r) => h('div', { class: 'rec' }, h('div', { class: `pri ${r.priority}` }), h('div', {}, h('b', {}, r.title, ' ', h('span', { class: `chip ${r.priority === 'high' ? 'red' : r.priority === 'medium' ? 'amber' : 'green'}` }, r.priority)), h('p', { class: 'muted', style: { margin: '4px 0 0' } }, r.evidence)))))),
    sourceNote('Metrics marked ~ are derived from the generation mix or density × area and are approximate.'));
}

function lines(p, defs, unit, yMin, yMax) {
  const series = defs.map(([k, name, color]) => ({ name, color, points: (p.series[k] || []).map((x) => ({ x: x.year, y: x.value })) })).filter((s) => s.points.length);
  if (!series.length) return emptyState('No data', 'This country does not report these indicators.');
  return h('div', {}, lineChart({ series, unit, yMin, yMax, height: 300 }), h('div', { class: 'legend' }, series.map((s) => h('span', {}, h('i', { style: { background: s.color } }), s.name))));
}
function mixView(p) {
  if (!p.mix.length) return emptyState('No generation data', 'Electricity generation by source is not reported for this country.');
  const last = p.mix.at(-1);
  return h('div', { class: 'grid g-main' },
    h('div', {}, stackedArea({ rows: p.mix.map((r) => ({ x: r.year, Fossil: r.fossil, Nuclear: r.nuclear, Renewable: r.renewable })), keys: [{ key: 'Fossil', name: 'Fossil', color: 'var(--c4)' }, { key: 'Nuclear', name: 'Nuclear', color: 'var(--c5)' }, { key: 'Renewable', name: 'Renewable', color: 'var(--c1)' }], unit: 'TWh', height: 300 })),
    h('div', {}, h('h3', { style: { marginBottom: '10px' } }, `Mix in ${last.year}`), donut({ parts: [{ label: 'Fossil', value: last.fossil || 0, color: 'var(--c4)' }, { label: 'Nuclear', value: last.nuclear || 0, color: 'var(--c5)' }, { label: 'Renewable', value: last.renewable || 0, color: 'var(--c1)' }], center: fmt(((last.renewable || 0) / ((last.fossil || 0) + (last.nuclear || 0) + (last.renewable || 0) || 1)) * 100, 0) + '%' }),
      h('p', { class: 'hint' }, 'Centre: renewable share of generation. Absolute TWh on the left chart.')));
}
function forecastView(c) {
  const S = { metric: 'renewable_share', to: 2030, target: '' };
  const out = h('div', {});
  const mSel = h('select', { class: 'input', 'aria-label': 'Forecast metric', onchange: (e) => { S.metric = e.target.value; run(); } },
    state.meta.metrics.filter((m) => m.forecastable).map((m) => h('option', { value: m.key }, m.label)));
  const toSel = h('select', { class: 'input', 'aria-label': 'Forecast to year', onchange: (e) => { S.to = +e.target.value; run(); } }, [2025, 2030, 2035, 2040].map((y) => h('option', { value: y, selected: y === 2030 }, 'to ' + y)));
  const target = h('input', { class: 'input', type: 'number', placeholder: 'Target (optional)', 'aria-label': 'Target value', onchange: (e) => { S.target = e.target.value; run(); } });
  async function run() {
    await load(out, async () => {
      let f;
      try { f = await api.get(`/api/forecast/${encodeURIComponent(c)}?` + qs({ metric: S.metric, to: S.to, target: S.target })); }
      catch (e) { if (e.status === 422) return emptyState('Not enough history', e.message); throw e; }
      const m = f.model, un = f.unit, mi = metricInfo(S.metric), eu = un.includes('%') ? 'pts' : un;
      const hist = f.history.map((x) => ({ x: x.year, y: x.value }));
      const fc = [{ x: hist.at(-1).x, y: hist.at(-1).y }, ...f.forecast.map((x) => ({ x: x.year, y: x.value }))];
      const band = [{ x: hist.at(-1).x, lo: hist.at(-1).y, hi: hist.at(-1).y }, ...f.forecast.map((x) => ({ x: x.year, lo: x.lo, hi: x.hi }))];
      const tc = f.target_crossing;
      const skill = m.skill_vs_naive;
      return h('div', { class: 'stack' },
        lineChart({ series: [{ name: 'Observed', points: hist, color: 'var(--c1)' }, { name: 'Forecast', points: fc, color: 'var(--c2)', dash: true, band }], unit: un, height: 320, markX: f.last_observed_year, ariaLabel: `${f.label} history and forecast for ${c}` }),
        h('div', { class: 'legend' }, h('span', {}, h('i', { style: { background: 'var(--c1)' } }), 'Observed'), h('span', { style: { color: 'var(--c2)' } }, h('i', { class: 'dash' }), 'Forecast (median)'), h('span', {}, h('i', { style: { background: 'var(--c2)', opacity: .3 } }), '80% interval')),
        tc && h('div', { class: 'callout green' }, tc.status === 'already_reached' ? `Already at or above ${S.target} ${un} (${tc.year}).` : tc.status === 'forecast' ? `The median forecast reaches ${S.target} ${un} in ${tc.year}.` : `The median forecast does not reach ${S.target} ${un} by ${S.to}.`),
        h('div', { class: 'grid g2' },
          h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Model card'),
            line('Method', ({ naive: 'Persistence', linear: 'Linear trend', damped: 'Damped-trend smoothing', ensemble: 'Linear + damped ensemble' })[m.method]),
            line('Backtested on', `${m.n_countries_backtested} countries, ${m.validated_horizon_years}-yr horizon`),
            line('Typical error (held-out)', `±${fmt(m.validation_mae, 2)} ${m.log_scale ? 'log units (≈' + fmt(m.validation_mae * 100, 0) + '%)' : eu}`),
            line('Beats “no change” by', skill != null ? `${fmt(skill * 100, 0)}%` : '–'),
            line('80% interval actual coverage', m.interval_coverage_validation != null ? `${fmt(m.interval_coverage_validation * 100, 0)}% on held-out origins` : '–'),
            line('Recent trend', f.recent_slope_per_year != null ? `${signed(f.recent_slope_per_year, 2)} ${eu}/yr (last 5 yrs)` : '–')),
          h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Read this carefully'),
            h('p', { class: 'muted', style: { margin: 0 } }, f.caveat),
            skill != null && skill < 0.1 && h('p', { class: 'muted' }, `For ${mi.label.toLowerCase()}, year-to-year changes are hard to predict: the best method only modestly beats assuming no change. Treat the central line as a trend, not a prediction of any given year.`))));
    }, { height: 380 });
  }
  const line = (a, b) => h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, a), h('b', {}, b));
  run();
  return h('div', { class: 'stack' }, h('div', { class: 'grid g3' }, h('label', { class: 'field' }, 'Indicator', mSel), h('label', { class: 'field' }, 'Horizon', toSel), h('label', { class: 'field' }, 'Target', target)), out);
}
