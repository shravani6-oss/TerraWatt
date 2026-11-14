import { api } from '../api.js';
import { h, logoMark, toast, clear } from '../ui.js';
import { state } from '../state.js';
import { navigate } from '../main.js';

export default async function auth({ props, query }) {
  const register = props.mode === 'register';
  const err = h('div', { class: 'err', role: 'alert' });
  const fields = {};
  const field = (name, label, attrs = {}) => {
    const input = h('input', { class: 'input', name, id: name, required: true, ...attrs });
    const msg = h('span', { class: 'err' });
    fields[name] = { input, msg };
    return h('label', { class: 'field', for: name }, label, input, msg);
  };
  const submit = h('button', { class: 'btn primary lg', type: 'submit', style: { justifyContent: 'center' } }, register ? 'Create account' : 'Sign in');
  const form = h('form', { novalidate: true, onsubmit: async (e) => {
    e.preventDefault(); err.textContent = ''; Object.values(fields).forEach((f) => { f.msg.textContent = ''; f.input.classList.remove('invalid'); });
    submit.disabled = true;
    try {
      const body = Object.fromEntries(Object.entries(fields).map(([k, f]) => [k, f.input.value]));
      if (register && !body.home_country) delete body.home_country;
      const r = await api.post(register ? '/api/auth/register' : '/api/auth/login', body);
      state.user = r.user; document.dispatchEvent(new Event('userchange'));
      toast(register ? `Welcome, ${r.user.name.split(' ')[0]}!` : 'Welcome back', 'ok');
      navigate(query.next ? decodeURIComponent(query.next) : '/dashboard');
    } catch (ex) {
      if (ex.details) ex.details.forEach((d) => { const f = fields[d.field]; if (f) { f.msg.textContent = d.message.replace('Value error, ', ''); f.input.classList.add('invalid'); } });
      else err.textContent = ex.message;
      if (ex.details && !ex.details.some((d) => fields[d.field])) err.textContent = ex.message;
    } finally { submit.disabled = false; }
  } },
    h('h1', { style: { fontSize: '34px' } }, register ? 'Create your account' : 'Welcome back'),
    h('p', { class: 'muted', style: { margin: 0 } }, register ? 'Save footprints, watch countries and set alerts.' : 'Sign in to your TerraWatt workspace.'),
    register && field('name', 'Name', { autocomplete: 'name', minlength: 2 }),
    field('email', 'Email', { type: 'email', autocomplete: 'email' }),
    field('password', 'Password', { type: 'password', autocomplete: register ? 'new-password' : 'current-password' }),
    register && h('p', { class: 'hint', style: { margin: '-8px 0 0' } }, 'At least 8 characters with a letter and a digit.'),
    err, submit,
    h('p', { class: 'muted small', style: { margin: 0, textAlign: 'center' } }, register ? 'Already have an account? ' : 'New here? ',
      h('a', { href: register ? '#/login' : '#/register' }, register ? 'Sign in' : 'Create an account')));
  return h('div', { class: 'auth' },
    h('div', { class: 'art' }, h('a', { class: 'brand', href: '#/', style: { color: '#fff', padding: 0 } }, logoMark(), 'TerraWatt'),
      h('div', {}, h('h2', {}, 'Track the transition. Cut your own footprint.'), h('p', { style: { opacity: .85, maxWidth: '38ch' } }, 'Twenty years of renewable-energy data, forecasts with their error on display, and a carbon tracker built on your grid.')),
      h('small', { style: { opacity: .7 } }, 'Historical open data · no tracking · passwords hashed with scrypt')),
    h('div', { class: 'formside' }, form));
}
