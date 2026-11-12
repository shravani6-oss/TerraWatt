import { api } from '../api.js';
import { h, fmt, load, clear, signed, toast, debounce, emptyState } from '../ui.js';
import { barH } from '../charts.js';
import { pageHead, countryPicker, sourceNote } from '../components.js';

export default async function scenario({ query }) {
  let cfg;
  try { cfg = await api.get('/api/ml/scenario-config', { cache: true }); } catch (e) { return h('div', { class: 'page' }, emptyState('Models not available', e.message)); }
  const S = { country: query.country || 'India', overrides: {} };
  const out = h('div', {}), sliders = h('div', { class: 'stack', style: { gap: '14px' } }), pickerHost = h('div', {});
  const run = debounce(async () => {
    try {
      const r = await api.post('/api/ml/predict', { country: S.country, overrides: S.overrides });
      clear(out).append(result(r));
    } catch (e) { clear(out).append(emptyState('Prediction unavailable', e.message)); }
  }, 180);
  async function setCountry(c) {
    S.country = c; S.overrides = {};
    clear(pickerHost).append(countryPicker({ placeholder: c, clearOnPick: false, value: c, onPick: setCountry }));
    const r = await api.post('/api/ml/predict', { country: c, overrides: {} });
    clear(sliders);
    cfg.features.forEach((f) => {
      const base = r.baseline.inputs[f.key] ?? f.median, lo = Math.min(f.p1, base), hi = Math.max(f.p99, base);
      const val = h('span', { class: 'num' }, fmt(base, 2)); const step = (hi - lo) / 200 || 0.01;
      const row = h('div', { class: 'slider-row' }); const input = h('input', { type: 'range', min: lo, max: hi, step, value: base, 'aria-label': f.label, oninput: (e) => { const v = +e.target.value; val.textContent = fmt(v, 2); S.overrides[f.key] = v; row.classList.add('changed'); run(); } });
      row.append(h('label', {}, f.label), val, input,
        h('button', { class: 'btn sm ghost', style: { justifySelf: 'start' }, onclick: () => { input.value = base; val.textContent = fmt(base, 2); delete S.overrides[f.key]; row.classList.remove('changed'); run(); } }, 'Reset')); sliders.append(row);
    });
    clear(out).append(result(r));
  }
  await setCountry(S.country);
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('What-if lab', 'Pick a country, move the sliders, and see how a trained model re-estimates its renewable share of final energy.'),
    h('div', { class: 'grid g-main', style: { alignItems: 'start' } },
      h('div', { class: 'card stack' }, h('label', { class: 'field' }, 'Country (starting values = its latest data)', pickerHost), sliders),
      out),
    h('div', { class: 'callout' }, 'These are statistical associations learned from 2000–2019 country data, not causal effects or policy forecasts. The Model lab shows the held-out error of the regression behind this page.'),
    sourceNote());
}

function result(r) {
  const up = r.delta > 0.005, down = r.delta < -0.005;
  return h('div', { class: 'card stack' },
    h('div', { class: 'grid g2' },
      h('div', {}, h('div', { class: 'muted small' }, 'Baseline estimate'), h('div', { class: 'big-num tnum' }, fmt(r.baseline.share, 1), h('small', { class: 'muted', style: { fontSize: '18px' } }, '%'))),
      h('div', {}, h('div', { class: 'muted small' }, 'Scenario estimate'), h('div', { class: 'big-num tnum', style: { color: up ? 'var(--ok)' : down ? 'var(--danger)' : 'inherit' } }, fmt(r.scenario.share, 1), h('small', { class: 'muted', style: { fontSize: '18px' } }, '%')),
        h('div', { class: `delta ${up ? 'up' : down ? 'down' : 'flat'}` }, signed(r.delta, 2), ' pts'))),
    h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, `Chance of being a “high adopter” (above ${fmt(r.high_threshold, 1)}% median)`), h('b', {}, `${fmt(r.baseline.p_high * 100, 0)}% → ${fmt(r.scenario.p_high * 100, 0)}%`)),
    r.effects.length ? h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Effect of each change on its own'), barH({ rows: r.effects.map((e) => ({ label: e.label, value: e.effect, color: e.effect >= 0 ? 'var(--c1)' : 'var(--c4)' })), format: (v) => signed(v, 2) }))
      : h('p', { class: 'muted', style: { margin: 0 } }, 'Move a slider to see its isolated effect.'),
    h('p', { class: 'hint' }, `Model: ${r.model.regressor} regressor (hold-out RMSE ${fmt(r.model.rmse_holdout, 1)} pts) + ${r.model.classifier} classifier. ${r.disclaimer}`));
}
