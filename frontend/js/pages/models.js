import { api } from '../api.js';
import { h, fmt, load, clear, errorState, signed } from '../ui.js';
import { lineChart, barH, scatter } from '../charts.js';
import { pageHead, tabs, goCountry, tip } from '../components.js';

const CL = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)', 'var(--ink-3)'];
const TARGET_NOTE = 'Renewable share of final energy (World Bank, includes traditional biomass), observed to 2019–2020';
const CARDS = {};   // cache of model cards for tabs that share it

export default async function models() {
  const body = h('div', {});
  const statusBox = h('span', {});
  const views = {
    forecast: () => forecastTab(), reg: () => regTab(), clf: () => clfTab(), kmeans: () => kmeansTab(), gmm: () => gmmTab(),
  };
  const show = (k) => { load(body, views[k], { height: 360 }); };
  show('forecast');
  // status chip is best-effort: a failure here never blocks the page
  api.get('/api/ml/status').then((s) => {
    statusBox.append(h('span', { class: `chip ${s.ok ? 'green' : 'red'}` }, s.ok ? `Models loaded · scikit-learn ${s.env?.sklearn ?? ''}${s.retrained_at_startup ? ' · rebuilt at startup' : ''}` : 'Models not loaded'));
    if (!s.ok) body.prepend(h('div', { class: 'note-partial' }, s.error));
  }).catch(() => {});
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Model lab', 'Every model behind TerraWatt: what it is for, what it uses, how it was tested, how well it does and where it fails. Scores are measured on data the model never saw.', statusBox),
    h('div', { class: 'card' }, tabs([['forecast', 'Forecasting'], ['reg', 'Regression'], ['clf', 'Classification'], ['kmeans', 'K-Means'], ['gmm', 'Gaussian mixture']], 'forecast', show), body));
}
const cards = async () => (CARDS.c ??= await api.get('/api/ml/models').catch((e) => { delete CARDS.c; throw e; }));

