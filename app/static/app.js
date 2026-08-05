const socket = io();
const activeAlerts = new Map();

const state = {
  running: false,
  lastAnalysisAt: null,
  lastFrameCounter: 0,
  fpsSamples: [],
  model: null,
  features: [],
  overlay: {},
  settings: {},
  events: [],
  eventKeys: new Set(),
  riskArea: null,
  riskEditor: {
    active: false,
    points: [],
  },
};

const els = {
  app: document.getElementById('app'),
  messageBar: document.getElementById('messageBar'),
  backendStatus: document.getElementById('backendStatus'),
  connectionStatus: document.getElementById('connectionStatus'),
  monitorStatus: document.getElementById('monitorStatus'),
  videoStatus: document.getElementById('videoStatus'),
  frameCounter: document.getElementById('frameCounter'),
  fpsCounter: document.getElementById('fpsCounter'),
  streamBadge: document.getElementById('streamBadge'),
  personBadge: document.getElementById('personBadge'),
  detectionBadge: document.getElementById('detectionBadge'),
  activeCount: document.getElementById('activeCount'),
  modelStatus: document.getElementById('modelStatus'),
  modelClasses: document.getElementById('modelClasses'),
  startBtn: document.getElementById('startBtn'),
  stopBtn: document.getElementById('stopBtn'),
  operatorModeBtn: document.getElementById('operatorModeBtn'),
  technicalModeBtn: document.getElementById('technicalModeBtn'),
  refreshPreflightBtn: document.getElementById('refreshPreflightBtn'),
  refreshEventsBtn: document.getElementById('refreshEventsBtn'),
  saveSettingsBtn: document.getElementById('saveSettingsBtn'),
  features: document.getElementById('features'),
  overlayControls: document.getElementById('overlayControls'),
  settingsPanel: document.getElementById('settingsPanel'),
  compliance: document.getElementById('compliance'),
  personCards: document.getElementById('personCards'),
  activeAlerts: document.getElementById('activeAlerts'),
  alerts: document.getElementById('alerts'),
  preflight: document.getElementById('preflight'),
  statusFilter: document.getElementById('statusFilter'),
  severityFilter: document.getElementById('severityFilter'),
  eventTimeline: document.getElementById('eventTimeline'),
  videoWrap: document.getElementById('videoWrap'),
  videoFeed: document.getElementById('videoFeed'),
  riskEditorCanvas: document.getElementById('riskEditorCanvas'),
  riskEditBtn: document.getElementById('riskEditBtn'),
  riskClearBtn: document.getElementById('riskClearBtn'),
  riskResetBtn: document.getElementById('riskResetBtn'),
  riskSaveBtn: document.getElementById('riskSaveBtn'),
  riskEditorStatus: document.getElementById('riskEditorStatus'),
};

const FEATURE_PROFILES = {
  basic: { ppe: false, helmet: false, vest: false, gloves: false, pose: true, falls: true, posture: true, risk_area: false },
  epi: { ppe: true, helmet: true, vest: true, gloves: true, pose: true, falls: false, posture: false, risk_area: false },
  risk: { ppe: false, helmet: false, vest: false, gloves: false, pose: true, falls: true, posture: true, risk_area: true },
  full: { ppe: true, helmet: true, vest: true, gloves: true, pose: true, falls: true, posture: true, risk_area: true },
};

const OVERLAY_LABELS = {
  boxes: 'Bounding boxes',
  labels: 'Labels',
  confidence: 'Confiança',
  pose: 'Pontos de pose',
  risk_area: 'Zona de risco',
};

socket.on('connect', () => {
  setCardStatus('socketCard', 'ok');
  els.connectionStatus.textContent = 'Conectado';
  refreshStatus();
  refreshPreflight();
  loadRuntime();
  loadEvents();
});

socket.on('disconnect', () => {
  setCardStatus('socketCard', 'error');
  els.connectionStatus.textContent = 'Desconectado';
});

socket.on('monitor_status', applyStatus);
socket.on('features_updated', payload => {
  state.features = payload.features || [];
  renderFeatures(state.features);
});
socket.on('model_diagnostics', renderModelStatus);
socket.on('settings_updated', settings => {
  state.settings = settings || {};
  renderSettings(state.settings);
});
socket.on('overlay_updated', overlay => {
  state.overlay = overlay || {};
  renderOverlay(state.overlay);
});
socket.on('risk_area_updated', riskArea => {
  applyRiskArea(riskArea);
  pushTimeline({ event_type: 'risk_area_updated', severity: 'info', message: 'Área de risco atualizada', created_at: new Date().toISOString() });
});
socket.on('timeline_event', pushTimeline);
socket.on('compliance_state', renderCompliance);
socket.on('active_alerts', payload => renderActiveAlerts(payload.items || []));
socket.on('alert_created', alert => {
  upsertActiveAlert(alert);
  addHistoryAlert(alert);
});
socket.on('alert_updated', alert => {
  upsertActiveAlert(alert);
  updateHistoryAlert(alert);
});
socket.on('alert_resolved', alert => {
  removeActiveAlert(alert);
  addHistoryAlert(alert);
});
socket.on('alert', upsertActiveAlert);
socket.on('analysis', payload => {
  if (payload?.alerts) renderActiveAlerts(payload.alerts);
  if (payload?.compliance) renderCompliance(payload.compliance);
  if (payload?.model) renderModelStatus(payload.model);
  renderDetections(payload?.detections || [], payload?.pose, payload?.compliance);
  refreshStatusLightweight(payload);
});

