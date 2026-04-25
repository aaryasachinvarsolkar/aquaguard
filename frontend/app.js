const API = 'http://localhost:8000';

// ── State ──────────────────────────────────────────────────────────────────────
let map1 = null, map2 = null;
let lastResult = null;
let reportText = '';
let chartSST = null, chartCHL = null;
let chartRiskChl = null, chartRiskSST = null;
let chartAlertFreq = null, chartRiskHistory = null;
let currentLocation = '';
let monitoredLocations = [];
let currentUser = null;
let _searchGlobe = null;
let _heatmapLayer = null;
let _heatmapOn = false;
let _currentTileLayer = null;
let _ws = null;
let _alertBadgeCount = 0;

// ── Auth Modal ─────────────────────────────────────────────────────────────────
function openAuthModal(tab) {
  document.getElementById('auth-modal').style.display = 'flex';
  showAuthTab(tab || 'login');
}

function closeAuthModal() {
  document.getElementById('auth-modal').style.display = 'none';
}

function showAuthTab(tab) {
  document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.auth-tab').forEach(t => {
    if (t.textContent.toLowerCase().includes(tab)) t.classList.add('active');
  });
  document.getElementById('auth-login').style.display = tab === 'login' ? 'block' : 'none';
  document.getElementById('auth-signup').style.display = tab === 'signup' ? 'block' : 'none';
}

async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const errEl = document.getElementById('login-error');
  errEl.textContent = '';
  if (!email || !password) { errEl.textContent = 'Please fill in all fields'; return; }
  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || 'Login failed'; return; }
    _setUser(data);
    closeAuthModal();
    _updateAllUserPills();
  } catch (e) { errEl.textContent = 'Connection error'; }
}

async function doSignup() {
  const name = document.getElementById('signup-name').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const alertEmail = document.getElementById('signup-alert-email').value.trim() || email;
  const location = document.getElementById('signup-location').value.trim();
  const errEl = document.getElementById('signup-error');
  errEl.textContent = '';
  if (!name || !email || !password) { errEl.textContent = 'Please fill in all fields'; return; }
  try {
    const res = await fetch(`${API}/auth/signup`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, alert_email: alertEmail, location })
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || 'Signup failed'; return; }
    _setUser(data);
    closeAuthModal();
    _updateAllUserPills();
  } catch (e) { errEl.textContent = 'Connection error'; }
}

function _setUser(data) {
  currentUser = data;
  localStorage.setItem('aq_token', data.token);
  localStorage.setItem('aq_name', data.name);
  localStorage.setItem('aq_email', data.email);
  localStorage.setItem('aq_alert', data.alert_email || data.email);
  localStorage.setItem('aq_location', data.location || '');
}

function _loadStoredUser() {
  const token = localStorage.getItem('aq_token');
  const name = localStorage.getItem('aq_name');
  const email = localStorage.getItem('aq_email');
  const alert = localStorage.getItem('aq_alert');
  const location = localStorage.getItem('aq_location');
  if (token && name) {
    currentUser = { token, name, email, alert_email: alert, location: location || '' };
    return true;
  }
  return false;
}

function _updateAllUserPills() {
  if (!currentUser) return;
  // Landing nav
  const landingPill = document.getElementById('landing-user-pill');
  if (landingPill) {
    landingPill.style.display = 'flex';
    document.getElementById('landing-user-avatar').textContent = currentUser.name[0].toUpperCase();
    document.getElementById('landing-user-name').textContent = currentUser.name.split(' ')[0];
  }
  document.getElementById('landing-signin-btn').style.display = 'none';
  document.getElementById('landing-signup-btn').style.display = 'none';

  // Dashboard nav
  const pill = document.getElementById('user-pill');
  if (pill) {
    pill.style.display = 'flex';
    document.getElementById('user-name-nav').textContent = currentUser.name.split(' ')[0];
    document.getElementById('user-avatar').textContent = currentUser.name[0].toUpperCase();
  }
  const dashSignin = document.getElementById('dash-signin-btn');
  if (dashSignin) dashSignin.style.display = 'none';

  // Profile dropdowns
  ['profile-avatar-big', 'dash-profile-avatar-big'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = currentUser.name[0].toUpperCase();
  });
  ['profile-name-big', 'dash-profile-name-big'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = currentUser.name;
  });
  ['profile-email-big', 'dash-profile-email-big'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = currentUser.email;
  });
  ['profile-alert-email', 'dash-profile-alert-email'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = currentUser.alert_email || currentUser.email;
  });
  ['profile-location', 'dash-profile-location'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = currentUser.location || '';
  });
}

function toggleProfile() {
  // In dashboard use dash dropdown, in landing use landing dropdown
  const inDash = document.getElementById('dashboard').style.display !== 'none';
  const ddId = inDash ? 'dash-profile-dropdown' : 'profile-dropdown';
  const dd = document.getElementById(ddId);
  dd.style.display = dd.style.display === 'none' ? 'block' : 'none';
}

async function saveProfile() {
  _doSaveProfile('profile-alert-email', 'profile-msg');
}

async function saveDashProfile() {
  _doSaveProfile('dash-profile-alert-email', 'dash-profile-msg');
}

async function _doSaveProfile(inputId, msgId) {
  if (!currentUser) return;
  const alertEmail = document.getElementById(inputId).value.trim();
  const locInputId = inputId.replace('alert-email', 'location');
  const location = (document.getElementById(locInputId)?.value || '').trim();
  const msg = document.getElementById(msgId);
  try {
    const res = await fetch(`${API}/auth/update`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: currentUser.token, alert_email: alertEmail, location })
    });
    const data = await res.json();
    if (res.ok) {
      currentUser.alert_email = data.alert_email;
      currentUser.location = data.location || '';
      localStorage.setItem('aq_alert', data.alert_email);
      localStorage.setItem('aq_location', data.location || '');
      msg.textContent = `Saved — alerts for "${data.location || 'all locations'}" → ${data.alert_email}`;
      setTimeout(() => { msg.textContent = ''; }, 4000);
    }
  } catch (e) { if (msg) msg.textContent = 'Save failed'; }
}

