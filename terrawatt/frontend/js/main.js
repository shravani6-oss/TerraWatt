import { api } from './api.js';
import { applyTheme, emit, initialTheme, state } from './state.js';
import { clear, h, icon, logoMark, toast, errorState, fmt } from './ui.js';
import { countryPicker, goCountry } from './components.js';

const root = document.getElementById('app');
applyTheme(initialTheme());

// path pattern -> {mod, auth, shell}
const ROUTES = [
  ['/', { mod: 'landing', shell: false }],
  ['/login', { mod: 'auth', shell: false, props: { mode: 'login' } }],
  ['/register', { mod: 'auth', shell: false, props: { mode: 'register' } }],
  ['/dashboard', { mod: 'dashboard', title: 'Overview' }],
  ['/atlas', { mod: 'atlas', title: 'Atlas' }],
  ['/country/:name', { mod: 'country', title: 'Country' }],
  ['/compare', { mod: 'compare', title: 'Compare' }],
  ['/lab', { mod: 'scenario', title: 'What-if lab' }],
  ['/carbon', { mod: 'footprint', title: 'Carbon' }],
  ['/alerts', { mod: 'alerts', title: 'Alerts', auth: true }],
  ['/data', { mod: 'data', title: 'Dataset' }],
  ['/models', { mod: 'models', title: 'Model lab' }],
  ['/settings', { mod: 'settings', title: 'Settings', auth: true }],
  ['/admin', { mod: 'admin', title: 'Admin', auth: 'admin' }],
];
function match(path) {
  for (const [pat, cfg] of ROUTES) {
    const names = [], re = new RegExp('^' + pat.replace(/:([a-z]+)/g, (_, n) => (names.push(n), '([^/]+)')) + '/?$');
    const m = path.match(re);
    if (m) return { cfg, params: Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(m[i + 1])])) };
  }
  return null;
}
export const navigate = (p) => { location.hash = '#' + p; };
let shellEls = null;

const NAV = [
  ['Explore', null], ['/dashboard', 'Overview', 'home'], ['/atlas', 'Atlas', 'globe'], ['/compare', 'Compare', 'scale'],
  ['Plan', null], ['/lab', 'What-if lab', 'flask'], ['/carbon', 'Carbon footprint', 'leaf'], ['/alerts', 'Alerts & watchlist', 'bell'],
  ['Data', null], ['/data', 'Dataset', 'table'], ['/models', 'Model lab', 'cpu'],
];

