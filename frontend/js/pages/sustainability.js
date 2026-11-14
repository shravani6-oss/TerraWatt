import { api } from '../api.js';
import { h, fmt, clear, toast, confirmBox, emptyState, icon, signed } from '../ui.js';
import { lineChart } from '../charts.js';
import { pageHead, kpi, seg, tip } from '../components.js';

const BADGE_ICON = { green_beginner: 'leaf', eco_warrior: 'bolt', consistent_saver: 'check', planet_protector: 'globe' };

export default async function sustainability() {
  const root = h('div', { class: 'page stack', style: { gap: '20px' } });
  async function refresh() {
    const [prog, ents] = await Promise.all([api.get('/api/goals/progress'), api.get('/api/footprint/entries')]);
    clear(root).append(pageHead('My Sustainability', 'Set a monthly reduction target, track it against a baseline month and earn badges. Progress only counts months that are comparable with your baseline.',
      prog.goal ? h('a', { class: 'btn primary', href: '#/carbon' }, icon('plus'), 'Log this month') : null), view(prog, ents.entries));
  }
  function view(prog, entries) {
    if (!entries.length) return h('div', { class: 'stack' }, h('div', { class: 'card' }, emptyState('Start with your baseline month', 'Calculate and save one month of your household footprint. That month becomes the baseline your goal is measured against.', h('a', { class: 'btn primary', href: '#/carbon' }, 'Open the carbon calculator'))), badges(prog.badges));
    return h('div', { class: 'stack', style: { gap: '20px' } }, prog.goal ? dashboard(prog) : goalForm(entries), prog.goal ? null : null, badges(prog.badges), prog.goal ? recs(prog) : null);
  }

  /* ---------- goal setup */
  function goalForm(entries, existing) {
    const S = { kind: 'percent', percent: 10, custom: '', kg: '', baseline: entries[0].period };
    const preview = h('div', { class: 'callout green' });
    const entryOf = () => entries.find((e) => e.period === S.baseline);
    const paint = () => {
      const base = entryOf().co2_kg;
      const pct = S.kind === 'percent' ? (S.percent === 'custom' ? +S.custom : S.percent) : null;
      const target = S.kind === 'percent' ? (pct > 0 && pct <= 90 ? base * (1 - pct / 100) : null) : (+S.kg > 0 ? +S.kg : null);
      clear(preview).append(target == null ? 'Choose a reduction to see your target.' : target >= base ? h('span', {}, 'The goal must be below your baseline of ', h('b', {}, fmt(base, 0) + ' kg'), '.') :
        h('span', {}, 'Baseline ', h('b', {}, fmt(base, 0) + ' kg CO₂e'), ' → target ', h('b', {}, fmt(target, 0) + ' kg'), ` per month (${fmt(((base - target) / base) * 100, 1)}% lower, ${fmt(base - target, 0)} kg less).`));
      go.disabled = target == null || target >= base;
    };
    const custom = h('input', { class: 'input', type: 'number', min: 1, max: 90, placeholder: '%', 'aria-label': 'Custom percentage', style: { maxWidth: '100px' }, oninput: (e) => { S.custom = e.target.value; S.percent = 'custom'; drawSeg(); paint(); } });
    const kg = h('input', { class: 'input', type: 'number', min: 1, placeholder: 'kg CO₂e per month', 'aria-label': 'Monthly goal in kg', style: { maxWidth: '220px' }, oninput: (e) => { S.kg = e.target.value; paint(); } });
    const segBox = h('div', {}), pctRow = h('div', { class: 'row wrap' }), kgRow = h('div', {});
    const drawSeg = () => { clear(segBox).append(seg([['percent', 'Reduce by a percentage'], ['absolute', 'Set a kg goal']], S.kind, (k) => { S.kind = k; drawSeg(); paint(); }));
      clear(pctRow).append(...(S.kind === 'percent' ? [seg([[5, '5%'], [10, '10%'], [20, '20%'], ['custom', 'Custom']], S.percent, (v) => { S.percent = v; drawSeg(); paint(); }), S.percent === 'custom' ? custom : null] : []));
      clear(kgRow).append(...(S.kind === 'absolute' ? [kg] : [])); };
    const go = h('button', { class: 'btn primary', onclick: async () => {
      try {
        const body = { kind: S.kind, baseline_period: S.baseline };
        if (S.kind === 'percent') body.percent = S.percent === 'custom' ? +S.custom : S.percent; else body.target_kg = +S.kg;
        const r = await api.post('/api/goals', body);
        toast('Goal set. Log your next month to start tracking.', 'ok');
        (r.new_badges || []).forEach((b) => toast(`🏅 Badge unlocked: ${b.name}`, 'ok'));
        refresh();
      } catch (e) { toast(e.message, 'err'); }
    } }, 'Set my goal');
    drawSeg(); paint();
    return h('div', { class: 'card stack' }, h('h3', {}, existing ? 'Change your goal' : 'Set your monthly goal'),
      h('p', { class: 'sub', style: { margin: 0 } }, 'Pick the month you want to improve on, then how much lower you want each later month to be.'),
      h('label', { class: 'field', style: { maxWidth: '360px' } }, h('span', {}, 'Baseline month', tip('Progress is measured against this saved month. Only later months recorded with the same calculator mode, country and household size are compared with it.')),
        h('select', { class: 'input', onchange: (e) => { S.baseline = e.target.value; paint(); } }, entries.map((e) => h('option', { value: e.period }, `${e.period} · ${fmt(e.co2_kg, 0)} kg CO₂e (${e.mode}, ${e.household_size} people)`)))),
      segBox, pctRow, kgRow, preview, h('div', { class: 'row' }, go, existing ? h('button', { class: 'btn ghost', onclick: refresh }, 'Cancel') : null));
  }

  /* ---------- dashboard */
  function dashboard(prog) {
    const g = prog.goal, d = prog.dashboard;
    const head = h('div', { class: 'row wrap spread' }, h('div', {}, h('b', {}, g.kind === 'percent' ? `${g.percent}% lower than ${g.baseline_period}` : `Stay under ${fmt(g.target_kg, 0)} kg a month`),
      h('div', { class: 'small muted' }, `Baseline ${g.baseline_period} · ${g.mode} mode · ${g.country} · ${g.household_size} ${g.household_size === 1 ? 'person' : 'people'}${g.first_achieved_at ? ` · first achieved ${g.first_achieved_period} (${g.first_achieved_at.slice(0, 10)})` : ''}`)),
      h('div', { class: 'row' }, h('button', { class: 'btn sm', onclick: async () => { const e = (await api.get('/api/footprint/entries')).entries; clear(slot).append(goalForm(e, true)); } }, 'Change goal'),
        h('button', { class: 'btn sm ghost danger', onclick: async () => { if (await confirmBox('End this goal?', 'Your badges and history are kept.', 'End goal')) { await api.del('/api/goals/active'); refresh(); } } }, 'End goal')));
    const slot = h('div', {});
    if (!d) return h('div', { class: 'stack' }, h('div', { class: 'card stack' }, head, emptyState('No comparable month yet', `Log a footprint for a month after ${g.baseline_period} using the same calculator mode, country and household size.`, h('a', { class: 'btn primary', href: '#/carbon' }, 'Log a month'))), slot, excluded(prog));
    const good = d.reduction_kg >= 0;
    const chartRows = prog.history;
    return h('div', { class: 'stack', style: { gap: '20px' } },
      h('div', { class: 'card stack' }, head, h('div', { class: 'row spread wrap' }, h('div', {}, h('div', { class: 'small muted' }, `Progress in ${d.period}`), h('div', { style: { font: '600 40px var(--serif)' } }, fmt(d.progress_pct, 0) + '%')),
        h('span', { class: `chip ${d.achieved ? 'green' : 'amber'}` }, d.achieved ? 'Target achieved this month' : `${fmt(d.remaining_kg, 0)} kg to go`)),
        h('div', { class: 'progress', role: 'progressbar', 'aria-valuenow': Math.round(d.progress_pct), 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: { width: Math.min(100, Math.max(0, d.progress_pct)) + '%' } }))),
      slot,
      h('div', { class: 'grid g3 kpi-row' },
        kpi({ label: 'Current month', year: d.period, value: fmt(d.current_kg, 0), unit: 'kg CO₂e' }),
        kpi({ label: 'Baseline', year: g.baseline_period, value: fmt(d.baseline_kg, 0), unit: 'kg CO₂e' }),
        kpi({ label: 'Target', value: fmt(d.target_kg, 0), unit: 'kg CO₂e' }),
        kpi({ label: 'Reduction achieved', value: signed(d.reduction_kg, 0), unit: 'kg', hint: `${signed(d.reduction_pct, 1)}% vs baseline` }),
        kpi({ label: 'Remaining to target', value: fmt(d.remaining_kg, 0), unit: 'kg', hint: d.remaining_kg === 0 ? 'Target met' : 'still to cut this month' }),
        kpi({ label: 'Months on target', value: `${d.months_achieved}/${d.months_tracked}`, hint: 'comparable months so far' })),
      h('div', { class: 'card' }, h('h3', {}, 'Monthly history'), h('p', { class: 'sub' }, 'kg CO₂e per month, recomputed with the current emission factors'),
        chartRows.length > 1 ? h('div', { style: { marginTop: '10px' } }, lineChart({ series: [
          { name: 'Footprint', color: 'var(--c1)', points: [{ x: 0, y: d.baseline_kg }, ...chartRows.map((r, i) => ({ x: i + 1, y: r.footprint_kg }))] },
          { name: 'Target', color: 'var(--c2)', dash: true, points: [{ x: 0, y: d.target_kg }, ...chartRows.map((r, i) => ({ x: i + 1, y: r.target_kg }))] }], unit: 'kg', height: 260, zeroBase: true, xFormat: (v) => (v === 0 ? g.baseline_period : chartRows[v - 1]?.period ?? ''), ariaLabel: 'Monthly footprint versus target' }),
          h('div', { class: 'legend' }, h('span', {}, h('i', { style: { background: 'var(--c1)' } }), 'Footprint (first point = baseline)'), h('span', { style: { color: 'var(--c2)' } }, h('i', { class: 'dash' }), 'Target'))) : h('p', { class: 'muted' }, 'Log another month to see the trend.'),
        h('div', { class: 'table-wrap', style: { marginTop: '12px' } }, h('table', {}, h('thead', {}, h('tr', {}, ['Month', 'kg CO₂e', 'Reduction', 'vs baseline', 'Target'].map((c, i) => h('th', { class: i ? 'r' : '' }, c)))),
          h('tbody', {}, [...chartRows].reverse().map((r) => h('tr', {}, h('td', {}, r.period), h('td', { class: 'r tnum' }, fmt(r.footprint_kg, 0)), h('td', { class: 'r tnum' }, signed(r.reduction_kg, 0) + ' kg'), h('td', { class: 'r tnum' }, signed(r.reduction_pct, 1) + '%'), h('td', { class: 'r' }, h('span', { class: `chip ${r.achieved ? 'green' : ''}` }, r.achieved ? 'achieved' : 'not yet')))))))),
      excluded(prog));
  }
  const excluded = (prog) => prog.excluded.length ? h('details', { class: 'more' }, h('summary', {}, `${prog.excluded.length} saved month${prog.excluded.length > 1 ? 's' : ''} not counted`),
    h('p', { class: 'hint', style: { margin: 0 } }, 'A month only counts if it uses the same calculator mode, country and household size as the baseline, so a change in circumstances is never mistaken for a reduction.'),
    prog.excluded.map((x) => h('div', { class: 'stat-line' }, h('span', {}, x.period), h('span', { class: 'muted' }, x.reason)))) : null;

  /* ---------- badges + recommendations */
  const badges = (list) => h('div', { class: 'card' }, h('h3', {}, 'Achievements'), h('p', { class: 'sub' }, 'Badges unlock automatically and are never taken away.'),
    h('div', { class: 'badge-grid', style: { marginTop: '12px' } }, list.map((b) => h('div', { class: `badge-card ${b.unlocked ? 'on' : 'locked'}`, 'data-badge': b.key, 'data-unlocked': String(b.unlocked) },
      h('div', { class: 'medal' }, icon(BADGE_ICON[b.key] || 'star')), h('b', {}, b.name), h('span', { class: 'small muted' }, b.how), b.unlocked ? h('span', { class: 'chip green' }, `Unlocked ${b.unlocked_at.slice(0, 10)}`) : h('span', { class: 'chip' }, 'Locked')))));
  const recs = (prog) => prog.recommendations?.length ? h('div', { class: 'card' }, h('h3', {}, 'Personalised suggestions'), h('p', { class: 'sub' }, `Based on where your ${prog.dashboard.period} emissions come from`),
    h('div', { style: { marginTop: '10px' } }, prog.recommendations.map((x) => h('div', { class: 'rec' }, h('div', { class: 'pri medium' }), h('div', {}, h('b', {}, x.title, ' ', h('span', { class: 'chip green' }, `≈ −${fmt(x.saving_kg_month, 0)} kg/month`)), h('p', { class: 'muted', style: { margin: '4px 0 0' } }, x.detail)))))) : null;

  await refresh();
  return root;
}
