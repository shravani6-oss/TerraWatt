import { api } from '../api.js';
import { h, fmt, load, clear, toast, emptyState, confirmBox, delta, download, icon } from '../ui.js';
import { lineChart, donut, barH } from '../charts.js';
import { pageHead, kpi, countryPicker, sourceNote } from '../components.js';
import { state } from '../state.js';

const monthNow = () => new Date().toISOString().slice(0, 7);

export default async function footprint() {
  const S = { country: state.user?.home_country || 'India' };
  const form = {}, resultBox = h('div', {}), historyBox = h('div', {});
  const num = (name, label, hint, max = 100000, v = '') => {
    form[name] = h('input', { class: 'input', type: 'number', min: 0, max, step: 'any', inputmode: 'decimal', value: v, placeholder: '0', 'aria-label': label });
    return h('label', { class: 'field' }, label, form[name], h('span', { class: 'hint', style: { margin: 0 } }, hint));
  };
  form.period = h('input', { class: 'input', type: 'month', value: monthNow(), max: monthNow() });
  const pickerHost = h('div', {});
  const paintPicker = () => clear(pickerHost).append(countryPicker({ placeholder: S.country, clearOnPick: false, value: S.country, onPick: (c) => { S.country = c; estimate(); } }));
  paintPicker();
  const payload = () => ({ period: form.period.value, country: S.country, electricity_kwh: +form.electricity_kwh.value || 0, gas_m3: +form.gas_m3.value || 0, car_km: +form.car_km.value || 0, flight_km: +form.flight_km.value || 0, renewable_pct: +form.renewable_pct.value || 0 });
  let last = null;
  async function estimate() {
    const b = payload();
    if (!b.electricity_kwh && !b.gas_m3 && !b.car_km && !b.flight_km) { last = null; return clear(resultBox).append(emptyState('Enter your monthly usage', 'Results appear here as you type. Nothing is saved until you press “Save month”.')); }
    try { last = await api.post('/api/footprint/estimate', b); clear(resultBox).append(renderResult(last, b)); }
    catch (e) { clear(resultBox).append(emptyState('Check your numbers', e.details?.[0]?.message?.replace('Value error, ', '') || e.message)); }
  }
  const est = (() => { let t; return () => { clearTimeout(t); t = setTimeout(estimate, 200); }; })();
  const saveBtn = h('button', { class: 'btn primary', onclick: async () => {
    if (!state.user) { toast('Sign in to save your footprint'); return (location.hash = '#/login?next=%2Fcarbon'); }
    try { await api.post('/api/footprint/entries', payload()); toast('Month saved', 'ok'); drawHistory(); } catch (e) { toast(e.details?.[0]?.message?.replace('Value error, ', '') || e.message, 'err'); }
  } }, icon('check'), 'Save month');
  const inputs = [num('electricity_kwh', 'Electricity (kWh)', 'From your bill'), num('gas_m3', 'Natural gas (m³)', 'Heating & cooking', 50000), num('car_km', 'Car travel (km)', 'Petrol passenger car', 100000), num('flight_km', 'Flights (km)', 'Passenger-km flown', 500000), num('renewable_pct', 'Your renewable electricity (%)', 'Rooftop solar or green tariff', 100)];
  Object.values(form).forEach((i) => i.addEventListener('input', est));
  async function drawHistory() {
    if (!state.user) return clear(historyBox).append(h('div', { class: 'card callout green row spread wrap' }, h('span', {}, 'Create a free account to save months, see your trend and compare with your country\'s average.'), h('a', { class: 'btn primary', href: '#/register' }, 'Create account')));
    await load(historyBox, async () => {
      const s = await api.get('/api/footprint/summary');
      if (!s.count) return emptyState('No saved months yet', 'Fill in the form and press “Save month” to start your history.');
      const cc = s.country_per_capita_t;
      return h('div', { class: 'stack' },
        h('div', { class: 'grid g4 kpi-row' }, kpi({ label: 'Average month', value: fmt(s.avg_month_kg, 0), unit: 'kg CO₂e', delta: s.change_vs_previous_pct != null ? delta(s.change_vs_previous_pct, { unit: '%', good: 'down', suffix: 'last vs prior month' }) : null }),
          kpi({ label: 'Annualised', value: fmt(s.annualised_t, 2), unit: 't CO₂e' }), kpi({ label: 'Months logged', value: s.count }),
          kpi({ label: `${cc?.country || 'Country'} avg per person ~`, value: cc ? fmt(cc.value, 1) : '–', unit: 't/yr', hint: cc ? `All sectors, ${cc.year}. Different scope than this tracker.` : '' })),
        h('div', { class: 'grid g-main' },
          h('div', { class: 'card' }, h('div', { class: 'row spread' }, h('h3', {}, 'Monthly emissions'), h('button', { class: 'btn sm', onclick: () => download('/api/footprint/export.csv') }, icon('download'), 'CSV')),
            lineChart({ series: [{ name: 'kg CO₂e', color: 'var(--c1)', area: true, points: s.entries.map((e, i) => ({ x: i, y: e.co2_kg })) }], height: 240, unit: 'kg', xFormat: (i) => s.entries[Math.round(i)]?.period ?? '', yMin: 0, ariaLabel: 'Monthly footprint' })),
          h('div', { class: 'card' }, h('h3', {}, 'Where it comes from'), h('div', { style: { marginTop: '12px' } }, donut({ parts: [['Electricity', 'electricity', 'var(--c3)'], ['Gas', 'gas', 'var(--c2)'], ['Car', 'car', 'var(--c4)'], ['Flights', 'flights', 'var(--c5)']].map(([l, k, c]) => ({ label: l, value: s.totals_by_category[k], color: c })), center: fmt(s.total_kg / 1000, 1) + ' t' })))),
        h('div', { class: 'grid g2' },
          h('div', { class: 'card' }, h('h3', {}, 'Best next steps'), h('p', { class: 'sub' }, 'From your latest month, ranked by kg CO₂e avoided per month.'), h('div', { style: { marginTop: '10px' } }, s.recommendations.map(recCard))),
          h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Month', 'Country', 'kg CO₂e', ''].map((t, i) => h('th', { class: i > 1 ? 'r' : '' }, t)))),
            h('tbody', {}, [...s.entries].reverse().map((e) => h('tr', {}, h('td', {}, e.period), h('td', {}, e.country), h('td', { class: 'r tnum' }, fmt(e.co2_kg, 0)),
              h('td', { class: 'r' }, h('button', { class: 'btn sm danger', 'aria-label': `Delete ${e.period}`, onclick: async () => { if (await confirmBox('Delete this month?', `${e.period} will be removed from your history.`)) { await api.del(`/api/footprint/entries/${e.id}`); toast('Deleted', 'ok'); drawHistory(); } } }, icon('trash'))))))))));
    }, { height: 260 });
  }
  estimate(); drawHistory();
  return h('div', { class: 'page stack', style: { gap: '22px' } },
    pageHead('Carbon footprint', 'Estimate a month of household emissions using your country\'s own electricity mix, then track it over time.'),
    h('div', { class: 'grid g-main', style: { alignItems: 'start' } },
      h('div', { class: 'card stack', style: { gap: '14px' } }, h('div', { class: 'grid g2' }, h('label', { class: 'field' }, 'Country', pickerHost), h('label', { class: 'field' }, 'Month', form.period)),
        h('div', { class: 'grid g2' }, inputs), h('div', { class: 'row' }, saveBtn, !state.user && h('span', { class: 'hint', style: { margin: 0 } }, 'Free account required to save.'))),
      resultBox),
    historyBox,
    h('div', { class: 'callout' }, 'Factors are typical published averages and approximate: gas 2.0 kg/m³, car 0.17 kg/km, flights 0.15 kg per passenger-km. Electricity uses the country\'s grid intensity estimated from its generation mix (fossil blend 700 g/kWh, nuclear 12, renewables 25).'),
    sourceNote());
}
const recCard = (r) => h('div', { class: 'rec' }, h('div', { class: 'pri low' }), h('div', {}, h('b', {}, r.title), h('p', { class: 'muted small', style: { margin: '2px 0' } }, r.detail), h('span', { class: 'chip green' }, `−${fmt(r.saving_kg_month, 1)} kg CO₂e / month`)));
function renderResult(r, b) {
  const names = { electricity: 'Electricity', gas: 'Natural gas', car: 'Car', flights: 'Flights' };
  return h('div', { class: 'card stack' }, h('div', { class: 'muted small' }, `Estimated emissions for ${r.country}`),
    h('div', { class: 'big-num tnum' }, fmt(r.total_kg, 0), h('small', { class: 'muted', style: { fontSize: '18px' } }, ' kg CO₂e / month')),
    h('p', { class: 'hint', style: { margin: 0 } }, `≈ ${fmt(r.total_kg * 12 / 1000, 1)} t per year at this rate. Grid intensity ${fmt(r.grid_g_per_kwh, 0)} g/kWh${r.grid_from_data ? ' (estimated from generation mix)' : ' (global fallback: no mix data)'}.`),
    barH({ rows: Object.entries(r.parts).filter(([, v]) => v > 0).map(([k, v]) => ({ label: names[k], value: v })), format: (v) => fmt(v, 0) + ' kg', color: 'var(--c1)' }),
    h('h3', {}, 'Ways to cut it'), ...r.recommendations.map(recCard));
}