function buildShell() {
  const nav = h('nav', { class: 'nav', 'aria-label': 'Primary' });
  const side = h('aside', { class: 'side' }, h('a', { class: 'brand', href: '#/' }, logoMark(), 'TerraWatt'), nav);
  const bell = h('button', { class: 'icon-btn', 'aria-label': 'Notifications', onclick: toggleNotifs }, icon('bell'));
  const themeBtn = h('button', { class: 'icon-btn', 'aria-label': 'Toggle dark mode', onclick: () => { applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); paintTheme(); document.dispatchEvent(new Event('themechange')); } });
  const paintTheme = () => { clear(themeBtn).append(icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon')); };
  paintTheme();
  const userBox = h('div', { class: 'row', style: { position: 'relative' } });
  const top = h('header', { class: 'topbar' },
    h('button', { class: 'icon-btn menu', 'aria-label': 'Open menu', onclick: () => side.classList.toggle('open') }, icon('menu')),
    h('div', { style: { flex: '1 1 160px', maxWidth: '420px', minWidth: 0 } }, countryPicker({ placeholder: 'Jump to a country…', onPick: goCountry })),
    h('div', { class: 'grow' }), themeBtn, bell, userBox);
  const content = h('main', { class: 'main-content', id: 'main' });
  const shell = h('div', { class: 'shell' }, side, h('div', { class: 'main' }, top, content));
  side.addEventListener('click', (e) => e.target.closest('a') && side.classList.remove('open'));
  shellEls = { shell, nav, content, bell, userBox, side };
  paintNav(); paintUser(); paintBell();
  return shellEls;
}
function paintNav() {
  if (!shellEls) return;
  const cur = location.hash.slice(1) || '/';
  clear(shellEls.nav);
  NAV.forEach(([a, b, c]) => {
    if (b === null) return shellEls.nav.append(h('h6', {}, a));
    shellEls.nav.append(h('a', { href: '#' + a, 'aria-current': cur === a || (a === '/dashboard' && cur.startsWith('/country')) ? 'page' : null }, icon(c), b));
  });
  shellEls.nav.append(h('h6', {}, 'Account'));
  if (state.user) {
    shellEls.nav.append(h('a', { href: '#/settings', 'aria-current': cur === '/settings' ? 'page' : null }, icon('user'), 'Settings'));
    if (state.user.role === 'admin') shellEls.nav.append(h('a', { href: '#/admin', 'aria-current': cur === '/admin' ? 'page' : null }, icon('shield'), 'Admin'));
  }
}
function paintUser() {
  if (!shellEls) return;
  clear(shellEls.userBox);
  if (state.user) {
    shellEls.userBox.append(h('span', { class: 'small muted', style: { maxWidth: '140px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, state.user.name),
      h('button', { class: 'btn sm', onclick: logout }, icon('logout'), 'Sign out'));
  } else shellEls.userBox.append(h('a', { class: 'btn sm', href: '#/login' }, 'Sign in'), h('a', { class: 'btn sm primary', href: '#/register' }, 'Get started'));
}
function paintBell() {
  if (!shellEls) return;
  shellEls.bell.querySelector('.badge-dot')?.remove();
  if (state.notifications.unread) shellEls.bell.append(h('span', { class: 'badge-dot' }, state.notifications.unread));
}
async function refreshNotifs() {
  if (!state.user) { state.notifications = { unread: 0, items: [] }; return paintBell(); }
  try { const r = await api.get('/api/notifications'); state.notifications = { unread: r.unread, items: r.notifications }; } catch { /* non-critical */ }
  paintBell();
}
let dropEl = null;
async function toggleNotifs() {
  if (dropEl) { dropEl.remove(); dropEl = null; return; }
  if (!state.user) { toast('Sign in to see alerts', ''); return navigate('/login'); }
  await refreshNotifs();
  const items = state.notifications.items;
  dropEl = h('div', { class: 'drop', role: 'dialog', 'aria-label': 'Notifications' },
    h('div', { class: 'row spread', style: { padding: '6px 8px' } }, h('b', {}, 'Notifications'),
      h('button', { class: 'btn sm ghost', onclick: async () => { await api.post('/api/notifications/read'); await refreshNotifs(); toggleNotifs(); } }, 'Mark all read')),
    items.length ? items.slice(0, 8).map((n) => h('div', { class: `notif ${n.is_read ? '' : 'unread'}` }, h('div', {}, h('b', {}, n.title), h('span', { class: 'small muted' }, n.body))))
      : h('div', { class: 'state', style: { padding: '24px' } }, h('p', { class: 'muted', style: { margin: 0 } }, 'No alerts yet. Create rules on the Alerts page.')),
    h('a', { href: '#/alerts', class: 'btn sm', style: { margin: '6px 8px' }, onclick: () => { dropEl?.remove(); dropEl = null; } }, 'Manage alerts'));
  shellEls.userBox.parentElement.append(dropEl);
  dropEl.style.right = '28px'; dropEl.style.top = '58px'; dropEl.style.position = 'fixed';
}
async function logout() { await api.post('/api/auth/logout'); state.user = null; document.dispatchEvent(new Event('userchange')); toast('Signed out', 'ok'); navigate('/'); }

let token = 0;
async function render() {
  const my = ++token;
  const path = location.hash.slice(1).split('?')[0] || '/';
  const query = Object.fromEntries(new URLSearchParams(location.hash.split('?')[1] || ''));
  const found = match(path) || { cfg: { mod: 'notfound', title: 'Not found' }, params: {} };
  const { cfg, params } = found;
  if (cfg.auth && !state.user) { toast('Please sign in to continue'); return navigate('/login?next=' + encodeURIComponent(path)); }
  if (cfg.auth === 'admin' && state.user?.role !== 'admin') { toast('Administrator access required', 'err'); return navigate('/dashboard'); }
  document.title = `${cfg.title ? cfg.title + ' · ' : ''}TerraWatt`;
  document.dispatchEvent(new Event('route'));
  let target;
  if (cfg.shell === false) { shellEls = null; target = clear(root); }
  else { if (!shellEls || !root.contains(shellEls.shell)) { clear(root).append(buildShell().shell); } target = clear(shellEls.content); paintNav(); }
  target.append(h('div', { class: 'page' }, h('div', { class: 'skeleton', style: { height: '320px' } })));
  try {
    const mod = await import(`./pages/${cfg.mod}.js`);
    const node = await mod.default({ params, query, props: cfg.props || {}, navigate });
    if (my !== token) return;
    clear(target); target.append(node); window.scrollTo({ top: 0 });
    document.getElementById('main')?.focus?.();
  } catch (e) {
    console.error(e);
    if (my !== token) return;
    clear(target).append(h('div', { class: 'page' }, errorState(e, render)));
  }
}

async function boot() {
  try {
    const [meta, me] = await Promise.all([api.get('/api/meta', { cache: true }), api.get('/api/auth/me')]);
    state.meta = meta; state.user = me.user;
  } catch (e) {
    clear(root).append(h('div', { class: 'page' }, errorState(e, () => location.reload()))); return;
  }
  refreshNotifs();
  window.addEventListener('hashchange', () => { render(); });
  document.addEventListener('userchange', () => { paintUser(); paintNav(); refreshNotifs(); });
  render();
}
export { refreshNotifs };
boot();
