import { api } from '../api.js';
import { h, fmt, clear, debounce, toast, confirmBox, emptyState, icon, download } from '../ui.js';
import { pageHead, seg, tip, countryPicker } from '../components.js';
import { state } from '../state.js';

const CAT_COLOR = { electricity: 'var(--c2)', cooking_heating: 'var(--c4)', vehicles: 'var(--c3)', public_transport: 'var(--c1)', flights: 'var(--c5)', other: 'var(--ink-3)' };
const now = new Date();
const thisMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
const num = (v) => (v === '' || v == null || Number.isNaN(Number(v)) ? null : Number(v));

/** Chips for approximate answers + a free number box. value() -> number|null, set by chip midpoint or typing. */
function approx({ bands, unit, value, onChange, placeholder = 'or type a number' }) {
  const box = h('div', { class: 'stack', style: { gap: '8px' } });
  const input = h('input', { class: 'input', type: 'number', min: 0, inputmode: 'decimal', placeholder, 'aria-label': `Exact amount in ${unit}`, style: { maxWidth: '190px' }, value: value ?? '', oninput: (e) => { onChange(num(e.target.value)); paint(); } });
  const paint = () => {
    const cur = num(input.value);
    clear(chips).append(...bands.map(([label, v]) => h('button', { type: 'button', class: 'opt', 'aria-pressed': String(cur === v), onclick: () => { input.value = v; onChange(v); paint(); } }, label)));
  };
  const chips = h('div', { class: 'opt-row' });
  paint(); box.append(chips, h('div', { class: 'row' }, input, h('span', { class: 'small muted' }, unit)));
  return box;
}
function optRow(options, value, onChange) {
  const row = h('div', { class: 'opt-row', role: 'group' });
  const draw = (v) => clear(row).append(...options.map(([k, label, hint]) => h('button', { type: 'button', class: 'opt', title: hint || '', 'aria-pressed': String(k === v), onclick: () => { draw(k); onChange(k); } }, label)));
  draw(value); return row;
}
function qCard(title, helpText, { skippable = true, skipped = false, onSkip }, ...body) {
  const card = h('section', { class: `q-card${skipped ? ' skipped' : ''}` });
  const cb = h('input', { type: 'checkbox', checked: skipped, 'aria-label': `Skip: ${title}`, onchange: (e) => { card.classList.toggle('skipped', e.target.checked); onSkip(e.target.checked); } });
  card.append(h('div', { class: 'q-head' }, h('h4', {}, title, helpText ? tip(helpText) : null), skippable ? h('label', { class: 'small muted row', style: { gap: '6px', cursor: 'pointer' } }, cb, 'Skip') : null), ...body);
  return card;
}