els.startBtn.addEventListener('click', async () => {
  await refreshPreflight();
  const res = await fetch('/start', { method: 'POST' });
  applyStatus(await res.json());
  refreshPreflight();
  loadEvents();
});

els.stopBtn.addEventListener('click', async () => {
  const res = await fetch('/stop', { method: 'POST' });
  applyStatus(await res.json());
});

els.refreshPreflightBtn.addEventListener('click', refreshPreflight);
if (els.refreshEventsBtn) els.refreshEventsBtn.addEventListener('click', loadEvents);
els.operatorModeBtn.addEventListener('click', () => setMode('operator'));
els.technicalModeBtn.addEventListener('click', () => setMode('technical'));
if (els.statusFilter) els.statusFilter.addEventListener('change', loadAlerts);
if (els.severityFilter) els.severityFilter.addEventListener('change', loadAlerts);
if (els.saveSettingsBtn) els.saveSettingsBtn.addEventListener('click', saveSettings);
if (els.riskEditBtn) els.riskEditBtn.addEventListener('click', toggleRiskEditor);
if (els.riskClearBtn) els.riskClearBtn.addEventListener('click', clearRiskEditor);
if (els.riskResetBtn) els.riskResetBtn.addEventListener('click', loadRiskArea);
if (els.riskSaveBtn) els.riskSaveBtn.addEventListener('click', saveRiskArea);
if (els.riskEditorCanvas) els.riskEditorCanvas.addEventListener('click', addRiskPointFromClick);
window.addEventListener('resize', drawRiskEditor);

if (els.videoFeed) {
  els.videoFeed.addEventListener('load', drawRiskEditor);
}

document.querySelectorAll('.profile-btn').forEach(button => {
  button.addEventListener('click', async () => {
    const profile = button.dataset.profile;
    if (!FEATURE_PROFILES[profile]) return;
    await updateFeatures(FEATURE_PROFILES[profile]);
  });
});

function setMode(mode) {
  const technical = mode === 'technical';
  els.app.classList.toggle('operator-mode', !technical);
  els.app.classList.toggle('technical-mode', technical);
  els.operatorModeBtn.classList.toggle('active', !technical);
  els.technicalModeBtn.classList.toggle('active', technical);
  drawRiskEditor();
}

async function refreshStatus() {
  try {
    const res = await fetch('/status');
    const payload = await res.json();
    setCardStatus('backendCard', 'ok');
    els.backendStatus.textContent = 'Online';
    applyStatus(payload);
  } catch (error) {
    setCardStatus('backendCard', 'error');
    els.backendStatus.textContent = 'Erro';
    showMessage('Não foi possível consultar o backend.', 'error');
  }
}

async function refreshPreflight() {
  try {
    const res = await fetch('/preflight');
    const payload = await res.json();
    renderPreflight(payload);
    return payload;
  } catch (error) {
    renderPreflight({ checks: [{ key: 'preflight', label: 'Checklist', status: 'error', message: 'Falha ao executar checklist' }] });
    return null;
  }
}

async function loadRuntime() {
  try {
    const res = await fetch('/settings');
    const payload = await res.json();
    state.settings = payload.settings || {};
    state.overlay = payload.overlay || {};
    renderSettings(state.settings);
    renderOverlay(state.overlay);
    await loadRiskArea();
  } catch (error) {
    showMessage('Não foi possível carregar configurações runtime.', 'warning');
  }
}

async function loadFeatures() {
  const res = await fetch('/features');
  const payload = await res.json();
  state.features = payload.features || [];
  renderFeatures(state.features);
}

async function updateFeatures(features) {
  const res = await fetch('/features', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ features })
  });
  const payload = await res.json();
  state.features = payload.features || state.features;
  renderFeatures(state.features);
  refreshStatus();
}

