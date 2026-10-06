/* RIP-X dashboard: plain SVG charts over the Python engine's JSON API. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const COLORS = { rip: '#ffb400', ripx: '#00f0ff' };
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d });

  // Themed number steppers: wrap each number input with - / + buttons (native spinners are hidden in CSS).
  document.querySelectorAll('input[type=number]').forEach(input => {
    const box = document.createElement('span'); box.className = 'num';
    const mk = (txt, dir) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = txt; b.setAttribute('aria-label', dir < 0 ? 'decrease' : 'increase');
      b.onclick = () => { dir < 0 ? input.stepDown() : input.stepUp(); input.dispatchEvent(new Event('change', { bubbles: true })); }; return b; };
    input.replaceWith(box); box.append(mk('−', -1), input, mk('+', 1));
  });

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
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="rgba(0,240,255,.1)"/>` +
           `<text x="${L - 6}" y="${y(v) + 4}" fill="#9d8fc7" font-size="11" text-anchor="end">${fmt(v)}</text>`;
    }
    Object.entries(events).forEach(([round, name]) => {
      g += `<line x1="${x(round)}" x2="${x(round)}" y1="${T}" y2="${H - B}" stroke="rgba(255,43,214,.4)" stroke-dasharray="2 4"/>` +
           `<text x="${x(round) + 3}" y="${T + 10}" fill="#64748b" font-size="9">${name.replace('_', ' ')}</text>`;
    });
    ['rip', 'ripx'].forEach(k => {
      const d = series[k].map((p, i) => `${i ? 'L' : 'M'}${x(p.x).toFixed(1)},${y(p.y).toFixed(1)}`).join('');
      g += `<path class="line" pathLength="1" d="${d}" fill="none" stroke="${COLORS[k]}" style="color:${COLORS[k]}" stroke-width="1.8"/>`;
    });
    g += `<text x="${(L + W) / 2}" y="${H - 6}" fill="#9d8fc7" font-size="11" text-anchor="middle">round</text>`;
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
           `<text x="${x + bw / 2}" y="${H - 14}" fill="#9d8fc7" font-size="11" text-anchor="middle">${it.name}</text>`;
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

  // Animate numbers (count-up with a short "decode" scramble), gauges and bars once the tiles are in the DOM.
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
          let text = fmt(to * eased, d);
          if (p < .6) text = text.replace(/\d/g, c => (Math.random() < .5 ? c : String(Math.floor(Math.random() * 10))));  // decode flicker
          el.textContent = text;
          if (p < 1) requestAnimationFrame(tick);
        })(t0);
      });
    }, i * 70));
  }

  // Pointer spotlight + 3D tilt, one delegated listener, throttled to animation frames.
  if (!REDUCED) {
    let frame = 0;
    document.addEventListener('pointermove', ev => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        const tile = ev.target.closest?.('.kpi');
        document.querySelectorAll('.kpi.hot').forEach(t => { if (t !== tile) { t.classList.remove('hot'); t.style.setProperty('--rx', '0deg'); t.style.setProperty('--ry', '0deg'); } });
        if (!tile) return;
        const r = tile.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
        tile.classList.add('hot');
        tile.style.setProperty('--mx', `${x * 100}%`); tile.style.setProperty('--my', `${y * 100}%`);
        tile.style.setProperty('--rx', `${((0.5 - y) * 9).toFixed(2)}deg`); tile.style.setProperty('--ry', `${((x - 0.5) * 11).toFixed(2)}deg`);
      });
    }, { passive: true });
  }

  // ---- chart zoom: hover (after a short pause) or tap enlarges a chart into a centred overlay; leave, backdrop click or Esc closes ----
  (function () {
    const zoom = $('zoom');
    let timer = 0, current = null;
    const close = () => { clearTimeout(timer); zoom.classList.remove('open'); current = null; };
    const open = chart => {
      if (current === chart) return;
      current = chart;
      zoom.innerHTML = chart.outerHTML + '<div class="hintkey">ESC OR MOVE AWAY TO CLOSE</div>';
      zoom.querySelector('.chart').style.animation = 'none';
      requestAnimationFrame(() => zoom.classList.add('open'));
    };
    const chartOf = ev => ev.target.closest?.('#cmpCharts .chart');
    document.addEventListener('pointerover', ev => {
      const c = chartOf(ev);
      if (!c || ev.pointerType !== 'mouse' || zoom.classList.contains('open')) return;
      clearTimeout(timer); timer = setTimeout(() => open(c), 350);
    });
    document.addEventListener('pointerout', ev => { if (chartOf(ev) && !ev.relatedTarget?.closest?.('.chart')) clearTimeout(timer); });
    document.addEventListener('click', ev => { const c = chartOf(ev); if (c && !zoom.classList.contains('open')) open(c); });
    zoom.addEventListener('pointerleave', close);
    zoom.addEventListener('click', ev => { if (!ev.target.closest('.chart')) close(); });
    document.addEventListener('keydown', ev => { if (ev.key === 'Escape') close(); });
  })();

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
    let html = `<p class="note">${b.seeds} seeds, from the ${b.source}.</p>` +
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