function doLogout() {
  localStorage.clear();
  currentUser = null;
  ['profile-dropdown', 'dash-profile-dropdown'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  // Reset landing nav buttons
  document.getElementById('landing-user-pill').style.display = 'none';
  document.getElementById('landing-signin-btn').style.display = 'block';
  document.getElementById('landing-signup-btn').style.display = 'block';
  // Go to landing
  document.getElementById('dashboard').style.display = 'none';
  document.getElementById('landing').style.display = 'flex';
}

// ── Close dropdowns on outside click ──────────────────────────────────────────
document.addEventListener('click', e => {
  ['profile-dropdown', 'dash-profile-dropdown'].forEach(id => {
    const dd = document.getElementById(id);
    const pill = document.getElementById(id === 'profile-dropdown' ? 'landing-user-pill' : 'user-pill');
    if (dd && pill && !dd.contains(e.target) && !pill.contains(e.target)) {
      dd.style.display = 'none';
    }
  });
  // Close auth modal on backdrop click is handled inline
});

// ── Quick search ───────────────────────────────────────────────────────────────
function quickSearch(loc) {
  document.getElementById('nav-search').value = loc;
  openDashboard('search');
  runSearch();
}

// ── Navigation ─────────────────────────────────────────────────────────────────
function openDashboard(tab) {
  document.getElementById('landing').style.display = 'none';
  document.getElementById('dashboard').style.display = 'block';
  _updateAllUserPills();
  if (!currentUser) {
    const btn = document.getElementById('dash-signin-btn');
    if (btn) btn.style.display = 'block';
  }
  // switchTab handles all tab-specific loading — don't call loadMonitor separately
  switchTab(tab);
}

function goHome() {
  document.getElementById('dashboard').style.display = 'none';
  document.getElementById('landing').style.display = 'flex';
}

let _tabAbortController = null;

function switchTab(name) {
  if (_tabAbortController) _tabAbortController.abort();
  _tabAbortController = new AbortController();

  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.querySelectorAll('.nav-tab').forEach(t => {
    if (t.textContent.toLowerCase().includes(name.toLowerCase())) t.classList.add('active');
  });
  if (name === 'map') { initMap2(); loadMonitorPins(); }
  if (name === 'monitor') { loadMonitor(); loadMonitorLocations(); }
  if (name === 'alerts') { _alertSubCurrent = 'alerts'; showAlertSub('alerts'); }
  if (name === 'search' && !lastResult) _initSearchGlobe();
}

// ── Search ─────────────────────────────────────────────────────────────────────
async function runSearch() {
  const loc = document.getElementById('nav-search').value.trim();
  if (!loc) return;

  switchTab('search');
  // Show skeletons
  _showMetricSkeletons();
  document.getElementById('search-empty-state').style.display = 'none';
  document.getElementById('search-loader').classList.add('active');
  document.getElementById('search-results').style.display = 'none';

  try {
    const res = await fetch(`${API}/search?location=${encodeURIComponent(loc)}`);
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    lastResult = data;
    currentLocation = loc;
    renderResults(data);
    document.getElementById('report-location').value = loc;
    loadTrends(90, true); // load baseline & risk history
  } catch (e) {
    alert('Error: ' + e.message);
    // Show empty state again on error
    document.getElementById('search-empty-state').style.display = 'flex';
  } finally {
    document.getElementById('search-loader').classList.remove('active');
  }
}

function renderResults(data) {
  const env = data.environment || {};
  const pred = data.prediction || {};
  const sp = data.species || {};
  const rule = pred.rule_based_risk || {};
  const coords = data.coordinates || {};

  const riskClass = pred.risk_label === 'High' ? 'high' : 'low';
  const pollData = data.pollution || {};
  const pollDetected = pollData.pollution_detected;
  const pollSev = pollData.overall_severity || 'None';
  const pollColor = { Critical: 'high', High: 'high', Moderate: 'mod', None: 'low' }[pollSev] || 'low';

  document.getElementById('metric-cards').innerHTML = `
    <div class="card ${riskClass} fade-in">
      <div class="card-label">Ecosystem Risk</div>
      <div class="card-value ${riskClass}">${pred.risk_label || 'N/A'}</div>
      <div class="card-sub">Confidence: ${pct(pred.risk_confidence)}</div>
    </div>
    <div class="card fade-in">
      <div class="card-label">Sea Surface Temp</div>
      <div class="card-value">${env.temperature ?? 'N/A'} °C</div>
      <div class="card-sub">${env.source || ''}</div>
    </div>
    <div class="card fade-in">
      <div class="card-label">Chlorophyll-a</div>
      <div class="card-value">${env.chlorophyll ?? 'N/A'}</div>
      <div class="card-sub">mg/m³</div>
    </div>
    <div class="card fade-in">
      <div class="card-label">Algal Bloom</div>
      <div class="card-value ${pred.bloom_detected ? 'high' : 'low'}">${pred.bloom_detected ? 'DETECTED' : 'Clear'}</div>
      <div class="card-sub">Confidence: ${pct(pred.bloom_confidence)}</div>
    </div>
    <div class="card ${pred.oil_spill_detected ? 'high' : 'low'} fade-in">
      <div class="card-label">Oil Spill</div>
      <div class="card-value ${pred.oil_spill_detected ? 'high' : 'low'}">${pred.oil_spill_detected ? '⚠ DETECTED' : 'Clear'}</div>
      <div class="card-sub">SAR: ${pred.sar_value ?? 'N/A'} dB</div>
    </div>
    <div class="card ${pollDetected ? pollColor : 'low'} fade-in">
      <div class="card-label">Pollution Discharge</div>
      <div class="card-value ${pollDetected ? pollColor : 'low'}">${pollDetected ? '⚠ ' + pollSev : 'Clear'}</div>
      <div class="card-sub">${pollDetected ? (pollData.events || []).map(e => e.name).join(', ').slice(0, 40) : 'No discharge detected'}</div>
    </div>
    <div class="card fade-in">
      <div class="card-label">Threatened Species</div>
      <div class="card-value">${sp.threatened_count ?? 0}</div>
      <div class="card-sub">${sp.harmed_count ?? 0} currently harmed${sp.iucn_token_missing ? ' · IUCN key missing' : ''}</div>
    </div>
  `;

  // IUCN notice
  const iucnNotice = document.getElementById('iucn-notice');
  if (sp.iucn_token_missing) {
    iucnNotice.style.display = 'block';
  } else {
    iucnNotice.style.display = 'none';
  }

  document.getElementById('search-results').style.display = 'block';

  // Map
  const lat = coords.lat, lon = coords.lon;
  if (lat && lon) {
    if (!map1) {
      map1 = L.map('map', { zoomControl: true }).setView([lat, lon], 6);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '© OpenStreetMap © CARTO', maxZoom: 18
      }).addTo(map1);
    } else {
      map1.eachLayer(l => { if (l instanceof L.Marker || l instanceof L.Circle) map1.removeLayer(l); });
      map1.setView([lat, lon], 6);
    }
    setTimeout(() => map1.invalidateSize(), 100);
    const color = pred.risk_label === 'High' ? '#ff4d4d' : '#00ff88';
    L.circle([lat, lon], { radius: 80000, color, fillColor: color, fillOpacity: 0.15, weight: 1 }).addTo(map1);
    L.marker([lat, lon]).addTo(map1)
      .bindPopup(`<b>${data.location}</b><br>Risk: ${pred.risk_label}<br>Temp: ${env.temperature}°C<br>Chl: ${env.chlorophyll} mg/m³`)
      .openPopup();
  }

  // Species table
  const allSp = (sp.all_species || []).slice(0, 25);
  const stressors = sp.active_stressors || {};
  const stressorBadges = Object.entries({
    'High Temp': stressors.high_temperature,
    'Algal Bloom': stressors.algal_bloom,
    'Oil Spill': stressors.oil_spill,
    'High Turbidity': stressors.high_turbidity
  }).filter(([, v]) => v).map(([k]) =>
    `<span style="background:rgba(255,170,0,.15);border:1px solid #ffaa00;color:#ffaa00;padding:2px 8px;font-size:10px;margin-right:6px">${k}</span>`
  ).join('');

  const stressorLine = stressorBadges
    ? `<div style="margin-bottom:10px;font-size:12px;color:var(--muted)">Active stressors: ${stressorBadges}</div>`
    : `<div style="margin-bottom:10px;font-size:12px;color:var(--low)">✓ No active stressors detected</div>`;

  document.getElementById('species-table').innerHTML = stressorLine + `
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr>
          <th style="text-align:left;padding:8px 10px;color:var(--muted);font-size:10px;letter-spacing:2px;border-bottom:1px solid var(--border)">SPECIES</th>
          <th style="text-align:left;padding:8px 10px;color:var(--muted);font-size:10px;letter-spacing:2px;border-bottom:1px solid var(--border)">STATUS</th>
          <th style="text-align:left;padding:8px 10px;color:var(--muted);font-size:10px;letter-spacing:2px;border-bottom:1px solid var(--border)">HARMED?</th>
          <th style="text-align:left;padding:8px 10px;color:var(--muted);font-size:10px;letter-spacing:2px;border-bottom:1px solid var(--border)">REASON</th>
        </tr>
      </thead>
      <tbody>
        ${allSp.map(s => `
          <tr style="border-bottom:1px solid rgba(0,60,100,.2)">
            <td style="padding:9px 10px">
              <span style="font-style:italic">${escHtml(s.name)}</span>
              ${s.common_name ? `<br><small style="color:var(--muted)">${escHtml(s.common_name)}</small>` : ''}
              ${s.family ? `<br><small style="color:var(--muted);font-size:10px">${escHtml(s.family)}</small>` : ''}
            </td>
            <td style="padding:9px 10px">
              <span class="badge-${(s.iucn_status_code || 'dd').toLowerCase()}">${s.iucn_status || 'DD'}</span>
            </td>
            <td style="padding:9px 10px;font-weight:600">
              ${s.currently_harmed
      ? '<span style="color:var(--high)">⚠ YES</span>'
      : '<span style="color:var(--low)">✓ No</span>'}
            </td>
            <td style="padding:9px 10px;font-size:12px;color:#8ab4cc">
              ${s.currently_harmed
      ? s.harm_reasons.map(r => `<div>• ${escHtml(r)}</div>`).join('')
      : `<span style="color:var(--muted)">${escHtml(s.safe_reason || 'No active stressors')}</span>`}
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;

  // Risk factors
  const factors = rule.contributing_factors || [];
  document.getElementById('risk-factors').innerHTML = factors.length
    ? factors.map(f => `<div>▸ ${f}</div>`).join('')
    : '<div style="color:var(--muted)">No significant risk factors detected</div>';

  renderRiskCharts(data); // Risk vs Chl + SST vs Risk

  // Anomaly banner
  const anomaly = pred.anomaly || {};
  const banner = document.getElementById('anomaly-banner');
  if (anomaly.is_anomaly) {
    banner.style.display = 'block';
    banner.innerHTML = `<div style="background:rgba(255,170,0,.12);border:1px solid #ffaa00;padding:12px 18px;font-size:13px;color:#ffaa00">
      ⚠ ANOMALY DETECTED — ${escHtml(anomaly.anomaly_explanation)}
      <span style="color:var(--muted);font-size:11px;margin-left:12px">Score: ${anomaly.anomaly_score}</span>
    </div>`;
  } else {
    banner.style.display = 'none';
  }

  // Pollution banner
  const pollution = data.pollution || {};
  const pollBanner = document.getElementById('pollution-banner');
  if (pollution.pollution_detected) {
    const sevColor = { Critical: '#cc0000', High: '#ff4d4d', Moderate: '#ff8c00' }[pollution.overall_severity] || '#ff8c00';
    const eventList = (pollution.events || []).map(e =>
      `<div style="margin-top:8px;padding:8px 12px;background:rgba(255,100,0,.08);border-left:3px solid ${sevColor}">
        <b style="color:#ff8c00">${escHtml(e.name)}</b>
        <span style="background:${sevColor};color:#fff;font-size:10px;padding:1px 7px;margin-left:8px;font-weight:700">${e.severity}</span>
        <div style="font-size:12px;color:#8ab4cc;margin-top:3px">${escHtml(e.evidence)}</div>
      </div>`
    ).join('');
    pollBanner.style.display = 'block';
    pollBanner.innerHTML = `
      <div style="background:rgba(255,60,0,.1);border:1px solid rgba(255,100,0,.5);padding:14px 18px">
        <div style="font-size:13px;font-weight:700;color:#ff8c00;margin-bottom:4px">
          ⚠ POLLUTION DISCHARGE DETECTED — ${pollution.overall_severity} Severity
        </div>
        <div style="font-size:12px;color:#8ab4cc;margin-bottom:6px">${escHtml(pollution.summary || '')}</div>
        ${eventList}
        <div style="font-size:11px;color:var(--muted);margin-top:10px">
          An email alert has been sent to subscribed users for this location.
        </div>
      </div>`;
  } else {
    pollBanner.style.display = 'none';
  }

  renderXAI(pred);
  renderRiskCharts(data);
}

