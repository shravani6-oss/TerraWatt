import { api } from '../api.js';
import { h, fmt, load, emptyState } from '../ui.js';
import { lineChart, barH, scatter } from '../charts.js';
import { pageHead, tabs, goCountry } from '../components.js';

const CL = ['var(--c1)', 'var(--c2)', 'var(--c3)', 'var(--c4)', 'var(--c5)'];
export default async function models() {
  let card, clusters, fq;
  try { [card, clusters, fq] = await Promise.all([api.get('/api/ml/models'), api.get('/api/ml/clusters'), api.get('/api/forecast-quality?metric=renewable_share')]); }
  catch (e) { return h('div', { class: 'page' }, emptyState('Models unavailable', e.message)); }
  const body = h('div', {});
  const tabsFn = { forecast: () => forecastTab(fq), reg: () => regTab(card), clf: () => clfTab(card), clu: () => cluTab(card, clusters) };
  const show = (k) => { body.replaceChildren(tabsFn[k]()); };
  show('forecast');
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Model lab', 'Every model behind TerraWatt, with its evaluation protocol and measured error. Nothing here is hand-tuned to look good.',
      h('span', { class: 'chip' }, `Trained ${card.trained_at.slice(0, 10)} · scikit-learn ${card.sklearn}`)),
    h('div', { class: 'card' }, tabs([['forecast', 'Forecasting'], ['reg', 'Regression'], ['clf', 'Classification'], ['clu', 'Clustering']], 'forecast', show), body));
}
const table = (cols, rows) => h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, cols.map(([, l], i) => h('th', { class: i ? 'r' : '' }, l)))),
  h('tbody', {}, rows.map((r) => h('tr', { style: r.selected ? { background: 'var(--brand-soft)' } : {} }, cols.map(([k, , f], i) => h('td', { class: i ? 'r tnum' : '' }, i === 0 ? h('b', {}, r[k], r.selected ? ' ✓' : '') : (f ? f(r[k]) : r[k]))))))));
const imp = (rows) => barH({ rows: rows.slice(0, 8).map((r) => ({ label: r.label, value: Math.max(r.importance, 0) })), format: (v) => fmt(v, 3) });

