import { api } from '../api.js';
import { h, fmt, load, clear, signed, toast, debounce, emptyState, errorState, icon } from '../ui.js';
import { barH } from '../charts.js';
import { pageHead, countryPicker, sourceNote, tip } from '../components.js';

const MIX = [['solar_mult', 'Solar', 'solar_twh'], ['wind_mult', 'Wind', 'wind_twh'], ['hydro_mult', 'Hydropower', 'hydro_twh'], ['bio_mult', 'Bioenergy', 'bioenergy_twh'], ['other_mult', 'Geothermal & other', 'other_renew_twh'], ['nuclear_mult', 'Nuclear', 'elec_nuclear_twh']];
const SRC_COLOR = { solar_twh: 'var(--c2)', wind_twh: 'var(--c3)', hydro_twh: 'var(--c1)', bioenergy_twh: 'var(--c5)', other_renew_twh: 'var(--c4)', elec_nuclear_twh: 'var(--ink-3)', elec_fossil_twh: '#8a7f78' };

export default async function scenario({ query }) {
  const S = { country: query.country || 'India', cfg: null, overrides: {}, mix: {}, preset: null, saved: [], last: null };
  let seq = 0;
  const inputs = h('div', { class: 'stack', style: { gap: '16px' } }), out = h('div', {}), pickerHost = h('div', {}), presetRow = h('div', { class: 'opt-row' });
  const refs = {};   // key -> {input, val, row, base}

  const body = () => ({ country: S.country, overrides: S.overrides, mix: S.mix });
  const run = debounce(async () => {
    const my = ++seq;
    try {
      const r = await api.post('/api/ml/predict', body());
      if (my !== seq) return;
      S.last = r; clear(out).append(result(r));
    } catch (e) { if (my === seq) clear(out).append(errorState(e, run, 'Prediction unavailable')); }
  }, 200);

  function paintPresets() {
    clear(presetRow).append(...Object.entries(S.cfg.presets).map(([k, p]) => h('button', { type: 'button', class: 'opt', 'aria-pressed': String(S.preset === k), title: p.text, onclick: () => applyPreset(k) }, p.label)),
      h('button', { type: 'button', class: 'btn sm', onclick: reset }, icon('x'), 'Reset all'));
  }
  function setSlider(key, v) { const r = refs[key]; if (!r) return; r.input.value = v; r.val.textContent = r.fmtv(v); }
  function reset() {
    S.overrides = {}; S.mix = {}; S.preset = null;
    Object.entries(refs).forEach(([k, r]) => { setSlider(k, r.base); r.row.classList.remove('changed'); });
    paintPresets(); run();
  }
  function applyPreset(k) {
    reset(); S.preset = k;
    const p = S.cfg.presets[k];
    Object.entries(p.mix || {}).forEach(([key, v]) => { S.mix[key] = v; setSlider(key, v); refs[key].row.classList.add('changed'); });
    if (p.access_close_gap_pct != null) {
      const f = S.cfg.features.find((x) => x.key === 'electricity_access');
      if (f.baseline != null) { const v = f.baseline + (100 - f.baseline) * p.access_close_gap_pct / 100; S.overrides.electricity_access = v; setSlider('electricity_access', v); refs.electricity_access.row.classList.add('changed'); }
      else toast('This country has no electricity-access value to improve.', 'err');
    }
    paintPresets(); run();
  }
  function slider({ key, label, min, max, step, base, fmtv, onSet, helpText, extra }) {
    const val = h('span', { class: 'num' }, fmtv(base));
    const row = h('div', { class: 'slider-row' });
    const input = h('input', { type: 'range', min, max, step, value: base, 'aria-label': label, oninput: (e) => { const v = +e.target.value; val.textContent = fmtv(v); onSet(v); row.classList.add('changed'); S.preset = null; paintPresets(); run(); } });
    row.append(h('label', {}, label, helpText ? tip(helpText) : null, extra || null), val, input,
      h('button', { class: 'btn sm ghost', style: { justifySelf: 'start' }, onclick: () => { setSlider(key, base); onSet(null); row.classList.remove('changed'); run(); } }, 'Reset'));
    refs[key] = { input, val, row, base, fmtv };
    return row;
  }
  function buildInputs() {
    clear(inputs); Object.keys(refs).forEach((k) => delete refs[k]);
    const cfg = S.cfg, mixBase = cfg.electricity_mix;
    const hasMix = !!mixBase;
    inputs.append(
      h('div', {}, h('div', { class: 'opt-row' }, presetRow)),
      hasMix ? h('div', { class: 'stack', style: { gap: '14px' } }, h('div', {}, h('h3', { style: { fontSize: '16px' } }, 'Electricity mix', tip(`Exact accounting on ${mixBase.year} generation by source (Ember). Multiply a source's generation; demand stays constant so extra clean power displaces fossil power.`)), h('p', { class: 'hint', style: { margin: '2px 0 0' } }, `Starting point: ${mixBase.year} generation, ${fmt(mixBase.total_twh, 0)} TWh, ${fmt(mixBase.renewable_share, 1)}% renewable.`)),
        ...MIX.map(([key, label, src]) => { const b = mixBase.by_source.find((x) => x.key === src)?.twh ?? 0; return slider({ key, label, min: 0, max: 10, step: 0.1, base: 1, fmtv: (v) => `×${fmt(v, 1)}`, onSet: (v) => { v == null || Math.abs(v - 1) < 1e-9 ? delete S.mix[key] : (S.mix[key] = v); }, extra: h('span', { class: 'small muted', style: { fontWeight: 400, marginLeft: '8px' } }, `${fmt(b, 1)} TWh today`) }); }),
        slider({ key: 'fossil_reduction_pct', label: 'Fossil generation replaced by renewables', min: 0, max: 100, step: 1, base: 0, fmtv: (v) => fmt(v, 0) + '%', helpText: 'Retires this share of the remaining fossil generation and replaces it with renewables in proportion to the current renewable mix.', onSet: (v) => { v ? (S.mix.fossil_reduction_pct = v) : delete S.mix.fossil_reduction_pct; } }))
        : h('div', { class: 'note-partial' }, 'This country reports no electricity generation, so the mix scenario is unavailable. Model inputs below still work.'),
      h('div', { class: 'stack', style: { gap: '14px' } }, h('div', {}, h('h3', { style: { fontSize: '16px' } }, 'Model inputs', tip('Inputs of the machine-learning model that estimates the renewable share of final energy. Starting values are the country’s own figures in its reference year.')),
        h('p', { class: 'hint', style: { margin: '2px 0 0' } }, `Values as of ${cfg.reference_year}, the last year the model's target is observed for this country.`)),
        ...cfg.features.map((f) => { const base = f.baseline ?? f.median ?? (f.min + f.max) / 2; return slider({ key: f.key, label: f.label, min: f.min, max: f.max, step: f.step, base, fmtv: (v) => fmt(v, 2) + (f.unit === '%' ? '%' : ''), onSet: (v) => { v == null ? delete S.overrides[f.key] : (S.overrides[f.key] = v); }, extra: f.imputed ? h('span', { class: 'chip amber', style: { marginLeft: '8px' }, title: 'Not reported for this country; the starting value is the training median.' }, 'not reported') : null }); })));
    paintPresets();
  }
  async function setCountry(c) {
    S.country = c; S.overrides = {}; S.mix = {}; S.preset = null;
    clear(pickerHost).append(countryPicker({ placeholder: c, clearOnPick: false, value: c, onPick: setCountry }));
    clear(inputs).append(h('div', { class: 'skeleton', style: { height: '320px' } }));
    try { S.cfg = await api.get('/api/ml/scenario-config?country=' + encodeURIComponent(c)); }
    catch (e) { clear(inputs).append(errorState(e, () => setCountry(c), 'What-if inputs unavailable')); clear(out); return; }
    buildInputs(); run();
  }

  /* ---------- results */
  function result(r) {
    const up = r.delta > 0.005, down = r.delta < -0.005, mx = r.electricity_mix;
    return h('div', { class: 'stack', style: { gap: '16px' } },
      h('div', { class: 'card stack' }, h('div', { class: 'row spread wrap' }, h('h3', {}, 'Model estimate', tip('Renewable share of FINAL energy (World Bank definition, includes traditional biomass), estimated by the trained model. Not the share of electricity.')), h('span', { class: 'chip' }, `reference year ${r.reference_year}`)),
        r.reliability_note && h('div', { class: 'note-partial' }, r.reliability_note),
        h('div', { class: 'grid g2' },
          h('div', {}, h('div', { class: 'muted small' }, 'Baseline'), h('div', { class: 'big-num tnum' }, fmt(r.baseline.share, 1), h('small', { class: 'muted', style: { fontSize: '18px' } }, '%'))),
          h('div', {}, h('div', { class: 'muted small' }, 'Scenario'), h('div', { class: 'big-num tnum', style: { color: up ? 'var(--ok)' : down ? 'var(--danger)' : 'inherit' } }, fmt(r.scenario.share, 1), h('small', { class: 'muted', style: { fontSize: '18px' } }, '%')),
            h('div', { class: `delta ${up ? 'up' : down ? 'down' : 'flat'}` }, signed(r.delta, 2), ' percentage points'))),
        h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, `Chance of being a “high adopter” (above ${fmt(r.high_threshold, 1)}%)`), h('b', {}, `${fmt(r.baseline.p_high * 100, 0)}% → ${fmt(r.scenario.p_high * 100, 0)}%`)),
        r.effects.length ? h('div', {}, h('h4', { style: { marginBottom: '8px' } }, 'Effect of each change on its own'), barH({ rows: r.effects.map((e) => ({ label: e.label, value: e.effect, color: e.effect >= 0 ? 'var(--c1)' : 'var(--c4)' })), format: (v) => signed(v, 2) + ' pp' })) : h('p', { class: 'muted', style: { margin: 0 } }, 'Move a slider or choose a preset to see the model respond.')),
      mx && mixCard(mx),
      changesCard(r),
      h('div', { class: 'card row wrap' }, h('button', { class: 'btn', onclick: save }, icon('plus'), 'Save for comparison'), h('button', { class: 'btn primary', onclick: report }, icon('download'), 'Download PDF report'), S.saved.length ? h('span', { class: 'small muted' }, `${S.saved.length} saved`) : null),
      S.saved.length ? comparison() : null,
      h('p', { class: 'hint' }, `Model: ${r.model.regressor} regressor (hold-out RMSE ${fmt(r.model.rmse_holdout, 1)} pp, R² ${fmt(r.model.r2_holdout, 2)}) + ${r.model.classifier} classifier, trained on ${r.model.trained_on?.join('–')} data. ${r.disclaimer}`));
  }
  function mixCard(mx) {
    const b = mx.baseline, s = mx.scenario, d = mx.delta;
    const bar = (m) => h('div', { class: 'stackbar', role: 'img', 'aria-label': 'Generation mix' }, m.by_source.filter((x) => x.twh > 0).map((x) => h('i', { style: { width: (x.twh / m.total_twh) * 100 + '%', background: SRC_COLOR[x.key] }, title: `${x.label} ${fmt(x.twh, 1)} TWh` })));
    return h('div', { class: 'card stack' }, h('div', { class: 'row spread wrap' }, h('h3', {}, 'Electricity mix result', tip('Exact arithmetic on reported generation, no machine learning. Grid intensity is calibrated so the baseline reproduces Ember’s reported figure.')), h('span', { class: 'chip' }, `${mx.year} generation`)),
      h('div', { class: 'stack', style: { gap: '6px' } }, h('div', { class: 'small muted' }, 'Baseline'), bar(b), h('div', { class: 'small muted' }, 'Scenario'), bar(s),
        h('div', { class: 'legend' }, b.by_source.map((x) => h('span', {}, h('i', { style: { background: SRC_COLOR[x.key] } }), x.label)))),
      h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['', 'Baseline', 'Scenario', 'Change'].map((c, i) => h('th', { class: i ? 'r' : '' }, c)))),
        h('tbody', {}, row('Renewable share of electricity', b.renewable_share, s.renewable_share, ' %', `${signed(d.renewable_share_pp, 1)} pp`), row('Fossil share', b.fossil_share, s.fossil_share, ' %', `${signed(s.fossil_share - b.fossil_share, 1)} pp`),
          row('Grid intensity (g CO₂e/kWh)', b.grid_intensity, s.grid_intensity, '', signed(d.grid_intensity, 0)), row('Power-sector emissions (Mt CO₂e)', b.emissions_mt, s.emissions_mt, '', `${signed(d.emissions_mt, 1)} (${signed(d.emissions_pct, 1)}%)`)))),
      mx.surplus_twh > 0 && h('div', { class: 'note-partial' }, `Generation exceeds demand by ${fmt(mx.surplus_twh, 1)} TWh in this scenario. It would need exports, storage or curtailment, so the benefit is overstated.`),
      h('details', { class: 'more' }, h('summary', {}, 'Assumptions'), h('ul', { class: 'small', style: { margin: 0, paddingLeft: '18px' } }, mx.assumptions.map((a) => h('li', {}, a)))));
  }
  const row = (a, x, y, u, dlt) => h('tr', {}, h('td', {}, a), h('td', { class: 'r tnum' }, fmt(x, 1) + u), h('td', { class: 'r tnum' }, fmt(y, 1) + u), h('td', { class: 'r tnum' }, dlt));
  function changesCard(r) {
    const items = [...r.changed_inputs.map((c) => `${c.label}: ${c.from == null ? 'n/a' : fmt(c.from, 2)} → ${fmt(c.to, 2)} ${c.unit}`), ...(r.electricity_mix?.changed || []).map((c) => `${c.label}: ${fmt(c.from_twh, 1)} → ${fmt(c.to_twh, 1)} TWh`), ...r.notes];
    return h('div', { class: 'card' }, h('h3', { style: { fontSize: '16px', marginBottom: '8px' } }, 'What changed'), items.length ? h('ul', { class: 'small', style: { margin: 0, paddingLeft: '18px' } }, items.map((i) => h('li', {}, i))) : h('p', { class: 'muted small', style: { margin: 0 } }, 'Nothing yet. The baseline is each country’s own reported values.'));
  }
  function save() {
    if (!S.last) return;
    if (S.saved.length >= 4) return toast('Keep up to four scenarios; clear some first.', 'err');
    const label = S.preset ? S.cfg.presets[S.preset].label : `Scenario ${S.saved.length + 1}`;
    S.saved.push({ label, country: S.country, r: S.last }); clear(out).append(result(S.last)); toast('Saved for comparison', 'ok');
  }
  function comparison() {
    return h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('h3', { style: { fontSize: '16px' } }, 'Scenario comparison'), h('button', { class: 'btn sm ghost', onclick: () => { S.saved = []; clear(out).append(result(S.last)); } }, 'Clear')),
      h('div', { class: 'table-wrap', style: { marginTop: '8px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Scenario', 'Country', 'Model share', 'Change', 'Renewable electricity', 'Grid g/kWh', 'Power emissions'].map((c, i) => h('th', { class: i > 1 ? 'r' : '' }, c)))),
        h('tbody', {}, S.saved.map((x) => { const m = x.r.electricity_mix; return h('tr', {}, h('td', {}, x.label), h('td', {}, x.country), h('td', { class: 'r tnum' }, fmt(x.r.scenario.share, 1) + '%'), h('td', { class: 'r tnum' }, signed(x.r.delta, 2) + ' pp'), h('td', { class: 'r tnum' }, m ? fmt(m.scenario.renewable_share, 1) + '%' : '–'), h('td', { class: 'r tnum' }, m ? fmt(m.scenario.grid_intensity, 0) : '–'), h('td', { class: 'r tnum' }, m ? signed(m.delta.emissions_pct, 1) + '%' : '–')); })))));
  }
  async function report() {
    try {
      const res = await fetch('/api/ml/scenario-report', { method: 'POST', credentials: 'same-origin', headers: { 'X-Requested-With': 'TerraWatt', 'Content-Type': 'application/json' }, body: JSON.stringify(body()) });
      if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(j.error?.message || `Report failed (${res.status})`); }
      const url = URL.createObjectURL(await res.blob()), a = h('a', { href: url, download: `terrawatt-scenario-${S.country.replace(/\s+/g, '_')}.pdf` });
      document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) { toast(e.message, 'err'); }
  }

  await setCountry(S.country);
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('What-if lab', 'Explore scenarios for a country: an exact electricity-mix calculation plus a trained model’s estimate of its renewable share of final energy.'),
    h('div', { class: 'grid g-main', style: { alignItems: 'start' } },
      h('div', { class: 'card stack' }, h('label', { class: 'field' }, 'Country', pickerHost), inputs), out),
    h('div', { class: 'callout' }, h('b', {}, 'Associations, not causes. '), 'The model learned statistical patterns across countries up to its last labelled year. It does not know policy, cost or build-time, and its estimate should be read with its hold-out error. The electricity-mix block is accounting, not a forecast.'),
    sourceNote());
}