function renderRiskCharts(data) {
  const env = data.environment || {};
  const pred = data.prediction || {};
  const curChl = env.chlorophyll || 0;
  const curSST = env.temperature || 0;
  const curRisk = pred.risk_confidence || 0;

  // 1. Risk vs Chlorophyll (Scatter)
  // Generating some background distribution for visualization
  const chlPoints = [];
  for (let x = 0; x <= 15; x += 0.5) {
    // Simulated risk probability based on chl
    let y = x > 5 ? 0.8 + Math.random() * 0.2 : (x > 3 ? 0.4 + Math.random() * 0.3 : 0.1 + Math.random() * 0.2);
    chlPoints.push({ x, y: Math.min(y, 1) });
  }

  if (chartRiskChl) chartRiskChl.destroy();
  chartRiskChl = new Chart(document.getElementById('chart-risk-chl'), {
    type: 'scatter',
    data: {
      datasets: [
        {
          label: 'Risk Distribution',
          data: chlPoints,
          backgroundColor: 'rgba(74, 122, 155, 0.2)',
          pointRadius: 2
        },
        {
          label: 'Current Location',
          data: [{ x: curChl, y: curRisk }],
          backgroundColor: '#00d4ff',
          pointRadius: 8,
          pointHoverRadius: 10,
          borderColor: '#fff',
          borderWidth: 2
        }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: 'Chlorophyll-a (mg/m³)', color: '#8ab4cc', font: { size: 10 } }, min: 0, max: 15, grid: { color: 'rgba(0,60,100,.2)' }, ticks: { color: '#4a7a9b' } },
        y: { title: { display: true, text: 'Risk Score (0-1)', color: '#8ab4cc', font: { size: 10 } }, min: 0, max: 1, grid: { color: 'rgba(0,60,100,.2)' }, ticks: { color: '#4a7a9b' } }
      }
    }
  });

  // 2. SST vs Risk (Line/Area)
  const sstRange = [];
  const sstRisk = [];
  for (let t = 15; t <= 35; t++) {
    sstRange.push(t);
    let r = t > 31 ? 0.9 : (t > 27 ? 0.6 : 0.2);
    sstRisk.push(r);
  }

  if (chartRiskSST) chartRiskSST.destroy();
  chartRiskSST = new Chart(document.getElementById('chart-risk-sst'), {
    type: 'line',
    data: {
      labels: sstRange,
      datasets: [{
        label: 'Risk Probability',
        data: sstRisk,
        borderColor: '#ff4d4d',
        backgroundColor: 'rgba(255, 77, 77, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0
      }, {
        label: 'Current SST',
        data: sstRange.map(t => t === Math.round(curSST) ? curRisk : null),
        pointRadius: 6,
        pointBackgroundColor: '#00d4ff',
        showLine: false
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: 'Temperature (°C)', color: '#8ab4cc', font: { size: 10 } }, grid: { color: 'rgba(0,60,100,.2)' }, ticks: { color: '#4a7a9b' } },
        y: { title: { display: true, text: 'Risk Probability', color: '#8ab4cc', font: { size: 10 } }, min: 0, max: 1, grid: { color: 'rgba(0,60,100,.2)' }, ticks: { color: '#4a7a9b' } }
      }
    }
  });
}

// ── Trend Charts ───────────────────────────────────────────────────────────────
async function loadTrends(days, isInitialSearch = false) {
  if (!currentLocation) return;
  document.getElementById('trend-loader').classList.add('active');
  document.getElementById('trend-charts').style.display = 'none';
  try {
    const res = await fetch(`${API}/trends?location=${encodeURIComponent(currentLocation)}&days=${days}`);
    if (!res.ok) throw new Error('Trend fetch failed');
    const data = await res.json();
    renderTrendCharts(data);
    document.getElementById('trend-charts').style.display = 'grid';

    if (isInitialSearch) {
      _renderBaselineComparison(data);
      _renderRiskHistoryChart(data);
    }
  } catch (e) {
    console.warn('Trends unavailable:', e.message);
  } finally {
    document.getElementById('trend-loader').classList.remove('active');
  }
}

function _renderBaselineComparison(data) {
  const container = document.getElementById('baseline-comparison');
  if (!container || !lastResult) return;

  const currentEnv = lastResult.environment || {};
  const sstBase = data.sst.filter(x => x != null).reduce((a, b) => a + b, 0) / data.sst.filter(x => x != null).length || 0;
  const chlBase = data.chlorophyll.filter(x => x != null).reduce((a, b) => a + b, 0) / data.chlorophyll.filter(x => x != null).length || 0;

  const sstDelta = (currentEnv.temperature || 0) - sstBase;
  const chlDelta = (currentEnv.chlorophyll || 0) - chlBase;

  const fmt = (v, u) => `<b style="color:${v > 0 ? 'var(--high)' : 'var(--low)'}">${v > 0 ? '+' : ''}${v.toFixed(2)}${u}</b>`;

  container.innerHTML = `
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:12px">
      <div>
        <div style="color:var(--muted);margin-bottom:4px">SST vs 90d Baseline</div>
        <div style="font-size:14px">${fmt(sstDelta, '°C')}</div>
      </div>
      <div>
        <div style="color:var(--muted);margin-bottom:4px">CHL vs 90d Baseline</div>
        <div style="font-size:14px">${fmt(chlDelta, ' mg/m³')}</div>
      </div>
    </div>
    <div style="margin-top:10px;font-size:11px;color:silver;text-align:center">
      90d Means: ${sstBase.toFixed(1)}°C | ${chlBase.toFixed(2)} mg/m³
    </div>
  `;
}

function _renderRiskHistoryChart(data) {
  const canvas = document.getElementById('chart-risk-history');
  if (!canvas) return;

  // Derive pseudo risk history from SST and CHL trends
  const riskLabels = data.labels || [];
  const riskValues = data.sst.map((s, i) => {
    const c = data.chlorophyll[i];
    if (s == null || c == null) return 0.2;
    // Simple heuristic for historical risk
    let r = 0.2;
    if (c > 3) r += 0.4;
    if (s > 29) r += 0.3;
    return Math.min(0.95, r + Math.random() * 0.1);
  });

  if (chartRiskHistory) chartRiskHistory.destroy();
  chartRiskHistory = new Chart(canvas, {
    type: 'line',
    data: {
      labels: riskLabels,
      datasets: [{
        label: 'Risk Probability',
        data: riskValues,
        borderColor: '#ff4d4d',
        backgroundColor: 'rgba(255, 77, 77, 0.1)',
        fill: true,
        tension: 0.4,
        pointRadius: 0
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { display: false },
        y: { min: 0, max: 1, ticks: { color: '#4a7a9b', font: { size: 9 } }, grid: { color: 'rgba(255,255,255,0.05)' } }
      }
    }
  });
}

function renderTrendCharts(data) {
  const labels = data.labels || [];
  const sst = data.sst || [];
  const chl = data.chlorophyll || [];

  if (chartSST) chartSST.destroy();
  chartSST = new Chart(document.getElementById('chart-sst'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'SST (°C)',
          data: sst,
          borderColor: '#00d4ff',
          backgroundColor: 'rgba(0,212,255,0.08)',
          borderWidth: 2,
          pointRadius: 3,
          yAxisID: 'y',
          tension: 0.4,
          spanGaps: true
        },
        {
          label: 'Chlorophyll',
          data: chl,
          borderColor: 'rgba(0, 255, 136, 0.4)',
          borderDash: [5, 5],
          borderWidth: 1,
          pointRadius: 0,
          yAxisID: 'y1',
          tension: 0.4,
          spanGaps: true
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: true, labels: { color: '#4a7a9b', font: { size: 10 } } } },
      scales: {
        x: { ticks: { color: '#4a7a9b', font: { size: 10 } }, grid: { color: 'rgba(0,60,100,.3)' } },
        y: {
          type: 'linear', display: true, position: 'left',
          ticks: { color: '#00d4ff', font: { size: 10 } }, grid: { color: 'rgba(0,212,255,0.1)' }
        },
        y1: {
          type: 'linear', display: true, position: 'right',
          ticks: { color: '#00ff88', font: { size: 10 } }, grid: { drawOnChartArea: false }
        }
      }
    }
  });

  if (chartCHL) chartCHL.destroy();
  chartCHL = new Chart(document.getElementById('chart-chl'), {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Chlorophyll (mg/m³)',
          data: chl,
          borderColor: '#00ff88',
          backgroundColor: 'rgba(0,255,136,0.08)',
          borderWidth: 2,
          pointRadius: (ctx) => (chl[ctx.dataIndex] > 5 ? 6 : 3),
          pointBackgroundColor: (ctx) => (chl[ctx.dataIndex] > 5 ? '#ff4d4d' : '#00ff88'),
          tension: 0.4,
          spanGaps: true
        }
      ]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#4a7a9b', font: { size: 10 } }, grid: { color: 'rgba(0,60,100,.3)' } },
        y: {
          ticks: { color: '#4a7a9b', font: { size: 10 } },
          grid: { color: 'rgba(0,60,100,.3)' },
          suggestedMax: 8
        }
      }
    }
  });
}