async function loadAlerts() {
  renderActiveAlerts([...activeAlerts.values()]);
  const params = new URLSearchParams({ limit: '50' });
  if (els.statusFilter?.value) params.set('status', els.statusFilter.value);
  if (els.severityFilter?.value) params.set('severity', els.severityFilter.value);
  const res = await fetch(`/alerts?${params.toString()}`);
  const payload = await res.json();
  els.alerts.innerHTML = '';
  (payload.items || []).reverse().forEach(addHistoryAlert);
}

async function loadEvents() {
  if (!els.eventTimeline) return;
  try {
    const res = await fetch('/events?limit=80&event_type=alert_resolved');
    const payload = await res.json();
    state.events = [];
    state.eventKeys.clear();
    (payload.items || []).reverse().forEach(pushTimeline);
  } catch (error) {
    els.eventTimeline.innerHTML = '<div class="empty-state">Linha do tempo indisponível.</div>';
  }
}

function applyStatus(payload) {
  state.running = Boolean(payload.running);
  els.monitorStatus.textContent = state.running ? 'Ativo' : 'Parado';
  setCardStatus('monitorCard', state.running ? 'ok' : 'warn');
  els.frameCounter.textContent = String(payload.frame_counter || 0);
  state.lastFrameCounter = payload.frame_counter || state.lastFrameCounter;
  if (payload.features) {
    state.features = Object.values(payload.features);
    renderFeatures(state.features);
  }
  if (payload.model) renderModelStatus(payload.model);
  if (payload.active_alerts) renderActiveAlerts(payload.active_alerts);
  if (payload.overlay) {
    state.overlay = payload.overlay;
    renderOverlay(state.overlay);
  }
  if (payload.settings) {
    state.settings = payload.settings;
    renderSettings(state.settings);
  }
  if (payload.risk_area) applyRiskArea(payload.risk_area);
  if (payload.cleanup) showCleanupMessage(payload.cleanup);
}

function refreshStatusLightweight(payload) {
  const now = Date.now();
  if (state.lastAnalysisAt) {
    const delta = Math.max(1, now - state.lastAnalysisAt);
    state.fpsSamples.push(1000 / delta);
    if (state.fpsSamples.length > 20) state.fpsSamples.shift();
    const avg = state.fpsSamples.reduce((a, b) => a + b, 0) / state.fpsSamples.length;
    els.fpsCounter.textContent = avg.toFixed(1);
  }
  state.lastAnalysisAt = now;
  state.lastFrameCounter += 1;
  els.frameCounter.textContent = String(state.lastFrameCounter);
  setVideoState('ok', 'recebendo');
}

function renderFeatures(features) {
  const order = ['ppe', 'helmet', 'vest', 'gloves', 'pose', 'falls', 'posture', 'risk_area'];
  const grouped = [...features].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
  els.features.innerHTML = '';
  grouped.forEach(feature => {
    const support = featureSupportMessage(feature.key);
    const item = document.createElement('label');
    const checked = Boolean(feature.enabled);
    item.className = `feature-card ${checked ? 'enabled' : 'off'} ${support.disabled ? 'disabled' : ''}`;
    item.innerHTML = `
      <input type="checkbox" ${checked ? 'checked' : ''} data-key="${escapeHtml(feature.key)}" aria-label="${escapeHtml(feature.label)}">
      <span class="feature-icon" aria-hidden="true">${featureIcon(feature.key)}</span>
      <span class="feature-copy">
        <strong>${escapeHtml(feature.label)}</strong>
        <small>${escapeHtml(shortFeatureDescription(feature))}</small>
        <em>${escapeHtml(support.message)}</em>
      </span>
      <span class="feature-state">${checked ? 'Ativo' : 'Inativo'}</span>
    `;
    item.querySelector('input').addEventListener('change', async (event) => {
      await updateFeatures({ [feature.key]: event.target.checked });
    });
    els.features.appendChild(item);
  });
}

function shortFeatureDescription(feature) {
  const map = {
    ppe: 'Grupo de EPI',
    helmet: 'Proteção da cabeça',
    vest: 'Proteção visual',
    gloves: 'Proteção das mãos',
    pose: 'Pontos corporais',
    falls: 'Pessoa caída',
    posture: 'Postura suspeita',
    risk_area: 'Zona configurável',
  };
  return map[feature.key] || feature.description || '';
}

