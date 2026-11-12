import { api, qs } from '../api.js';
import { h, fmt, load, toast, debounce } from '../ui.js';
import { barH } from '../charts.js';
import { pageHead, kpi, tabs } from '../components.js';
import { state } from '../state.js';

export default async function admin() {
  const s = await api.get('/api/admin/stats'), body = h('div', {});
  const views = { users: usersView, audit: auditView, system: () => systemView(s) };
  const show = (k) => { body.replaceChildren(views[k]()); };
  show('users');
  return h('div', { class: 'page stack', style: { gap: '20px' } }, pageHead('Administration', 'Users, audit trail and system health.'),
    h('div', { class: 'grid g4 kpi-row' }, kpi({ label: 'Users', value: s.users, hint: `${s.active_users} active · ${s.admins} admin` }), kpi({ label: 'Footprint entries', value: s.footprint_entries }), kpi({ label: 'Alert rules', value: s.alert_rules }), kpi({ label: 'Notifications', value: s.notifications })),
    h('div', { class: 'card' }, tabs([['users', 'Users'], ['audit', 'Audit log'], ['system', 'System']], 'users', show), body));
}
function usersView() {
  const S = { q: '', page: 1 }, box = h('div', {});
  const draw = () => load(box, async () => {
    const r = await api.get('/api/admin/users?' + qs(S));
    return h('div', {}, h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, ['Name', 'Email', 'Role', 'Status', 'Joined', 'Last login', ''].map((t) => h('th', {}, t)))),
      h('tbody', {}, r.users.map((u) => { const me = u.id === state.user.id; return h('tr', {}, h('td', {}, h('b', {}, u.name)), h('td', {}, u.email), h('td', {}, h('span', { class: `chip ${u.role === 'admin' ? 'amber' : ''}` }, u.role)), h('td', {}, h('span', { class: `chip ${u.is_active ? 'green' : 'red'}` }, u.is_active ? 'active' : 'disabled')), h('td', { class: 'muted' }, u.created_at.slice(0, 10)), h('td', { class: 'muted' }, u.last_login_at?.slice(0, 10) || '–'),
        h('td', {}, me ? h('span', { class: 'muted small' }, 'you') : h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: () => patch(u.id, { role: u.role === 'admin' ? 'user' : 'admin' }) }, u.role === 'admin' ? 'Make user' : 'Make admin'), h('button', { class: 'btn sm', onclick: () => patch(u.id, { is_active: !u.is_active }) }, u.is_active ? 'Disable' : 'Enable')))); })))),
      h('div', { class: 'pager' }, h('span', { class: 'muted small' }, `${r.total} users · page ${r.page}`), h('button', { class: 'btn sm', disabled: S.page <= 1, onclick: () => { S.page--; draw(); } }, '‹'), h('button', { class: 'btn sm', disabled: S.page * 20 >= r.total, onclick: () => { S.page++; draw(); } }, '›')));
  }, { height: 240 });
  const patch = async (id, b) => { try { await api.patch(`/api/admin/users/${id}`, b); toast('Updated', 'ok'); draw(); } catch (e) { toast(e.message, 'err'); } };
  draw();
  return h('div', {}, h('input', { class: 'input', placeholder: 'Search name or email…', 'aria-label': 'Search users', style: { maxWidth: '320px', marginBottom: '12px' }, oninput: debounce((e) => { S.q = e.target.value; S.page = 1; draw(); }, 250) }), box);
}
function auditView() {
  const box = h('div', {});
  load(box, async () => { const { events } = await api.get('/api/admin/audit'); return h('div', { class: 'table-wrap', style: { maxHeight: '460px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Time (UTC)', 'User', 'Action', 'Detail', 'IP'].map((t) => h('th', {}, t)))), h('tbody', {}, events.map((e) => h('tr', {}, h('td', { class: 'muted' }, e.created_at), h('td', {}, e.email || '–'), h('td', {}, h('span', { class: 'chip' }, e.action)), h('td', { class: 'muted' }, e.detail), h('td', { class: 'muted' }, e.ip || '–')))))); }, { height: 240 });
  return box;
}
function systemView(s) {
  return h('div', { class: 'grid g2' },
    h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Dataset'), ...Object.entries({ Source: s.dataset.source, Rows: fmt(s.dataset.rows, 0), Countries: s.dataset.countries, Years: s.dataset.years.join('–'), 'Headline year': s.dataset.headline_year }).map(([k, v]) => h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, k), h('b', {}, v)))),
    h('div', {}, h('h3', { style: { marginBottom: '8px' } }, 'Models'), h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, 'Loaded'), h('b', {}, s.models_loaded ? 'yes' : 'no')), h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, 'Trained at'), h('b', {}, s.models_trained_at || '–')),
      h('div', { class: 'stat-line' }, h('span', { class: 'muted' }, 'Forecast backtests cached'), h('b', {}, s.forecast_cache.length)),
      h('button', { class: 'btn', style: { marginTop: '12px' }, onclick: async () => { const r = await api.post('/api/admin/models/reload'); toast(r.models_loaded ? 'Models reloaded' : r.error, r.models_loaded ? 'ok' : 'err'); } }, 'Reload models from disk')),
    h('div', { style: { gridColumn: '1/-1' } }, h('h3', { style: { marginBottom: '8px' } }, 'Sign-ups, last 14 days'), s.signups_14d.length ? barH({ rows: s.signups_14d.map((d) => ({ label: d.d, value: d.n })), format: (v) => v }) : h('p', { class: 'muted' }, 'No sign-ups in the last 14 days.')));
}
