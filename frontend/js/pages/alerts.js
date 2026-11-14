import { api } from '../api.js';
import { h, fmt, load, clear, toast, emptyState, confirmBox, icon } from '../ui.js';
import { pageHead, countryPicker, goCountry } from '../components.js';
import { spark as sparkChart } from '../charts.js';
import { state } from '../state.js';
import { refreshNotifs } from '../main.js';

const CONDS = [['below', 'drops below'], ['above', 'rises above'], ['yoy_drop', 'falls year-on-year by ≥'], ['forecast_below', 'is forecast below']];

export default async function alerts() {
  const S = { country: state.user.home_country || 'India', metric: 'renewable_elec_share', condition: 'below', threshold: 30, year: 2030 };
  const rulesBox = h('div', {}), notifBox = h('div', {}), watchBox = h('div', {}), pickerHost = h('div', {});
  clear(pickerHost).append(countryPicker({ placeholder: S.country, value: S.country, clearOnPick: false, onPick: (c) => { S.country = c; } }));
  const metricSel = h('select', { class: 'input', 'aria-label': 'Metric', onchange: (e) => { S.metric = e.target.value; } }, state.meta.metrics.map((m) => h('option', { value: m.key, selected: m.key === S.metric }, m.label)));
  const yearField = h('label', { class: 'field', style: { display: 'none' } }, 'Target year', h('input', { class: 'input', type: 'number', min: 2021, max: 2040, value: S.year, oninput: (e) => { S.year = +e.target.value; } }));
  const condSel = h('select', { class: 'input', 'aria-label': 'Condition', onchange: (e) => { S.condition = e.target.value; yearField.style.display = S.condition === 'forecast_below' ? '' : 'none'; } }, CONDS.map(([v, l]) => h('option', { value: v }, l)));
  const thr = h('input', { class: 'input', type: 'number', step: 'any', value: S.threshold, 'aria-label': 'Threshold', oninput: (e) => { S.threshold = +e.target.value; } });
  const create = h('button', { class: 'btn primary', onclick: async () => {
    try {
      const body = { country: S.country, metric: S.metric, condition: S.condition, threshold: S.threshold, year: S.condition === 'forecast_below' ? S.year : null };
      if (S.condition === 'forecast_below' && !state.meta.metrics.find((m) => m.key === S.metric).forecastable) return toast('Choose a forecastable indicator for forecast alerts', 'err');
      const r = await api.post('/api/alerts/rules', body);
      toast(r.notifications_created ? 'Rule created. It already triggered!' : 'Rule created', 'ok'); drawAll();
    } catch (e) { toast(e.details?.[0]?.message?.replace('Value error, ', '') || e.message, 'err'); }
  } }, icon('plus'), 'Add rule');
  async function drawRules() {
    await load(rulesBox, async () => {
      const { rules } = await api.get('/api/alerts/rules');
      if (!rules.length) return emptyState('No rules yet', 'Create a rule above, for example “India renewable share falls below 30%”.');
      return h('div', { class: 'stack', style: { gap: '8px' } }, rules.map((r) => h('div', { class: 'row spread card', style: { padding: '12px 16px', boxShadow: 'none' } },
        h('span', { style: { opacity: r.enabled ? 1 : .5 } }, r.description),
        h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: async () => { await api.patch(`/api/alerts/rules/${r.id}`, { enabled: !r.enabled }); drawRules(); } }, r.enabled ? 'Pause' : 'Resume'),
          h('button', { class: 'btn sm danger', 'aria-label': 'Delete rule', onclick: async () => { if (await confirmBox('Delete rule?', r.description)) { await api.del(`/api/alerts/rules/${r.id}`); drawRules(); } } }, icon('trash'))))));
    }, { height: 90 });
  }
  async function drawNotifs() {
    await load(notifBox, async () => {
      const { notifications } = await api.get('/api/notifications');
      await refreshNotifs();
      if (!notifications.length) return emptyState('All quiet', 'Triggered alerts appear here and in the bell menu.');
      return h('div', { class: 'stack', style: { gap: '8px' } }, notifications.map((n) => h('div', { class: `notif ${n.is_read ? '' : 'unread'}`, style: { border: '1px solid var(--line)' } },
        h('span', { class: `chip ${n.severity === 'warning' ? 'amber' : 'green'}` }, n.severity), h('div', {}, h('b', {}, n.title), h('span', { class: 'small muted' }, n.body), h('div', { class: 'small muted' }, n.created_at + ' UTC')))));
    }, { height: 120 });
  }
  async function drawWatch() {
    await load(watchBox, async () => {
      const { items } = await api.get('/api/watchlist');
      if (!items.length) return emptyState('Not watching any country', 'Open a country page and press Watch.');
      return h('div', { class: 'grid g3' }, items.map((i) => h('div', { class: 'card', style: { cursor: 'pointer', boxShadow: 'none' }, onclick: () => goCountry(i.country) },
        h('div', { class: 'row spread' }, h('b', {}, i.country), sparkChart(i.series.map((p) => p.value), { w: 80 })), h('div', { class: 'muted small' }, `Renewable share ${fmt(i.value, 1)}% (${i.year})`))));
    }, { height: 90 });
  }
  const drawAll = () => { drawRules(); drawNotifs(); drawWatch(); };
  drawAll();
  return h('div', { class: 'page stack', style: { gap: '20px' } },
    pageHead('Alerts & watchlist', 'Rules are checked against the latest data and forecasts whenever you create one or press “Check now”.',
      h('button', { class: 'btn', onclick: async () => { const r = await api.post('/api/alerts/evaluate'); toast(r.notifications_created ? `${r.notifications_created} new alert(s)` : 'No new alerts', 'ok'); drawNotifs(); } }, 'Check now')),
    h('div', { class: 'card stack' }, h('h3', {}, 'New rule'),
      h('div', { class: 'grid g4' }, h('label', { class: 'field' }, 'Country', pickerHost), h('label', { class: 'field' }, 'Indicator', metricSel), h('label', { class: 'field' }, 'When it', condSel), h('label', { class: 'field' }, 'Threshold', thr)),
      h('div', { class: 'row wrap' }, yearField, create),
      h('p', { class: 'hint', style: { margin: 0 } }, 'The data is annual, so “current” alerts fire on the newest reported year of each indicator (shown with the alert); forecast alerts use the backtested model.')),
    h('div', { class: 'grid g2', style: { alignItems: 'start' } }, h('div', { class: 'stack', style: { gap: '10px' } }, h('h3', {}, 'Rules'), rulesBox), h('div', { class: 'stack', style: { gap: '10px' } }, h('h3', {}, 'Notifications'), notifBox)),
    h('div', { class: 'stack', style: { gap: '10px' } }, h('h3', {}, 'Watchlist'), watchBox));
}