export default async function footprint() {
  const factors = await api.get('/api/footprint/factors', { cache: true });
  const S = {
    mode: 'simple', period: thisMonth, country: 'India', size: 4,
    elec: { skip: false, type: 'bill', bill: null, kwh: null, tariff: factors.default_tariff_inr_per_kwh, ren: 0 },
    cook: { skip: false, type: 'lpg_14kg', per: 1 },
    veh: [{ type: 'motorcycle', km: null }], vehSkip: false,
    transit: { skip: false, bus: null, train: null, metro: null, cab: null },
    flights: 'never', flightSkip: false, dg: null,
    adv: { kwh: null, gas: null, lpg: null, car: null, flight: null, ren: 0 },
  };
  let seq = 0;
  const result = h('div', {}), history = h('div', {});

  function payload() {
    if (S.mode === 'advanced') {
      const a = S.adv;
      return { mode: 'advanced', period: S.period, country: S.country, household_size: S.size, electricity_kwh: a.kwh ?? 0, gas_m3: a.gas ?? 0, lpg_kg: a.lpg ?? 0, car_km: a.car ?? 0, flight_km: a.flight ?? 0, renewable_pct: a.ren || 0 };
    }
    const p = { mode: 'simple', period: S.period, country: S.country, household_size: S.size };
    const e = S.elec;
    if (!e.skip) {
      const el = { renewable_pct: e.ren || 0 };
      if (e.type === 'kwh' && e.kwh != null) el.kwh = e.kwh; else if (e.type === 'bill' && e.bill != null) { el.bill_inr = e.bill; el.tariff_inr_per_kwh = e.tariff; }
      if (el.kwh != null || el.bill_inr != null) p.electricity = el;
    }
    if (!S.cook.skip) p.cooking = { type: S.cook.type, per_month: S.cook.type === 'none' ? 0 : S.cook.per || 0 };
    if (!S.vehSkip) p.vehicles = S.veh.filter((v) => v.type !== 'none' && v.km > 0).map((v) => ({ type: v.type, km_per_month: v.km }));
    if (!S.transit.skip) p.transit = { bus_km: S.transit.bus || 0, train_km: S.transit.train || 0, metro_km: S.transit.metro || 0, cab_km: S.transit.cab || 0 };
    if (!S.flightSkip) p.flights = { frequency: S.flights };
    if (S.dg) p.other = { generator_hours: S.dg };
    return p;
  }
  const run = debounce(async () => {
    const my = ++seq;
    try {
      const r = await api.post('/api/footprint/estimate', payload());
      if (my === seq) paintResult(r);
    } catch (e) {
      if (my !== seq) return;
      clear(result).append(e.status === 422 && /at least one|non-zero/i.test(`${e.message} ${JSON.stringify(e.details || '')}`)
        ? emptyState('Answer a question to see your estimate', 'Fill in anything you know, approximate answers are fine, and skip the rest.')
        : h('div', { class: 'callout' }, e.message));
    }
  }, 350);

  /* ------------------------------------------------ result */
  function paintResult(r) {
    const cats = factors.categories, parts = Object.entries(r.parts).filter(([, v]) => v > 0);
    const b = r.benchmark;
    clear(result).append(h('div', { class: 'card stack', style: { gap: '14px' } },
      h('div', {}, h('div', { class: 'small muted' }, 'Estimated household operational footprint · per month'),
        h('div', { class: 'result-total tnum' }, fmt(r.total_kg, 0), h('small', { style: { fontSize: '16px', fontFamily: 'var(--sans)', marginLeft: '6px', color: 'var(--ink-3)' } }, 'kg CO₂e')),
        h('div', { class: 'small muted' }, `Likely range ${fmt(r.low_kg, 0)}–${fmt(r.high_kg, 0)} kg`, tip('Combines the uncertainty of every answer. Exact readings (like kWh) narrow the range; approximate answers widen it.'))),
      h('div', { class: 'grid g2' }, stat('Per person', fmt(r.per_person_kg, 0) + ' kg', `household of ${r.household_size}`), stat('Estimated inputs', fmt(r.estimated_share * 100, 0) + '%', 'of the footprint is based on approximate answers')),
      h('div', {}, h('div', { class: 'stackbar', role: 'img', 'aria-label': 'Footprint by category' }, parts.map(([k, v]) => h('i', { style: { width: (v / r.total_kg) * 100 + '%', background: CAT_COLOR[k] }, title: `${cats[k]} ${fmt(v, 0)} kg` }))),
        h('div', { class: 'stack', style: { gap: '4px', marginTop: '10px' } }, parts.map(([k, v]) => h('div', { class: 'row spread small' }, h('span', {}, h('i', { class: 'sw', style: { background: CAT_COLOR[k] } }), cats[k]), h('span', { class: 'tnum' }, `${fmt(v, 0)} kg · ${fmt((v / r.total_kg) * 100, 0)}%`))))),
      b && h('div', { class: 'callout green' }, h('b', {}, 'Context: '), `${fmt(b.you_kg_per_person_month, 0)} kg per person per month vs ${fmt(b.national_kg_per_person_month, 0)} kg for the average person in ${b.country} (${b.national_year})${b.world_kg_per_person_month ? ` and ${fmt(b.world_kg_per_person_month, 0)} kg worldwide` : ''}. `, h('span', { class: 'muted' }, b.caveat)),
      h('details', { class: 'more' }, h('summary', {}, 'How each part was calculated'),
        h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Item', 'kg CO₂e', 'Basis'].map((c, i) => h('th', { class: i === 1 ? 'r' : '' }, c)))),
          h('tbody', {}, r.items.map((i) => h('tr', {}, h('td', {}, h('div', {}, i.label), h('div', { class: 'small muted' }, i.note)), h('td', { class: 'r tnum' }, fmt(i.kg, 1)), h('td', {}, h('span', { class: `flag ${i.basis}` }, i.basis))))))),
        r.skipped.length ? h('p', { class: 'hint', style: { margin: 0 } }, `Skipped (not counted): ${r.skipped.join(', ')}.`) : null),
      h('details', { class: 'more' }, h('summary', {}, 'Methodology & assumptions'), methodology(r)),
      r.recommendations?.length ? h('div', {}, h('h3', { style: { fontSize: '17px', marginBottom: '8px' } }, 'Where you could cut most'),
        r.recommendations.map((x) => h('div', { class: 'rec' }, h('div', { class: 'pri medium' }), h('div', {}, h('b', {}, x.title, ' ', h('span', { class: 'chip green' }, `≈ −${fmt(x.saving_kg_month, 0)} kg/month`)), h('p', { class: 'muted', style: { margin: '4px 0 0' } }, x.detail))))) : null,
      h('div', { class: 'row wrap' }, h('button', { class: 'btn primary', onclick: save }, icon('plus'), `Save ${S.period} to my account`), h('span', { class: 'small muted' }, state.user ? 'Saving the same month again replaces it.' : 'Sign in to save and track goals.'))));
  }
  const stat = (a, b2, c) => h('div', { class: 'card', style: { boxShadow: 'none', padding: '12px' } }, h('div', { class: 'small muted' }, a), h('div', { style: { font: '600 22px var(--serif)' } }, b2), h('div', { class: 'small muted' }, c));
  function methodology(r) {
    const f = factors.factors;
    return h('div', { class: 'stack', style: { gap: '8px' }, 'data-testid': 'methodology' },
      h('p', { style: { margin: 0 } }, 'This is an ', h('b', {}, 'estimated household operational carbon footprint'), ': electricity, cooking and heating fuel, transport and flights. It excludes food, goods, services, home construction and waste, so it is not a full lifestyle footprint.'),
      h('p', { style: { margin: 0 } }, `Electricity uses ${r.country}'s grid intensity of ${fmt(r.grid.g_per_kwh, 0)} g CO₂e/kWh${r.grid.year ? ` (${r.grid.year}, ${r.grid.source})` : ` (${r.grid.source})`}. The year is pinned so months stay comparable. It excludes transmission and distribution losses.`),
      h('ul', { class: 'small', style: { margin: 0, paddingLeft: '18px' } },
        h('li', {}, `LPG ${f.lpg_kg} kg CO₂ per kg (a 14.2 kg cylinder ≈ ${fmt(14.2 * f.lpg_kg, 0)} kg; 5 kg ≈ ${fmt(5 * f.lpg_kg, 0)} kg). Piped gas ${f.png_m3} kg per m³.`),
        h('li', {}, `Petrol ${f.petrol_l} kg and diesel ${f.diesel_l} kg per litre, with assumed mileage: motorcycle 40, scooter 45, petrol car 15, diesel car 18 km/L. Electric vehicles use kWh per km × grid intensity.`),
        h('li', {}, `Public transport per passenger-km: bus ${f.bus_pkm}, train ${f.train_pkm}, metro ≈ ${f.metro_kwh_per_pkm} kWh × grid. Taxi/auto ${f.cab_km} kg per km.`),
        h('li', {}, `Flights ${f.flight_pkm} kg per passenger-km (no radiative forcing). "Occasionally" ≈ ${fmt(factors.flight_bands_pkm_per_year.occasionally, 0)} and "frequently" ≈ ${fmt(factors.flight_bands_pkm_per_year.frequently, 0)} passenger-km a year for the household.`),
        h('li', {}, `Electricity bills are converted at ₹${factors.default_tariff_inr_per_kwh}/kWh unless you choose another tariff.`)),
      r.assumptions.length ? h('p', { class: 'small muted', style: { margin: 0 } }, 'Applied to your answers: ' + r.assumptions.join(' ')) : null,
      h('p', { class: 'hint', style: { margin: 0 } }, `Factor set ${factors.version}. ${factors.note}`));
  }
  async function save() {
    if (!state.user) { toast('Sign in to save your footprint'); return (location.hash = '#/login?next=/carbon'); }
    try {
      const r = await api.post('/api/footprint/entries', payload());
      toast(`Saved ${S.period}: ${fmt(r.entry.co2_kg, 0)} kg CO₂e`, 'ok');
      (r.new_badges || []).forEach((bd) => toast(`🏅 Badge unlocked: ${bd.name}`, 'ok'));
      loadHistory();
    } catch (e) { toast(e.message, 'err'); }
  }
  async function loadHistory() {
    clear(history);
    if (!state.user) return history.append(h('div', { class: 'card callout green row spread wrap' }, h('span', {}, 'Create a free account to save monthly footprints and set reduction goals.'), h('a', { class: 'btn primary', href: '#/register' }, 'Create account')));
    try {
      const { entries } = await api.get('/api/footprint/entries');
      history.append(h('div', { class: 'card' }, h('div', { class: 'row spread wrap' }, h('h3', {}, 'Your saved months'), h('div', { class: 'row' }, h('a', { class: 'btn sm primary', href: '#/sustainability' }, 'Set a reduction goal'), entries.length ? h('button', { class: 'btn sm', onclick: () => download('/api/footprint/export.csv') }, icon('download'), 'CSV') : null)),
        entries.length ? h('div', { class: 'table-wrap', style: { marginTop: '10px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Month', 'Mode', 'People', 'kg CO₂e', 'Per person', ''].map((c, i) => h('th', { class: i > 1 ? 'r' : '' }, c)))),
          h('tbody', {}, entries.map((e) => h('tr', {}, h('td', {}, e.period), h('td', {}, e.mode), h('td', { class: 'r tnum' }, e.household_size), h('td', { class: 'r tnum' }, fmt(e.co2_kg, 0)), h('td', { class: 'r tnum' }, fmt(e.per_person_kg, 0)),
            h('td', { class: 'r' }, h('button', { class: 'btn sm ghost danger', 'aria-label': `Delete ${e.period}`, onclick: async () => { if (await confirmBox('Delete this month?', `${e.period} will be removed and goal progress recalculated.`)) { await api.del(`/api/footprint/entries/${e.id}`); loadHistory(); } } }, icon('trash'))))))))
          : h('p', { class: 'muted' }, 'Nothing saved yet.')));
    } catch (e) { history.append(h('div', { class: 'callout' }, e.message)); }
  }

  /* ------------------------------------------------ forms */
  const form = h('div', { class: 'stack' });
  const common = () => h('div', { class: 'q-card' }, h('div', { class: 'q-head' }, h('h4', {}, 'About your household')),
    h('div', { class: 'grid g3' },
      h('label', { class: 'field' }, h('span', {}, 'People in the household', tip('Everyone who shares the electricity bill and kitchen. Used for the per-person figure.')), h('input', { class: 'input', type: 'number', min: 1, max: 20, value: S.size, oninput: (e) => { S.size = Math.min(20, Math.max(1, Math.round(+e.target.value || 1))); run(); } })),
      h('label', { class: 'field' }, h('span', {}, 'Month', tip('The month these answers describe. One entry per month; saving again replaces it.')), h('input', { class: 'input', type: 'month', value: S.period, max: thisMonth, onchange: (e) => { S.period = e.target.value || thisMonth; run(); } })),
      h('label', { class: 'field' }, h('span', {}, 'Country', tip('Sets the electricity grid emission factor and the benchmark.')), countryPicker({ placeholder: S.country, clearOnPick: false, value: S.country, onPick: (c) => { S.country = c; run(); } }))));
  function simpleForm() {
    const e = S.elec;
    const elecBody = h('div', { class: 'stack', style: { gap: '10px' } });
    const drawElec = () => {
      clear(elecBody).append(optRow([['bill', 'I know my bill (₹)'], ['kwh', 'I know my units (kWh)']], e.type, (v) => { e.type = v; drawElec(); run(); }),
        e.type === 'bill' ? h('div', { class: 'stack', style: { gap: '10px' } },
          approx({ bands: [['₹500', 500], ['₹1,000', 1000], ['₹2,000', 2000], ['₹3,500', 3500], ['₹6,000', 6000]], unit: '₹ per month', value: e.bill, onChange: (v) => { e.bill = v; run(); } }),
          h('label', { class: 'field' }, h('span', {}, 'Tariff used to convert the bill into units', tip('Bills include fixed charges and taxes, so the average ₹ per kWh is higher than the slab rate. Pick the closest or type your own. The estimate is flagged "estimated".')),
            h('div', { class: 'row wrap' }, optRow(factors.tariff_presets.map((t) => [t.value, t.label]), e.tariff, (v) => { e.tariff = v; tariffIn.value = v; run(); }),
              h('span', { style: { display: 'none' } }))),
          (() => { tariffIn = h('input', { class: 'input', type: 'number', min: 1, max: 50, step: 0.5, value: e.tariff, style: { maxWidth: '120px' }, 'aria-label': 'Tariff in rupees per kWh', oninput: (ev) => { e.tariff = num(ev.target.value) || factors.default_tariff_inr_per_kwh; run(); } }); return h('div', { class: 'row' }, tariffIn, h('span', { class: 'small muted' }, '₹ per kWh (editable)')); })())
          : h('div', {}, approx({ bands: [['100', 100], ['200', 200], ['300', 300], ['500', 500], ['800', 800]], unit: 'kWh (units) per month', value: e.kwh, onChange: (v) => { e.kwh = v; run(); } }), h('p', { class: 'hint' }, 'Units are on your bill as "units consumed" or "kWh".')),
        h('label', { class: 'field', style: { maxWidth: '260px' } }, h('span', {}, 'Share from your own rooftop solar (%)', tip('Leave at 0 if you buy all your electricity from the grid.')), h('input', { class: 'input', type: 'number', min: 0, max: 100, value: e.ren, oninput: (ev) => { e.ren = Math.min(100, Math.max(0, +ev.target.value || 0)); run(); } })));
    };
    let tariffIn; drawElec();
    const cookBody = h('div', { class: 'stack', style: { gap: '10px' } });
    const drawCook = () => {
      clear(cookBody).append(optRow([['lpg_14kg', 'LPG 14.2 kg cylinder'], ['lpg_5kg', 'LPG 5 kg cylinder'], ['piped', 'Piped gas (PNG)'], ['none', 'Induction / none']], S.cook.type, (v) => { S.cook.type = v; S.cook.per = v === 'piped' ? 15 : v === 'none' ? 0 : 1; drawCook(); run(); }),
        S.cook.type.startsWith('lpg') ? approx({ bands: [['Lasts 2 months', 0.5], ['Lasts 6 weeks', 0.7], ['1 a month', 1], ['1.5 a month', 1.5], ['2 a month', 2]], unit: 'cylinders per month', value: S.cook.per, onChange: (v) => { S.cook.per = v; run(); } })
          : S.cook.type === 'piped' ? approx({ bands: [['Light (10 m³)', 10], ['Typical (15 m³)', 15], ['Heavy (25 m³)', 25]], unit: 'm³ per month (on the PNG bill)', value: S.cook.per, onChange: (v) => { S.cook.per = v; run(); } }) : h('p', { class: 'hint', style: { margin: 0 } }, 'Electricity for induction is counted under electricity.'));
    };
    drawCook();
    const vehBody = h('div', { class: 'stack', style: { gap: '12px' } });
    const bands = [['< 100 km', 50], ['100–300', 200], ['300–600', 450], ['600–1,000', 800], ['1,000+', 1400]];
    const drawVeh = () => {
      clear(vehBody).append(...S.veh.map((v, i) => h('div', { class: 'stack', style: { gap: '8px', paddingBottom: '10px', borderBottom: i < S.veh.length - 1 ? '1px dashed var(--line)' : 0 } },
        h('div', { class: 'row wrap' }, h('select', { class: 'input', style: { maxWidth: '240px' }, 'aria-label': `Vehicle ${i + 1} type`, onchange: (ev) => { v.type = ev.target.value; run(); } },
          h('option', { value: 'none', selected: v.type === 'none' }, 'No vehicle'), ...Object.entries(factors.vehicles).map(([k, x]) => h('option', { value: k, selected: v.type === k }, x.label))),
          S.veh.length > 1 ? h('button', { class: 'btn sm ghost', type: 'button', onclick: () => { S.veh.splice(i, 1); drawVeh(); run(); } }, 'Remove') : null),
        v.type !== 'none' ? approx({ bands, unit: 'km per month (rough is fine)', value: v.km, onChange: (x) => { v.km = x; run(); } }) : null)),
        S.veh.length < 4 ? h('button', { class: 'btn sm', type: 'button', onclick: () => { S.veh.push({ type: 'scooter', km: null }); drawVeh(); } }, icon('plus'), 'Add another vehicle') : null);
    };
    drawVeh();
    const tb = [['None', 0], ['A little', 50], ['Some', 150], ['A lot', 400]];
    const trRow = (key, label, helpText) => h('div', { class: 'stack', style: { gap: '6px' } }, h('div', { class: 'small', style: { fontWeight: 600 } }, label, tip(helpText)), approx({ bands: tb, unit: 'km per month, whole household', value: S.transit[key], onChange: (v) => { S.transit[key] = v; run(); } }));
    return h('div', { class: 'stack' }, common(),
      qCard('Electricity', 'Your monthly bill is enough. We convert it to units with the tariff you choose and flag it as an estimate. If you know your units, choose kWh for a tighter range.', { skipped: e.skip, onSkip: (v) => { e.skip = v; run(); } }, elecBody),
      qCard('Cooking gas', 'Indian homes usually use a 14.2 kg LPG cylinder. If one lasts about 6 weeks, that is 0.7 cylinders a month.', { skipped: S.cook.skip, onSkip: (v) => { S.cook.skip = v; run(); } }, cookBody),
      qCard('Vehicles you own', 'Two-wheelers and cars. Choose the closest distance band, or type a number. Mileage is assumed (shown under "How each part was calculated").', { skipped: S.vehSkip, onSkip: (v) => { S.vehSkip = v; run(); } }, vehBody),
      qCard('Public transport & cabs', 'Distance travelled by everyone in the household combined, per month. Rough bands are fine.', { skipped: S.transit.skip, onSkip: (v) => { S.transit.skip = v; run(); } },
        h('div', { class: 'stack' }, trRow('bus', 'Bus', 'City or intercity bus journeys.'), trRow('train', 'Train', 'Suburban and long-distance trains.'), trRow('metro', 'Metro', 'Electric metro rail.'), trRow('cab', 'Taxi / auto-rickshaw', 'Ride-hailing, taxis and autos.'))),
      qCard('Flights', `Occasionally ≈ ${fmt(factors.flight_bands_pkm_per_year.occasionally, 0)} km a year for the household (about two return domestic trips). Frequently ≈ ${fmt(factors.flight_bands_pkm_per_year.frequently, 0)} km.`, { skipped: S.flightSkip, onSkip: (v) => { S.flightSkip = v; run(); } },
        optRow([['never', 'Never'], ['occasionally', 'Occasionally'], ['frequently', 'Frequently']], S.flights, (v) => { S.flights = v; run(); })),
      qCard('Other', 'Diesel generators burn about a litre per hour. Leave empty if you do not use one.', { skippable: false, onSkip() {} },
        h('label', { class: 'field', style: { maxWidth: '260px' } }, 'Generator hours per month', h('input', { class: 'input', type: 'number', min: 0, max: 744, value: S.dg ?? '', oninput: (ev) => { S.dg = num(ev.target.value); run(); } }))));
  }
  function advancedForm() {
    const f = (key, label, unit, helpText, max = 100000) => h('label', { class: 'field' }, h('span', {}, label, tip(helpText)), h('div', { class: 'row' }, h('input', { class: 'input', type: 'number', min: 0, max, step: 'any', value: S.adv[key] ?? '', oninput: (e) => { S.adv[key] = num(e.target.value); run(); } }), h('span', { class: 'small muted' }, unit)));
    return h('div', { class: 'stack' }, common(),
      h('div', { class: 'q-card' }, h('div', { class: 'q-head' }, h('h4', {}, 'Exact quantities for the month'), h('span', { class: 'flag actual' }, 'all counted as actual')),
        h('div', { class: 'grid g2' },
          f('kwh', 'Electricity', 'kWh', 'Units consumed this month, from your bill or smart meter.'),
          f('ren', 'Own renewable share', '%', 'Share of that electricity from your own rooftop solar or a certified green tariff.', 100),
          f('gas', 'Natural gas (piped)', 'm³', 'Standard cubic metres of piped natural gas.'),
          f('lpg', 'LPG', 'kg', 'Mass of LPG used. A 14.2 kg cylinder = 14.2.'),
          f('car', 'Car travel', 'km', 'Kilometres driven in a petrol car (0.17 kg CO₂e per km, average).'),
          f('flight', 'Flights', 'passenger-km', 'Distance flown by household members (a 1,000 km one-way flight = 1,000).'))));
  }
  const draw = () => { clear(form).append(S.mode === 'simple' ? simpleForm() : advancedForm()); run(); };
  draw(); loadHistory();
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Carbon footprint', 'An estimated household operational carbon footprint: electricity, cooking fuel, transport and flights. Approximate answers are fine.',
      seg([['simple', 'Simple'], ['advanced', 'Advanced']], 'simple', (m) => { S.mode = m; draw(); })),
    h('div', { class: 'calc-layout' }, form, h('div', { class: 'calc-result' }, result)),
    history);
}