function featureIcon(key) {
  const icons = {
    ppe: '<svg viewBox="0 0 24 24"><path d="M4 12a8 8 0 0 1 16 0v2h1v3H3v-3h1v-2Zm3 2h10v-2a5 5 0 0 0-10 0v2Z"/></svg>',
    helmet: '<svg viewBox="0 0 24 24"><path d="M5 13a7 7 0 0 1 14 0v1h2v3H3v-3h2v-1Zm3 1h8v-1a4 4 0 0 0-8 0v1Z"/></svg>',
    vest: '<svg viewBox="0 0 24 24"><path d="M8 3h3l1 3 1-3h3l4 5-2 3v10H6V11L4 8l4-5Zm1 8v7h2v-7H9Zm4 0v7h2v-7h-2Z"/></svg>',
    gloves: '<svg viewBox="0 0 24 24"><path d="M7 3a2 2 0 0 1 2 2v5h1V4a2 2 0 0 1 4 0v6h1V6a2 2 0 0 1 4 0v7c0 5-3 8-7 8s-7-3-7-8V5a2 2 0 0 1 2-2Z"/></svg>',
    pose: '<svg viewBox="0 0 24 24"><path d="M12 5a3 3 0 1 0 0-1 3 3 0 0 0 0 1Zm-5 6 4-2h2l4 2v3l-3-1v8h-4v-8l-3 1v-3Z"/></svg>',
    falls: '<svg viewBox="0 0 24 24"><path d="M7 6a3 3 0 1 1 6 0 3 3 0 0 1-6 0Zm1 8 4-4 3 3 5 1-1 3-5-1-4 4-6-1 1-3 3-2Z"/></svg>',
    posture: '<svg viewBox="0 0 24 24"><path d="M12 4a3 3 0 1 1 0 6 3 3 0 0 1 0-6Zm-2 8h4l3 8h-3l-2-5-2 5H7l3-8Z"/></svg>',
    risk_area: '<svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Zm1 14h-2v2h2v-2Zm0-7h-2v5h2v-5Z"/></svg>',
  };
  return icons[key] || '<svg viewBox="0 0 24 24"><path d="M4 4h16v16H4z"/></svg>';
}

function featureSupportMessage(key) {
  if (!state.model) return { message: 'Aguardando diagnóstico', disabled: false };
  const supported = state.model.supported_ppe || {};
  if (['helmet', 'vest', 'gloves'].includes(key) && !supported[key]) {
    return { message: 'Indisponível no modelo YOLO atual', disabled: false };
  }
  if (key === 'ppe' && !state.model.ppe_ready) return { message: 'Ativo, mas aguardando modelo PPE completo', disabled: false };
  if (key === 'pose' || key === 'falls' || key === 'posture') return { message: 'Disponível via MediaPipe', disabled: false };
  if (key === 'risk_area') return { message: 'Disponível por zona configurável + YOLO pessoa', disabled: false };
  return { message: 'Disponível', disabled: false };
}

function renderOverlay(overlay) {
  if (!els.overlayControls) return;
  els.overlayControls.innerHTML = '';
  Object.entries(OVERLAY_LABELS).forEach(([key, label]) => {
    const item = document.createElement('label');
    item.className = 'feature-item';
    item.innerHTML = `
      <input type="checkbox" ${overlay[key] !== false ? 'checked' : ''} data-key="${escapeHtml(key)}">
      <span><strong>${escapeHtml(label)}</strong><small>Controle visual dentro do vídeo</small></span>
    `;
    item.querySelector('input').addEventListener('change', async event => {
      await updateOverlay({ [key]: event.target.checked });
    });
    els.overlayControls.appendChild(item);
  });
}

async function updateOverlay(overlay) {
  const res = await fetch('/overlay', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(overlay),
  });
  const payload = await res.json();
  state.overlay = payload.overlay || state.overlay;
  renderOverlay(state.overlay);
}

function renderSettings(settings) {
  if (!els.settingsPanel) return;
  const fields = [
    ['target_fps', 'FPS alvo', 'number'],
    ['jpeg_quality', 'Qualidade JPEG', 'number'],
    ['yolo_confidence', 'Confiança YOLO', 'number', '0.05'],
    ['yolo_max_detections', 'Máx. detecções YOLO', 'number'],
    ['alert_create_after_frames', 'Frames para criar alerta', 'number'],
    ['alert_resolve_after_frames', 'Frames para resolver alerta', 'number'],
    ['snapshot_jpeg_quality', 'Qualidade do snapshot', 'number'],
    ['multi_person_detection', 'Multi-pessoa via YOLO', 'checkbox'],
    ['cleanup_on_monitor_start', 'Limpar arquivos ao iniciar', 'checkbox'],
    ['snapshot_enabled', 'Salvar snapshot de alerta', 'checkbox'],
  ];
  els.settingsPanel.innerHTML = fields.map(([key, label, type, step]) => {
    const value = settings[key];
    if (type === 'checkbox') {
      return `<label><span>${escapeHtml(label)}</span><input data-setting="${key}" type="checkbox" ${value ? 'checked' : ''}></label>`;
    }
    return `<label><span>${escapeHtml(label)}</span><input data-setting="${key}" type="number" step="${step || '1'}" value="${escapeHtml(value ?? '')}"></label>`;
  }).join('');
}

