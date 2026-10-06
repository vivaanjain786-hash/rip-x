/* RIP-X dashboard: plain SVG charts over the Python engine's JSON API. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const COLORS = { rip: '#f59e0b', ripx: '#06b6d4' };
  const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

  async function api(path, body) {
    const res = await fetch(path, body === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function busy(button, errEl, task) {
    button.disabled = true; errEl.textContent = '';
    try { await task(); } catch (e) { errEl.textContent = e.message; }
    button.disabled = false;
  }

  // ---- charts ------------------------------------------------------------
  function lineChart(title, series, events) {
    const W = 520, H = 220, L = 46, R = 10, T = 8, B = 24;
    const xs = series.rip.map(p => p.x);
    const xMax = Math.max(...xs, 1);
    const yMax = Math.max(1, ...['rip', 'ripx'].flatMap(k => series[k].map(p => p.y)));
    const x = v => L + (v / xMax) * (W - L - R);
    const y = v => H - B - (v / yMax) * (H - T - B);
    let g = '';
    for (let i = 0; i <= 4; i++) {
      const v = (yMax * i) / 4;
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(148,163,184,.15)"/>` +
           `<text x="${L - 6}" y="${y(v) + 4}" fill="#94a3b8" font-size="10" text-anchor="end">${fmt(v)}</text>`;
    }
    Object.entries(events).forEach(([round, name]) => {
      g += `<line x1="${x(round)}" x2="${x(round)}" y1="${T}" y2="${H - B}" stroke="rgba(148,163,184,.35)" stroke-dasharray="2 4"/>` +
           `<text x="${x(round) + 3}" y="${T + 10}" fill="#64748b" font-size="9">${name.replace('_', ' ')}</text>`;
    });
    ['rip', 'ripx'].forEach(k => {
      const d = series[k].map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join('');
      g += `<path d="${d}" fill="none" stroke="${COLORS[k]}" stroke-width="1.8"/>`;
    });
    g += `<text x="${(L + W) / 2}" y="${H - 6}" fill="#94a3b8" font-size="10" text-anchor="middle">round</text>`;
    return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 ${W} ${H}">${g}</svg></div>`;
  }

  function barChart(title, items, max) {
    const W = 520, H = 200, L = 60, B = 34, T = 14, gap = 40;
    const bw = (W - L - 20 - gap * (items.length - 1)) / items.length;
    const top = max || Math.max(...items.map(i => i.value), 1);
    let g = '';
    items.forEach((it, i) => {
      const x = L + i * (bw + gap), h = (it.value / top) * (H - T - B);
      g += `<rect x="${x}" y="${H - B - h}" width="${bw}" height="${h}" fill="${it.color}" rx="3"/>` +
           `<text x="${x + bw / 2}" y="${H - B - h - 5}" fill="#f1f5f9" font-size="12" text-anchor="middle">${it.label}</text>` +
           `<text x="${x + bw / 2}" y="${H - 14}" fill="#94a3b8" font-size="11" text-anchor="middle">${it.name}</text>`;
    });
    return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 ${W} ${H}">${g}</svg></div>`;
  }

  const card = (k, v, d, cls) =>
    `<div class="card"><div class="k">${k}</div><div class="v">${v}</div><div class="d ${cls || 'flat'}">${d || ''}</div></div>`;

  // ---- 1. comparison -------------------------------------------------------
  function convergenceRounds(run, start, end) {
    // Rounds after the event until every routing table is correct again.
    const window = run.series.slice(start, end);
    let last = -1;
    window.forEach((p, i) => { if (p.incorrect > 0) last = i; });
    return last === window.length - 1 && window.length ? null : last + 1;
  }

  function showComparison(data) {
    const { rip, ripx } = data.runs;
    const t = data.timeline;
    const events = data.events;
    const bounds = [t.link_failure, t.link_recovery, t.router_failure, t.router_recovery, t.horizon];
    const conv = run => bounds.slice(0, 4).map((s, i) => convergenceRounds(run, s, bounds[i + 1]));
    const cr = conv(rip), cx = conv(ripx);
    const msgs = [rip, ripx].map(r => r.series[r.series.length - 1].messages);
    const black = [rip, ripx].map(r => r.blackhole_pair_rounds);
    const saved = 100 * (1 - msgs[1] / msgs[0]);
    const label = c => (c === null ? 'not converged' : `${c} rounds`);
    $('cmpCards').innerHTML =
      card('Control messages', `${fmt(msgs[0])} → ${fmt(msgs[1])}`, `RIP-X sent ${fmt(Math.abs(saved), 0)}% ${saved >= 0 ? 'fewer' : 'more'}`, saved > 0 ? 'good' : 'bad') +
      card('Link failure repaired in', `${label(cr[0])} → ${label(cx[0])}`, 'standard RIP → RIP-X') +
      card('Router failure repaired in', `${label(cr[2])} → ${label(cx[2])}`, 'standard RIP → RIP-X') +
      card('Black-holed pair-rounds', `${fmt(black[0])} → ${fmt(black[1])}`, black[1] > black[0] ? 'RIP-X drops more traffic while repairing' : 'RIP-X drops no more traffic', black[1] > black[0] ? 'bad' : 'good') +
      card('Looping pair-rounds', `${fmt(rip.loop_pair_rounds)} → ${fmt(ripx.loop_pair_rounds)}`, '', ripx.loop_pair_rounds <= rip.loop_pair_rounds ? 'good' : 'bad') +
      card('Route changes', `${fmt(rip.route_changes)} → ${fmt(ripx.route_changes)}`, 'routing churn');
    const pick = f => ({ rip: rip.series.map(p => ({ x: p.round, y: f(p) })), ripx: ripx.series.map(p => ({ x: p.round, y: f(p) })) });
    $('cmpCharts').innerHTML =
      lineChart('Cumulative control messages', pick(p => p.messages), events) +
      lineChart('Routers with a wrong route entry (per round)', pick(p => p.incorrect), events) +
      lineChart('Black-holed source/destination pairs (per round)', pick(p => p.blackhole), events) +
      lineChart('Looping source/destination pairs (per round)', pick(p => p.loop), events);
  }

  $('cmpGo').onclick = () => busy($('cmpGo'), $('cmpErr'), async () => {
    showComparison(await api('/api/compare', { routers: +$('cmpRouters').value, seed: +$('cmpSeed').value }));
  });

  // ---- 2. traffic engineering ---------------------------------------------
  $('teGo').onclick = () => busy($('teGo'), $('teErr'), async () => {
    const t = await api('/api/demo/traffic', { seed: +$('teSeed').value });
    const r = t.rip, x = t.ripx;
    $('teCards').innerHTML =
      card('Delivered / offered traffic', `${fmt(100 * r.delivered_ratio, 1)}% → ${fmt(100 * x.delivered_ratio, 1)}%`, x.delivered_ratio >= r.delivered_ratio ? 'RIP-X delivers more' : 'RIP-X delivers less', x.delivered_ratio >= r.delivered_ratio ? 'good' : 'bad') +
      card('Peak link utilization', `${fmt(r.maximum_utilization, 2)} → ${fmt(x.maximum_utilization, 2)}`, '1.00 = link full', x.maximum_utilization <= r.maximum_utilization ? 'good' : 'bad') +
      card('Mean path length', `${fmt(r.mean_path_hops, 2)} → ${fmt(x.mean_path_hops, 2)} hops`, 'longer detours are the price') +
      card('Extra control messages', fmt(x.te_control_messages), `${x.epochs_run} epochs, best = epoch ${x.selected_epoch}`);
    $('teTable').hidden = false;
    $('teTable').querySelector('tbody').innerHTML = x.epochs.map(e =>
      `<tr><td>${e.epoch}${e.epoch === x.selected_epoch ? ' ✓ chosen' : ''}</td><td class="num">${fmt(e.delivered_mbps, 1)}</td>` +
      `<td class="num">${fmt(e.maximum_utilization, 2)}</td><td>${e.raised_links.join(', ') || '–'}</td><td class="num">${e.control_messages}</td></tr>`).join('');
  });

  // ---- 3. benchmark ----------------------------------------------------------
  const ci = s => `${fmt(s.mean, 1)} <span class="flat">[${fmt(s.ci95_low, 1)}, ${fmt(s.ci95_high, 1)}]</span>`;
  const delta = (s, lowerIsBetter = true) => {
    if (!s) return '';
    const cls = s.ci95_low > 0 || s.ci95_high < 0 ? ((s.mean < 0) === lowerIsBetter ? 'good' : 'bad') : 'flat';
    return `<span class="${cls}">${s.mean > 0 ? '+' : ''}${fmt(s.mean, 1)} <span class="flat">[${fmt(s.ci95_low, 1)}, ${fmt(s.ci95_high, 1)}]</span></span>`;
  };

  function showBenchmark(b) {
    if (!b.source) { $('bmBody').innerHTML = '<p class="note">No saved benchmark yet. Run one above.</p>'; return; }
    const u = b.update_control;
    const rows = [
      ['control_messages', 'Control messages (whole run)'], ['stable_control_messages', 'Control messages (stable period)'],
      ['link_failure_convergence_rounds', 'Convergence after link failure (rounds)'], ['router_failure_convergence_rounds', 'Convergence after router failure (rounds)'],
      ['blackhole_pair_rounds', 'Black-holed pair-rounds'], ['loop_pair_rounds', 'Looping pair-rounds'], ['route_changes', 'Route changes']
    ];
    const names = Object.keys(u);
    let html = `<p class="note">${b.seeds} seeds, from the ${b.source}. Cells: mean [95% CI]. Δ = paired difference against standard RIP (green = better, red = worse, grey = not distinguishable from noise).</p>` +
      `<div style="overflow-x:auto"><table><thead><tr><th>Metric</th>${names.map(n => `<th>${n}</th>`).join('')}${names.slice(1).map(n => `<th>Δ ${n}</th>`).join('')}</tr></thead><tbody>` +
      rows.map(([k, l]) => `<tr><td>${l}</td>${names.map(n => `<td class="num">${ci(u[n][k])}</td>`).join('')}` +
        `${names.slice(1).map(n => `<td class="num">${delta(u[n][k].paired_difference_vs_rip)}</td>`).join('')}</tr>`).join('') + '</tbody></table></div>';
    const t = b.traffic_engineering;
    html += `<h3 style="margin:16px 0 6px;font-size:14px">Traffic engineering</h3><table><thead><tr><th>Metric</th><th>rip</th><th>ripx</th><th>Δ ripx</th></tr></thead><tbody>` +
      [['delivered_ratio', 'Delivered / offered', 3, false], ['maximum_utilization', 'Peak link utilization', 2, true], ['mean_path_hops', 'Mean path length (hops)', 2, true]].map(([k, l, d, lower]) =>
        `<tr><td>${l}</td><td class="num">${fmt(t.rip[k].mean, d)}</td><td class="num">${fmt(t.ripx[k].mean, d)}</td>` +
        `<td class="num">${delta(t.ripx[k].paired_difference_vs_rip, lower)}</td></tr>`).join('') +
      `</tbody></table><p class="note">RIP-X delivered more traffic in ${t.ripx.trials_improved} trials and less in ${t.ripx.trials_worse}.</p>`;
    $('bmBody').innerHTML = html;
  }

  async function pollBenchmark() {
    const s = await api('/api/benchmark/status');
    if (s.state === 'running') { $('bmStatus').textContent = `Running ${s.seeds} seeds…`; setTimeout(pollBenchmark, 1500); return; }
    $('bmGo').disabled = false;
    $('bmStatus').textContent = s.state === 'error' ? `Failed: ${s.error}` : (s.state === 'done' ? 'Finished.' : '');
    showBenchmark(await api('/api/benchmark/latest'));
  }

  $('bmGo').onclick = async () => {
    $('bmGo').disabled = true;
    try {
      await api('/api/benchmark/run', { seeds: +$('bmSeeds').value });
      pollBenchmark();
    } catch (e) { $('bmStatus').textContent = e.message; $('bmGo').disabled = false; }
  };

  // ---- start -----------------------------------------------------------------
  (async function init() {
    try {
      const h = await api('/api/health');
      $('engine').textContent = `· engine: ${h.engine}`;
    } catch (e) {
      $('engine').textContent = '· engine not running: start it with python run_live_simulator.py';
      document.querySelectorAll('button.go').forEach(b => { b.disabled = true; });
      return;
    }
    showBenchmark(await api('/api/benchmark/latest'));
    const s = await api('/api/benchmark/status');
    if (s.state === 'running') { $('bmGo').disabled = true; pollBenchmark(); }
    $('cmpGo').click();
  })();
})();
