import { api } from '../api.js';
import { h, icon, logoMark, fmt, compact, load } from '../ui.js';
import { heroDots } from '../map.js';
import { state } from '../state.js';

const FEATURES = [
  ['globe', 'Atlas of 176 countries', 'Every country plotted at its true coordinates. Switch metrics, scrub years, click through to a full country profile.'],
  ['trend', 'Backtested forecasts', 'Projections to 2030 with 80% intervals, chosen by a rolling-origin backtest across all countries, with the error shown.'],
  ['flask', 'What-if lab', 'Change GDP, electricity access or fossil generation and see how a trained model re-estimates renewable share.'],
  ['leaf', 'Carbon tracker', 'Log monthly energy use and get CO₂e using your country\'s estimated grid mix, plus ranked ways to cut it.'],
  ['bell', 'Smart alerts', 'Watch countries and get notified when an indicator crosses a threshold or a forecast slips below a target.'],
  ['download', 'Reports & exports', 'One-click PDF country reports and CSV exports of any ranking, country or your own footprint history.'],
];

export default async function landing() {
  const page = h('div', {});
  const [ov, map] = await Promise.all([api.get('/api/overview', { cache: true }), api.get(`/api/map?metric=renewable_share&year=${state.meta.headline_year}`, { cache: true })]);
  const k = ov.kpis, prov = state.meta.provenance;
  const themeBtn = h('button', { class: 'icon-btn', 'aria-label': 'Toggle dark mode', onclick: () => { document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; try { localStorage.setItem('tw-theme', document.documentElement.dataset.theme); } catch {} } }, icon('moon'));
  page.append(
    h('header', { class: 'nav-top' },
      h('a', { class: 'brand', href: '#/', style: { padding: 0 } }, logoMark(), 'TerraWatt'),
      h('nav', { class: 'links', 'aria-label': 'Landing' }, h('a', { href: '#/dashboard' }, 'Explore'), h('a', { href: '#/carbon' }, 'Carbon calculator'), h('a', { href: '#/models' }, 'Model lab'), h('a', { href: '#how' }, 'How it works')),
      h('div', { class: 'row' }, themeBtn, state.user ? h('a', { class: 'btn primary', href: '#/dashboard' }, 'Open app') : [h('a', { class: 'btn ghost', href: '#/login' }, 'Sign in'), h('a', { class: 'btn primary', href: '#/register' }, 'Get started')])),
    h('section', { class: 'hero' },
      heroDots(map.points.map((p) => ({ lat: p.lat, lon: p.lon, value: p.value }))),
      h('div', { class: 'copy' },
        h('span', { class: 'eyebrow' }, icon('bolt').cloneNode(true), ' Renewable energy intelligence'),
        h('h1', {}, 'See the energy transition ', h('em', {}, 'before'), ' it happens.'),
        h('p', { class: 'lead' }, `Twenty years of real data for ${prov.countries} countries, honest forecasts to 2030, and a carbon tracker that uses your own grid. Built on open data, with every model's error on display.`),
        h('div', { class: 'row wrap', style: { marginTop: '28px' } },
          h('a', { class: 'btn primary lg', href: '#/dashboard' }, 'Explore the data', icon('arrow')),
          h('a', { class: 'btn lg', href: '#/carbon' }, 'Calculate my footprint')),
        h('p', { class: 'hint', style: { marginTop: '18px' } }, 'No sign-up needed to explore. Create a free account to save footprints, watch countries and set alerts.'))),
    h('div', { class: 'stats-band' },
      stat(fmt(k.global_renewable_electricity_share, 1) + '%', `of world electricity was renewable in ${ov.year}`),
      stat(compact(k.renewable_twh) + ' TWh', 'renewable electricity generated'),
      stat(String(prov.countries), `countries, ${prov.years[0]}–${prov.years[1]}`),
      stat(fmt(k.avg_electricity_access, 0) + '%', 'average access to electricity')),
    h('section', { class: 'section' }, h('h2', {}, 'Everything a transition analyst needs, none of the noise.'),
      h('div', { class: 'grid g3', style: { marginTop: '36px' } }, FEATURES.map(([ic, t, d]) => h('div', { class: 'feature card' }, h('div', { class: 'ic' }, icon(ic)), h('h3', {}, t), h('p', { class: 'muted', style: { margin: 0 } }, d))))),
    h('section', { class: 'section', id: 'how', style: { background: 'var(--surface)', borderBlock: '1px solid var(--line)' } },
      h('h2', {}, 'Honest by design.'),
      h('div', { class: 'grid g3', style: { marginTop: '32px' } },
        h('div', {}, h('h3', {}, '1 · Real data, labelled'), h('p', { class: 'muted' }, `Figures come from the Kaggle “Global Data on Sustainable Energy” table (World Bank / IEA-derived). It is historical, not live: the renewable-share series ends in ${ov.year}. Derived metrics are marked with a tilde.`)),
        h('div', {}, h('h3', {}, '2 · Forecasts you can audit'), h('p', { class: 'muted' }, 'Methods compete in a rolling-origin backtest over every country. We show which one won, how much it beats “no change”, and whether its 80% intervals really cover 80%.')),
        h('div', {}, h('h3', {}, '3 · No black-box claims'), h('p', { class: 'muted' }, 'The what-if lab reports held-out error, feature importance and a reminder that associations are not causal effects. Nothing is faked or simulated.')))),
    h('section', { class: 'section', style: { textAlign: 'center' } }, h('h2', { style: { margin: '0 auto' } }, 'Start with your country.'),
      h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '24px' } }, h('a', { class: 'btn primary lg', href: '#/atlas' }, 'Open the atlas'))),
    h('footer', { class: 'footer row spread wrap' }, h('span', {}, '© TerraWatt · Open data: ', h('a', { href: prov.url, target: '_blank', rel: 'noopener' }, 'Kaggle dataset')), h('span', {}, 'Historical data · forecasts are model output, not guarantees')));
  return page;
}
const stat = (b, s) => h('div', {}, h('b', { class: 'tnum' }, b), h('span', {}, s));