async function saveSettings() {
  const updates = {};
  els.settingsPanel.querySelectorAll('[data-setting]').forEach(input => {
    const key = input.dataset.setting;
    updates[key] = input.type === 'checkbox' ? input.checked : Number(input.value);
  });
  const res = await fetch('/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  const payload = await res.json();
  state.settings = payload.settings || state.settings;
  renderSettings(state.settings);
  showMessage('Configurações runtime salvas.', 'ok');
  loadEvents();
}

function renderModelStatus(model) {
  if (!model) return;
  state.model = model;
  const supported = model.supported_ppe || {};
  const statusClass = model.error ? 'error' : model.ppe_ready ? 'ok' : 'warn';
  const statusText = model.ppe_ready ? 'Modelo PPE completo' : model.error ? 'Modelo indisponível' : 'Modelo PPE incompleto';
  const parts = [
    `<strong>${escapeHtml(statusText)}</strong>`,
    `arquivo: ${escapeHtml(model.model_path || 'indefinido')}`,
    `pessoa: ${model.person_supported ? 'suportado' : 'não suportado'}`,
    `multi-pessoa: ${model.multi_person_detection ? 'ativo' : 'inativo'}`,
    `máx. detecções: ${escapeHtml(model.max_detections ?? '-')}`,
    `capacete: ${supported.helmet ? 'suportado' : 'não suportado'}`,
    `colete: ${supported.vest ? 'suportado' : 'não suportado'}`,
    `luvas: ${supported.gloves ? 'suportado' : 'não suportado'}`,
  ];
  els.modelStatus.innerHTML = parts.join('<br>');
  els.modelStatus.className = `model-status ${statusClass}`;

  if (els.modelClasses) {
    const classes = model.classes || [];
    els.modelClasses.innerHTML = classes.length
      ? classes.slice(0, 140).map(item => `<span class="class-chip">${escapeHtml(item.id)} · ${escapeHtml(item.normalized || item.name)}</span>`).join('')
      : '<span class="class-chip">Nenhuma classe disponível</span>';
  }

  if (model.warning) showMessage(model.warning, statusClass === 'error' ? 'error' : 'warning');
  else hideMessage();
  renderFeatures(state.features);
}

function renderCompliance(statePayload) {
  if (!statePayload) return;
  const items = [];
  const ppe = statePayload.ppe || {};
  ['helmet', 'vest', 'gloves'].forEach(key => {
    const item = ppe[key];
    if (!item) return;
    items.push(complianceCard(item.label, item.message, item.status, item.supported));
  });
  if (statePayload.pose) items.push(complianceCard('Pose', statePayload.pose.message, statePayload.pose.status, true));
  if (statePayload.risk_area) items.push(complianceCard('Área de risco', statePayload.risk_area.message, statePayload.risk_area.status, true));
  els.compliance.innerHTML = items.length ? items.join('') : '<div class="empty-state">Aguardando análise.</div>';
  if (statePayload.people) renderPersonCompliance(statePayload.people, statePayload.person_count || 0);
}

function complianceCard(label, message, status, supported) {
  const detail = supported === false ? 'Modelo incompatível' : message;
  return `
    <div class="compliance-card ${escapeHtml(status)}">
      <strong>${escapeHtml(label)}</strong>
      <span>${escapeHtml(detail || status)}</span>
    </div>
  `;
}

function renderDetections(detections, pose, compliance) {
  const people = detections.filter(item => item.label === 'person' || item.category === 'person');
  const posePerson = Boolean(pose?.found) && people.length === 0;
  const personCount = compliance?.person_count ?? people.length + (posePerson ? 1 : 0);
  els.personBadge.textContent = `${personCount} pessoa${personCount === 1 ? '' : 's'}`;
  els.detectionBadge.textContent = `${detections.length} detecção${detections.length === 1 ? '' : 'ões'}`;
  if (compliance?.people?.length) return renderPersonCompliance(compliance.people, personCount);

  if (!detections.length && !posePerson) {
    els.personCards.innerHTML = '<div class="empty-state">Nenhuma detecção recebida no frame atual.</div>';
    return;
  }
  const cards = [];
  if (posePerson) {
    cards.push(`<article class="person-card"><strong>Pessoa 1</strong><span>Inferida por pose MediaPipe. Para múltiplas pessoas, use YOLO com classe person ativa.</span><div class="metrics"><span class="metric">Pose: detectada</span></div></article>`);
  }
  people.forEach((person, index) => {
    cards.push(`<article class="person-card"><strong>Pessoa ${index + 1}</strong><span>Confiança ${(Number(person.confidence || 0) * 100).toFixed(1)}% · box ${formatBox(person.box)}</span><div class="metrics"><span class="metric">Multi-pessoa via YOLO</span></div></article>`);
  });
  els.personCards.innerHTML = cards.join('') || '<div class="empty-state">Pessoa ainda não detectada.</div>';
}

function renderPersonCompliance(people, count) {
  els.personBadge.textContent = `${count || people.length} pessoa${(count || people.length) === 1 ? '' : 's'}`;
  if (!people.length) {
    els.personCards.innerHTML = '<div class="empty-state">Nenhuma pessoa detectada pelo YOLO no frame atual.</div>';
    return;
  }
  els.personCards.innerHTML = people.map(person => {
    const ppe = person.ppe || {};
    const metrics = ['helmet', 'vest', 'gloves'].map(key => {
      const item = ppe[key] || {};
      return `<span class="metric ${escapeHtml(item.status || '')}">${translateLabel(key)}: ${escapeHtml(item.message || item.status || '-')}</span>`;
    }).join('');
    return `
      <article class="person-card">
        <strong>${escapeHtml(person.label || person.id)}</strong>
        <span>Confiança ${(Number(person.confidence || 0) * 100).toFixed(1)}% · box ${formatBox(person.box)}</span>
        <div class="metrics">${metrics}<span class="metric">Risco: ${escapeHtml(person.risk_area?.message || 'não avaliado')}</span></div>
      </article>
    `;
  }).join('');
}

function renderActiveAlerts(alerts) {
  activeAlerts.clear();
  (alerts || []).forEach(alert => {
    if (alert.status !== 'resolved') activeAlerts.set(alert.key || `${alert.rule}:${alert.feature}`, alert);
  });
  drawActiveAlerts();
}

function upsertActiveAlert(alert) {
  if (!alert || !alert.message || alert.status === 'resolved') return;
  activeAlerts.set(alert.key || `${alert.rule}:${alert.feature}`, alert);
  drawActiveAlerts();
}

function removeActiveAlert(alert) {
  if (!alert) return;
  activeAlerts.delete(alert.key || `${alert.rule}:${alert.feature}`);
  drawActiveAlerts();
}

function drawActiveAlerts() {
  els.activeAlerts.innerHTML = '';
  const values = [...activeAlerts.values()];
  els.activeCount.textContent = String(values.length);
  els.activeCount.className = `badge ${values.length ? 'error' : 'ok'}`;
  if (!values.length) {
    els.activeAlerts.innerHTML = '<div class="empty-state">Nenhum alerta ativo.</div>';
    return;
  }
  severityOrder(values).forEach(alert => els.activeAlerts.appendChild(alertNode(alert, { active: true })));
}

function addHistoryAlert(alert) {
  if (!alert || !alert.message || !els.alerts) return;
  const existing = els.alerts.querySelector(`[data-alert-id="${alert.id}"]`);
  if (existing) existing.remove();
  els.alerts.prepend(alertNode(alert, { active: false }));
  while (els.alerts.children.length > 80) els.alerts.removeChild(els.alerts.lastChild);
}

function updateHistoryAlert(alert) {
  if (!els.alerts || !alert?.id) return;
  const existing = els.alerts.querySelector(`[data-alert-id="${alert.id}"]`);
  if (existing) existing.replaceWith(alertNode(alert, { active: alert.status !== 'resolved' }));
}

function alertNode(alert, options = {}) {
  const item = document.createElement('div');
  item.className = `alert ${alert.severity || ''} ${alert.status || ''} ${alert.false_positive ? 'false-positive' : ''}`;
  item.dataset.alertId = alert.id || '';
  const meta = alert.metadata || {};
  const subject = meta.person_label || meta.person_id || meta.subject || 'global';
  const evidence = alert.frame_ref && alert.id ? `<a class="evidence-link" href="/alerts/${encodeURIComponent(alert.id)}/evidence" target="_blank" rel="noopener">Ver evidência</a>` : '<span class="muted">Sem snapshot</span>';
  const falsePositive = alert.false_positive ? '<span class="false-positive-label">Falso positivo</span>' : `<button class="secondary small false-positive-btn" type="button">Falso positivo</button>`;
  item.innerHTML = `
    <strong>${escapeHtml(alert.message)}</strong>
    <div>${escapeHtml(alert.rule || '')} · ${escapeHtml(alert.feature || '')} · ${escapeHtml(alert.severity || '')} · ${escapeHtml(alert.status || 'active')} · ${escapeHtml(subject)}</div>
    <span class="alert-time">visto: ${formatDate(alert.last_seen_at || alert.created_at)}${alert.resolved_at ? ` · resolvido: ${formatDate(alert.resolved_at)}` : ''}</span>
    <div class="alert-actions">${evidence}${falsePositive}</div>
  `;
  const falseBtn = item.querySelector('.false-positive-btn');
  if (falseBtn) falseBtn.addEventListener('click', () => markFalsePositive(alert));
  return item;
}

async function markFalsePositive(alert) {
  if (!alert?.id) return;
  try {
    const res = await fetch(`/alerts/${alert.id}/false-positive`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: 'Marcado pelo operador no dashboard' }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'Falha ao marcar falso positivo');
    const updated = payload.alert;
    removeActiveAlert(updated);
    addHistoryAlert(updated);
    showMessage('Alerta marcado como falso positivo.', 'ok');
    loadEvents();
  } catch (error) {
    showMessage(error.message || 'Falha ao marcar falso positivo.', 'error');
  }
}