// ── Alerts Tab ─────────────────────────────────────────────────────────────────
let _alertSubCurrent = 'alerts';
let _allAlerts = [];
let _activeAlertFilter = 'all';

function filterLabels(label) {
  _activeAlertFilter = label;
  document.querySelectorAll('#alert-filters .filter-btn').forEach(btn => {
    btn.classList.toggle('active', btn.textContent.includes(label === 'all' ? 'All' : label));
  });
  _renderAlertsTable();
}

function _renderAlertsTable() {
  const body = document.getElementById('alerts-body');
  if (!body) return;

  let filtered = _allAlerts;
  if (_activeAlertFilter === 'High') {
    filtered = _allAlerts.filter(a => a.risk_label === 'High');
  } else if (_activeAlertFilter === 'Bloom') {
    filtered = _allAlerts.filter(a => a.bloom_detected);
  } else if (_activeAlertFilter === 'Oil') {
    filtered = _allAlerts.filter(a => a.oil_spill_detected);
  }

  body.innerHTML = filtered.map(a => `
    <tr class="fade-in">
      <td style="color:var(--muted);font-size:11px">${a.timestamp ? a.timestamp.slice(0, 16).replace('T', ' ') : 'N/A'}</td>
      <td><b>${a.location}</b></td>
      <td class="risk-${(a.risk_label || 'low').toLowerCase()}">${a.risk_label || 'N/A'}</td>
      <td>${a.bloom_detected ? '<span style="color:var(--high)">⚠ Yes</span>' : 'No'}</td>
      <td>${a.oil_spill_detected ? '<span style="color:var(--high)">⚠ Yes</span>' : 'No'}</td>
      <td>${a.temperature ?? 'N/A'}</td>
      <td>${a.chlorophyll ?? 'N/A'}</td>
      <td>${a.threatened_count ?? 0}</td>
    </tr>
  `).join('');
}

