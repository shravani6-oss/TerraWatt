import { h } from '../ui.js';
export default async function notfound() {
  return h('div', { class: 'page' }, h('div', { class: 'state' }, h('h1', {}, '404'), h('h4', {}, 'That page does not exist'), h('a', { class: 'btn primary', href: '#/dashboard' }, 'Back to overview')));
}