function renderPreflight(payload) {
  const checks = payload?.checks || [];
  if (!checks.length) {
    els.preflight.innerHTML = '<div class="empty-state">Checklist indisponível.</div>';
    return;
  }
  els.preflight.innerHTML = checks.map(item => `
    <div class="check-item ${escapeHtml(item.status)}">
      <span class="check-status">${escapeHtml(labelStatus(item.status))}</span>
      <div>
        <strong>${escapeHtml(item.label)}</strong>
        <small>${escapeHtml(item.message)}</small>
      </div>
    </div>
  `).join('');
}

async function loadRiskArea() {
  if (!els.riskEditorStatus) return;
  try {
    const res = await fetch('/risk-area');
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'Falha ao carregar área de risco');
    applyRiskArea(payload.risk_area);
  } catch (error) {
    els.riskEditorStatus.textContent = 'Área de risco indisponível.';
  }
}

function applyRiskArea(riskArea) {
  if (!riskArea) return;
  state.riskArea = riskArea;
  state.riskEditor.points = (riskArea.polygon || []).map(point => ({ x: Number(point.x), y: Number(point.y) }));
  renderRiskEditorStatus();
  drawRiskEditor();
}

function renderRiskEditorStatus() {
  if (!els.riskEditorStatus) return;
  const points = state.riskEditor.points || [];
  const mode = state.riskEditor.active ? 'editando' : 'visualização';
  els.riskEditorStatus.textContent = `${state.riskArea?.name || 'Área de risco'} · ${points.length} ponto(s) · modo ${mode}`;
}

