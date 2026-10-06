/* RIP-X dashboard: plain SVG charts over the Python engine's JSON API. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const COLORS = { rip: '#ffb547', ripx: '#3de8e0' };
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="grid"/>` +
           `<text x="${L - 6}" y="${y(v) + 4}" fill="#8e96b3" font-size="10" text-anchor="end">${fmt(v)}</text>`;
    }
    Object.entries(events).forEach(([round, name]) => {
      g += `<line x1="${x(round)}" x2="${x(round)}" y1="${T}" y2="${H - B}" stroke="rgba(139,108,255,.55)" stroke-dasharray="2 4"/>` +
           `<text x="${x(round) + 3}" y="${T + 10}" fill="#5d6584" font-size="9">${name.replace('_', ' ')}</text>`;
    });
    ['rip', 'ripx'].forEach(k => {
      const d = series[k].map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join('');
      const last = series[k][series[k].length - 1];
      g += `<path class="area" d="${d}L${x(last.x).toFixed(1)},${y(0)}L${x(0)},${y(0)}Z" fill="${COLORS[k]}" fill-opacity=".07"/>` +
           `<path class="line" pathLength="1" d="${d}" fill="none" stroke="${COLORS[k]}" stroke-width="1.8" stroke-linejoin="round"/>`;
    });
    g += `<text x="${(L + W) / 2}" y="${H - 6}" fill="#8e96b3" font-size="10" text-anchor="middle">round</text>`;
    return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 ${W} ${H}">${g}</svg></div>`;
  }

  function barChart(title, items, max) {
    const W = 520, H = 200, L = 60, B = 34, T = 14, gap = 40;
    const bw = (W - L - 20 - gap * (items.length - 1)) / items.length;
    const top = max || Math.max(...items.map(i => i.value), 1);
    let g = '';
    items.forEach((it, i) => {
      const x = L + i * (bw + gap), h = (it.value / top) * (H - T - B);
      g += `<rect class="bar" x="${x}" y="${H - B - h}" width="${bw}" height="${h}" fill="${it.color}" rx="3"/>` +
           `<text x="${x + bw / 2}" y="${H - B - h - 5}" fill="#e8ebf5" font-size="12" text-anchor="middle">${it.label}</text>` +
           `<text x="${x + bw / 2}" y="${H - 14}" fill="#8e96b3" font-size="11" text-anchor="middle">${it.name}</text>`;
    });
    return `<div class="chart"><h3>${title}</h3><svg viewBox="0 0 ${W} ${H}">${g}</svg></div>`;
  }

  // ---- KPI tiles ---------------------------------------------------------
  // One tile = label, animated before -> after numbers, an arc gauge showing the change, two bars, and a verdict line.
  // `lower` says whether a smaller "after" is the good direction. Values may be null (shown as "n/c").
  const ARC = 'M 25 45 A 20 20 0 1 1 45 25';  // 270-degree arc, drawn with pathLength=1
  let tileCount = 0;
  function kpi({ label, before, after, digits = 0, unit = '', lower = true, note = '', verdict }) {
    const num = Number.isFinite(before) && Number.isFinite(after);
    const better = !num ? null : (lower ? after <= before : after >= before);
    const cls = verdict || (better === null ? 'flat' : (after === before ? 'flat' : (better ? 'good' : 'bad')));
    const top = num ? Math.max(before, after, 1e-9) : 1;
    const change = num && before !== 0 ? (after - before) / Math.abs(before) * 100 : null;
    // gauge: how large RIP-X is relative to the larger of the two values
    const off = num ? (1 - Math.min(1, after / top)).toFixed(3) : 1;
    const centre = change === null ? '–' : `${change > 0 ? '+' : ''}${fmt(change, Math.abs(change) < 10 ? 1 : 0)}%`;
    const spec = v => (Number.isFinite(v) ? `data-to="${v}" data-d="${digits}"` : '');
    const show = v => (Number.isFinite(v) ? fmt(v, digits) : 'n/c');
    return `<div class="card kpi ${cls}" style="--i:${tileCount++}">
      <svg class="gauge" viewBox="0 0 70 70" style="--off:${off}"><path class="track" d="${ARC}" fill="none" stroke-width="5" stroke-linecap="round" pathLength="1"/>` +
      `<path class="arc" d="${ARC}" fill="none" stroke-width="5" stroke-linecap="round" pathLength="1"/><text x="35" y="39">${centre}</text></svg>
      <div class="k">${label}</div>
      <div class="vals"><span class="a" ${spec(before)}>${show(before)}</span><span class="arrow">→</span><span class="b" ${spec(after)}>${show(after)}</span><span class="flat">${unit}</span></div>
      ${num ? `<div class="bars"><i class="ra" style="--w:${(before / top) * 100}%"></i><i class="rb" style="--w:${(after / top) * 100}%"></i></div>` : ''}
      <div class="d">${note}</div></div>`;
  }

  // Animate numbers (count-up), gauges and bars once the tiles are in the DOM.
  function animateKpis(root) {
    tileCount = 0;
    const tiles = [...root.querySelectorAll('.kpi')];
    const place = el => { const to = +el.dataset.to; el.textContent = fmt(to, +el.dataset.d); };
    if (REDUCED) { tiles.forEach(t => { t.classList.add('on'); t.querySelectorAll('[data-to]').forEach(place); t.querySelector('.gauge')?.classList.add('on'); }); return; }
    tiles.forEach((t, i) => setTimeout(() => {
      t.classList.add('on'); t.querySelector('.gauge')?.classList.add('on');
      t.querySelectorAll('[data-to]').forEach(el => {
        const to = +el.dataset.to, d = +el.dataset.d, t0 = performance.now(), dur = 1100;
        (function tick(now) {
          const p = Math.min(1, (now - t0) / dur), eased = 1 - Math.pow(1 - p, 4);
          el.textContent = fmt(to * eased, d);
          if (p < 1) requestAnimationFrame(tick);
        })(t0);
      });
    }, i * 70));
  }

  // Hover spotlight: one delegated listener, throttled to animation frames.
  if (!REDUCED) {
    let frame = 0;
    document.addEventListener('pointermove', ev => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const tile = ev.target.closest?.('.kpi');
        if (!tile) return;
        const r = tile.getBoundingClientRect();
        tile.style.setProperty('--mx', `${((ev.clientX - r.left) / r.width * 100).toFixed(1)}%`);
        tile.style.setProperty('--my', `${((ev.clientY - r.top) / r.height * 100).toFixed(1)}%`);
      });
    }, { passive: true });
  }

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
    $('cmpCards').innerHTML = [
      kpi({ label: 'Control messages', before: msgs[0], after: msgs[1], note: `RIP-X sent ${fmt(Math.abs(saved), 0)}% ${saved >= 0 ? 'fewer' : 'more'}` }),
      kpi({ label: 'Link failure repaired in', before: cr[0], after: cx[0], unit: 'rounds', note: 'standard RIP → RIP-X' }),
      kpi({ label: 'Router failure repaired in', before: cr[2], after: cx[2], unit: 'rounds', note: 'standard RIP → RIP-X' }),
      kpi({ label: 'Black-holed pair-rounds', before: black[0], after: black[1], note: black[1] > black[0] ? '⚠ RIP-X drops more traffic while repairing' : 'RIP-X drops no more traffic' }),
      kpi({ label: 'Looping pair-rounds', before: rip.loop_pair_rounds, after: ripx.loop_pair_rounds, note: 'forwarding loops during repair' }),
      kpi({ label: 'Route changes', before: rip.route_changes, after: ripx.route_changes, note: 'routing churn' })
    ].join('');
    animateKpis($('cmpCards'));
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
    $('teCards').innerHTML = [
      kpi({ label: 'Delivered / offered traffic', before: 100 * r.delivered_ratio, after: 100 * x.delivered_ratio, digits: 1, unit: '%', lower: false, note: x.delivered_ratio >= r.delivered_ratio ? 'RIP-X delivers more' : '⚠ RIP-X delivers less' }),
      kpi({ label: 'Peak link utilization', before: r.maximum_utilization, after: x.maximum_utilization, digits: 2, note: '1.00 = link full' }),
      kpi({ label: 'Mean path length', before: r.mean_path_hops, after: x.mean_path_hops, digits: 2, unit: 'hops', verdict: 'flat', note: 'longer detours are the price' }),
      kpi({ label: 'Extra control messages', before: 0, after: x.te_control_messages, verdict: 'flat', note: `${x.epochs_run} epochs, best = epoch ${x.selected_epoch}` })
    ].join('');
    animateKpis($('teCards'));
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
      $('engine').textContent = '';
    } catch (e) {
      $('engine').textContent = 'Engine not running: start it with python run_live_simulator.py';
      document.querySelectorAll('button.go').forEach(b => { b.disabled = true; });
      return;
    }
    showBenchmark(await api('/api/benchmark/latest'));
    const s = await api('/api/benchmark/status');
    if (s.state === 'running') { $('bmGo').disabled = true; pollBenchmark(); }
    $('cmpGo').click();
  })();
})();