function forecastTab(fq) {
  const names = { naive: 'Persistence (no change)', linear: 'Linear trend (8 yrs)', damped: 'Damped-trend smoothing', ensemble: 'Linear + damped ensemble' };
  const rows = Object.keys(names).map((m) => ({ model: names[m], cal: fq.mae_calibration[m], val: fq.mae_validation[m], selected: m === fq.method }));
  const hs = Object.keys(fq.mae_by_horizon_validation.naive);
  return h('div', { class: 'stack' },
    h('p', { class: 'muted', style: { margin: 0 } }, `Rolling-origin backtest of renewable share over ${fq.n_series} countries. The method is chosen using origins ${fq.origins.calibration.join('–')} and scored on later origins ${fq.origins.validation.join('–')}, 1 to 5 years ahead.`),
    table([['model', 'Method'], ['cal', 'MAE selection (pts)', (v) => fmt(v, 3)], ['val', 'MAE held-out (pts)', (v) => fmt(v, 3)]], rows),
    h('div', { class: 'grid g2' }, h('div', {}, h('h3', {}, 'Error grows with horizon'), lineChart({ series: [{ name: fq.method, color: 'var(--c1)', points: hs.map((x) => ({ x: +x, y: fq.mae_by_horizon_validation[fq.method][x] })) }, { name: 'persistence', color: 'var(--c3)', points: hs.map((x) => ({ x: +x, y: fq.mae_by_horizon_validation.naive[x] })) }], unit: 'pts', xFormat: (v) => v + 'y', height: 240, zeroBase: true, decimals: 2 })),
      h('div', {}, h('h3', {}, 'Honest summary'), h('p', { class: 'muted' }, `The winner beats persistence by ${fmt(fq.skill_vs_naive * 100, 0)}%. Its nominal 80% intervals cover ${fmt(fq.interval_coverage_validation * 100, 0)}% of ${fmt(fq.n_validation_forecasts, 0)} held-out forecasts. Renewable share moves slowly and unevenly, so beating “no change” by a wide margin is not realistic.`),
        h('p', { class: 'muted' }, 'Forecast years beyond the 5-year validated horizon are flagged and use wider, extrapolated intervals.'))));
}
function regTab(c) {
  const r = c.regression;
  return h('div', { class: 'stack' }, h('p', { class: 'muted', style: { margin: 0 } }, `Chronological split: train ≤ ${r.cutoff_year} (${r.n_train} rows), test ${r.cutoff_year + 1}–2019 (${r.n_test} rows). The model is picked on an inner validation window, then scored once on the test years.`),
    table([['model', 'Model'], ['MAE', 'MAE (pts)', (v) => fmt(v, 2)], ['RMSE', 'RMSE (pts)', (v) => fmt(v, 2)], ['R2', 'R²', (v) => fmt(v, 3)]], r.table),
    h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Permutation importance (test years, RMSE increase)'), imp(r.importance)),
    h('p', { class: 'hint' }, 'Country identity carries most of the signal: a country\'s own history is the best predictor of its renewable share. Without it, R² falls to the plain “Ridge” row.'));
}
function clfTab(c) {
  const r = c.classification, sel = r.table.find((x) => x.selected), cm = sel.confusion;
  return h('div', { class: 'stack' }, h('p', { class: 'muted', style: { margin: 0 } }, `Target: renewable share above the training median (${fmt(r.threshold_eval, 1)}%). Held-out split by country (${r.n_test_countries} unseen countries) because a country's years are near-duplicates. Selected by grouped 5-fold CV F1 on training data only.`),
    table([['model', 'Model'], ['cv_f1', 'CV F1', (v) => fmt(v, 3)], ['accuracy', 'Accuracy', (v) => fmt(v, 3)], ['precision', 'Precision', (v) => fmt(v, 3)], ['recall', 'Recall', (v) => fmt(v, 3)], ['f1', 'F1', (v) => fmt(v, 3)], ['roc_auc', 'ROC-AUC', (v) => fmt(v, 3)]], r.table),
    h('div', { class: 'grid g2' }, h('div', {}, h('h3', { style: { marginBottom: '8px' } }, `Confusion matrix · ${sel.model}`),
      h('div', { class: 'cm' }, h('div', {}), h('div', { class: 'muted' }, 'Pred. Low'), h('div', { class: 'muted' }, 'Pred. High'),
        h('div', { class: 'muted' }, 'Actual Low'), cmCell(cm[0][0], true), cmCell(cm[0][1]), h('div', { class: 'muted' }, 'Actual High'), cmCell(cm[1][0]), cmCell(cm[1][1], true))),
      h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Permutation importance (F1)'), imp(r.importance))));
}
const cmCell = (v, ok) => h('div', { style: { background: ok ? 'var(--brand-soft)' : 'var(--danger-soft)', fontWeight: 700, fontSize: '20px' } }, v);
function cluTab(card, cl) {
  const pts = Object.entries(cl.countries).map(([c, v]) => ({ x: v.pc1, y: v.pc2, color: CL[v.cluster % 5], label: `<b>${c}</b>${v.label}`, onClick: () => goCountry(c) }));
  return h('div', { class: 'stack' }, h('p', { class: 'muted', style: { margin: 0 } }, `K-Means on ${cl.features.length} indicators (mean of ${cl.window_years.join('–')}), log-scaled and standardised. K=${cl.k} chosen by silhouette among 3–6 (silhouette ${fmt(cl.silhouette_chosen, 2)}: moderate, so cluster edges are soft).`),
    scatter({ points: pts, height: 360, xLabel: 'PC1', yLabel: 'PC2' }),
    h('div', { class: 'legend' }, cl.profiles.map((p) => h('span', {}, h('i', { style: { background: CL[p.cluster % 5] } }), `${p.label} (${p.n})`))),
    h('div', { class: 'grid g3' }, cl.profiles.map((p) => h('div', { class: 'card', style: { boxShadow: 'none' } }, h('b', {}, p.label), h('div', { class: 'muted small' }, `${p.n} countries · e.g. ${p.examples.slice(0, 3).join(', ')}`),
      h('div', { style: { marginTop: '8px' } }, ['renewable_share', 'electricity_access', 'clean_cooking_access', 'gdp_per_capita'].map((f) => h('div', { class: 'stat-line' }, h('span', { class: 'muted small' }, f.replaceAll('_', ' ')), h('b', { class: 'tnum' }, fmt(p.means[f], f === 'gdp_per_capita' ? 0 : 1)))))))));
}