function toggleRiskEditor() {
  state.riskEditor.active = !state.riskEditor.active;
  els.riskEditorCanvas.classList.toggle('hidden', !state.riskEditor.active);
  els.videoWrap.classList.toggle('editing-risk', state.riskEditor.active);
  els.riskEditBtn.textContent = state.riskEditor.active ? 'Encerrar edição' : 'Editar no vídeo';
  renderRiskEditorStatus();
  drawRiskEditor();
}

function clearRiskEditor() {
  state.riskEditor.points = [];
  renderRiskEditorStatus();
  drawRiskEditor();
}

function addRiskPointFromClick(event) {
  if (!state.riskEditor.active) return;
  const rect = els.riskEditorCanvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const x = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
  const y = Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height));
  state.riskEditor.points.push({ x: round4(x), y: round4(y) });
  renderRiskEditorStatus();
  drawRiskEditor();
}

async function saveRiskArea() {
  if (state.riskEditor.points.length < 3) {
    showMessage('Área de risco precisa de pelo menos 3 pontos.', 'warning');
    return;
  }
  try {
    const res = await fetch('/risk-area', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: state.riskArea?.name || 'Área de risco', polygon: state.riskEditor.points }),
    });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || 'Falha ao salvar área de risco');
    applyRiskArea(payload.risk_area);
    showMessage('Área de risco atualizada no backend.', 'ok');
  } catch (error) {
    showMessage(error.message || 'Falha ao salvar área de risco.', 'error');
  }
}