function exportAlertsCSV() {
  if (!_allAlerts.length) return;
  const headers = ['Timestamp', 'Location', 'Risk', 'Bloom', 'Oil Spill', 'Temp', 'Chl', 'Threatened'];
  const rows = _allAlerts.map(a => [
    a.timestamp, a.location, a.risk_label, a.bloom_detected, a.oil_spill_detected,
    a.temperature, a.chlorophyll, a.threatened_count
  ]);

  let csv = headers.join(',') + '\n';
  rows.forEach(r => { csv += r.join(',') + '\n'; });

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.setAttribute('hidden', '');
  a.setAttribute('href', url);
  a.setAttribute('download', `oceansense_alerts_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

function renderAlertFreqChart(alerts) {
  const counts = {};
  alerts.forEach(a => {
    const d = a.timestamp ? a.timestamp.slice(0, 10) : 'Unknown';
    counts[d] = (counts[d] || 0) + 1;
  });
  const labels = Object.keys(counts).sort().slice(-30);
  const data = labels.map(l => counts[l]);

  if (chartAlertFreq) chartAlertFreq.destroy();
  chartAlertFreq = new Chart(document.getElementById('chart-alert-freq'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Alerts',
        data,
        backgroundColor: 'rgba(0, 212, 255, 0.3)',
        borderColor: '#00d4ff',
        borderWidth: 1
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: '#4a7a9b', font: { size: 9 } }, grid: { display: false } },
        y: { ticks: { color: '#4a7a9b', font: { size: 9 }, stepSize: 1 }, grid: { color: 'rgba(0,60,100,.2)' } }
      }
    }
  });
}

function showAlertSub(sub) {
  _alertSubCurrent = sub;
  document.getElementById('alert-sub-alerts').style.display = sub === 'alerts' ? 'block' : 'none';
  document.getElementById('alert-sub-pollution').style.display = sub === 'pollution' ? 'block' : 'none';
  document.getElementById('alert-sub-btn').style.borderColor = sub === 'alerts' ? 'var(--cyan)' : '';
  document.getElementById('pollution-sub-btn').style.borderColor = sub === 'pollution' ? '#ff8c00' : '';
  if (sub === 'pollution') loadPollution();
  else loadAlerts();
}

function refreshAlertTab() {
  if (_alertSubCurrent === 'pollution') loadPollution();
  else loadAlerts();
}

async function loadPollution() {
  const loader = document.getElementById('pollution-loader');
  const list = document.getElementById('pollution-events-list');
  const empty = document.getElementById('pollution-empty');
  loader.classList.add('active');
  list.innerHTML = '';
  empty.style.display = 'none';
  try {
    const res = await fetch(`${API}/pollution/history?limit=50`);
    const data = await res.json();
    const events = data.events || [];
    if (!events.length) {
      empty.style.display = 'block';
    } else {
      list.innerHTML = events.map(e => _renderPollutionCard(e)).join('');
    }
  } catch (err) {
    list.innerHTML = `<div style="color:var(--high);padding:20px">Failed to load: ${escHtml(err.message)}</div>`;
  } finally {
    loader.classList.remove('active');
  }
}

function _renderPollutionCard(e) {
  const sevColor = { Critical: '#cc0000', High: '#ff4d4d', Moderate: '#ff8c00', None: '#4a7a9b' }[e.overall_severity] || '#ff8c00';
  const ts = e.timestamp ? e.timestamp.slice(0, 16).replace('T', ' ') : 'N/A';
  const eventRows = (e.events || []).map(ev => `
    <div style="background:rgba(255,100,0,.06);border-left:3px solid ${sevColor};padding:10px 14px;margin-bottom:8px">
      <div style="font-weight:600;color:#ff8c00;font-size:13px;margin-bottom:4px">${escHtml(ev.name)}</div>
      <div style="font-size:12px;color:#8ab4cc;margin-bottom:4px">${escHtml(ev.evidence)}</div>
      <div style="font-size:11px;color:var(--muted);font-style:italic">${escHtml(ev.description)}</div>
      <span style="background:${sevColor};color:#fff;font-size:10px;padding:2px 8px;font-weight:700;margin-top:6px;display:inline-block">${ev.severity}</span>
    </div>`).join('');
  return `
    <div style="background:var(--card);border:1px solid rgba(255,100,0,.3);padding:18px 20px;margin-bottom:14px">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px">
        <div>
          <span style="font-size:16px;font-weight:700;color:#fff">⚠ ${escHtml(e.location)}</span>
          <span style="background:${sevColor};color:#fff;font-size:11px;padding:3px 10px;font-weight:700;margin-left:10px">${e.overall_severity}</span>
        </div>
        <span style="font-size:11px;color:var(--muted)">${ts} UTC</span>
      </div>
      ${eventRows}
      <div style="font-size:12px;color:var(--muted);margin-top:8px;font-style:italic">${escHtml(e.summary || '')}</div>
    </div>`;
}

async function loadAlerts() {
  document.getElementById('alerts-loader').classList.add('active');
  document.getElementById('alerts-table').style.display = 'none';
  document.getElementById('alerts-empty').style.display = 'none';
  if (currentUser) {
    const notice = document.getElementById('alert-email-notice');
    notice.style.display = 'block';
    const locStr = currentUser.location ? ` for <b>${escHtml(currentUser.location)}</b>` : ' for all locations';
    notice.innerHTML = `🔔 Alerts${locStr} are sent to <b>${escHtml(currentUser.alert_email || currentUser.email)}</b>. <span style="color:var(--cyan);cursor:pointer" onclick="toggleProfile()">Change →</span>`;
  }
  try {
    const res = await fetch(`${API}/alerts/history`);
    const data = await res.json();
    _allAlerts = data.alerts || [];
    if (!_allAlerts.length) {
      document.getElementById('alerts-empty').style.display = 'block';
    } else {
      _renderAlertsTable();
      renderAlertFreqChart(_allAlerts);
      document.getElementById('alerts-table').style.display = 'table';
    }
  } catch (e) {
    document.getElementById('alerts-empty').style.display = 'block';
    document.getElementById('alerts-empty').textContent = 'Failed to load alerts: ' + e.message;
  } finally {
    document.getElementById('alerts-loader').classList.remove('active');
  }
}

// ── Configurable Locations ─────────────────────────────────────────────────────
async function loadMonitorLocations() {
  try {
    const res = await fetch(`${API}/locations`);
    const data = await res.json();
    monitoredLocations = data.locations || [];
    renderLocationTags();
  } catch (_) { }
}

function renderLocationTags() {
  document.getElementById('location-tags').innerHTML = monitoredLocations.map((loc, i) => `
    <span style="background:rgba(0,212,255,.1);border:1px solid var(--border);padding:4px 10px;font-size:12px;color:var(--cyan);display:flex;align-items:center;gap:6px">
      ${escHtml(loc)}
      <span style="cursor:pointer;color:var(--muted)" onclick="removeLocation(${i})">✕</span>
    </span>
  `).join('');
}

function addLocation() {
  const input = document.getElementById('new-location-input');
  const val = input.value.trim();
  if (!val || monitoredLocations.includes(val)) return;
  monitoredLocations.push(val);
  input.value = '';
  renderLocationTags();
}

function removeLocation(i) {
  monitoredLocations.splice(i, 1);
  renderLocationTags();
}

async function saveLocations() {
  try {
    const res = await fetch(`${API}/locations`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ locations: monitoredLocations })
    });
    const data = await res.json();
    const msg = document.getElementById('monitor-status-msg');
    msg.textContent = `Saved ${data.locations.length} locations`;
    msg.style.color = 'var(--cyan)';
    setTimeout(() => msg.textContent = '', 3000);
  } catch (e) { alert('Save failed: ' + e.message); }
}

// ── Map Tab ────────────────────────────────────────────────────────────────────

async function loadMonitorPins() {
  if (!map2) return;
  try {
    const res = await fetch(`${API}/scheduler/status`);
    const data = await res.json();
    const results = data.results || {};
    Object.values(results).forEach(r => {
      if (!r.lat || !r.lon) return;
      const color = r.risk_label === 'High' ? '#ff4d4d' : '#00ff88';
      L.circle([r.lat, r.lon], { radius: 120000, color, fillColor: color, fillOpacity: 0.2, weight: 1 })
        .addTo(map2)
        .bindPopup(`<b>${r.location}</b><br>Risk: ${r.risk_label}<br>Bloom: ${r.bloom_detected ? 'Yes' : 'No'}<br>Oil: ${r.oil_spill_detected ? '⚠ Yes' : 'No'}`);
    });
  } catch (_) { }
}

// ── Monitor Tab ────────────────────────────────────────────────────────────────
async function runSchedulerNow() {
  const btn = document.querySelector('[onclick="runSchedulerNow()"]');
  const msg = document.getElementById('monitor-status-msg');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Running...'; }
  if (msg) { msg.textContent = ''; }
  try {
    const res = await fetch(`${API}/scheduler/run`, { method: 'POST' });
    const data = await res.json();
    if (msg) { msg.textContent = data.message; msg.style.color = 'var(--cyan)'; }
    loadMonitor(); // shows spinner + starts polling automatically
  } catch (e) {
    if (msg) { msg.textContent = 'Failed: ' + e.message; msg.style.color = 'var(--high)'; }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '▶ Run Now'; }
  }
}

// ── Agent Chat — Voice + Multilingual ─────────────────────────────────────────
let _currentLang = 'en';
let _ttsEnabled = true;
let _recognition = null;
let _isListening = false;

const _LANG_CONFIG = {
  en: { code: 'en-IN', label: 'English', placeholder: 'Type your question or press 🎤 to speak...' },
  hi: { code: 'hi-IN', label: 'हिंदी', placeholder: 'अपना प्रश्न टाइप करें या 🎤 दबाएं...' },
  mr: { code: 'mr-IN', label: 'मराठी', placeholder: 'तुमचा प्रश्न टाइप करा किंवा 🎤 दाबा...' },
};

const _WELCOME = {
  en: 'Ask me anything about ocean health, algal blooms, oil spills, or marine species.\n\nYou can type or use the 🎤 microphone. Switch language above.',
  hi: 'समुद्री स्वास्थ्य, शैवाल प्रस्फुटन, तेल रिसाव या समुद्री प्रजातियों के बारे में कुछ भी पूछें।\n\n🎤 माइक्रोफ़ोन या टाइपिंग का उपयोग करें।',
  mr: 'समुद्री आरोग्य, शैवाल फुलणे, तेल गळती किंवा सागरी प्रजातींबद्दल काहीही विचारा।\n\n🎤 मायक्रोफोन किंवा टायपिंग वापरा।',
};

function setLang(lang) {
  _currentLang = lang;
  document.querySelectorAll('.lang-btn[id^="lang-"]').forEach(b => b.classList.remove('active'));
  document.getElementById('lang-' + lang).classList.add('active');
  const cfg = _LANG_CONFIG[lang];
  document.getElementById('chat-input').placeholder = cfg.placeholder;
  // Update welcome message
  const wm = document.getElementById('welcome-msg');
  if (wm) wm.innerHTML = _WELCOME[lang].replace(/\n/g, '<br>') +
    `<br><br><span style="color:var(--muted);font-size:12px">${cfg.label} mode active</span>`;
  // Stop any ongoing speech
  if (_isListening) toggleVoice();
  window.speechSynthesis && window.speechSynthesis.cancel();
}

function toggleTTS() {
  _ttsEnabled = !_ttsEnabled;
  document.getElementById('tts-status').textContent = _ttsEnabled ? 'ON' : 'OFF';
  document.getElementById('tts-toggle').classList.toggle('active', _ttsEnabled);
  if (!_ttsEnabled) window.speechSynthesis && window.speechSynthesis.cancel();
}

// ── Voice Input ────────────────────────────────────────────────────────────────
function toggleVoice() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    _setVoiceStatus('⚠ Voice input not supported in this browser. Use Chrome.', 'var(--high)');
    return;
  }
  if (_isListening) {
    _recognition && _recognition.stop();
    return;
  }
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  _recognition = new SpeechRecognition();
  _recognition.lang = _LANG_CONFIG[_currentLang].code;
  _recognition.continuous = false;
  _recognition.interimResults = true;

  _recognition.onstart = () => {
    _isListening = true;
    document.getElementById('mic-btn').classList.add('listening');
    document.getElementById('mic-btn').textContent = '⏹';
    const waveformContainer = document.getElementById('voice-status-container');
    if (waveformContainer) waveformContainer.style.display = 'flex';
    _setVoiceStatus('🎤 Listening... speak now', 'var(--cyan)');
  };

  _recognition.onresult = (e) => {
    const transcript = Array.from(e.results).map(r => r[0].transcript).join('');
    document.getElementById('chat-input').value = transcript;
    if (e.results[e.results.length - 1].isFinal) {
      _setVoiceStatus('✓ Got it — sending...', 'var(--low)');
      setTimeout(() => sendChat(), 400);
    }
  };

  _recognition.onerror = (e) => {
    _setVoiceStatus(`⚠ Voice error: ${e.error}`, 'var(--high)');
    _stopListening();
  };

  _recognition.onend = () => _stopListening();
  _recognition.start();
}

function _stopListening() {
  _isListening = false;
  const btn = document.getElementById('mic-btn');
  if (btn) {
    btn.classList.remove('listening');
    btn.textContent = '🎤';
  }
  const waveformContainer = document.getElementById('voice-status-container');
  if (waveformContainer) waveformContainer.style.display = 'none';
  setTimeout(() => _setVoiceStatus('', ''), 2000);
}

function _setVoiceStatus(msg, color) {
  const el = document.getElementById('voice-status');
  if (el) { el.textContent = msg; el.style.color = color; }
}

// ── Text-to-Speech output ──────────────────────────────────────────────────────
function _setStopBtn(visible) {
  const btn = document.getElementById('stop-audio-btn');
  if (btn) btn.style.display = visible ? 'inline-flex' : 'none';
}

function stopAudio() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  _setStopBtn(false);
}

function _speak(text) {
  if (!_ttsEnabled || !window.speechSynthesis) return;
  window.speechSynthesis.cancel();

  // Strip markdown/HTML tags and limit length for speech
  const clean = text
    .replace(/[#*`_~\[\]]/g, '')
    .replace(/<[^>]+>/g, '')
    .replace(/\n+/g, '. ')
    .trim()
    .slice(0, 600);

  if (!clean) return;

  const utt = new SpeechSynthesisUtterance(clean);
  utt.lang = _LANG_CONFIG[_currentLang].code;
  utt.rate = 0.92;
  utt.pitch = 1;

  utt.onstart = () => _setStopBtn(true);
  utt.onend = () => _setStopBtn(false);
  utt.onerror = () => _setStopBtn(false);

  // Voices load async — wait for them then speak
  function _doSpeak() {
    const voices = window.speechSynthesis.getVoices();
    if (voices.length) {
      const langCode = _currentLang === 'en' ? 'en' : _currentLang;
      const match = voices.find(v => v.lang.startsWith(langCode))
        || voices.find(v => v.lang.startsWith('en'));
      if (match) utt.voice = match;
    }
    window.speechSynthesis.speak(utt);
  }

  const voices = window.speechSynthesis.getVoices();
  if (voices.length) {
    _doSpeak();
  } else {
    window.speechSynthesis.onvoiceschanged = () => {
      window.speechSynthesis.onvoiceschanged = null;
      _doSpeak();
    };
    setTimeout(_doSpeak, 300);
  }
}

