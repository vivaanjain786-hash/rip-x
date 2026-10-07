/**
 * RIP-X Live Interactive Network Simulator (Packet Tracer Simulation Mode)
 * Core Engine & Interactive Canvas
 */

(function () {
  'use strict';

  // --- Constants ---
  const INFINITY_METRIC = 16;
  const NODE_RADIUS = 28;

  // --- Simulation State ---
  const state = {
    routers: {},      // { id: { id, name, x, y, up, routingTable: { dest: { metric, nextHop, reachable } } } }
    links: [],        // [ { u, v, up, bandwidth, latency, loss } ]
    selectedRouterId: 'R1',
    currentRound: 0,
    controlMessages: 0,
    isPlaying: false,
    speedMultiplier: 1.0,
    isConverged: false,
    poisonReverse: true,
    splitHorizon: true,
    triggeredUpdates: true,
    engine: 'js',     // 'python' when served by `python -m ripx.server`
    profile: 'baseline',
    busy: false,
    packets: [],      // [ { from, to, type: 'rip'|'data', progress: 0..1, label, path: [], pathIdx: 0 } ]
    log: [],
    draggingNode: null,
    dragOffset: { x: 0, y: 0 },
    lastTimestamp: 0,
    playTimer: null
  };

  // --- DOM Elements ---
  const canvas = document.getElementById('networkCanvas');
  const ctx = canvas.getContext('2d');
  const btnPlayPause = document.getElementById('btnPlayPause');
  const playIcon = document.getElementById('playIcon');
  const playText = document.getElementById('playText');
  const btnStep = document.getElementById('btnStep');
  const btnReset = document.getElementById('btnReset');
  const topologySelect = document.getElementById('topologySelect');
  const togglePoisonReverse = document.getElementById('togglePoisonReverse');
  const toggleSplitHorizon = document.getElementById('toggleSplitHorizon');
  const profileSelect = document.getElementById('profileSelect');
  const engineVal = document.getElementById('engineVal');
  const toggleTriggeredUpdates = document.getElementById('toggleTriggeredUpdates');
  const btnSendTraffic = document.getElementById('btnSendTraffic');
  const convergenceChip = document.getElementById('convergenceChip');
  const convergenceStatusText = document.getElementById('convergenceStatusText');
  const currentRoundVal = document.getElementById('currentRoundVal');
  const totalMsgsVal = document.getElementById('totalMsgsVal');
  const activeRoutesVal = document.getElementById('activeRoutesVal');
  const selectedRouterName = document.getElementById('selectedRouterName');
  const btnToggleNodeState = document.getElementById('btnToggleNodeState');
  const inspectorStatus = document.getElementById('inspectorStatus');
  const inspectorNeighbors = document.getElementById('inspectorNeighbors');
  const inspectorRouteCount = document.getElementById('inspectorRouteCount');
  const routingTableBody = document.getElementById('routingTableBody');
  const eventLogContainer = document.getElementById('eventLogContainer');
  const btnClearLog = document.getElementById('btnClearLog');
  const canvasOverlayNotice = document.getElementById('canvasOverlayNotice');

  // --- Topology Presets ---
  function loadTopologyPreset(preset) {
    state.routers = {};
    state.links = [];
    state.currentRound = 0;
    state.controlMessages = 0;
    state.packets = [];
    state.isConverged = false;

    const width = canvas.width || 800;
    const height = canvas.height || 600;
    const cx = width / 2;
    const cy = height / 2;

    if (preset === 'ring5') {
      const n = 5;
      const r = Math.min(width, height) * 0.32;
      for (let i = 1; i <= n; i++) {
        const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
        const id = `R${i}`;
        state.routers[id] = createRouter(id, cx + r * Math.cos(angle), cy + r * Math.sin(angle));
      }
      for (let i = 1; i <= n; i++) {
        const next = (i % n) + 1;
        state.links.push(createLink(`R${i}`, `R${next}`));
      }
      state.selectedRouterId = 'R1';
    } else if (preset === 'ring8') {
      const n = 8;
      const r = Math.min(width, height) * 0.36;
      for (let i = 1; i <= n; i++) {
        const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
        const id = `R${i}`;
        state.routers[id] = createRouter(id, cx + r * Math.cos(angle), cy + r * Math.sin(angle));
      }
      for (let i = 1; i <= n; i++) {
        const next = (i % n) + 1;
        state.links.push(createLink(`R${i}`, `R${next}`));
      }
      state.selectedRouterId = 'R1';
    } else if (preset === 'star6') {
      state.routers['R1'] = createRouter('R1', cx, cy);
      const n = 5;
      const r = Math.min(width, height) * 0.34;
      for (let i = 1; i <= n; i++) {
        const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
        const id = `R${i + 1}`;
        state.routers[id] = createRouter(id, cx + r * Math.cos(angle), cy + r * Math.sin(angle));
        state.links.push(createLink('R1', id));
      }
      state.selectedRouterId = 'R1';
    } else if (preset === 'mesh5') {
      const n = 5;
      const r = Math.min(width, height) * 0.33;
      for (let i = 1; i <= n; i++) {
        const angle = (i * 2 * Math.PI) / n - Math.PI / 2;
        const id = `R${i}`;
        state.routers[id] = createRouter(id, cx + r * Math.cos(angle), cy + r * Math.sin(angle));
      }
      for (let i = 1; i <= n; i++) {
        for (let j = i + 1; j <= n; j++) {
          state.links.push(createLink(`R${i}`, `R${j}`));
        }
      }
      state.selectedRouterId = 'R1';
    } else if (preset === 'cti') {
      // Count-to-Infinity 3-node Line A - B - C
      state.routers['R1'] = createRouter('R1', cx - 220, cy);
      state.routers['R2'] = createRouter('R2', cx, cy);
      state.routers['R3'] = createRouter('R3', cx + 220, cy);
      state.links.push(createLink('R1', 'R2'));
      state.links.push(createLink('R2', 'R3'));
      state.selectedRouterId = 'R1';
    } else if (preset === 'scalefree') {
      const coords = [
        [cx, cy - 60], [cx - 150, cy - 140], [cx + 150, cy - 140],
        [cx - 200, cy + 40], [cx + 200, cy + 40], [cx - 90, cy + 180],
        [cx + 90, cy + 180], [cx - 280, cy - 60], [cx + 280, cy - 60],
        [cx, cy + 220]
      ];
      for (let i = 1; i <= 10; i++) {
        const id = `R${i}`;
        const pos = coords[i - 1] || [cx + (i * 20), cy];
        state.routers[id] = createRouter(id, pos[0], pos[1]);
      }
      const edges = [
        [1,2], [1,3], [1,4], [1,5], [2,3], [2,8], [3,9],
        [4,6], [5,7], [6,7], [6,10], [7,10]
      ];
      edges.forEach(([u, v]) => state.links.push(createLink(`R${u}`, `R${v}`)));
      state.selectedRouterId = 'R1';
    }

    initRoutingTables();
    addLog('info', 'SYS', `Loaded topology: ${preset.toUpperCase()} (${Object.keys(state.routers).length} Routers, ${state.links.length} Links)`);
    updateUI();
    if (state.engine === 'python') loadNetworkIntoEngine();
  }

  function createRouter(id, x, y) {
    return {
      id,
      name: id,
      x: Math.round(x),
      y: Math.round(y),
      up: true,
      routingTable: {} // destination -> { metric, nextHop, reachable }
    };
  }

  function createLink(u, v) {
    return {
      u,
      v,
      up: true,
      bandwidth: 100.0,
      latency: 1.0,
      loss: 0.0
    };
  }

  function getNeighbors(routerId) {
    const neighbors = [];
    state.links.forEach(l => {
      if (l.up) {
        if (l.u === routerId && state.routers[l.v]?.up) neighbors.push(l.v);
        else if (l.v === routerId && state.routers[l.u]?.up) neighbors.push(l.u);
      }
    });
    return neighbors;
  }

  function getLink(u, v) {
    return state.links.find(l => (l.u === u && l.v === v) || (l.u === v && l.v === u));
  }


  // --- Python Engine Adapter ---
  // When the page is served by `python -m ripx.server`, every routing decision
  // comes from the Python RipNetwork. The in-browser engine below is only a
  // fallback for opening index.html without the server.
  async function api(path, body) {
    const response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    return payload;
  }

  async function detectEngine() {
    try {
      const health = await api('/api/health');
      state.engine = health.engine === 'python' ? 'python' : 'js';
    } catch (err) {
      state.engine = 'js';
    }
    engineVal.textContent = state.engine === 'python' ? 'Python' : 'Browser';
    profileSelect.disabled = state.engine !== 'python';
    toggleSplitHorizon.disabled = state.engine !== 'python';
    addLog('info', 'ENGINE', state.engine === 'python'
      ? 'Connected to the Python RIP-X engine. Routing is computed by ripx.RipNetwork.'
      : 'Python engine not found; using the standalone in-browser engine.');
  }

  function engineConfig() {
    return {
      profile: state.profile,
      split_horizon: state.splitHorizon,
      poison_reverse: state.poisonReverse,
      triggered_updates: state.triggeredUpdates
    };
  }

  function applyServerState(snapshot) {
    state.currentRound = snapshot.round;
    state.controlMessages = snapshot.controlMessages;
    state.isConverged = snapshot.converged;
    Object.entries(snapshot.routers).forEach(([id, info]) => {
      const router = state.routers[id];
      if (!router) return;
      router.up = info.up;
      router.updateInterval = info.updateInterval;
      router.routingTable = info.routes;
    });
    snapshot.links.forEach(serverLink => {
      const link = getLink(serverLink.u, serverLink.v);
      if (!link) return;
      link.up = serverLink.up;
      link.cost = serverLink.cost;
      link.utilization = serverLink.utilization;
      link.bandwidth = serverLink.bandwidth_mbps;
      link.latency = serverLink.latency_ms;
      link.loss = serverLink.packet_loss;
    });
    updateUI();
  }

  async function engineCall(path, body) {
    try {
      return await api(path, body);
    } catch (err) {
      addLog('fail', 'ENGINE', `Python engine error: ${err.message}`);
      pauseSimulation();
      return null;
    }
  }

  async function loadNetworkIntoEngine() {
    const result = await engineCall('/api/network', {
      routers: Object.keys(state.routers),
      links: state.links.map(l => [l.u, l.v]),
      config: engineConfig()
    });
    if (result) {
      applyServerState(result);
      const cfg = result.config;
      addLog('info', 'ENGINE', `Profile ${cfg.profile}: updates ${cfg.updates.type}, metric ${cfg.metric.type}, split horizon ${cfg.split_horizon !== false ? 'on' : 'off'}.`);
    }
  }

  async function stepRipRoundPython() {
    if (state.busy) return;
    state.busy = true;
    const result = await engineCall('/api/step', { rounds: 1 });
    state.busy = false;
    if (!result) return;
    result.advertisements.forEach(([from, to]) => spawnPacket(from, to, 'rip', `RIP Adv [${from}→${to}]`));
    result.requests.forEach(([from, to]) => spawnPacket(from, to, 'rip', `RIP Request [${from}→${to}]`));
    applyServerState(result.state);
    const sent = result.advertisements.length + result.requests.length;
    if (state.isConverged) {
      addLog('converged', 'CONVERGE', `Network CONVERGED at Round ${state.currentRound} (${state.controlMessages} total messages).`);
      if (state.isPlaying) pauseSimulation();
    } else {
      const requestNote = result.requests.length ? `, ${result.requests.length} route requests` : '';
      addLog('info', 'ROUND', `Round ${state.currentRound}: ${result.advertisements.length} RIP advertisements${requestNote}${result.changed ? '. Routing tables updated.' : '.'}`);
    }
    return sent;
  }

  async function toggleRouterPython(routerId) {
    const result = await engineCall('/api/router/toggle', { router: routerId });
    if (!result) return;
    applyServerState(result.state);
    const failed = result.action === 'failed';
    addLog(failed ? 'fail' : 'recover', failed ? 'FAIL' : 'RECOVER', `Router ${routerId} ${failed ? 'FAILED' : 'RECOVERED'} (Python engine).`);
    showOverlayNotice(`Router ${routerId} ${failed ? 'FAILED' : 'RECOVERED'}`);
    if (state.triggeredUpdates) await stepRipRoundPython();
  }

  async function toggleLinkPython(link) {
    const result = await engineCall('/api/link/toggle', { u: link.u, v: link.v });
    if (!result) return;
    applyServerState(result.state);
    const failed = result.action === 'failed';
    addLog(failed ? 'fail' : 'recover', 'LINK', `Link ${link.u} <-> ${link.v} ${failed ? 'SEVERED' : 'RESTORED'}`);
    showOverlayNotice(`Link ${link.u} - ${link.v} ${failed ? 'SEVERED' : 'RESTORED'}`);
    if (state.triggeredUpdates) await stepRipRoundPython();
  }

  async function sendDataTrafficPython(sourceId, destId) {
    const result = await engineCall('/api/trace', { source: sourceId, destination: destId });
    if (!result) return;
    const path = result.path;
    if (result.outcome === 'blackhole') {
      addLog('fail', 'TRAFFIC', `Traffic ${sourceId}→${destId} DROPPED at ${path[path.length - 1]} (no usable route)`);
      showOverlayNotice(`Traffic Dropped: No route to ${destId}`);
    } else if (result.outcome === 'loop') {
      addLog('fail', 'LOOP', `ROUTING LOOP DETECTED on path: ${path.join(' -> ')}`);
      showOverlayNotice('Routing Loop Detected!');
    } else {
      addLog('traffic', 'TRAFFIC', `Data Flow: ${sourceId} → ${destId} routed via [${path.join(' -> ')}] (${path.length - 1} hops)`);
    }
    for (let i = 0; i < path.length - 1; i++) {
      setTimeout(() => spawnPacket(path[i], path[i + 1], 'data', `Data [${sourceId}→${destId}]`), i * 350);
    }
  }

  // --- RIP Routing Protocol Engine (standalone fallback) ---
  function initRoutingTables() {
    Object.values(state.routers).forEach(r => {
      r.routingTable = {};
      // Direct connected route to self (metric 0)
      r.routingTable[r.id] = { metric: 0, nextHop: r.id, reachable: true };
    });
  }

  function stepRipRound() {
    if (state.engine === 'python') return stepRipRoundPython();
    state.currentRound++;
    let anyRouteChanged = false;
    let roundMsgs = 0;

    // Phase 1: Prepare advertisement vectors from all active routers
    const advertisements = [];

    Object.values(state.routers).forEach(sender => {
      if (!sender.up) return;

      const neighbors = getNeighbors(sender.id);
      neighbors.forEach(neighborId => {
        const vector = {};

        // Apply Split Horizon / Poison Reverse
        Object.entries(sender.routingTable).forEach(([dest, entry]) => {
          if (!entry.reachable) {
            vector[dest] = INFINITY_METRIC;
          } else if (state.poisonReverse && entry.nextHop === neighborId && dest !== neighborId) {
            // Poison reverse: advertise metric 16 back to the next-hop
            vector[dest] = INFINITY_METRIC;
          } else {
            vector[dest] = entry.metric;
          }
        });

        advertisements.push({
          from: sender.id,
          to: neighborId,
          vector: vector
        });

        // Add visual packet animation
        spawnPacket(sender.id, neighborId, 'rip', `RIP Adv [${sender.id}→${neighborId}]`);
        roundMsgs++;
      });
    });

    state.controlMessages += roundMsgs;

    // Phase 2: Process distance vectors at receivers using Bellman-Ford
    advertisements.forEach(adv => {
      const receiver = state.routers[adv.to];
      if (!receiver || !receiver.up) return;

      Object.entries(adv.vector).forEach(([dest, advMetric]) => {
        if (dest === receiver.id) return; // Don't route to self via neighbor

        const offeredMetric = Math.min(advMetric + 1, INFINITY_METRIC);
        const currentEntry = receiver.routingTable[dest];

        if (!currentEntry) {
          // New route discovered
          if (offeredMetric < INFINITY_METRIC) {
            receiver.routingTable[dest] = {
              metric: offeredMetric,
              nextHop: adv.from,
              reachable: true
            };
            anyRouteChanged = true;
          }
        } else {
          // Existing route
          if (currentEntry.nextHop === adv.from) {
            // Update from current next hop is authoritative (even if metric increases)
            if (currentEntry.metric !== offeredMetric) {
              currentEntry.metric = offeredMetric;
              currentEntry.reachable = offeredMetric < INFINITY_METRIC;
              anyRouteChanged = true;
            }
          } else {
            // Alternative next hop offers a strictly shorter path
            if (offeredMetric < currentEntry.metric) {
              currentEntry.metric = offeredMetric;
              currentEntry.nextHop = adv.from;
              currentEntry.reachable = true;
              anyRouteChanged = true;
            }
          }
        }
      });
    });

    if (anyRouteChanged) {
      state.isConverged = false;
      addLog('info', 'ROUND', `Round ${state.currentRound}: Exchanged ${roundMsgs} RIP messages. Routing tables updated.`);
    } else {
      state.isConverged = true;
      addLog('converged', 'CONVERGE', `Network CONVERGED at Round ${state.currentRound} (${state.controlMessages} total messages).`);
      if (state.isPlaying) {
        pauseSimulation();
      }
    }

    updateUI();
  }

  function handleRouterFailure(routerId) {
    if (state.engine === 'python') return toggleRouterPython(routerId);
    const router = state.routers[routerId];
    if (!router) return;

    router.up = !router.up;
    const isNowUp = router.up;

    if (!isNowUp) {
      addLog('fail', 'FAIL', `Router ${routerId} FAILED! Dependent neighbors poisoning routes.`);
      showOverlayNotice(`Router ${routerId} FAILED`);
      
      // Neighbors poison routes going through this failed router
      Object.values(state.routers).forEach(r => {
        if (!r.up) return;
        Object.entries(r.routingTable).forEach(([dest, entry]) => {
          if (entry.nextHop === routerId || dest === routerId) {
            entry.metric = INFINITY_METRIC;
            entry.reachable = false;
          }
        });
      });
    } else {
      addLog('recover', 'RECOVER', `Router ${routerId} RECOVERED! Re-announcing distance vectors.`);
      showOverlayNotice(`Router ${routerId} RECOVERED`);
      router.routingTable = {};
      router.routingTable[router.id] = { metric: 0, nextHop: router.id, reachable: true };
    }

    state.isConverged = false;
    updateUI();

    if (state.triggeredUpdates) {
      stepRipRound();
    }
  }

  function handleLinkToggle(link) {
    if (state.engine === 'python') return toggleLinkPython(link);
    link.up = !link.up;
    const stateStr = link.up ? 'RESTORED' : 'SEVERED';
    addLog(link.up ? 'recover' : 'fail', 'LINK', `Link ${link.u} <-> ${link.v} ${stateStr}`);
    showOverlayNotice(`Link ${link.u} - ${link.v} ${stateStr}`);

    if (!link.up) {
      // Invalidate direct routes if no other path
      [state.routers[link.u], state.routers[link.v]].forEach(r => {
        if (!r) return;
        Object.entries(r.routingTable).forEach(([dest, entry]) => {
          if (entry.nextHop === (r.id === link.u ? link.v : link.u)) {
            entry.metric = INFINITY_METRIC;
            entry.reachable = false;
          }
        });
      });
    }

    state.isConverged = false;
    updateUI();

    if (state.triggeredUpdates) {
      stepRipRound();
    }
  }

  function sendDataTraffic(sourceId, destId) {
    if (state.engine === 'python') return sendDataTrafficPython(sourceId, destId);
    const src = state.routers[sourceId];
    const dst = state.routers[destId];
    if (!src || !dst || !src.up || !dst.up) {
      addLog('fail', 'TRAFFIC', `Cannot send traffic: ${sourceId} or ${destId} is offline.`);
      return;
    }

    // Trace path via next-hops
    const path = [sourceId];
    let curr = sourceId;
    let loopDetected = false;
    const visited = new Set([sourceId]);

    while (curr !== destId) {
      const route = state.routers[curr]?.routingTable[destId];
      if (!route || !route.reachable || route.metric >= INFINITY_METRIC) {
        addLog('fail', 'TRAFFIC', `Traffic ${sourceId}→${destId} DROPPED at ${curr} (No route / metric=16)`);
        showOverlayNotice(`Traffic Dropped: No route to ${destId}`);
        return;
      }
      curr = route.nextHop;
      if (visited.has(curr)) {
        loopDetected = true;
        path.push(curr);
        break;
      }
      visited.add(curr);
      path.push(curr);
    }

    if (loopDetected) {
      addLog('fail', 'LOOP', `ROUTING LOOP DETECTED on path: ${path.join(' -> ')}`);
      showOverlayNotice(`Routing Loop Detected!`);
    } else {
      addLog('traffic', 'TRAFFIC', `Data Flow: ${sourceId} → ${destId} routed via [${path.join(' -> ')}] (${path.length - 1} hops)`);
    }

    // Animate flow along path
    for (let i = 0; i < path.length - 1; i++) {
      setTimeout(() => {
        spawnPacket(path[i], path[i + 1], 'data', `Data [${sourceId}→${destId}]`);
      }, i * 350);
    }
  }

  // --- Packet Animation Management ---
  function spawnPacket(fromId, toId, type, label) {
    state.packets.push({
      from: fromId,
      to: toId,
      type: type,
      progress: 0.0,
      label: label
    });
  }

  function updatePackets(delta) {
    const speed = (0.75 * state.speedMultiplier);
    for (let i = state.packets.length - 1; i >= 0; i--) {
      const p = state.packets[i];
      p.progress += delta * speed;
      if (p.progress >= 1.0) {
        state.packets.splice(i, 1);
      }
    }
  }

  // --- Canvas Rendering ---
  function resizeCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
  }

  function draw() {
    const width = canvas.width / (window.devicePixelRatio || 1);
    const height = canvas.height / (window.devicePixelRatio || 1);

    ctx.clearRect(0, 0, width, height);

    // 1. Draw Grid Background
    drawGrid(width, height);

    // 2. Draw Links
    state.links.forEach(link => {
      const u = state.routers[link.u];
      const v = state.routers[link.v];
      if (!u || !v) return;

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(u.x, u.y);
      ctx.lineTo(v.x, v.y);

      if (link.up && u.up && v.up) {
        ctx.strokeStyle = 'rgba(107, 181, 228, 0.45)';
        ctx.lineWidth = 3;
        ctx.stroke();

        // Subtle link pulse
        ctx.strokeStyle = 'rgba(107, 181, 228, 0.15)';
        ctx.lineWidth = 8;
        ctx.stroke();

        // RIP-X link cost (only shown when it differs from one hop)
        if (link.cost && link.cost > 1) {
          ctx.fillStyle = '#FFB86B';
          ctx.font = 'bold 11px JetBrains Mono';
          ctx.textAlign = 'center';
          ctx.fillText(`cost ${link.cost}`, (u.x + v.x) / 2, (u.y + v.y) / 2 - 8);
        }
      } else {
        ctx.strokeStyle = 'rgba(255, 107, 122, 0.6)';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([6, 6]);
        ctx.stroke();

        // Cross marker on broken link
        const mx = (u.x + v.x) / 2;
        const my = (u.y + v.y) / 2;
        ctx.fillStyle = '#FF6B7A';
        ctx.font = 'bold 12px Inter';
        ctx.textAlign = 'center';
        ctx.fillText('✖ LINK DOWN', mx, my - 6);
      }
      ctx.restore();
    });

    // 3. Draw Packets Flying Along Links
    state.packets.forEach(p => {
      const u = state.routers[p.from];
      const v = state.routers[p.to];
      if (!u || !v) return;

      const px = u.x + (v.x - u.x) * p.progress;
      const py = u.y + (v.y - u.y) * p.progress;

      ctx.save();
      if (p.type === 'rip') {
        // Glowing cyan envelope / circle
        ctx.shadowColor = '#6BB5E4';
        ctx.shadowBlur = 12;
        ctx.fillStyle = '#6BB5E4';
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.fill();

        // Small message label
        ctx.shadowBlur = 0;
        ctx.font = '9px JetBrains Mono';
        ctx.fillStyle = '#F1F1F1';
        ctx.textAlign = 'center';
        ctx.fillText('RIP', px, py - 9);
      } else {
        // Emerald Data Packet
        ctx.shadowColor = '#FFB86B';
        ctx.shadowBlur = 15;
        ctx.fillStyle = '#FFB86B';
        ctx.beginPath();
        ctx.arc(px, py, 8, 0, Math.PI * 2);
        ctx.fill();

        ctx.shadowBlur = 0;
        ctx.font = 'bold 10px JetBrains Mono';
        ctx.fillStyle = '#F1F1F1';
        ctx.textAlign = 'center';
        ctx.fillText('DATA', px, py - 11);
      }
      ctx.restore();
    });

    // 4. Draw Routers
    Object.values(state.routers).forEach(r => {
      const isSelected = r.id === state.selectedRouterId;
      ctx.save();

      // Outer Glow / Selection Ring
      if (isSelected) {
        ctx.beginPath();
        ctx.arc(r.x, r.y, NODE_RADIUS + 7, 0, Math.PI * 2);
        ctx.strokeStyle = 'rgba(107, 181, 228, 0.9)';
        ctx.lineWidth = 2.5;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
      }

      // Router Body
      ctx.beginPath();
      ctx.arc(r.x, r.y, NODE_RADIUS, 0, Math.PI * 2);

      if (r.up) {
        const grad = ctx.createRadialGradient(r.x - 6, r.y - 6, 4, r.x, r.y, NODE_RADIUS);
        grad.addColorStop(0, '#282828');
        grad.addColorStop(1, '#1E1E1E');
        ctx.fillStyle = grad;
        ctx.fill();

        ctx.strokeStyle = isSelected ? '#6BB5E4' : 'rgba(107, 181, 228, 0.7)';
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.stroke();

        // Cisco 4-arrow Router Symbol Icon
        drawRouterSymbol(r.x, r.y, '#6BB5E4');
      } else {
        ctx.fillStyle = '#331111';
        ctx.fill();
        ctx.strokeStyle = '#FF6B7A';
        ctx.lineWidth = 2.5;
        ctx.stroke();

        // Failed X icon
        ctx.strokeStyle = '#FF6B7A';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(r.x - 10, r.y - 10);
        ctx.lineTo(r.x + 10, r.y + 10);
        ctx.moveTo(r.x + 10, r.y - 10);
        ctx.lineTo(r.x - 10, r.y + 10);
        ctx.stroke();
      }

      // Label below router
      ctx.font = 'bold 12px Inter';
      ctx.fillStyle = r.up ? '#ffffff' : '#FF6B7A';
      ctx.textAlign = 'center';
      ctx.fillText(r.name, r.x, r.y + NODE_RADIUS + 16);

      // Status indicator dot on top right of node
      ctx.beginPath();
      ctx.arc(r.x + NODE_RADIUS * 0.7, r.y - NODE_RADIUS * 0.7, 5, 0, Math.PI * 2);
      ctx.fillStyle = r.up ? '#FFB86B' : '#FF6B7A';
      ctx.fill();

      ctx.restore();
    });
  }

  function drawGrid(w, h) {
    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.025)';
    ctx.lineWidth = 1;
    const step = 40;
    for (let x = 0; x < w; x += step) {
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, h);
      ctx.stroke();
    }
    for (let y = 0; y < h; y += step) {
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(w, y);
      ctx.stroke();
    }
    ctx.restore();
  }

  function drawRouterSymbol(x, y, color) {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    const len = 9;
    
    // Inward/outward cross arrows
    ctx.beginPath();
    ctx.moveTo(x - len, y); ctx.lineTo(x + len, y);
    ctx.moveTo(x, y - len); ctx.lineTo(x, y + len);
    ctx.stroke();

    ctx.restore();
  }

  // --- Animation Loop ---
  function animate(timestamp) {
    if (!state.lastTimestamp) state.lastTimestamp = timestamp;
    const delta = (timestamp - state.lastTimestamp) / 1000;
    state.lastTimestamp = timestamp;

    updatePackets(delta);
    draw();

    requestAnimationFrame(animate);
  }

  // --- UI Update & Inspector ---
  function updateUI() {
    // Header Metrics
    currentRoundVal.textContent = state.currentRound;
    totalMsgsVal.textContent = state.controlMessages;

    let activeRoutesCount = 0;
    Object.values(state.routers).forEach(r => {
      if (r.up) {
        Object.values(r.routingTable).forEach(e => {
          if (e.reachable && e.metric < INFINITY_METRIC) activeRoutesCount++;
        });
      }
    });
    activeRoutesVal.textContent = activeRoutesCount;

    // Convergence Chip
    if (state.isConverged) {
      convergenceChip.className = 'status-chip';
      convergenceChip.querySelector('.indicator').className = 'indicator indicator-converged';
      convergenceStatusText.textContent = 'Network Converged';
    } else if (state.isPlaying) {
      convergenceChip.className = 'status-chip';
      convergenceChip.querySelector('.indicator').className = 'indicator indicator-running';
      convergenceStatusText.textContent = 'Simulating RIP...';
    } else {
      convergenceChip.className = 'status-chip';
      convergenceChip.querySelector('.indicator').className = 'indicator indicator-idle';
      convergenceStatusText.textContent = 'Paused / Stepping';
    }

    // Selected Router Panel
    const router = state.routers[state.selectedRouterId];
    if (router) {
      selectedRouterName.textContent = `Router ${router.id} Details`;
      const intervalNote = router.up && router.updateInterval ? ` · updates every ${router.updateInterval} rounds` : '';
      inspectorStatus.textContent = (router.up ? 'UP / ACTIVE' : 'FAILED / DOWN') + intervalNote;
      inspectorStatus.className = `meta-val ${router.up ? 'status-up' : 'status-down'}`;
      btnToggleNodeState.textContent = router.up ? 'Fail Router' : 'Recover Router';
      btnToggleNodeState.className = `btn btn-sm ${router.up ? 'btn-danger' : 'btn-accent'}`;

      const neighbors = getNeighbors(router.id);
      inspectorNeighbors.textContent = neighbors.length > 0 ? neighbors.join(', ') : 'None';

      const routes = Object.entries(router.routingTable);
      inspectorRouteCount.textContent = routes.length;

      // Render Routing Table
      routingTableBody.innerHTML = '';
      if (routes.length === 0) {
        routingTableBody.innerHTML = `<tr><td colspan="4" style="text-align:center; color:rgba(241, 241, 241, 0.46);">No routing entries</td></tr>`;
      } else {
        routes.sort((a, b) => a[0].localeCompare(b[0])).forEach(([dest, entry]) => {
          const tr = document.createElement('tr');
          const isDirect = entry.metric === 0;
          const isPoisoned = entry.metric >= INFINITY_METRIC || !entry.reachable;

          let stateClass = isDirect ? 'route-direct' : (isPoisoned ? 'route-poisoned' : 'route-reachable');
          let stateLabel = isDirect ? 'Direct (Connected)' : (isPoisoned ? 'Unreachable (Poisoned)' : 'Valid Hop');

          tr.innerHTML = `
            <td><strong>${dest}</strong></td>
            <td class="${stateClass}">${entry.metric}</td>
            <td>${entry.nextHop}</td>
            <td class="${stateClass}">${stateLabel}</td>
          `;
          routingTableBody.appendChild(tr);
        });
      }
    }
  }

  function addLog(type, tag, message) {
    const time = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const entry = { type, tag, message, time };
    state.log.unshift(entry);
    if (state.log.length > 80) state.log.pop();

    const div = document.createElement('div');
    div.className = `log-entry log-${type}`;
    div.innerHTML = `<span class="log-time">[${time}]</span><span class="log-tag">[${tag}]</span>${message}`;
    eventLogContainer.insertBefore(div, eventLogContainer.firstChild);
  }

  function showOverlayNotice(text) {
    canvasOverlayNotice.textContent = text;
    canvasOverlayNotice.style.display = 'block';
    setTimeout(() => {
      canvasOverlayNotice.style.display = 'none';
    }, 2200);
  }

  function startSimulation() {
    state.isPlaying = true;
    playText.textContent = 'Pause';
    playIcon.innerHTML = '<rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect>';
    btnPlayPause.className = 'btn btn-danger';
    updateUI();

    clearInterval(state.playTimer);
    state.playTimer = setInterval(() => {
      if (!state.isConverged) {
        stepRipRound();
      } else {
        pauseSimulation();
      }
    }, 1200 / state.speedMultiplier);
  }

  function pauseSimulation() {
    state.isPlaying = false;
    playText.textContent = 'Play';
    playIcon.innerHTML = '<polygon points="5 3 19 12 5 21 5 3"></polygon>';
    btnPlayPause.className = 'btn btn-primary';
    clearInterval(state.playTimer);
    updateUI();
  }

  // --- Interaction & Event Handlers ---
  function setupEventListeners() {
    window.addEventListener('resize', () => {
      resizeCanvas();
      draw();
    });

    btnPlayPause.addEventListener('click', () => {
      if (state.isPlaying) pauseSimulation();
      else startSimulation();
    });

    btnStep.addEventListener('click', () => {
      pauseSimulation();
      stepRipRound();
    });

    btnReset.addEventListener('click', () => {
      pauseSimulation();
      loadTopologyPreset(topologySelect.value);
    });

    topologySelect.addEventListener('change', (e) => {
      pauseSimulation();
      loadTopologyPreset(e.target.value);
    });

    // In Python-engine mode a protocol change rebuilds the network, since
    // routers are created with their protocol settings.
    function protocolChanged() {
      if (state.engine === 'python') {
        pauseSimulation();
        loadTopologyPreset(topologySelect.value);
      }
    }

    togglePoisonReverse.addEventListener('change', (e) => {
      state.poisonReverse = e.target.checked;
      addLog('info', 'CONFIG', `Split Horizon with Poison Reverse: ${state.poisonReverse ? 'ENABLED' : 'DISABLED'}`);
      protocolChanged();
    });

    toggleSplitHorizon.addEventListener('change', (e) => {
      state.splitHorizon = e.target.checked;
      addLog('info', 'CONFIG', `Split Horizon: ${state.splitHorizon ? 'ENABLED' : 'DISABLED (count-to-infinity possible)'}`);
      protocolChanged();
    });

    profileSelect.addEventListener('change', (e) => {
      state.profile = e.target.value;
      addLog('info', 'CONFIG', `Protocol profile: ${state.profile}`);
      protocolChanged();
    });

    toggleTriggeredUpdates.addEventListener('change', (e) => {
      state.triggeredUpdates = e.target.checked;
      addLog('info', 'CONFIG', `Triggered Updates on Link Failure: ${state.triggeredUpdates ? 'ENABLED' : 'DISABLED'}`);
      protocolChanged();
    });

    btnSendTraffic.addEventListener('click', () => {
      const keys = Object.keys(state.routers);
      if (keys.length >= 3) {
        sendDataTraffic('R1', 'R3');
      } else if (keys.length >= 2) {
        sendDataTraffic(keys[0], keys[1]);
      }
    });

    btnToggleNodeState.addEventListener('click', () => {
      if (state.selectedRouterId) {
        handleRouterFailure(state.selectedRouterId);
      }
    });

    btnClearLog.addEventListener('click', () => {
      state.log = [];
      eventLogContainer.innerHTML = '';
    });

    // Speed selector
    document.querySelectorAll('.speed-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        state.speedMultiplier = parseFloat(btn.dataset.speed);
        if (state.isPlaying) {
          startSimulation(); // Restart interval with new speed
        }
      });
    });

    // Canvas Mouse Events (Selection, Dragging, Fault Injection)
    canvas.addEventListener('mousedown', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      // Check if clicking a router
      let clickedRouter = null;
      Object.values(state.routers).forEach(r => {
        const dist = Math.hypot(r.x - mx, r.y - my);
        if (dist <= NODE_RADIUS) {
          clickedRouter = r;
        }
      });

      if (clickedRouter) {
        state.selectedRouterId = clickedRouter.id;
        state.draggingNode = clickedRouter;
        state.dragOffset = { x: clickedRouter.x - mx, y: clickedRouter.y - my };
        updateUI();
        draw();
        return;
      }

      // Check if clicking a link to toggle it
      state.links.forEach(l => {
        const u = state.routers[l.u];
        const v = state.routers[l.v];
        if (!u || !v) return;

        // Distance from point to line segment
        const dist = distToSegment({ x: mx, y: my }, u, v);
        if (dist < 10) {
          handleLinkToggle(l);
        }
      });
    });

    canvas.addEventListener('mousemove', (e) => {
      if (state.draggingNode) {
        const rect = canvas.getBoundingClientRect();
        state.draggingNode.x = Math.max(NODE_RADIUS, Math.min(canvas.width - NODE_RADIUS, e.clientX - rect.left + state.dragOffset.x));
        state.draggingNode.y = Math.max(NODE_RADIUS, Math.min(canvas.height - NODE_RADIUS, e.clientY - rect.top + state.dragOffset.y));
        draw();
      }
    });

    window.addEventListener('mouseup', () => {
      state.draggingNode = null;
    });

    // Double-click router to toggle failure
    canvas.addEventListener('dblclick', (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      Object.values(state.routers).forEach(r => {
        const dist = Math.hypot(r.x - mx, r.y - my);
        if (dist <= NODE_RADIUS) {
          handleRouterFailure(r.id);
        }
      });
    });
  }

  function distToSegment(p, v, w) {
    const l2 = (w.x - v.x) ** 2 + (w.y - v.y) ** 2;
    if (l2 === 0) return Math.hypot(p.x - v.x, p.y - v.y);
    let t = ((p.x - v.x) * (w.x - v.x) + (p.y - v.y) * (w.y - v.y)) / l2;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(p.x - (v.x + t * (w.x - v.x)), p.y - (v.y + t * (w.y - v.y)));
  }

  // --- App Initialization ---
  async function init() {
    resizeCanvas();
    setupEventListeners();
    await detectEngine();
    loadTopologyPreset('ring5');
    requestAnimationFrame(animate);
  }

  window.addEventListener('DOMContentLoaded', init);
})();