function drawRiskEditor() {
  const canvas = els.riskEditorCanvas;
  if (!canvas || !els.videoWrap) return;
  const rect = els.videoWrap.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.max(1, Math.floor(rect.width * dpr));
  canvas.height = Math.max(1, Math.floor(rect.height * dpr));
  canvas.style.width = `${rect.width}px`;
  canvas.style.height = `${rect.height}px`;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);
  const points = state.riskEditor.points || [];
  if (!points.length) return;
  ctx.lineWidth = 2;
  ctx.strokeStyle = '#f59e0b';
  ctx.fillStyle = 'rgba(245, 158, 11, .12)';
  ctx.beginPath();
  points.forEach((point, index) => {
    const x = point.x * rect.width;
    const y = point.y * rect.height;
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  if (points.length >= 3) ctx.closePath();
  ctx.stroke();
  if (points.length >= 3) ctx.fill();
  points.forEach((point, index) => {
    const x = point.x * rect.width;
    const y = point.y * rect.height;
    ctx.beginPath();
    ctx.arc(x, y, 5, 0, Math.PI * 2);
    ctx.fillStyle = '#f59e0b';
    ctx.fill();
    ctx.fillStyle = '#07111f';
    ctx.font = 'bold 11px system-ui';
    ctx.fillText(String(index + 1), x + 8, y - 8);
  });
}

function pushTimeline(event) {
  if (!event || !event.message) return;
  if (event.event_type !== 'alert_resolved') return;
  const alertId = event.metadata?.alert_id || event.metadata?.alert?.id || event.id;
  const key = `alert_resolved:${alertId}`;
  if (state.eventKeys.has(key)) return;
  state.eventKeys.add(key);
  state.events.push(event);
  if (state.events.length > 90) state.events.shift();
  renderTimeline();
}

function renderTimeline() {
  if (!els.eventTimeline) return;
  if (!state.events.length) {
    els.eventTimeline.innerHTML = '<div class="empty-state">Nenhum alerta resolvido neste ciclo.</div>';
    return;
  }
  const unique = [];
  const seen = new Set();
  state.events.forEach(event => {
    const alertId = event.metadata?.alert_id || event.metadata?.alert?.id || event.id;
    const key = `alert_resolved:${alertId}`;
    if (seen.has(key)) return;
    seen.add(key);
    unique.push(event);
  });
  els.eventTimeline.innerHTML = unique.slice(-80).reverse().map(event => {
    const alert = event.metadata?.alert || {};
    const detail = [event.subject, alert.feature, alert.false_positive ? 'falso positivo' : 'resolvido'].filter(Boolean).join(' · ');
    return `
      <div class="timeline-item ${escapeHtml(event.severity || 'info')}">
        <span class="timeline-time">${formatTime(event.created_at)}</span>
        <div>
          <strong>${escapeHtml(event.message)}</strong>
          <small>${escapeHtml(detail || event.event_type || '')}</small>
        </div>
      </div>
    `;
  }).join('');
}

function showCleanupMessage(cleanup) {
  if (!cleanup || cleanup.enabled === false) return;
  const removed = cleanup.removed_files || 0;
  const stale = cleanup.resolved_stale_alerts || 0;
  if (removed > 0 || stale > 0) showMessage(`Limpeza de teste executada: ${removed} arquivo(s) antigo(s) removido(s), ${stale} alerta(s) antigo(s) resolvido(s).`, 'ok');
}

function setVideoState(status, label) {
  els.videoStatus.textContent = label;
  setCardStatus('videoCard', status);
  els.streamBadge.textContent = label;
  els.streamBadge.className = `badge ${status === 'ok' ? 'ok' : status === 'error' ? 'error' : 'warn'}`;
}

function setCardStatus(cardId, status) {
  const card = document.getElementById(cardId);
  if (!card) return;
  card.classList.remove('ok', 'warn', 'error');
  card.classList.add(status);
}

function showMessage(message, type = 'warning') {
  if (!message) return hideMessage();
  els.messageBar.textContent = message;
  els.messageBar.className = `message-bar ${type}`;
}

function hideMessage() {
  els.messageBar.className = 'message-bar hidden';
  els.messageBar.textContent = '';
}

function severityOrder(alerts) {
  const order = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return [...alerts].sort((a, b) => (order[a.severity] ?? 9) - (order[b.severity] ?? 9));
}

function labelStatus(status) {
  return { ok: 'OK', warning: 'Aviso', error: 'Erro' }[status] || status;
}

function formatDate(value) {
  if (!value) return new Date().toLocaleString();
  return new Date(value).toLocaleString();
}

function formatTime(value) {
  if (!value) return new Date().toLocaleTimeString();
  return new Date(value).toLocaleTimeString();
}

function translateLabel(label) {
  return { helmet: 'Capacete', vest: 'Colete', gloves: 'Luvas', person: 'Pessoa' }[label] || label;
}

function formatBox(box) {
  if (!box) return 'indefinido';
  return `${box.x1},${box.y1} → ${box.x2},${box.y2}`;
}

function round4(value) {
  return Math.round(Number(value) * 10000) / 10000;
}

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

setInterval(() => {
  if (!state.running) {
    setVideoState('warn', 'parado');
    return;
  }
  if (!state.lastAnalysisAt) {
    setVideoState('warn', 'aguardando frame');
    return;
  }
  const age = Date.now() - state.lastAnalysisAt;
  if (age > 4500) setVideoState('error', 'congelado');
  else if (age > 1800) setVideoState('warn', 'instável');
  else setVideoState('ok', 'recebendo');
}, 1000);

loadFeatures();
loadAlerts();
loadEvents();
refreshStatus();
refreshPreflight();
loadRuntime();