// ── Format agent response as rich HTML ────────────────────────────────────────
function _formatResponse(text) {
  if (!text) return '';
  let html = escHtml(text);

  // Headers: **Title** or ### Title
  html = html.replace(/###\s*(.+)/g, '<h3>$1</h3>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

  // Risk badges
  html = html.replace(/\b(High Risk|HIGH RISK|उच्च जोखिम|उच्च धोका)\b/g,
    '<span class="badge badge-high">$1</span>');
  html = html.replace(/\b(Low Risk|LOW RISK|कम जोखिम|कमी धोका)\b/g,
    '<span class="badge badge-low">$1</span>');
  html = html.replace(/\b(DETECTED|ALERT|⚠)\b/g,
    '<span class="badge badge-warn">$1</span>');
  html = html.replace(/\b(Clear|Normal|Safe|सामान्य)\b/g,
    '<span class="badge badge-low">$1</span>');

  // Bullet points
  html = html.replace(/^[-•]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

  // Line breaks
  html = html.replace(/\n\n/g, '<hr class="divider">');
  html = html.replace(/\n/g, '<br>');

  return `<div class="chat-response">${html}</div>`;
}

// ── Send chat ──────────────────────────────────────────────────────────────────
async function sendChat() {
  const input = document.getElementById('chat-input');
  const query = input.value.trim();
  if (!query) return;
  input.value = '';
  window.speechSynthesis && window.speechSynthesis.cancel();

  const box = document.getElementById('chat-box');
  const langLabel = _LANG_CONFIG[_currentLang].label;

  box.innerHTML += `
    <div class="msg user fade-in">
      <div class="msg-label">You <span style="color:var(--muted);font-size:9px;margin-left:6px">${langLabel}</span></div>
      ${escHtml(query)}
    </div>`;
  box.innerHTML += `
    <div class="msg agent fade-in" id="typing">
      <div class="msg-label">OceanSense AI</div>
      <span style="color:var(--muted)">
        <span class="spinner" style="display:inline-block;width:12px;height:12px;border-width:2px;vertical-align:middle;margin-right:6px"></span>
        Thinking...
      </span>
    </div>`;
  box.scrollTop = box.scrollHeight;

  try {
    const res = await fetch(`${API}/agent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, language: _currentLang })
    });
    const data = await res.json();
    const answer = data.answer || data.detail || 'No response';
    document.getElementById('typing').innerHTML =
      `<div class="msg-label">OceanSense AI <span style="color:var(--muted);font-size:9px;margin-left:6px">${langLabel}</span></div>
       ${_formatResponse(answer)}`;
    _speak(answer);
  } catch (e) {
    document.getElementById('typing').innerHTML =
      `<div class="msg-label">OceanSense AI</div>
       <span style="color:var(--high)">⚠ Error: ${escHtml(e.message)}</span>`;
  }
  box.scrollTop = box.scrollHeight;
}

// ── Report ─────────────────────────────────────────────────────────────────────
async function generateReport() {
  const loc = document.getElementById('report-location').value.trim();
  if (!loc) { alert('Enter a location first'); return; }
  document.getElementById('report-loader').classList.add('active');
  document.getElementById('report-content').style.display = 'none';
  try {
    const res = await fetch(`${API}/report?location=${encodeURIComponent(loc)}`);
    if (!res.ok) throw new Error((await res.json()).detail);
    const data = await res.json();
    reportText = data.report;
    document.getElementById('report-content').textContent = reportText;
    document.getElementById('report-content').style.display = 'block';
  } catch (e) {
    alert('Error: ' + e.message);
  } finally {
    document.getElementById('report-loader').classList.remove('active');
  }
}

function downloadReport() {
  if (!reportText) { alert('Generate a report first'); return; }
  const blob = new Blob([reportText], { type: 'text/markdown' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'oceansense_report.md';
  a.click();
}

// ── Helpers ────────────────────────────────────────────────────────────────────
function pct(v) { return v != null ? (v * 100).toFixed(1) + '%' : 'N/A'; }
function escHtml(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

// ── THREE.JS — shared globe builder ───────────────────────────────────────────
function _buildGlobe(canvas, small) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 100);
  camera.position.set(0, 0.2, small ? 3.8 : 4.6);

  const geoSphere = new THREE.SphereGeometry(1, 64, 64);
  const posArr = geoSphere.attributes.position.array;
  for (let i = 0; i < posArr.length; i += 3) {
    const n = (Math.random() - 0.5) * 0.01;
    posArr[i] += posArr[i] * n;
    posArr[i + 1] += posArr[i + 1] * n;
    posArr[i + 2] += posArr[i + 2] * n;
  }
  geoSphere.computeVertexNormals();

  const globe = new THREE.Mesh(geoSphere, new THREE.MeshPhongMaterial({
    color: 0x0a3a6e, emissive: 0x051a3a, specular: 0x00d4ff, shininess: 60, transparent: true, opacity: 0.72
  }));
  scene.add(globe);

  // Atmosphere
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.18, 32, 32),
    new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.05, side: THREE.BackSide })));
  // Wireframe
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.015, 36, 36),
    new THREE.MeshBasicMaterial({ color: 0x00d4ff, wireframe: true, transparent: true, opacity: 0.06 })));

  const ring1 = new THREE.Mesh(new THREE.TorusGeometry(1.32, 0.004, 2, 200),
    new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.35 }));
  ring1.rotation.x = Math.PI / 2.4;
  scene.add(ring1);

  const ring2 = new THREE.Mesh(new THREE.TorusGeometry(1.65, 0.002, 2, 200),
    new THREE.MeshBasicMaterial({ color: 0x0066aa, transparent: true, opacity: 0.22 }));
  ring2.rotation.x = Math.PI / 3.2; ring2.rotation.y = 0.6;
  scene.add(ring2);

  const scan = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 0.003),
    new THREE.MeshBasicMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.35, side: THREE.DoubleSide }));
  scene.add(scan);

  // Fewer, subtler dots
  const dotColors = [0x00d4ff, 0x00ff88, 0xff4d4d, 0xffaa00];
  for (let i = 0; i < 28; i++) {
    const phi = Math.acos(1 - (2 * (i + 0.5)) / 28);
    const theta = Math.PI * (1 + Math.sqrt(5)) * i;
    const dot = new THREE.Mesh(
      new THREE.SphereGeometry(i % 7 === 0 ? 0.009 : 0.005, 6, 6),
      new THREE.MeshBasicMaterial({ color: dotColors[i % 4], transparent: true, opacity: Math.random() * 0.35 + 0.15 })
    );
    dot.position.setFromSphericalCoords(1.025, phi, theta);
    scene.add(dot);
  }

  const pGeo = new THREE.BufferGeometry();
  const pPos = new Float32Array(450);
  for (let i = 0; i < 450; i++) pPos[i] = (Math.random() - 0.5) * 8;
  pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
  const particles = new THREE.Points(pGeo,
    new THREE.PointsMaterial({ color: 0x003355, size: 0.018, transparent: true, opacity: 0.25 }));
  scene.add(particles);

  scene.add(new THREE.AmbientLight(0x002244, 3.5));
  const sun = new THREE.DirectionalLight(0x00d4ff, 2.2);
  sun.position.set(3, 2, 2);
  scene.add(sun);
  const rimLight = new THREE.DirectionalLight(0x0055aa, 1.2);
  rimLight.position.set(-2, -1, -1);
  scene.add(rimLight);
  const rim = new THREE.PointLight(0x00aaff, 1.8, 8);
  rim.position.set(-2, 1, -1);
  scene.add(rim);

  let scanY = -1.1, scanDir = 1, t = 0;
  let mouseX = 0, mouseY = 0;
  if (!small) {
    document.addEventListener('mousemove', e => {
      mouseX = (e.clientX / window.innerWidth - 0.5) * 0.4;
      mouseY = (e.clientY / window.innerHeight - 0.5) * 0.2;
    });
  }

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight || 400;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  resize();
  window.addEventListener('resize', resize);

  const atmMat = scene.children.find(c => c.material && c.material.opacity === 0.04)?.material;

  return {
    renderer, scene, camera, globe, ring1, ring2, scan, particles, atmMat,
    tick() {
      t += 0.01;
      globe.rotation.y += 0.0018;
      ring1.rotation.z += 0.0012;
      ring2.rotation.z -= 0.0007;
      particles.rotation.y += 0.0003;
      if (!small) {
        camera.position.x += (mouseX * 0.5 - camera.position.x) * 0.03;
        camera.position.y += (-mouseY * 0.3 + 0.2 - camera.position.y) * 0.03;
        camera.lookAt(0, 0, 0);
      }
      scanY += 0.005 * scanDir;
      if (scanY > 1.15 || scanY < -1.15) scanDir *= -1;
      scan.position.y = scanY;
      scan.material.opacity = 0.2 + 0.18 * Math.abs(Math.sin(t * 2));
      if (atmMat) atmMat.opacity = 0.03 + 0.02 * Math.sin(t * 1.5);
      ring1.material.opacity = 0.25 + 0.12 * Math.sin(t * 0.8);
      renderer.render(scene, camera);
    }
  };
}

function initThreeLanding() {
  const canvas = document.getElementById('three-canvas');
  if (!canvas) return;
  const g = _buildGlobe(canvas, false);
  function loop() { requestAnimationFrame(loop); g.tick(); }
  loop();
}

// ── Search tab globe (empty state) ────────────────────────────────────────────
function _initSearchGlobe() {
  if (_searchGlobe) return;
  const canvas = document.getElementById('search-globe-canvas');
  if (!canvas) return;
  // Wait a tick for the container to be visible and sized
  requestAnimationFrame(() => {
    _searchGlobe = _buildGlobe(canvas, true);
    function loop() {
      // Stop if results are showing
      if (document.getElementById('search-results').style.display !== 'none') return;
      requestAnimationFrame(loop);
      _searchGlobe.tick();
    }
    loop();
  });
}

// ── Startup ────────────────────────────────────────────────────────────────────
(function init() {
  _loadStoredUser();
  document.getElementById('landing').style.display = 'flex';
  if (currentUser) {
    _updateAllUserPills();
  }
  initThreeLanding();
  _connectWebSocket();
  _pollAlertBadge();
  // Pre-load TTS voices so they're ready when first response arrives
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
  }
})();

// ── WebSocket — live alert push ────────────────────────────────────────────────
function _connectWebSocket() {
  try {
    _ws = new WebSocket(`ws://localhost:8000/ws/alerts`);
    _ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === 'init' || msg.type === 'alert_count') {
        _setAlertBadge(msg.count || 0);
      }
      if (msg.type === 'scheduler_update') {
        // Refresh monitor table silently if it's visible
        const monTab = document.getElementById('tab-monitor');
        if (monTab && monTab.classList.contains('active')) loadMonitor();
        // Bump badge if any high-risk results
        const results = Object.values(msg.results || {});
        const highRisk = results.filter(r => r.risk_label === 'High').length;
        if (highRisk > 0) _setAlertBadge(_alertBadgeCount + highRisk);
      }
    };
    _ws.onclose = () => {
      // Reconnect after 10s
      setTimeout(_connectWebSocket, 10000);
    };
    _ws.onerror = () => _ws.close();
  } catch (_) { }
}

// ── Alert badge ────────────────────────────────────────────────────────────────
function _setAlertBadge(count) {
  _alertBadgeCount = count;
  const badge = document.getElementById('alert-badge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count > 99 ? '99+' : count;
    badge.style.display = 'inline';
  } else {
    badge.style.display = 'none';
  }
}

async function _pollAlertBadge() {
  try {
    const res = await fetch(`${API}/alerts/unread-count`);
    const data = await res.json();
    _setAlertBadge(data.count || 0);
  } catch (_) { }
  // Poll every 60s as fallback when WebSocket is unavailable
  setTimeout(_pollAlertBadge, 60000);
}

// ── Map tile switcher ──────────────────────────────────────────────────────────
const TILES = {
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    attr: '© OpenStreetMap © CARTO'
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr: '© Esri © DigitalGlobe'
  }
};

