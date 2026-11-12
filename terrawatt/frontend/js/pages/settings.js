import { api } from '../api.js';
import { h, toast, clear, confirmBox } from '../ui.js';
import { pageHead, countryPicker } from '../components.js';
import { state } from '../state.js';
import { navigate } from '../main.js';

export default async function settings() {
  const u = state.user; let home = u.home_country || '';
  const name = h('input', { class: 'input', value: u.name, minlength: 2, maxlength: 60, id: 'name' });
  const pick = h('div', {}); const paint = () => clear(pick).append(countryPicker({ placeholder: home || 'Choose home country', value: home, clearOnPick: false, onPick: (c) => { home = c; } }));
  paint();
  const msgs = (e) => e.details?.map((d) => d.message.replace('Value error, ', '')).join(' ') || e.message;
  const cur = h('input', { class: 'input', type: 'password', autocomplete: 'current-password', id: 'cur' }), nw = h('input', { class: 'input', type: 'password', autocomplete: 'new-password', id: 'new' });
  return h('div', { class: 'page stack', style: { gap: '20px', maxWidth: '760px' } }, pageHead('Settings', u.email),
    h('form', { class: 'card stack', onsubmit: async (e) => { e.preventDefault(); try { const r = await api.patch('/api/users/me', { name: name.value, home_country: home || null }); state.user = r.user; document.dispatchEvent(new Event('userchange')); toast('Profile saved', 'ok'); } catch (ex) { toast(msgs(ex), 'err'); } } },
      h('h3', {}, 'Profile'), h('label', { class: 'field', for: 'name' }, 'Name', name), h('label', { class: 'field' }, 'Home country (default for the carbon calculator)', pick), h('div', {}, h('button', { class: 'btn primary', type: 'submit' }, 'Save profile'))),
    h('form', { class: 'card stack', onsubmit: async (e) => { e.preventDefault(); try { await api.put('/api/auth/password', { current_password: cur.value, new_password: nw.value }); cur.value = nw.value = ''; toast('Password updated', 'ok'); } catch (ex) { toast(msgs(ex), 'err'); } } },
      h('h3', {}, 'Change password'), h('label', { class: 'field', for: 'cur' }, 'Current password', cur), h('label', { class: 'field', for: 'new' }, 'New password', nw), h('p', { class: 'hint', style: { margin: 0 } }, 'At least 8 characters, with a letter and a digit.'), h('div', {}, h('button', { class: 'btn primary', type: 'submit' }, 'Update password'))),
    h('div', { class: 'card stack' }, h('h3', {}, 'Danger zone'), h('p', { class: 'muted', style: { margin: 0 } }, 'Deleting your account permanently removes your footprint history, watchlist, rules and notifications.'),
      h('div', {}, h('button', { class: 'btn danger', onclick: async () => { if (await confirmBox('Delete account?', 'This cannot be undone.', 'Delete account')) { await api.del('/api/users/me'); state.user = null; document.dispatchEvent(new Event('userchange')); toast('Account deleted', 'ok'); navigate('/'); } } }, 'Delete my account'))));
}
