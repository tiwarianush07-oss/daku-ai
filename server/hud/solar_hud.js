/**
 * DAKU Solar AI Agent Swarm HUD — Phase 7 Engine
 * Real-time 3D/2D Canvas simulation, interactive camera controls,
 * real VoiceSession client, security boundaries, and telemetry telemetry.
 */

(function () {
  'use strict';

  // UI Status States
  const UIStates = {
    STANDBY: 'STANDBY',
    LISTENING: 'LISTENING',
    TRANSCRIBING: 'TRANSCRIBING',
    THINKING: 'THINKING',
    CONFIRMATION_REQUIRED: 'CONFIRMATION_REQUIRED',
    EXECUTING: 'EXECUTING',
    SPEAKING: 'SPEAKING',
    FALLBACK: 'FALLBACK',
    ERROR: 'ERROR',
    OFFLINE: 'OFFLINE',
  };

  // Visual Agent States
  const AgentStates = {
    IDLE: 'IDLE',
    ACTIVE: 'ACTIVE',
    THINKING: 'THINKING',
    EXECUTING: 'EXECUTING',
    ERROR: 'ERROR',
  };

  // Core Agent Swarm Definition mapped to real DAKU Capabilities
  const CORE_AGENTS = [
    {
      id: 'researcher',
      name: 'Researcher',
      role: 'Research & Search Specialist',
      capability: 'DAKU research/search capability',
      tools: ['browser_tool (search, scrape, page_title, page_text)', 'file_tool (search_files)'],
      color: '#00d2ff',
      radius: 12,
      orbitRadius: 150,
      orbitSpeed: 0.008,
      orbitAngle: 0.8,
      state: AgentStates.IDLE,
      icon: '🔍',
      description: 'Web research, documentation queries, scraping, file search',
    },
    {
      id: 'coder',
      name: 'Coder Agent',
      role: 'Coding & Execution Engine',
      capability: 'DAKU coding/execution capability',
      tools: ['application_tool (launch_app, list_apps)', 'file_tool (create, read, write)', 'system_tool (ram, cpu, execution)'],
      color: '#06d6a0',
      radius: 14,
      orbitRadius: 230,
      orbitSpeed: 0.0055,
      orbitAngle: 2.4,
      state: AgentStates.IDLE,
      icon: '⚡',
      description: 'Code synthesis, script running, system command dispatch, output verification',
    },
    {
      id: 'vision',
      name: 'Vision Analyst',
      role: 'Visual & DOM Inspector',
      capability: 'DAKU vision capability',
      tools: ['browser_tool (screenshot, viewport, DOM inspection, element query)'],
      color: '#9d4edd',
      radius: 13,
      orbitRadius: 310,
      orbitSpeed: 0.004,
      orbitAngle: 4.1,
      state: AgentStates.IDLE,
      icon: '👁️',
      description: 'Visual UI verification, page layout inspection, multimodal visual telemetry',
    },
    {
      id: 'strategist',
      name: 'Executive Strategist',
      role: 'Planning & Multi-Pass Orchestrator',
      capability: 'DAKU planning/orchestration',
      tools: ['TaskPlanner (step decomposition, dependencies)', 'MultiPassReasoner (hypothesis, reflection, verifier)'],
      color: '#ffb703',
      radius: 16,
      orbitRadius: 390,
      orbitSpeed: 0.0028,
      orbitAngle: 5.3,
      state: AgentStates.IDLE,
      icon: '🧭',
      description: 'Multi-step task decomposition, intent routing, reflection, permission validation',
    },
  ];

  // Central Sun definition
  const CENTRAL_SUN = {
    id: 'brain',
    name: 'DAKU Central Brain',
    role: 'Central Autonomous Brain & Router',
    capability: 'Central Model Router & Task Core',
    tools: ['DirectModelRouter', 'MultiPassReasoner', 'PermissionManager', 'ToolRegistry'],
    color: '#ff8800',
    coreColor: '#ffe600',
    radius: 36,
    state: AgentStates.IDLE,
    icon: '☀️',
    description: 'Central authoritative intelligence, multi-tier permissions, and provider routing',
  };

  // State
  let currentUIState = UIStates.STANDBY;
  let agents = [...CORE_AGENTS];
  let activeTarget = CENTRAL_SUN; // currently focused body
  let camera = { x: 0, y: 0, zoom: 1.0, targetX: 0, targetY: 0, targetZoom: 1.0 };
  let isRecording = false;
  let mediaRecorder = null;
  let recordedAudioChunks = [];
  let stars = [];
  let pendingConfirmationAction = null;
  let liveTelemetryFeed = [];

  // DOM Elements
  const canvas = document.getElementById('solar-canvas');
  const ctx = canvas.getContext('2d');
  const hudTurnBadge = document.getElementById('hud-turn-badge');
  const hudStateLabel = document.getElementById('hud-state-label');
  const hudStateDetail = document.getElementById('hud-state-detail');
  const systemStatusText = document.getElementById('system-status-text');
  const systemStatusBadge = document.getElementById('system-status-badge');
  const metricRamVal = document.getElementById('metric-ram-val');
  const metricToolsVal = document.getElementById('metric-tools-val');
  const quickbarAgentList = document.getElementById('quickbar-agent-list');

  // Drawer Elements
  const telemetryDrawer = document.getElementById('telemetry-drawer');
  const btnDrawerClose = document.getElementById('btn-drawer-close');
  const drawerIcon = document.getElementById('drawer-icon');
  const drawerAgentName = document.getElementById('drawer-agent-name');
  const drawerAgentRole = document.getElementById('drawer-agent-role');
  const drawerAgentState = document.getElementById('drawer-agent-state');
  const drawerAgentMode = document.getElementById('drawer-agent-mode');
  const drawerAgentProvider = document.getElementById('drawer-agent-provider');
  const drawerCapabilitiesList = document.getElementById('drawer-capabilities-list');
  const drawerTelemetryFeed = document.getElementById('drawer-telemetry-feed');

  // Voice & Input Controls
  const btnHudMic = document.getElementById('btn-hud-mic');
  const micInstructionLabel = document.getElementById('mic-instruction-label');
  const textPromptForm = document.getElementById('text-prompt-form');
  const hudTextInput = document.getElementById('hud-text-input');
  const dialogueOverlay = document.getElementById('dialogue-overlay');
  const dialogueSpeakerLabel = document.getElementById('dialogue-speaker-label');
  const dialogueContent = document.getElementById('dialogue-content');
  const hudAudioPlayer = document.getElementById('hud-audio-player');
  const hudSttProvider = document.getElementById('hud-stt-provider');
  const hudTtsProvider = document.getElementById('hud-tts-provider');

  // Modals
  const confirmationModal = document.getElementById('confirmation-modal');
  const modalConfirmPrompt = document.getElementById('modal-confirm-prompt');
  const modalConfirmAction = document.getElementById('modal-confirm-action');
  const modalConfirmTool = document.getElementById('modal-confirm-tool');
  const btnModalConfirm = document.getElementById('btn-modal-confirm');
  const btnModalDeny = document.getElementById('btn-modal-deny');

  const addAgentModal = document.getElementById('add-agent-modal');
  const btnAddAgentModal = document.getElementById('btn-add-agent-modal');
  const btnCloseAddAgent = document.getElementById('btn-close-add-agent');
  const formAddAgent = document.getElementById('form-add-agent');

  // Camera Buttons
  const btnCamReset = document.getElementById('btn-cam-reset');
  const btnCamSun = document.getElementById('btn-cam-sun');
  const btnCamZoomIn = document.getElementById('btn-cam-zoom-in');
  const btnCamZoomOut = document.getElementById('btn-cam-zoom-out');

  // =========================================================================
  // Canvas & Resize Setup
  // =========================================================================

  function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    initStars();
  }

  function initStars() {
    stars = [];
    const count = Math.floor((canvas.width * canvas.height) / 2500);
    for (let i = 0; i < count; i++) {
      stars.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        size: Math.random() * 1.8 + 0.3,
        alpha: Math.random() * 0.8 + 0.2,
        twinkleSpeed: Math.random() * 0.02 + 0.005,
      });
    }
  }

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  // =========================================================================
  // UI Status State Transitions (10 States)
  // =========================================================================

  function setUIState(state, detailText) {
    currentUIState = state;
    hudTurnBadge.setAttribute('data-state', state);
    hudStateLabel.textContent = state;

    const details = {
      [UIStates.STANDBY]: 'Ready for voice or text prompt',
      [UIStates.LISTENING]: 'Listening... speak clearly into microphone',
      [UIStates.TRANSCRIBING]: 'Transcribing speech via STT provider...',
      [UIStates.THINKING]: 'DAKU Brain multi-pass reasoning in progress...',
      [UIStates.CONFIRMATION_REQUIRED]: 'Authorization required for sensitive action',
      [UIStates.EXECUTING]: 'Executing tool with verified permissions...',
      [UIStates.SPEAKING]: 'Synthesizing voice response with TTS...',
      [UIStates.FALLBACK]: 'Operating in degraded fallback mode',
      [UIStates.ERROR]: 'Execution error encountered',
      [UIStates.OFFLINE]: 'Backend server unreachable',
    };

    hudStateDetail.textContent = detailText || details[state] || '';

    // Update Central Sun state
    if (state === UIStates.THINKING) {
      CENTRAL_SUN.state = AgentStates.THINKING;
    } else if (state === UIStates.EXECUTING) {
      CENTRAL_SUN.state = AgentStates.EXECUTING;
    } else if (state === UIStates.ERROR) {
      CENTRAL_SUN.state = AgentStates.ERROR;
    } else if (state === UIStates.SPEAKING || state === UIStates.LISTENING) {
      CENTRAL_SUN.state = AgentStates.ACTIVE;
    } else {
      CENTRAL_SUN.state = AgentStates.IDLE;
    }

    renderQuickbar();
    if (activeTarget && activeTarget.id === 'brain') {
      updateDrawer(CENTRAL_SUN);
    }
  }

  // =========================================================================
  // Solar Canvas Render Loop (Keplerian orbits + 3D projection)
  // =========================================================================

  let timeAngle = 0;

  function renderScene() {
    timeAngle += 0.01;

    // Smooth Camera Interpolation
    camera.x += (camera.targetX - camera.x) * 0.08;
    camera.y += (camera.targetY - camera.y) * 0.08;
    camera.zoom += (camera.targetZoom - camera.zoom) * 0.08;

    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 1. Draw Starfield
    ctx.save();
    for (let star of stars) {
      star.alpha += Math.sin(timeAngle * 50 * star.twinkleSpeed) * 0.01;
      const a = Math.max(0.1, Math.min(1.0, star.alpha));
      ctx.fillStyle = `rgba(230, 240, 255, ${a})`;
      ctx.beginPath();
      ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();

    ctx.save();
    // Apply Camera Transform
    ctx.translate(cx, cy);
    ctx.scale(camera.zoom, camera.zoom);
    ctx.translate(-camera.x, -camera.y);

    // 2. Draw Orbital Rings (inclined perspective ellipse)
    const tilt = 0.45; // 3D orbital tilt

    for (let agent of agents) {
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(0, 0, agent.orbitRadius, agent.orbitRadius * tilt, 0, 0, Math.PI * 2);
      ctx.strokeStyle = `${agent.color}22`;
      ctx.lineWidth = 1.2;
      ctx.stroke();

      // Orbit active glow when agent is executing
      if (agent.state === AgentStates.EXECUTING || agent.state === AgentStates.ACTIVE) {
        ctx.strokeStyle = `${agent.color}55`;
        ctx.lineWidth = 2.5;
        ctx.stroke();
      }
      ctx.restore();
    }

    // 3. Update & Draw Central Sun (DAKU Brain)
    drawCentralSun(0, 0);

    // 4. Update & Draw Planetary Agents
    for (let agent of agents) {
      agent.orbitAngle += agent.orbitSpeed;
      const px = Math.cos(agent.orbitAngle) * agent.orbitRadius;
      const py = Math.sin(agent.orbitAngle) * agent.orbitRadius * tilt;

      agent.worldX = px;
      agent.worldY = py;

      drawPlanetaryAgent(agent, px, py);
    }

    ctx.restore();

    requestAnimationFrame(renderScene);
  }

  function drawCentralSun(x, y) {
    ctx.save();
    ctx.translate(x, y);

    const baseRadius = CENTRAL_SUN.radius;
    let pulse = Math.sin(timeAngle * 3) * 3;

    // React to Brain thinking or execution states
    if (currentUIState === UIStates.THINKING) {
      pulse = Math.sin(timeAngle * 12) * 8;
    } else if (currentUIState === UIStates.EXECUTING) {
      pulse = Math.sin(timeAngle * 8) * 6;
    }

    const rad = baseRadius + pulse;

    // Outer Coronal Atmosphere
    const coronaGrad = ctx.createRadialGradient(0, 0, rad * 0.5, 0, 0, rad * 3.5);
    if (currentUIState === UIStates.ERROR) {
      coronaGrad.addColorStop(0, 'rgba(239, 71, 111, 0.8)');
      coronaGrad.addColorStop(0.5, 'rgba(239, 71, 111, 0.25)');
      coronaGrad.addColorStop(1, 'rgba(239, 71, 111, 0)');
    } else if (currentUIState === UIStates.THINKING) {
      coronaGrad.addColorStop(0, 'rgba(255, 0, 127, 0.8)');
      coronaGrad.addColorStop(0.5, 'rgba(255, 140, 0, 0.3)');
      coronaGrad.addColorStop(1, 'rgba(255, 0, 127, 0)');
    } else if (currentUIState === UIStates.LISTENING) {
      coronaGrad.addColorStop(0, 'rgba(0, 229, 255, 0.8)');
      coronaGrad.addColorStop(0.5, 'rgba(0, 150, 255, 0.3)');
      coronaGrad.addColorStop(1, 'rgba(0, 229, 255, 0)');
    } else {
      coronaGrad.addColorStop(0, 'rgba(255, 170, 0, 0.7)');
      coronaGrad.addColorStop(0.5, 'rgba(255, 80, 0, 0.25)');
      coronaGrad.addColorStop(1, 'rgba(255, 80, 0, 0)');
    }

    ctx.fillStyle = coronaGrad;
    ctx.beginPath();
    ctx.arc(0, 0, rad * 3.5, 0, Math.PI * 2);
    ctx.fill();

    // Solar Flares / Rays
    ctx.strokeStyle = 'rgba(255, 200, 0, 0.4)';
    ctx.lineWidth = 1.5;
    const rayCount = 12;
    for (let i = 0; i < rayCount; i++) {
      const angle = (i / rayCount) * Math.PI * 2 + timeAngle * 0.5;
      const rayLen = rad * 1.5 + Math.sin(timeAngle * 5 + i) * 10;
      ctx.beginPath();
      ctx.moveTo(Math.cos(angle) * rad, Math.sin(angle) * rad);
      ctx.lineTo(Math.cos(angle) * rayLen, Math.sin(angle) * rayLen);
      ctx.stroke();
    }

    // Dense Star Core
    const coreGrad = ctx.createRadialGradient(0, 0, 0, 0, 0, rad);
    coreGrad.addColorStop(0, '#ffffff');
    coreGrad.addColorStop(0.3, CENTRAL_SUN.coreColor);
    coreGrad.addColorStop(0.8, CENTRAL_SUN.color);
    coreGrad.addColorStop(1, '#ff3700');

    ctx.fillStyle = coreGrad;
    ctx.beginPath();
    ctx.arc(0, 0, rad, 0, Math.PI * 2);
    ctx.fill();

    // Central Sun Label
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 11px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('DAKU BRAIN', 0, rad + 18);

    ctx.restore();
  }

  function drawPlanetaryAgent(agent, x, y) {
    ctx.save();
    ctx.translate(x, y);

    const rad = agent.radius;

    // Selection or Active Halo
    const isSelected = activeTarget && activeTarget.id === agent.id;
    if (isSelected || agent.state === AgentStates.ACTIVE || agent.state === AgentStates.EXECUTING) {
      ctx.strokeStyle = agent.color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(0, 0, rad * 1.8, 0, Math.PI * 2);
      ctx.stroke();
    }

    // State Pulsing Glow
    if (agent.state === AgentStates.THINKING) {
      ctx.fillStyle = 'rgba(255, 0, 127, 0.3)';
      ctx.beginPath();
      ctx.arc(0, 0, rad * 2.2, 0, Math.PI * 2);
      ctx.fill();
    }

    // Planet Body Gradient (spherical shading)
    const grad = ctx.createRadialGradient(-rad * 0.3, -rad * 0.3, rad * 0.1, 0, 0, rad);
    grad.addColorStop(0, '#ffffff');
    grad.addColorStop(0.3, agent.color);
    grad.addColorStop(1, '#05070d');

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(0, 0, rad, 0, Math.PI * 2);
    ctx.fill();

    // Label & State Indicator
    ctx.fillStyle = '#e6f1ff';
    ctx.font = '10px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(agent.name, 0, rad + 14);

    if (agent.state !== AgentStates.IDLE) {
      ctx.fillStyle = agent.state === AgentStates.ERROR ? '#ef476f' : '#06d6a0';
      ctx.font = '9px monospace';
      ctx.fillText(agent.state, 0, rad + 24);
    }

    ctx.restore();
  }

  // =========================================================================
  // Interactive Camera & Selection
  // =========================================================================

  function focusAgent(target) {
    activeTarget = target;
    if (target.id === 'brain') {
      camera.targetX = 0;
      camera.targetY = 0;
      camera.targetZoom = 1.35;
    } else {
      // Focus on agent's approximate position with moderate zoom
      camera.targetX = target.worldX || 0;
      camera.targetY = target.worldY || 0;
      camera.targetZoom = 1.8;
    }
    updateDrawer(target);
    openDrawer();
    renderQuickbar();
  }

  function resetCamera() {
    activeTarget = null;
    camera.targetX = 0;
    camera.targetY = 0;
    camera.targetZoom = 1.0;
    renderQuickbar();
  }

  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const clickY = e.clientY - rect.top;

    const cx = canvas.width / 2;
    const cy = canvas.height / 2;

    // Convert Screen Space to World Space
    const worldX = (clickX - cx) / camera.zoom + camera.x;
    const worldY = (clickY - cy) / camera.zoom + camera.y;

    // Check Central Sun click
    const distSun = Math.hypot(worldX - 0, worldY - 0);
    if (distSun <= CENTRAL_SUN.radius * 1.5) {
      focusAgent(CENTRAL_SUN);
      return;
    }

    // Check Planetary Agents click
    for (let agent of agents) {
      const dist = Math.hypot(worldX - (agent.worldX || 0), worldY - (agent.worldY || 0));
      if (dist <= agent.radius * 2.2) {
        focusAgent(agent);
        return;
      }
    }
  });

  // Camera Buttons
  btnCamReset.addEventListener('click', resetCamera);
  btnCamSun.addEventListener('click', () => focusAgent(CENTRAL_SUN));
  btnCamZoomIn.addEventListener('click', () => { camera.targetZoom = Math.min(3.5, camera.zoom * 1.3); });
  btnCamZoomOut.addEventListener('click', () => { camera.targetZoom = Math.max(0.4, camera.zoom * 0.7); });

  // =========================================================================
  // Quickbar & Telemetry Drawer
  // =========================================================================

  function renderQuickbar() {
    quickbarAgentList.innerHTML = '';

    // Sun item
    const sunChip = document.createElement('div');
    sunChip.className = `agent-chip ${activeTarget && activeTarget.id === 'brain' ? 'selected' : ''}`;
    sunChip.innerHTML = `
      <div class="chip-left">
        <span class="chip-dot" style="background: ${CENTRAL_SUN.color}; box-shadow: 0 0 6px ${CENTRAL_SUN.color};"></span>
        <span class="chip-name">DAKU Brain</span>
      </div>
      <span class="chip-status">${CENTRAL_SUN.state}</span>
    `;
    sunChip.addEventListener('click', () => focusAgent(CENTRAL_SUN));
    quickbarAgentList.appendChild(sunChip);

    // Orbiting agent items
    for (let ag of agents) {
      const chip = document.createElement('div');
      chip.className = `agent-chip ${activeTarget && activeTarget.id === ag.id ? 'selected' : ''}`;
      chip.innerHTML = `
        <div class="chip-left">
          <span class="chip-dot" style="background: ${ag.color}; box-shadow: 0 0 6px ${ag.color};"></span>
          <span class="chip-name">${ag.name}</span>
        </div>
        <span class="chip-status">${ag.state}</span>
      `;
      chip.addEventListener('click', () => focusAgent(ag));
      quickbarAgentList.appendChild(chip);
    }
  }

  function updateDrawer(entity) {
    drawerIcon.textContent = entity.icon || '🛸';
    drawerAgentName.textContent = entity.name;
    drawerAgentRole.textContent = entity.role;
    drawerAgentState.textContent = entity.state || 'IDLE';
    drawerAgentState.className = `row-value badge-state ${entity.state || 'IDLE'}`;

    drawerAgentMode.textContent = entity.id === 'brain' ? 'Central Autonomous Core' : 'Swarm Sub-Agent Profile';
    drawerAgentProvider.textContent = entity.id === 'brain' ? 'DirectModelRouter + MultiPass' : 'DAKU Tool Dispatch';

    drawerCapabilitiesList.innerHTML = '';
    const tools = entity.tools || [];
    for (let tool of tools) {
      const tag = document.createElement('span');
      tag.className = 'cap-tag';
      tag.textContent = tool;
      drawerCapabilitiesList.appendChild(tag);
    }

    renderTelemetryFeed(entity);
  }

  function renderTelemetryFeed(entity) {
    drawerTelemetryFeed.innerHTML = '';
    const relevant = liveTelemetryFeed.filter(item => !item.agentId || item.agentId === entity.id || entity.id === 'brain');
    if (relevant.length === 0) {
      drawerTelemetryFeed.innerHTML = '<div class="feed-item"><span class="feed-time">--:--:--</span><span class="feed-msg">Agent active. Standing by for instructions.</span></div>';
      return;
    }
    for (let item of relevant.slice(-6).reverse()) {
      const row = document.createElement('div');
      row.className = 'feed-item';
      row.innerHTML = `<span class="feed-time">${item.time}</span><span class="feed-msg">${item.message}</span>`;
      drawerTelemetryFeed.appendChild(row);
    }
  }

  function logTelemetry(agentId, message) {
    const time = new Date().toTimeString().split(' ')[0];
    liveTelemetryFeed.push({ agentId, message, time });
    if (activeTarget) {
      renderTelemetryFeed(activeTarget);
    }
  }

  function openDrawer() {
    telemetryDrawer.classList.remove('drawer-closed');
  }

  function closeDrawer() {
    telemetryDrawer.classList.add('drawer-closed');
  }

  btnDrawerClose.addEventListener('click', closeDrawer);

  // =========================================================================
  // Real DAKU Voice Session & Turn Execution
  // =========================================================================

  async function startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedAudioChunks = [];
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedAudioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(recordedAudioChunks, { type: 'audio/wav' });
        stream.getTracks().forEach(track => track.stop());
        await processVoiceAudio(audioBlob);
      };

      mediaRecorder.start();
      isRecording = true;
      btnHudMic.classList.add('recording');
      micInstructionLabel.textContent = 'Recording... Click to finish';
      setUIState(UIStates.LISTENING, 'Listening to your voice input...');
      logTelemetry('brain', 'Voice turn initiated: recording audio');
    } catch (err) {
      console.warn('Browser mic unavailable or permission denied. Prompting for text turn:', err);
      // Fallback to text prompt turn
      const prompt = window.prompt('Microphone input is unavailable. Enter your command for DAKU:');
      if (prompt && prompt.trim()) {
        dispatchTurn(prompt.trim());
      } else {
        setUIState(UIStates.STANDBY);
      }
    }
  }

  function stopRecording() {
    if (mediaRecorder && isRecording) {
      mediaRecorder.stop();
      isRecording = false;
      btnHudMic.classList.remove('recording');
      micInstructionLabel.textContent = 'Processing Voice Turn...';
      setUIState(UIStates.TRANSCRIBING, 'Transcribing recorded audio...');
    }
  }

  btnHudMic.addEventListener('click', () => {
    if (!isRecording) {
      startRecording();
    } else {
      stopRecording();
    }
  });

  async function processVoiceAudio(audioBlob) {
    const reader = new FileReader();
    reader.readAsDataURL(audioBlob);
    reader.onloadend = async () => {
      const base64Audio = reader.result.split(',')[1];
      await dispatchTurn(null, base64Audio);
    };
  }

  textPromptForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const text = hudTextInput.value.trim();
    if (!text) return;
    hudTextInput.value = '';
    dispatchTurn(text);
  });

  async function dispatchTurn(textInput, audioBase64) {
    setUIState(audioBase64 ? UIStates.TRANSCRIBING : UIStates.THINKING);

    showDialogue('USER', textInput || '(Voice Audio Input)');

    // Assign visual agent states based on intent keyword heuristics
    if (textInput) {
      const low = textInput.toLowerCase();
      if (low.includes('search') || low.includes('browser') || low.includes('find') || low.includes('url')) {
        setAgentState('researcher', AgentStates.ACTIVE);
      } else if (low.includes('code') || low.includes('launch') || low.includes('run') || low.includes('file')) {
        setAgentState('coder', AgentStates.ACTIVE);
      } else if (low.includes('look') || low.includes('view') || low.includes('title') || low.includes('inspect')) {
        setAgentState('vision', AgentStates.ACTIVE);
      } else {
        setAgentState('strategist', AgentStates.ACTIVE);
      }
    }

    try {
      const payload = {};
      if (textInput) payload.text = textInput;
      if (audioBase64) payload.audio_base64 = audioBase64;

      const res = await fetch('/api/hud/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const data = await res.json();

      // Check if STT was performed
      if (data.transcript) {
        showDialogue('USER (Transcribed)', data.transcript);
        logTelemetry('brain', `STT transcribed: "${data.transcript}" via ${data.stt_provider || 'Sarvam Saaras'}`);
      }

      // Check if permission confirmation is required
      if (data.requires_confirmation) {
        setUIState(UIStates.CONFIRMATION_REQUIRED, 'Sensitive action requires confirmation');
        triggerConfirmationModal(data.pending_action);
        return;
      }

      // Tool execution state
      if (data.executed_tools && data.executed_tools.length > 0) {
        setUIState(UIStates.EXECUTING, `Executed tool: ${data.executed_tools.join(', ')}`);
        for (let t of data.executed_tools) {
          logTelemetry('coder', `Tool execution verified: ${t}`);
        }
      }

      // Speech synthesis & dialogue output
      const reply = data.response || 'Action completed.';
      showDialogue('DAKU BRAIN', reply);
      logTelemetry('brain', `Brain reply generated (${data.elapsed_seconds || '0.1'}s)`);

      // Audio Playback
      if (data.audio_base64) {
        setUIState(UIStates.SPEAKING, `Speaking via ${data.tts_provider || 'Sarvam Bulbul'}`);
        await playAudioBase64(data.audio_base64);
      } else if (data.tts_provider === 'windows_sapi') {
        setUIState(UIStates.SPEAKING, 'Spoken via Windows SAPI native audio');
      } else {
        setUIState(UIStates.STANDBY);
      }

      // Reset agent states to IDLE
      setTimeout(() => {
        resetAllAgentStates();
        setUIState(UIStates.STANDBY);
      }, 3000);

    } catch (err) {
      console.error('Turn dispatch error:', err);
      setUIState(UIStates.ERROR, `Failed: ${err.message}`);
      showDialogue('DAKU ERROR', `Error during turn: ${err.message}`);
      logTelemetry('brain', `Execution error: ${err.message}`);
      setTimeout(() => setUIState(UIStates.STANDBY), 4000);
    }
  }

  function setAgentState(agentId, state) {
    const ag = agents.find(a => a.id === agentId);
    if (ag) {
      ag.state = state;
      renderQuickbar();
    }
  }

  function resetAllAgentStates() {
    for (let a of agents) a.state = AgentStates.IDLE;
    renderQuickbar();
  }

  function showDialogue(speaker, text) {
    dialogueSpeakerLabel.textContent = speaker;
    dialogueContent.textContent = text;
    dialogueOverlay.classList.remove('dialogue-hidden');
    clearTimeout(dialogueOverlay._hideTimer);
    dialogueOverlay._hideTimer = setTimeout(() => {
      dialogueOverlay.classList.add('dialogue-hidden');
    }, 8000);
  }

  async function playAudioBase64(b64) {
    return new Promise((resolve) => {
      try {
        hudAudioPlayer.src = `data:audio/wav;base64,${b64}`;
        hudAudioPlayer.onended = () => {
          setUIState(UIStates.STANDBY);
          resolve();
        };
        hudAudioPlayer.onerror = () => {
          setUIState(UIStates.STANDBY);
          resolve();
        };
        hudAudioPlayer.play().catch(e => {
          console.warn('Audio autoplay blocked or failed:', e);
          setUIState(UIStates.STANDBY);
          resolve();
        });
      } catch (e) {
        setUIState(UIStates.STANDBY);
        resolve();
      }
    });
  }

  // =========================================================================
  // Confirmation Modal Flow (3-Tier Security Boundary)
  // =========================================================================

  function triggerConfirmationModal(pendingAction) {
    pendingConfirmationAction = pendingAction;
    modalConfirmAction.textContent = pendingAction.action || 'Execute Action';
    modalConfirmTool.textContent = pendingAction.tool || 'application_tool';
    modalConfirmPrompt.textContent = pendingAction.prompt || 'DAKU requests authorization to proceed.';
    confirmationModal.classList.remove('modal-hidden');
  }

  btnModalConfirm.addEventListener('click', async () => {
    confirmationModal.classList.add('modal-hidden');
    await resolveConfirmation(true);
  });

  btnModalDeny.addEventListener('click', async () => {
    confirmationModal.classList.add('modal-hidden');
    await resolveConfirmation(false);
  });

  async function resolveConfirmation(confirmed) {
    try {
      setUIState(confirmed ? UIStates.EXECUTING : UIStates.STANDBY);
      const res = await fetch('/api/confirm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action_id: pendingConfirmationAction ? pendingConfirmationAction.id : 'action-1',
          confirmed: confirmed,
        }),
      });
      const data = await res.json();
      logTelemetry('brain', `Permission authorization result: ${data.message || (confirmed ? 'Authorized' : 'Denied')}`);
      showDialogue('DAKU SECURITY', data.message || (confirmed ? 'Action confirmed.' : 'Action denied.'));
      setTimeout(() => setUIState(UIStates.STANDBY), 2000);
    } catch (err) {
      setUIState(UIStates.ERROR, 'Failed to resolve confirmation');
    }
  }

  // =========================================================================
  // Add Agent Visual Profile Modal (Subject to Security Constraints)
  // =========================================================================

  btnAddAgentModal.addEventListener('click', () => {
    addAgentModal.classList.remove('modal-hidden');
  });

  btnCloseAddAgent.addEventListener('click', () => {
    addAgentModal.classList.add('modal-hidden');
  });

  formAddAgent.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = document.getElementById('input-agent-name').value.trim();
    const capabilityKey = document.getElementById('select-agent-capability').value;
    const color = document.getElementById('input-agent-color').value;
    const desc = document.getElementById('input-agent-desc').value.trim();

    if (!name) return;

    const capabilityMap = {
      research: { role: 'Custom Research Profile', tools: ['browser_tool', 'file_tool'], icon: '🌐' },
      coding: { role: 'Custom Coding Profile', tools: ['application_tool', 'system_tool'], icon: '⚙️' },
      vision: { role: 'Custom Vision Profile', tools: ['browser_tool (inspection)'], icon: '🔭' },
      planning: { role: 'Custom Planning Profile', tools: ['TaskPlanner'], icon: '📊' },
    };

    const capInfo = capabilityMap[capabilityKey] || capabilityMap.research;

    // Safe UI profile addition
    const newProfile = {
      id: `agent-custom-${Date.now()}`,
      name: name,
      role: capInfo.role,
      capability: desc || capInfo.role,
      tools: capInfo.tools,
      color: color,
      radius: 12,
      orbitRadius: 450 + (agents.length - 4) * 50,
      orbitSpeed: 0.002,
      orbitAngle: Math.random() * Math.PI * 2,
      state: AgentStates.IDLE,
      icon: capInfo.icon,
      description: desc || 'Custom UI agent profile',
    };

    agents.push(newProfile);
    renderQuickbar();
    addAgentModal.classList.add('modal-hidden');
    formAddAgent.reset();

    // Persist safe profile to backend
    try {
      await fetch('/api/hud/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ profile: newProfile }),
      });
    } catch (e) {
      console.warn('Profile local sync only:', e);
    }

    logTelemetry('brain', `Configured UI-level visual profile for "${name}". Governed by existing permissions.`);
  });

  // =========================================================================
  // Telemetry Polling & Health Sync
  // =========================================================================

  async function pollSystemHealth() {
    try {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        systemStatusText.textContent = 'ONLINE';
        systemStatusBadge.querySelector('.status-dot').style.background = '#06d6a0';

        if (data.system && data.system.ram_used_mb) {
          metricRamVal.textContent = `${data.system.ram_used_mb} MB`;
        }
        if (data.tools && data.tools.count) {
          metricToolsVal.textContent = `${data.tools.count} Ready`;
        }
      } else {
        throw new Error('Non-200 status');
      }
    } catch (err) {
      systemStatusText.textContent = 'OFFLINE';
      systemStatusBadge.querySelector('.status-dot').style.background = '#ef476f';
    }
  }

  async function initHUD() {
    // Initial fetch of real agent capability telemetry from DAKU
    try {
      const res = await fetch('/api/hud/agents');
      if (res.ok) {
        const data = await res.json();
        if (data.stt_provider) hudSttProvider.textContent = data.stt_provider;
        if (data.tts_provider) hudTtsProvider.textContent = data.tts_provider;
      }
    } catch (e) {
      // Running offline or dev
    }

    renderQuickbar();
    updateDrawer(CENTRAL_SUN);
    setInterval(pollSystemHealth, 5000);
    pollSystemHealth();
    renderScene();
  }

  initHUD();
})();