function setMapTile(type) {
  if (!map2) return;
  if (_currentTileLayer) map2.removeLayer(_currentTileLayer);
  const t = TILES[type] || TILES.dark;
  _currentTileLayer = L.tileLayer(t.url, { attribution: t.attr, maxZoom: 18 }).addTo(map2);
  // Visual feedback on buttons
  document.getElementById('tile-dark').style.borderColor = type === 'dark' ? 'var(--cyan)' : '';
  document.getElementById('tile-sat').style.borderColor = type === 'satellite' ? 'var(--cyan)' : '';
}

// ── Heatmap layer ──────────────────────────────────────────────────────────────
async function toggleHeatmap() {
  if (!map2) return;
  const btn = document.getElementById('heatmap-btn');

  if (_heatmapOn && _heatmapLayer) {
    map2.removeLayer(_heatmapLayer);
    _heatmapLayer = null;
    _heatmapOn = false;
    btn.textContent = 'Heatmap: OFF';
    btn.style.borderColor = '';
    return;
  }

  // Build heatmap points from scheduler results
  try {
    const res = await fetch(`${API}/scheduler/status`);
    const data = await res.json();
    const results = Object.values(data.results || {});

    if (!results.length) { alert('No scheduler data yet. Run the scheduler first.'); return; }

    // Points: [lat, lon, intensity]  intensity 0–1 based on risk + bloom + oil
    const points = results
      .filter(r => r.lat && r.lon)
      .map(r => {
        const intensity =
          (r.risk_label === 'High' ? 0.6 : 0.2) +
          (r.bloom_detected ? 0.2 : 0) +
          (r.oil_spill_detected ? 0.2 : 0);
        return [r.lat, r.lon, Math.min(intensity, 1)];
      });

    _heatmapLayer = L.heatLayer(points, {
      radius: 60,
      blur: 40,
      maxZoom: 8,
      gradient: { 0.2: '#00ff88', 0.5: '#ffaa00', 0.8: '#ff4d4d', 1.0: '#ff0000' }
    }).addTo(map2);

    _heatmapOn = true;
    btn.textContent = 'Heatmap: ON';
    btn.style.borderColor = 'var(--cyan)';
  } catch (e) {
    alert('Heatmap failed: ' + e.message);
  }
}

// ── Map tile switcher + initMap2 ──────────────────────────────────────────────
function initMap2() {
  if (map2) { setTimeout(() => map2.invalidateSize(), 100); return; }
  map2 = L.map('map2').setView([20, 70], 4);
  _currentTileLayer = L.tileLayer(TILES.dark.url, {
    attribution: TILES.dark.attr, maxZoom: 18
  }).addTo(map2);
  setTimeout(() => map2.invalidateSize(), 100);
}

// ── Sparklines in Monitor tab ──────────────────────────────────────────────────
const _sparklineCache = {};

async function _loadSparkline(location) {
  if (_sparklineCache[location]) return _sparklineCache[location];
  try {
    const res = await fetch(`${API}/trends?location=${encodeURIComponent(location)}&days=30`);
    if (!res.ok) return null;
    const data = await res.json();
    const result = {
      sst: (data.sst || []).filter(v => v != null).slice(-8),
      chl: (data.chlorophyll || []).filter(v => v != null).slice(-8)
    };
    _sparklineCache[location] = result;
    return result;
  } catch (_) { return null; }
}

function _drawSparkline(canvas, values, color) {
  if (!canvas || !values || values.length < 2) return;
  const ctx = canvas.getContext('2d');
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => ({
    x: (i / (values.length - 1)) * w,
    y: h - ((v - min) / range) * (h - 4) - 2
  }));
  ctx.beginPath();
  ctx.moveTo(pts[0].x, pts[0].y);
  pts.slice(1).forEach(p => ctx.lineTo(p.x, p.y));
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  // Fill under line
  ctx.lineTo(pts[pts.length - 1].x, h);
  ctx.lineTo(pts[0].x, h);
  ctx.closePath();
  ctx.fillStyle = color.replace(')', ', 0.12)').replace('rgb', 'rgba');
  ctx.fill();
}

// ── Monitor tab ───────────────────────────────────────────────────────────────
function _isRowPending(r) {
  // A row is live if it has a real timestamp AND status is "ok" or "error" (not "pending")
  if (!r) return true;
  if (r.status === 'ok' || r.status === 'error') return false;
  if (r.timestamp && r.timestamp !== 'null' && r.status !== 'pending') return false;
  return true;
}

let _monitorPollTimer = null;
let _monitorPollStart = 0;
const MONITOR_POLL_TIMEOUT = 90000; // 90 sec max