/* ---------- shared pieces */
const about = (rows) => h('div', { class: 'grid g2', style: { gap: '12px' } }, rows.map(([t, txt]) => h('div', { class: 'card', style: { boxShadow: 'none', padding: '12px 14px' } }, h('div', { class: 'small muted', style: { fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.05em' } }, t), h('div', { style: { fontSize: '13.5px', marginTop: '4px' } }, txt))));
const table = (cols, rows) => h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, cols.map(([, l], i) => h('th', { class: i ? 'r' : '' }, l)))),
  h('tbody', {}, rows.map((r) => h('tr', { style: r.selected ? { background: 'var(--brand-soft)' } : {} }, cols.map(([k, , f], i) => h('td', { class: i ? 'r tnum' : '' }, i === 0 ? h('b', {}, r[k], r.selected ? ' ✓' : '') : (f ? f(r[k]) : r[k]))))))));
const imp = (rows) => barH({ rows: rows.slice(0, 8).map((r) => ({ label: r.label, value: Math.max(r.importance, 0) })), format: (v) => fmt(v, 2) });
const featureList = (c) => c.features.join(', ').replace(/_/g, ' ');
const sec = (title, ...kids) => h('div', {}, h('h3', { style: { marginBottom: '8px' } }, title), ...kids);

/* ---------- forecasting */
async function forecastTab() {
  const S = { metric: 'renewable_elec_share' };
  const out = h('div', {});
  const names = { naive: 'Persistence (no change)', linear: 'Linear trend (8 yrs)', damped: 'Damped-trend smoothing', ensemble: 'Linear + damped ensemble' };
  const draw = () => load(out, async () => {
    const fq = await api.get('/api/forecast-quality?metric=' + S.metric);
    const rows = Object.keys(names).map((m) => ({ model: names[m], cal: fq.mae_calibration[m], val: fq.mae_validation[m], selected: m === fq.method }));
    const hs = Object.keys(fq.mae_by_horizon_validation.naive);
    const log = fq.log_scale;
    return h('div', { class: 'stack' },
      h('p', { class: 'muted', style: { margin: 0 } }, `Rolling-origin backtest over ${fq.n_series} country series. The method is chosen on origins ${fq.origins.calibration.join('–')} and scored on later origins ${fq.origins.validation.join('–')}, 1 to 5 years ahead.`),
      table([['model', 'Method'], ['cal', 'Selection error', (v) => fmt(v, 3)], ['val', 'Held-out error', (v) => fmt(v, 3)]], rows),
      h('p', { class: 'hint', style: { margin: 0 } }, log ? 'Errors are in log units (≈ relative error) because this indicator spans orders of magnitude.' : 'Errors are mean absolute errors in the indicator’s own units (percentage points for shares).'),
      h('div', { class: 'grid g2' }, sec('Error grows with horizon', lineChart({ series: [{ name: fq.method, color: 'var(--c1)', points: hs.map((x) => ({ x: +x, y: fq.mae_by_horizon_validation[fq.method][x] })) }, { name: 'persistence', color: 'var(--c3)', points: hs.map((x) => ({ x: +x, y: fq.mae_by_horizon_validation.naive[x] })) }], xFormat: (v) => v + 'y', height: 240, zeroBase: true, decimals: 2 })),
        sec('Honest summary', h('p', { class: 'muted' }, `The chosen method beats “no change” by ${fmt(fq.skill_vs_naive * 100, 0)}% on held-out origins. Its nominal 80% intervals contain the truth ${fmt(fq.interval_coverage_validation * 100, 0)}% of the time across ${fmt(fq.n_validation_forecasts, 0)} held-out forecasts. Year-to-year changes are hard to predict, so a modest edge over “no change” is realistic.`),
          h('p', { class: 'muted' }, 'Years beyond the 5-year validated horizon are flagged and use wider, extrapolated intervals. 2026–2030 is validated for countries whose last observation is 2025.'))));
  }, { height: 300 });
  const sel = h('select', { class: 'input', style: { maxWidth: '300px' }, 'aria-label': 'Forecast indicator', onchange: (e) => { S.metric = e.target.value; draw(); } },
    ...[['renewable_elec_share', 'Renewable share of electricity'], ['solar_twh', 'Solar generation'], ['wind_twh', 'Wind generation'], ['low_carbon_elec_pct', 'Low-carbon electricity'], ['co2_kt', 'CO₂ emissions'], ['renewable_share', 'Renewable share of final energy (to 2020)'], ['electricity_access', 'Electricity access (to 2020)'], ['clean_cooking_access', 'Clean cooking (to 2020)']].map(([k, l]) => h('option', { value: k }, l)));
  draw();
  return h('div', { class: 'stack' },
    about([['Purpose', 'Project a single country’s indicator a few years ahead, with an uncertainty range, to show direction and pace. It is a trend extrapolation, not a policy model.'],
      ['Inputs', 'Only the indicator’s own history for that country (no other variables). Shares are modelled directly; CO₂ in log space.'],
      ['Methods compared', 'Persistence, 8-year linear trend, damped-trend exponential smoothing (grid-tuned) and their ensemble. The one with the lowest calibration error is used.'],
      ['Intervals', '80% intervals from empirical backtest errors, scaled to each series’ volatility and widening with the horizon.'],
      ['Limitations', 'Cannot anticipate policy shocks, new capacity or crises. Short, jumpy series are unreliable. Compare any forecast with an official target only where the definitions match.'],
      ['Example', 'Open any country page → “Trend & forecast” to see 2026–2030 with the interval, and official targets where one is verified and comparable.']]),
    h('label', { class: 'field' }, 'Indicator to evaluate', sel), out);
}

/* ---------- regression */
async function regTab() {
  const c = await cards(), r = c.regression;
  const test = `${r.cutoff_year + 1}–${r.target_years[1]}`;
  return h('div', { class: 'stack' },
    about([['Purpose', `Estimate a country’s ${TARGET_NOTE}, and power the What-if lab by re-estimating it when inputs change.`],
      ['Input features', featureList(c) + '. Country identity is also given to the selected model, which is why it tracks each country’s own level.'],
      ['Training & testing', `Chronological split: train ≤ ${r.cutoff_year} (${r.n_train} rows), test ${test} (${r.n_test} rows, ${r.n_countries} countries). The model type is picked on an inner validation window, then scored once on the test years.`],
      ['Metrics', 'MAE and RMSE are errors in percentage points (lower is better; RMSE punishes large misses). R² is the share of variation explained (1 is perfect, 0 is no better than the average).'],
      ['Limitations', 'It learns associations, not causes. Static country attributes (area, coordinates) act as proxies for country identity. Predictions for countries with missing inputs lean on training medians. The target ends in 2020, so it cannot reflect the 2021–2025 surge in solar and wind.'],
      ['Chosen model', `${r.chosen}. Plain Ridge without country identity does much worse (see table), so most of the skill comes from knowing the country.`]]),
    table([['model', 'Model'], ['MAE', 'MAE (pp)', (v) => fmt(v, 2)], ['RMSE', 'RMSE (pp)', (v) => fmt(v, 2)], ['R2', 'R²', (v) => fmt(v, 3)]], r.table),
    sec('Example predictions on held-out years', h('p', { class: 'hint', style: { margin: '0 0 8px' } }, 'One row per country, from years the model was not trained on. Picked at random with a fixed seed, not selected for accuracy.'),
      table([['country', 'Country'], ['year', 'Year', (v) => v], ['actual', 'Actual (%)', (v) => fmt(v, 1)], ['predicted', 'Predicted (%)', (v) => fmt(v, 1)], ['error', 'Error (pp)', (v) => signed(v, 1)]], r.examples)),
    sec('Permutation importance (test years, increase in RMSE)', imp(r.importance)));
}

/* ---------- classification */
async function clfTab() {
  const c = await cards(), r = c.classification, sel = r.table.find((x) => x.selected), cm = sel.confusion;
  const cmCell = (v, ok) => h('div', { style: { background: ok ? 'var(--brand-soft)' : 'var(--danger-soft)', fontWeight: 700, fontSize: '20px' } }, v);
  return h('div', { class: 'stack' },
    about([['Purpose', 'Label a country as a “high adopter” (renewable share of final energy above the training median) or not, with a probability. Used for the “chance of high adopter” in the What-if lab.'],
      ['Input features', featureList(c) + '. Country identity is NOT used, so it generalises to unseen countries.'],
      ['Training & testing', `Held-out split by country (${r.n_test_countries} unseen countries) because a country’s years are near-duplicates. Model chosen by grouped 5-fold cross-validated F1 on training countries only. Threshold ${fmt(r.threshold_eval, 1)}%.`],
      ['Metrics', 'Accuracy: share correct. Precision: of predicted highs, how many are high. Recall: of true highs, how many were found. F1: balance of both. ROC-AUC: how well it ranks highs above lows (0.5 is chance).'],
      ['Limitations', 'The median cut-off is arbitrary, and countries near it are inherently uncertain. Traditional biomass in the target makes some low-income countries “high”, which is not the same as having clean power.'],
      ['Chosen model', sel.model]]),
    table([['model', 'Model'], ['cv_f1', 'CV F1', (v) => fmt(v, 3)], ['accuracy', 'Accuracy', (v) => fmt(v, 3)], ['precision', 'Precision', (v) => fmt(v, 3)], ['recall', 'Recall', (v) => fmt(v, 3)], ['f1', 'F1', (v) => fmt(v, 3)], ['roc_auc', 'ROC-AUC', (v) => fmt(v, 3)]], r.table),
    h('div', { class: 'grid g2' }, sec(`Confusion matrix · ${sel.model}`, h('div', { class: 'cm' }, h('div', {}), h('div', { class: 'muted' }, 'Pred. Low'), h('div', { class: 'muted' }, 'Pred. High'), h('div', { class: 'muted' }, 'Actual Low'), cmCell(cm[0][0], true), cmCell(cm[0][1]), h('div', { class: 'muted' }, 'Actual High'), cmCell(cm[1][0]), cmCell(cm[1][1], true))),
      sec('Permutation importance (F1)', imp(r.importance))),
    sec('Example predictions on unseen countries', table([['country', 'Country'], ['year', 'Year', (v) => v], ['actual_share', 'Actual share (%)', (v) => fmt(v, 1)], ['actual_label', 'Actual', (v) => (v ? 'High' : 'Low')], ['p_high', 'P(high)', (v) => fmt(v * 100, 0) + '%'], ['predicted_label', 'Predicted', (v) => (v ? 'High' : 'Low')]], r.examples)));
}

/* ---------- clustering */
async function kmeansTab() {
  const [c, cl] = await Promise.all([cards(), api.get('/api/ml/clusters')]);
  const k = c.clustering;
  const pts = Object.entries(cl.countries).map(([n, v]) => ({ x: v.pc1, y: v.pc2, color: CL[v.cluster % 6], label: `<b>${n}</b>${v.label}`, onClick: () => goCountry(n) }));
  return h('div', { class: 'stack' },
    about([['Purpose', 'Group countries with similar energy, access and income profiles into peer groups for comparison and for the “intervention priority” score on country pages.'],
      ['Input features', k.features.join(', ').replace(/_/g, ' ') + `, averaged over ${k.window_years.join('–')}.`],
      ['Method', `Log-scaled and standardised features, K-Means with K chosen by silhouette among 3–6 (K=${k.k}, silhouette ${fmt(k.silhouette_chosen, 2)}). PCA to two components for the plot.`],
      ['Metrics', 'Silhouette ranges from −1 to 1: how much closer a country is to its own group than to the next. Above 0.5 is strong, 0.25–0.5 is moderate.'],
      ['Limitations', 'Moderate silhouette means group edges are soft, and the choice of features shapes the groups. Labels describe group averages; individual countries differ. Unsupervised, so there is no “accuracy”.'],
      ['Window', 'Uses the last five years in which the World Bank indicators are broadly reported, since the clustering needs access and income data that stop in 2020.']]),
    scatter({ points: pts, height: 360, xLabel: 'PC1', yLabel: 'PC2' }),
    h('div', { class: 'legend' }, cl.profiles.map((p) => h('span', {}, h('i', { style: { background: CL[p.cluster % 6] } }), `${p.label} (${p.n})`))),
    h('div', { class: 'grid g3' }, cl.profiles.map((p) => profile(p.label, p.n, p.examples, p.means))),
    h('p', { class: 'hint' }, 'Silhouette by K: ' + Object.entries(k.silhouette).filter(([kk]) => +kk >= 3 && +kk <= 6).map(([kk, v]) => `K=${kk}: ${fmt(v, 2)}`).join(' · ')));
}
const profile = (label, n, ex, means) => h('div', { class: 'card', style: { boxShadow: 'none' } }, h('b', {}, label), h('div', { class: 'muted small' }, `${n} countries · e.g. ${ex.slice(0, 3).join(', ')}`),
  h('div', { style: { marginTop: '8px' } }, ['renewable_share', 'renewable_elec_share', 'electricity_access', 'clean_cooking_access', 'gdp_per_capita'].map((f) => h('div', { class: 'stat-line' }, h('span', { class: 'muted small' }, f.replaceAll('_', ' ')), h('b', { class: 'tnum' }, fmt(means[f], f === 'gdp_per_capita' ? 0 : 1))))));

async function gmmTab() {
  const [c, cl] = await Promise.all([cards(), api.get('/api/ml/clusters')]);
  const g = c.gmm, G = cl.gmm;
  const ks = Object.keys(g.bic).map(Number);
  const pts = Object.entries(G.countries).map(([n, v]) => ({ x: v.pc1, y: v.pc2, color: CL[v.component % 6], label: `<b>${n}</b>${v.label} · ${fmt(v.confidence * 100, 0)}% sure`, onClick: () => goCountry(n) }));
  const unsure = Object.entries(G.countries).filter(([, v]) => v.confidence < 0.7).sort((a, b) => a[1].confidence - b[1].confidence).slice(0, 8);
  return h('div', { class: 'stack' },
    about([['Purpose', 'Soft clustering: each country gets a probability of belonging to each group, so countries between groups are visible instead of being forced into one.'],
      ['Input features', 'The same indicators and window as K-Means, standardised.'],
      ['Method', `Gaussian mixture with diagonal covariance, 5 random starts per size. The number of components (${g.k}) minimises the BIC among 3–6.${g.bic_at_upper_bound ? ' BIC was still improving at the upper limit, so the cap of 6 is a readability choice.' : ''}`],
      ['Metrics', 'BIC/AIC balance fit against complexity (lower is better). Agreement with K-Means is the adjusted Rand index (1 = identical groups, 0 = chance).'],
      ['Limitations', 'Assumes groups are roughly bell-shaped, and with ~170 countries and 9 features the fit is sensitive to the starting points. Component numbers carry no meaning beyond the ordering by renewable share.'],
      ['This fit', `${g.n} countries · ${g.n_uncertain_lt_70pct} have under 70% confidence in any single component · agreement with K-Means ARI ${fmt(g.agreement_with_kmeans_ari, 2)}.`]]),
    h('div', { class: 'grid g2' }, sec('Model selection (BIC, lower is better)', lineChart({ series: [{ name: 'BIC', color: 'var(--c3)', points: ks.map((k) => ({ x: k, y: g.bic[k] })) }], xFormat: (v) => 'k=' + v, height: 220, decimals: 0 })),
      sec('Least certain countries', table([['c', 'Country'], ['p', 'Top probability', (v) => fmt(v * 100, 0) + '%']], unsure.map(([n, v]) => ({ c: n, p: v.confidence }))))),
    scatter({ points: pts, height: 360, xLabel: 'PC1', yLabel: 'PC2' }),
    h('div', { class: 'legend' }, g.profiles.map((p) => h('span', {}, h('i', { style: { background: CL[p.component % 6] } }), `${p.label} (${p.n})`))),
    h('div', { class: 'grid g3' }, g.profiles.map((p) => profile(p.label, p.n, p.examples, p.means))));
}