function _startMonitorPoll() {
  if (_monitorPollTimer) return;
  _monitorPollStart = Date.now();

  _monitorPollTimer = setInterval(async () => {
    // Timeout guard — stop after 2 minutes and show error
    if (Date.now() - _monitorPollStart > MONITOR_POLL_TIMEOUT) {
      clearInterval(_monitorPollTimer);
      _monitorPollTimer = null;
      const body = document.getElementById('monitor-body');
      if (body) body.innerHTML = `
        <tr><td colspan="9" style="text-align:center;padding:40px;color:var(--high)">
          ⚠ Pipeline timed out. Check that the backend is running and GEE is authenticated.<br>
          <small style="color:var(--muted)">Try running: <code>earthengine authenticate</code></small><br><br>
          <button onclick="loadMonitor()" style="margin-top:12px;padding:8px 20px;background:rgba(0,212,255,.1);
            border:1px solid var(--cyan);color:var(--cyan);cursor:pointer">↺ Retry</button>
        </td></tr>`;
      document.getElementById('monitor-table').style.display = 'table';
      return;
    }

    try {
      // Check if run is still in progress
      const runRes = await fetch(`${API}/scheduler/running`);
      const runData = await runRes.json();

      if (!runData.running) {
        // Run finished — check for results
        const res = await fetch(`${API}/scheduler/status`);
        const data = await res.json();
        const liveRows = Object.values(data.results || {}).filter(r => !_isRowPending(r));
        clearInterval(_monitorPollTimer);
        _monitorPollTimer = null;
        if (liveRows.length > 0) {
          loadMonitor();
        } else {
          // Run finished but all rows still pending/error
          const body = document.getElementById('monitor-body');
          if (body) body.innerHTML = `
            <tr><td colspan="9" style="text-align:center;padding:40px;color:var(--high)">
              ⚠ Pipeline completed but no data was returned.<br>
              <small style="color:var(--muted)">GEE may not be authenticated. Using synthetic data as fallback.</small><br><br>
              <button onclick="loadMonitor()" style="margin-top:12px;padding:8px 20px;background:rgba(0,212,255,.1);
                border:1px solid var(--cyan);color:var(--cyan);cursor:pointer">↺ Retry</button>
            </td></tr>`;
          document.getElementById('monitor-table').style.display = 'table';
        }
      }
    } catch (_) { }
  }, 3000);
}

async function loadMonitor() {
  const loader = document.getElementById('monitor-loader');
  const table = document.getElementById('monitor-table');
  const body = document.getElementById('monitor-body');
  if (!loader || !table || !body) return;

  loader.classList.add('active');
  table.style.display = 'none';
  body.innerHTML = '';

  try {
    const res = await fetch(`${API}/scheduler/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const results = Object.values(data.results || {});
    const liveRows = results.filter(r => !_isRowPending(r));

    // ── No live data — auto-trigger run and show loading state ────────────────
    if (!liveRows.length) {
      // Check if already running before triggering
      let alreadyRunning = false;
      try {
        const rr = await fetch(`${API}/scheduler/running`);
        const rd = await rr.json();
        alreadyRunning = rd.running;
      } catch (_) { }

      // Auto-trigger only if not already running and never ran
      if (!alreadyRunning) {
        const neverRan = results.every(r => !r.timestamp);
        if (neverRan) {
          fetch(`${API}/scheduler/run`, { method: 'POST' }).catch(() => { });
          alreadyRunning = true;
        }
      }

      body.innerHTML = `
        <tr>
          <td colspan="10" style="text-align:center;padding:48px 20px">
            ${alreadyRunning ? `
            <div style="margin-bottom:18px">
              <div class="spinner" style="display:inline-block;width:32px;height:32px;border-width:3px"></div>
            </div>
            <div style="color:var(--text);font-size:15px;font-weight:600;margin-bottom:8px">
              Fetching live ocean data…
            </div>
            <div style="color:var(--muted);font-size:13px;margin-bottom:24px">
              Running predictions for ${results.length || 5} locations. This takes ~30–60 seconds.
            </div>` : `
            <div style="font-size:36px;margin-bottom:14px">🌊</div>
            <div style="color:var(--text);font-size:15px;font-weight:600;margin-bottom:8px">No live data yet</div>
            <div style="color:var(--muted);font-size:13px;margin-bottom:24px">
              Click <b style="color:var(--cyan)">▶ Run Now</b> to fetch real-time ocean data.
            </div>`}
            <div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center">
              ${results.map(r => `
                <span style="background:rgba(0,212,255,.07);border:1px solid var(--border);
                  padding:5px 14px;font-size:12px;color:var(--muted)">
                  ⏳ ${escHtml(r.location)}
                </span>`).join('')}
            </div>
          </td>
        </tr>`;
      table.style.display = 'table';
      if (alreadyRunning) _startMonitorPoll();
      return;
    }

    // ── Render live rows ──────────────────────────────────────────────────────
    body.innerHTML = liveRows.map((r, idx) => {
      const riskClass = (r.risk_label || 'low').toLowerCase();
      const pollCell = r.pollution_detected
        ? `<span style="color:#ff8c00;font-weight:600">⚠ ${escHtml(r.pollution_severity || 'Yes')}</span>`
        : `<span style="color:var(--low)">Clear</span>`;
      const statusDot = r.status === 'error'
        ? '<span style="color:var(--high);font-size:11px">⚠ error</span>'
        : `<span class="dot ${riskClass}"></span><span class="risk-${riskClass}">${r.risk_label}</span>`;
      const trend = r.risk_trend || 'stable';
      const trendIcon = trend === 'worse' ? '↑' : (trend === 'better' ? '↓' : '→');
      const trendColor = trend === 'worse' ? 'var(--high)' : (trend === 'better' ? 'var(--low)' : 'var(--muted)');
      return `
      <tr class="fade-in">
        <td><b>${escHtml(r.location)}</b></td>
        <td>${statusDot}</td>
        <td>${r.bloom_detected ? '<span style="color:var(--high)">⚠ Yes</span>' : '<span style="color:var(--low)">No</span>'}</td>
        <td>${r.oil_spill_detected ? '<span style="color:var(--high)">⚠ Yes</span>' : '<span style="color:var(--low)">No</span>'}</td>
        <td>${pollCell}</td>
        <td>${r.temperature ?? '—'}</td>
        <td>${r.chlorophyll ?? '—'}</td>
        <td>${r.threatened_count ?? 0}</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="color:${trendColor};font-weight:bold;font-size:16px" title="Risk Trend: ${trend}">${trendIcon}</span>
            <canvas id="spark-${idx}" width="60" height="24" style="display:block"></canvas>
          </div>
        </td>
        <td style="color:var(--muted);font-size:11px">
          ${r.timestamp ? r.timestamp.slice(0, 16).replace('T', ' ') : '—'}
        </td>
      </tr>`;
    }).join('');

    // Draw sparklines
    liveRows.forEach(async (r, idx) => {
      const canvas = document.getElementById(`spark-${idx}`);
      if (!canvas) return;
      const spark = await _loadSparkline(r.location);
      if (spark && spark.sst.length > 1) _drawSparkline(canvas, spark.sst, '#00d4ff');
    });

    table.style.display = 'table';
  } catch (e) {
    body.innerHTML = `
      <tr><td colspan="10" style="color:var(--high);padding:24px;text-align:center">
        ✕ Failed to load: ${escHtml(e.message)}<br>
        <small style="color:var(--muted)">Make sure the backend is running on port 8000</small>
      </td></tr>`;
    table.style.display = 'table';
  } finally {
    loader.classList.remove('active');
  }
}

// ── Enhanced XAI — show SHAP values if available ───────────────────────────────
function renderXAI(pred) {
  const ex = pred.explanations || {};
  const riskContribs = pred.risk_feature_contributions || [];
  const bloomContribs = pred.bloom_feature_contributions || [];

  function barRows(contribs) {
    return contribs.map(c => {
      const shapBadge = c.shap_value != null
        ? `<span style="font-size:10px;color:${c.shap_value >= 0 ? 'var(--low)' : 'var(--high)'};margin-left:6px">
             SHAP ${c.shap_value >= 0 ? '+' : ''}${c.shap_value.toFixed(3)}
           </span>`
        : '';
      return `
        <div class="xai-bar-row">
          <span class="xai-bar-label">${c.feature}</span>
          <div class="xai-bar-track">
            <div class="xai-bar-fill" style="width:${c.contribution_pct}%"></div>
          </div>
          <span class="xai-bar-pct">${c.contribution_pct}%</span>
          <span style="color:var(--muted);font-size:11px">(${c.value})${shapBadge}</span>
        </div>
      `;
    }).join('');
  }

  const cards = [
    { title: '⚠ Ecosystem Risk Model', explanation: ex.risk || '', bars: barRows(riskContribs) },
    { title: '🌿 Algal Bloom Model', explanation: ex.bloom || '', bars: barRows(bloomContribs) },
    { title: '🛢 Oil Spill Detection', explanation: ex.oil_spill || '', bars: '' },
    { title: '📐 Rule-Based Assessment', explanation: ex.rule_based || '', bars: '' }
  ];

  document.getElementById('xai-panel').innerHTML = cards.map(c => `
    <div class="xai-card fade-in">
      <div class="xai-card-title">${c.title}</div>
      <div class="xai-explanation">${escHtml(c.explanation)}</div>
      ${c.bars}
    </div>
  `).join('');
}

// ── Skeletons ────────────────────────────────────────────────────────────────
function _showMetricSkeletons() {
  const grid = document.getElementById('metric-cards');
  if (!grid) return;
  grid.innerHTML = Array(7).fill(0).map(() => `
    <div class="card skeleton">
      <div class="skeleton-text skeleton" style="width: 40%"></div>
      <div class="skeleton-val skeleton"></div>
      <div class="skeleton-text skeleton" style="width: 30%; margin-top: 10px"></div>
    </div>
  `).join('');
  document.getElementById('search-results').style.display = 'block';
}

// ── Ctrl+K Shortcut ───────────────────────────────────────────────────────────
window.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    const searchInput = document.getElementById('nav-search');
    if (searchInput) {
      searchInput.focus();
      searchInput.select();
    }
  }
});
