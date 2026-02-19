/* ================================================================
   AutomacaoAds — Frontend App
   Vanilla JS SPA — sem frameworks, sem dependências externas.
   Comunicação com a FastAPI via Fetch API.
   ================================================================ */

'use strict';

// ================================================================
// CONFIG & STATE
// ================================================================

const CONFIG = {
  apiBase: '/api/v1',
  getApiKey: () => localStorage.getItem('ads_api_key') || '',
  setApiKey: (k) => localStorage.setItem('ads_api_key', k),
};

// Estado local simples — armazena automacoes carregados para uso nos forms
const STATE = {
  automacoes: [],
  currentRoute: '',
};

// ================================================================
// API CLIENT
// ================================================================

const api = {
  _headers() {
    return {
      'Content-Type': 'application/json',
      'X-API-Key': CONFIG.getApiKey(),
    };
  },

  async _request(method, path, body) {
    const opts = { method, headers: this._headers() };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(CONFIG.apiBase + path, opts);
    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || data.message || `HTTP ${res.status}`);
    }
    return data;
  },

  get:   (path)       => api._request('GET',   path),
  post:  (path, body) => api._request('POST',  path, body),
  patch: (path, body) => api._request('PATCH', path, body),

  // Shortcuts para cada recurso
  async checkHealth() {
    const res = await fetch('/health');
    return res.ok;
  },

  registerAutomacao: (data)              => api.post('/automacao', data),
  listAutomacoes:    ()                  => api.get('/automacoes'),
  createCampaign:    (data)              => api.post('/campaign', data),
  getCampaigns:      (automacao_id)      => api.get(`/campaigns?automacao_id=${automacao_id}`),
  pauseCampaign:     (id, automacao_id)  => api.patch(`/campaign/${id}/pause?automacao_id=${automacao_id}`),
  activateCampaign:  (id, automacao_id)  => api.patch(`/campaign/${id}/activate?automacao_id=${automacao_id}`),
  getInsights:       (id, automacao_id, preset) =>
    api.get(`/campaign/${id}/insights?automacao_id=${automacao_id}&date_preset=${preset}`),
  updateBudget:      (id, automacao_id, data) =>
    api.patch(`/campaign/${id}/budget?automacao_id=${automacao_id}`, data),
  createAdSet:       (data)              => api.post('/adset', data),
  createAd:          (data)              => api.post('/ad', data),

  // IA
  generateCopy:      (data)              => api.post('/ai/generate-copy', data),
  generateAudience:  (data)              => api.post('/ai/generate-audience', data),
  generateImage:     (data)              => api.post('/ai/generate-image', data),
  createFullAd:      (data)              => api.post('/ai/create-full-ad', data),

  // A/B Test
  createABTest:      (data)              => api.post('/ab-test/create', data),
  createABTestAI:    (data)              => api.post('/ab-test/create-with-ai', data),
  listABTests:       (automacao_id)      => api.get(`/ab-tests?automacao_id=${automacao_id}`),
  getABTest:         (test_id)           => api.get(`/ab-test/${test_id}`),
  evaluateABTest:    (test_id, auto)     => api.post(`/ab-test/${test_id}/evaluate?auto_apply=${auto}`),

  // Optimizer
  optimize:          (data, useAI)       => api.post(`/optimize?use_ai=${useAI}`, data),
  getPresets:        ()                  => api.get('/optimize/presets'),
};

// ================================================================
// TOAST
// ================================================================

function toast(message, type = 'info', duration = 4000) {
  const icons = { success: '✓', error: '✕', info: 'ℹ', warning: '⚠' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || 'ℹ'}</span><span>${message}</span>`;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), duration);
}

// ================================================================
// MODAL
// ================================================================

function openModal(title, bodyHtml, footerHtml = '') {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHtml;
  document.getElementById('modal-footer').innerHTML = footerHtml;
  document.getElementById('modal-backdrop').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal-backdrop').classList.add('hidden');
  document.getElementById('modal-body').innerHTML = '';
  document.getElementById('modal-footer').innerHTML = '';
}

// ================================================================
// UTILITIES
// ================================================================

function currency(centavos) {
  if (!centavos) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })
    .format(centavos / 100);
}

function reaisToCentavos(v) {
  return Math.round(parseFloat(v) * 100);
}

function formatDate(raw) {
  if (!raw) return '—';
  const d = raw._seconds ? new Date(raw._seconds * 1000) : new Date(raw);
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function statusBadge(status) {
  const map = {
    ACTIVE:   'active',
    active:   'active',
    PAUSED:   'paused',
    paused:   'paused',
    error:    'error',
    DELETED:  'gray',
    ARCHIVED: 'gray',
  };
  return `<span class="badge badge-${map[status] || 'gray'}">${status}</span>`;
}

function objectiveName(obj) {
  const map = {
    OUTCOME_AWARENESS:      'Awareness',
    OUTCOME_TRAFFIC:        'Tráfego',
    OUTCOME_ENGAGEMENT:     'Engajamento',
    OUTCOME_LEADS:          'Leads',
    OUTCOME_APP_PROMOTION:  'App',
    OUTCOME_SALES:          'Vendas',
  };
  return map[obj] || obj || '—';
}

// Preenche select de automacoes nos forms
function automacaoOptions(selected = '') {
  if (!STATE.automacoes.length) {
    return '<option value="">— Nenhuma automação registrada —</option>';
  }
  return STATE.automacoes.map(a =>
    `<option value="${a.automacao_id}" ${a.automacao_id === selected ? 'selected' : ''}>
      ${a.automacao_id} (${a.ad_account_id || ''})
    </option>`
  ).join('');
}

async function loadAutomacoes() {
  try {
    const res = await api.listAutomacoes();
    STATE.automacoes = res.data || [];
  } catch (_) {
    STATE.automacoes = [];
  }
}

// ================================================================
// ROUTER
// ================================================================

const ROUTES = {
  '':               { title: 'Dashboard',       fn: renderDashboard },
  'automacoes':     { title: 'Automações',      fn: renderAutomacoes },
  'campanhas':      { title: 'Campanhas',       fn: renderCampanhas },
  'ai-creator':     { title: '🤖 Criar com IA', fn: renderAICreator },
  'ab-test':        { title: '⚗ Teste A/B',     fn: renderABTest },
  'optimizer':      { title: '⚡ Otimizador',    fn: renderOptimizer },
  'nova-campanha':  { title: 'Nova Campanha',   fn: renderNovaCampanha },
  'novo-adset':     { title: 'Novo Ad Set',     fn: renderNovoAdSet },
  'novo-ad':        { title: 'Novo Anúncio',    fn: renderNovoAd },
  'configuracoes':  { title: 'Configurações',   fn: renderConfiguracoes },
  'guia':           { title: '📖 Guia de Uso',  fn: renderGuia },
};

function navigate(route) {
  window.location.hash = route;
}

function handleRoute() {
  const route = window.location.hash.slice(1) || '';
  STATE.currentRoute = route;

  const match = ROUTES[route] || ROUTES[''];
  document.getElementById('page-title').textContent = match.title;

  // Atualiza nav ativo
  document.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.route === route);
  });

  // Renderiza a página
  match.fn();
}

// ================================================================
// PAGE: DASHBOARD
// ================================================================

async function renderDashboard() {
  const content = document.getElementById('content');
  content.innerHTML = `<div class="page-loading"><div class="spinner"></div><p>Carregando...</p></div>`;

  let automacaoCount = '—';
  let lastAction = '—';

  try {
    const res = await api.listAutomacoes();
    const list = res.data || [];
    automacaoCount = list.length;

    // Última ação de qualquer automação
    const allLogs = list.flatMap(a => a.logs || []);
    if (allLogs.length) {
      const last = allLogs.sort((a, b) => b.timestamp > a.timestamp ? 1 : -1)[0];
      lastAction = last.action.replace(/_/g, ' ');
    }
    STATE.automacoes = list;
  } catch (_) {}

  content.innerHTML = `
    <div class="page-header">
      <div>
        <h2>Dashboard</h2>
        <p>Visão geral da automação de anúncios Meta</p>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-primary btn-sm" onclick="navigate('nova-campanha')">＋ Nova Campanha</button>
        <button class="btn btn-ghost btn-sm" onclick="navigate('automacoes')">Gerenciar Automações</button>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card blue">
        <span class="stat-label">Automações</span>
        <span class="stat-value">${automacaoCount}</span>
        <span class="stat-sub">Contas registradas</span>
      </div>
      <div class="stat-card green">
        <span class="stat-label">Última Ação</span>
        <span class="stat-value" style="font-size:16px;margin-top:4px">${lastAction}</span>
        <span class="stat-sub">Atividade recente</span>
      </div>
      <div class="stat-card yellow">
        <span class="stat-label">API</span>
        <span class="stat-value" style="font-size:16px;margin-top:4px" id="dash-api-ver">—</span>
        <span class="stat-sub">Graph API versão</span>
      </div>
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Início Rápido</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:10px;">
          <button class="btn btn-ghost" onclick="navigate('automacoes')" style="justify-content:flex-start;">
            🔑 1. Registrar credenciais Meta (automacao_id)
          </button>
          <button class="btn btn-ghost" onclick="navigate('nova-campanha')" style="justify-content:flex-start;">
            📢 2. Criar primeira campanha
          </button>
          <button class="btn btn-ghost" onclick="navigate('novo-adset')" style="justify-content:flex-start;">
            🎯 3. Criar Ad Set com segmentação
          </button>
          <button class="btn btn-ghost" onclick="navigate('novo-ad')" style="justify-content:flex-start;">
            🖼 4. Criar anúncio com criativo
          </button>
          <button class="btn btn-ghost" onclick="navigate('campanhas')" style="justify-content:flex-start;">
            📊 5. Consultar métricas
          </button>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Automações Registradas</span>
          <button class="btn btn-ghost btn-sm" onclick="navigate('automacoes')">Ver todas</button>
        </div>
        ${STATE.automacoes.length === 0
          ? `<div class="empty-state">
              <div class="empty-icon">🔑</div>
              <p>Nenhuma automação registrada ainda.</p>
              <button class="btn btn-primary btn-sm" onclick="navigate('automacoes')">Registrar agora</button>
             </div>`
          : `<div class="table-wrap">
              <table>
                <thead><tr><th>ID</th><th>Conta</th><th>Status</th></tr></thead>
                <tbody>
                  ${STATE.automacoes.slice(0,5).map(a => `
                    <tr>
                      <td><strong>${a.automacao_id}</strong></td>
                      <td style="font-family:var(--mono);font-size:12px">${a.ad_account_id || '—'}</td>
                      <td>${statusBadge(a.status)}</td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
             </div>`
        }
      </div>
    </div>
  `;

  // Busca versão da API em background
  fetch('/health').then(r => r.json()).then(d => {
    const el = document.getElementById('dash-api-ver');
    if (el) el.textContent = d.version || '1.0.0';
  }).catch(() => {});
}

// ================================================================
// PAGE: AUTOMAÇÕES
// ================================================================

async function renderAutomacoes() {
  const content = document.getElementById('content');

  const formHtml = `
    <div class="card">
      <div class="card-header">
        <span class="card-title">Registrar / Atualizar Automação</span>
        <span class="card-subtitle">Salva as credenciais Meta no Firestore</span>
      </div>
      <div class="alert alert-info">
        ℹ Registre aqui as credenciais de cada conta Meta. O <strong>automacao_id</strong>
        é um nome interno seu (ex: "cliente_joao"). Pode registrar múltiplas contas.
      </div>
      <form id="form-automacao">
        <div class="form-row">
          <div class="form-group">
            <label>automacao_id *</label>
            <input class="form-control" name="automacao_id" placeholder="ex: cliente_joao_2024" required />
            <span class="hint">Identificador único interno. Sem espaços.</span>
          </div>
          <div class="form-group">
            <label>Ad Account ID *</label>
            <input class="form-control" name="ad_account_id" placeholder="ex: 1234567890" required />
            <span class="hint">Número da conta (com ou sem 'act_').</span>
          </div>
        </div>
        <div class="form-group">
          <label>Access Token *</label>
          <input class="form-control" name="access_token" type="password" placeholder="EAABs..." required />
          <span class="hint">Token de acesso da Meta API. Mantenha seguro.</span>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>App ID *</label>
            <input class="form-control" name="app_id" placeholder="ex: 1234567890" required />
          </div>
          <div class="form-group">
            <label>App Secret *</label>
            <input class="form-control" name="app_secret" type="password" placeholder="abc123..." required />
          </div>
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit">🔑 Registrar Automação</button>
        </div>
      </form>
    </div>
  `;

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Automações</h2><p>Gerencie as credenciais Meta de cada conta.</p></div>
    </div>
    ${formHtml}
    <div class="card section-gap">
      <div class="card-header">
        <span class="card-title">Automações Cadastradas</span>
        <button class="btn btn-ghost btn-sm" onclick="loadAndShowAutomacoes()">↺ Atualizar</button>
      </div>
      <div id="automacoes-table">
        <div class="page-loading"><div class="spinner"></div></div>
      </div>
    </div>
  `;

  // Form handler
  document.getElementById('form-automacao').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = Object.fromEntries(fd.entries());
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Registrando...';
    try {
      const res = await api.registerAutomacao(body);
      toast(res.message || 'Automação registrada!', 'success');
      e.target.reset();
      loadAndShowAutomacoes();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🔑 Registrar Automação';
    }
  });

  loadAndShowAutomacoes();
}

async function loadAndShowAutomacoes() {
  const el = document.getElementById('automacoes-table');
  if (!el) return;
  el.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;

  try {
    const res = await api.listAutomacoes();
    const list = res.data || [];
    STATE.automacoes = list;

    if (!list.length) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔑</div>
          <h3>Nenhuma automação registrada</h3>
          <p>Use o formulário acima para registrar a primeira.</p>
        </div>`;
      return;
    }

    el.innerHTML = `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>automacao_id</th>
              <th>Ad Account</th>
              <th>Status</th>
              <th>Campaign ID</th>
              <th>Criado em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${list.map(a => `
              <tr>
                <td><strong>${a.automacao_id}</strong></td>
                <td style="font-family:var(--mono);font-size:12px">${a.ad_account_id || '—'}</td>
                <td>${statusBadge(a.status)}</td>
                <td style="font-family:var(--mono);font-size:12px">${a.campaign_id || '—'}</td>
                <td>${formatDate(a.created_at)}</td>
                <td class="actions-cell">
                  <button class="btn btn-ghost btn-sm"
                    onclick="navigate('campanhas');sessionStorage.setItem('filter_automacao','${a.automacao_id}')">
                    📢 Campanhas
                  </button>
                  <button class="btn btn-ghost btn-sm" onclick="showLogs('${a.automacao_id}', ${JSON.stringify(a.logs || []).replace(/"/g,'&quot;')})">
                    📋 Logs
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-danger">Erro ao carregar: ${err.message}</div>`;
  }
}

function showLogs(automacaoId, logs) {
  if (!logs || !logs.length) {
    openModal(`Logs — ${automacaoId}`, `<div class="empty-state"><p>Nenhum log ainda.</p></div>`);
    return;
  }
  const rows = [...logs].reverse().map(l => `
    <tr>
      <td style="font-family:var(--mono);font-size:11px">${l.timestamp ? l.timestamp.slice(0,19).replace('T',' ') : '—'}</td>
      <td><span class="badge badge-blue">${l.action}</span></td>
      <td style="color:${l.error ? 'var(--red)' : 'var(--green)'};font-size:12px">
        ${l.error ? '✕ ' + l.error : '✓ OK'}
      </td>
    </tr>
  `).join('');

  openModal(`Logs — ${automacaoId}`, `
    <div class="table-wrap">
      <table>
        <thead><tr><th>Timestamp</th><th>Ação</th><th>Resultado</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `);
}

// ================================================================
// PAGE: CAMPANHAS
// ================================================================

async function renderCampanhas() {
  const content = document.getElementById('content');
  const prefill = sessionStorage.getItem('filter_automacao') || '';
  sessionStorage.removeItem('filter_automacao');

  await loadAutomacoes();

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Campanhas</h2><p>Gerencie campanhas de cada conta Meta.</p></div>
      <button class="btn btn-primary btn-sm" onclick="navigate('nova-campanha')">＋ Nova Campanha</button>
    </div>

    <div class="card">
      <div class="card-header"><span class="card-title">Buscar Campanhas</span></div>
      <div class="search-bar">
        <select class="form-control" id="camp-automacao-select">
          <option value="">— Selecione a automação —</option>
          ${STATE.automacoes.map(a =>
            `<option value="${a.automacao_id}" ${a.automacao_id === prefill ? 'selected' : ''}>${a.automacao_id}</option>`
          ).join('')}
        </select>
        <button class="btn btn-primary" onclick="fetchCampaigns()">Buscar</button>
      </div>
      <div id="campaigns-result"></div>
    </div>
  `;

  if (prefill) fetchCampaigns();
}

async function fetchCampaigns() {
  const automacao_id = document.getElementById('camp-automacao-select').value;
  const el = document.getElementById('campaigns-result');

  if (!automacao_id) {
    toast('Selecione uma automação primeiro.', 'warning');
    return;
  }

  el.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;

  try {
    const res = await api.getCampaigns(automacao_id);
    const list = res.data || [];

    if (!list.length) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📢</div>
          <h3>Nenhuma campanha encontrada</h3>
          <p>Crie a primeira campanha para esta conta.</p>
          <button class="btn btn-primary btn-sm" onclick="navigate('nova-campanha')">Criar agora</button>
        </div>`;
      return;
    }

    el.innerHTML = `
      <div class="table-wrap" style="margin-top:16px">
        <table>
          <thead>
            <tr>
              <th>Nome</th>
              <th>Status</th>
              <th>Objetivo</th>
              <th>Orçamento/dia</th>
              <th>Criada em</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            ${list.map(c => `
              <tr>
                <td>
                  <strong>${c.name || '—'}</strong>
                  <div style="font-family:var(--mono);font-size:11px;color:var(--text-2)">${c.id}</div>
                </td>
                <td>${statusBadge(c.status)}</td>
                <td>${objectiveName(c.objective)}</td>
                <td>${currency(c.daily_budget)}</td>
                <td>${formatDate(c.created_time)}</td>
                <td class="actions-cell">
                  ${c.status === 'PAUSED'
                    ? `<button class="btn btn-success btn-sm" onclick="actionCampaign('activate','${c.id}','${automacao_id}')">▶ Ativar</button>`
                    : `<button class="btn btn-ghost btn-sm" onclick="actionCampaign('pause','${c.id}','${automacao_id}')">⏸ Pausar</button>`
                  }
                  <button class="btn btn-ghost btn-sm" onclick="showInsights('${c.id}','${automacao_id}','${c.name}')">
                    📊 Insights
                  </button>
                  <button class="btn btn-ghost btn-sm" onclick="showBudgetModal('${c.id}','${automacao_id}')">
                    💰 Orçamento
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  } catch (err) {
    el.innerHTML = `<div class="alert alert-danger">Erro: ${err.message}</div>`;
  }
}

async function actionCampaign(action, campaignId, automacaoId) {
  try {
    const res = action === 'pause'
      ? await api.pauseCampaign(campaignId, automacaoId)
      : await api.activateCampaign(campaignId, automacaoId);
    toast(res.message || 'Ação executada!', 'success');
    fetchCampaigns();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function showInsights(campaignId, automacaoId, name) {
  openModal(`Insights — ${name}`, `<div class="page-loading"><div class="spinner"></div><p>Carregando métricas...</p></div>`);

  const presets = ['today', 'yesterday', 'last_7d', 'last_14d', 'last_30d'];
  const presetLabels = { today:'Hoje', yesterday:'Ontem', last_7d:'7 dias', last_14d:'14 dias', last_30d:'30 dias' };

  async function loadPreset(preset) {
    document.getElementById('modal-body').innerHTML =
      `<div class="page-loading"><div class="spinner"></div></div>`;
    try {
      const res = await api.getInsights(campaignId, automacaoId, preset);
      const d = res.data || {};

      const keys = ['impressions','reach','clicks','spend','cpm','cpc','ctr','frequency'];
      const labels = {
        impressions:'Impressões', reach:'Alcance', clicks:'Cliques',
        spend:'Gasto (R$)', cpm:'CPM', cpc:'CPC', ctr:'CTR (%)', frequency:'Frequência',
      };

      const items = keys.map(k => {
        let val = d[k] || '—';
        if (k === 'spend' && val !== '—') val = `R$ ${parseFloat(val).toFixed(2)}`;
        if (['cpm','cpc'].includes(k) && val !== '—') val = `R$ ${parseFloat(val).toFixed(2)}`;
        if (k === 'ctr' && val !== '—') val = `${parseFloat(val).toFixed(2)}%`;
        return `<div class="insight-item">
          <div class="i-label">${labels[k]||k}</div>
          <div class="i-value">${val}</div>
        </div>`;
      }).join('');

      document.getElementById('modal-body').innerHTML = `
        <div style="margin-bottom:12px;">
          ${presets.map(p => `
            <button class="btn btn-sm ${p===preset?'btn-primary':'btn-ghost'}"
              style="margin:2px" onclick="loadPresetInsights('${campaignId}','${automacaoId}','${name}','${p}')">
              ${presetLabels[p]}
            </button>
          `).join('')}
        </div>
        ${Object.keys(d).length === 0
          ? `<div class="empty-state"><p>Sem dados para o período.</p></div>`
          : `<div class="insight-grid">${items}</div>`
        }
        ${d.date_start ? `<p style="color:var(--text-2);font-size:12px;margin-top:12px">
          Período: ${d.date_start} → ${d.date_stop}
        </p>` : ''}
      `;
    } catch (err) {
      document.getElementById('modal-body').innerHTML =
        `<div class="alert alert-danger">Erro: ${err.message}</div>`;
    }
  }

  // Expõe para chamada do HTML
  window.loadPresetInsights = (cid, aid, n, p) => showInsights(cid, aid, n) || loadPreset(p);

  loadPreset('last_7d');
}

function showBudgetModal(campaignId, automacaoId) {
  openModal(
    'Atualizar Orçamento',
    `<form id="form-budget">
      <div class="alert alert-info">
        Informe o novo orçamento em <strong>Reais (R$)</strong>. O valor será convertido automaticamente.
      </div>
      <div class="form-group">
        <label>Orçamento Diário (R$)</label>
        <input class="form-control" name="daily_budget" type="number" step="0.01" min="0.01"
          placeholder="ex: 50.00" />
        <span class="hint">Deixe em branco para não alterar.</span>
      </div>
    </form>`,
    `<button class="btn btn-ghost" onclick="closeModal()">Cancelar</button>
     <button class="btn btn-primary" onclick="submitBudget('${campaignId}','${automacaoId}')">
       Salvar Orçamento
     </button>`
  );
}

window.submitBudget = async (campaignId, automacaoId) => {
  const form = document.getElementById('form-budget');
  const fd = new FormData(form);
  const daily = fd.get('daily_budget');

  const body = {};
  if (daily) body.daily_budget = reaisToCentavos(daily);

  if (!Object.keys(body).length) {
    toast('Informe ao menos um valor de orçamento.', 'warning');
    return;
  }

  try {
    const res = await api.updateBudget(campaignId, automacaoId, body);
    toast(res.message || 'Orçamento atualizado!', 'success');
    closeModal();
    fetchCampaigns();
  } catch (err) {
    toast(err.message, 'error');
  }
};

// ================================================================
// PAGE: NOVA CAMPANHA
// ================================================================

async function renderNovaCampanha() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Nova Campanha</h2><p>Cria a campanha na Meta API e salva no Firestore.</p></div>
    </div>

    <div class="card" style="max-width:680px">
      <form id="form-campaign">
        <div class="form-group">
          <label>Automação *</label>
          <select class="form-control" name="automacao_id" required>
            ${automacaoOptions()}
          </select>
          <span class="hint">Credenciais que serão usadas para criar a campanha.</span>
        </div>

        <div class="form-group">
          <label>Nome da Campanha *</label>
          <input class="form-control" name="name" placeholder="ex: Campanha Verão 2025" required />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Objetivo *</label>
            <select class="form-control" name="objective" required>
              <option value="OUTCOME_TRAFFIC">Tráfego</option>
              <option value="OUTCOME_AWARENESS">Awareness</option>
              <option value="OUTCOME_ENGAGEMENT">Engajamento</option>
              <option value="OUTCOME_LEADS">Leads</option>
              <option value="OUTCOME_APP_PROMOTION">Promoção de App</option>
              <option value="OUTCOME_SALES">Vendas</option>
            </select>
          </div>
          <div class="form-group">
            <label>Status Inicial</label>
            <select class="form-control" name="status">
              <option value="PAUSED">Pausada (recomendado)</option>
              <option value="ACTIVE">Ativa</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Orçamento Diário (R$)</label>
            <input class="form-control" name="daily_budget" type="number" step="0.01" min="0.01"
              placeholder="ex: 50.00" />
            <span class="hint">Informe diário ou total, não ambos.</span>
          </div>
          <div class="form-group">
            <label>Orçamento Total (R$)</label>
            <input class="form-control" name="lifetime_budget" type="number" step="0.01" min="0.01"
              placeholder="ex: 500.00" />
          </div>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit">🚀 Criar Campanha</button>
          <button class="btn btn-ghost" type="button" onclick="navigate('campanhas')">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('form-campaign').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const raw = Object.fromEntries(fd.entries());

    const body = {
      automacao_id: raw.automacao_id,
      name: raw.name,
      objective: raw.objective,
      status: raw.status,
      special_ad_categories: [],
    };

    if (raw.daily_budget)    body.daily_budget    = reaisToCentavos(raw.daily_budget);
    if (raw.lifetime_budget) body.lifetime_budget = reaisToCentavos(raw.lifetime_budget);

    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Criando...';

    try {
      const res = await api.createCampaign(body);
      toast(`Campanha criada! ID: ${res.data?.id}`, 'success');
      // Prefill no próximo form
      sessionStorage.setItem('last_campaign_id', res.data?.id || '');
      sessionStorage.setItem('last_automacao_id', body.automacao_id);
      e.target.reset();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🚀 Criar Campanha';
    }
  });
}

// ================================================================
// PAGE: NOVO AD SET
// ================================================================

async function renderNovoAdSet() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  const lastCampaign  = sessionStorage.getItem('last_campaign_id') || '';
  const lastAutomacao = sessionStorage.getItem('last_automacao_id') || '';

  const defaultTargeting = JSON.stringify({
    geo_locations: { countries: ['BR'] },
    age_min: 18,
    age_max: 65,
  }, null, 2);

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Novo Ad Set</h2><p>Conjunto de anúncios com segmentação e orçamento.</p></div>
    </div>

    <div class="card" style="max-width:680px">
      <form id="form-adset">
        <div class="form-row">
          <div class="form-group">
            <label>Automação *</label>
            <select class="form-control" name="automacao_id" required>
              ${automacaoOptions(lastAutomacao)}
            </select>
          </div>
          <div class="form-group">
            <label>Campaign ID *</label>
            <input class="form-control" name="campaign_id" value="${lastCampaign}"
              placeholder="ex: 1234567890" required />
            <span class="hint">ID da campanha pai na Meta.</span>
          </div>
        </div>

        <div class="form-group">
          <label>Nome do Ad Set *</label>
          <input class="form-control" name="name" placeholder="ex: AdSet Brasil 18-45" required />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Orçamento Diário (R$) *</label>
            <input class="form-control" name="daily_budget" type="number" step="0.01" min="0.01"
              placeholder="ex: 20.00" required />
          </div>
          <div class="form-group">
            <label>Billing Event</label>
            <select class="form-control" name="billing_event">
              <option value="IMPRESSIONS">Impressões</option>
              <option value="LINK_CLICKS">Cliques no Link</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Optimization Goal</label>
            <select class="form-control" name="optimization_goal">
              <option value="REACH">Alcance</option>
              <option value="LINK_CLICKS">Cliques</option>
              <option value="LANDING_PAGE_VIEWS">Visualizações de Landing</option>
              <option value="LEAD_GENERATION">Geração de Leads</option>
              <option value="CONVERSIONS">Conversões</option>
              <option value="IMPRESSIONS">Impressões</option>
            </select>
          </div>
          <div class="form-group">
            <label>Status Inicial</label>
            <select class="form-control" name="status">
              <option value="PAUSED">Pausado</option>
              <option value="ACTIVE">Ativo</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label>Data de Início</label>
            <input class="form-control" name="start_time" type="datetime-local" />
          </div>
          <div class="form-group">
            <label>Data de Término</label>
            <input class="form-control" name="end_time" type="datetime-local" />
          </div>
        </div>

        <div class="form-group">
          <label>Targeting (JSON) *</label>
          <textarea class="form-control" name="targeting" rows="8" required>${defaultTargeting}</textarea>
          <span class="hint">
            Especificação de segmentação Meta. <code>geo_locations</code>, <code>age_min/max</code>,
            <code>interests</code>, etc.
          </span>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit">🎯 Criar Ad Set</button>
          <button class="btn btn-ghost" type="button" onclick="navigate('campanhas')">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('form-adset').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const raw = Object.fromEntries(fd.entries());

    let targeting;
    try {
      targeting = JSON.parse(raw.targeting);
    } catch (_) {
      toast('Targeting inválido. Verifique o JSON.', 'error');
      return;
    }

    const body = {
      automacao_id:     raw.automacao_id,
      campaign_id:      raw.campaign_id,
      name:             raw.name,
      daily_budget:     reaisToCentavos(raw.daily_budget),
      billing_event:    raw.billing_event,
      optimization_goal: raw.optimization_goal,
      targeting,
      status:           raw.status,
    };

    if (raw.start_time) body.start_time = new Date(raw.start_time).toISOString();
    if (raw.end_time)   body.end_time   = new Date(raw.end_time).toISOString();

    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Criando...';

    try {
      const res = await api.createAdSet(body);
      toast(`Ad Set criado! ID: ${res.data?.id}`, 'success');
      sessionStorage.setItem('last_adset_id', res.data?.id || '');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🎯 Criar Ad Set';
    }
  });
}

// ================================================================
// PAGE: NOVO AD
// ================================================================

async function renderNovoAd() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  const lastAdSet     = sessionStorage.getItem('last_adset_id') || '';
  const lastAutomacao = sessionStorage.getItem('last_automacao_id') || '';

  const defaultCreative = JSON.stringify({ creative_id: 'SEU_CREATIVE_ID_AQUI' }, null, 2);

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Novo Anúncio</h2><p>Cria um anúncio vinculado a um Ad Set.</p></div>
    </div>

    <div class="card" style="max-width:680px">
      <div class="alert alert-warning">
        ⚠ O <strong>creative</strong> deve ser um ID de criativo já existente na sua conta Meta,
        ou uma especificação inline com <code>image_hash</code>, <code>message</code> e <code>link</code>.
      </div>
      <form id="form-ad">
        <div class="form-row">
          <div class="form-group">
            <label>Automação *</label>
            <select class="form-control" name="automacao_id" required>
              ${automacaoOptions(lastAutomacao)}
            </select>
          </div>
          <div class="form-group">
            <label>Ad Set ID *</label>
            <input class="form-control" name="adset_id" value="${lastAdSet}"
              placeholder="ex: 1234567890" required />
          </div>
        </div>

        <div class="form-group">
          <label>Nome do Anúncio *</label>
          <input class="form-control" name="name" placeholder="ex: Ad Produto A - Imagem" required />
        </div>

        <div class="form-group">
          <label>Status Inicial</label>
          <select class="form-control" name="status">
            <option value="PAUSED">Pausado</option>
            <option value="ACTIVE">Ativo</option>
          </select>
        </div>

        <div class="form-group">
          <label>Creative (JSON) *</label>
          <textarea class="form-control" name="creative" rows="6" required>${defaultCreative}</textarea>
          <span class="hint">
            Use <code>{"creative_id": "ID"}</code> para criativo existente, ou especificação inline.
          </span>
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" type="submit">🖼 Criar Anúncio</button>
          <button class="btn btn-ghost" type="button" onclick="navigate('campanhas')">Cancelar</button>
        </div>
      </form>
    </div>
  `;

  document.getElementById('form-ad').addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const raw = Object.fromEntries(fd.entries());

    let creative;
    try {
      creative = JSON.parse(raw.creative);
    } catch (_) {
      toast('Creative inválido. Verifique o JSON.', 'error');
      return;
    }

    const body = {
      automacao_id: raw.automacao_id,
      adset_id:     raw.adset_id,
      name:         raw.name,
      creative,
      status:       raw.status,
    };

    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true;
    btn.textContent = 'Criando...';

    try {
      const res = await api.createAd(body);
      toast(`Anúncio criado! ID: ${res.data?.id}`, 'success');
      e.target.reset();
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '🖼 Criar Anúncio';
    }
  });
}

// ================================================================
// PAGE: CONFIGURAÇÕES
// ================================================================

function renderConfiguracoes() {
  const content = document.getElementById('content');
  const currentKey = CONFIG.getApiKey();

  content.innerHTML = `
    <div class="page-header">
      <div><h2>Configurações</h2><p>Parâmetros da conexão com a API.</p></div>
    </div>

    <div class="card" style="max-width:560px">
      <div class="card-header"><span class="card-title">API Key</span></div>
      <p style="color:var(--text-2);font-size:13px;margin-bottom:14px">
        Chave configurada no <code>.env</code> como <code>API_SECRET_KEY</code>.
        Armazenada apenas no seu navegador (localStorage).
      </p>
      <form id="form-config">
        <div class="form-group">
          <label>X-API-Key</label>
          <input class="form-control" id="input-api-key" type="password"
            value="${currentKey}" placeholder="Sua API Key..." />
        </div>
        <div class="form-actions">
          <button class="btn btn-primary" type="submit">💾 Salvar</button>
          <button class="btn btn-ghost" type="button" onclick="testConnection()">🔌 Testar Conexão</button>
        </div>
      </form>
    </div>

    <div class="card section-gap" style="max-width:560px">
      <div class="card-header"><span class="card-title">Endpoints da API</span></div>
      <div class="code-block">${[
        'POST   /api/v1/automacao          — Registrar automação',
        'GET    /api/v1/automacoes          — Listar automações',
        'POST   /api/v1/campaign           — Criar campanha',
        'GET    /api/v1/campaigns          — Listar campanhas',
        'PATCH  /api/v1/campaign/{id}/pause    — Pausar',
        'PATCH  /api/v1/campaign/{id}/activate — Ativar',
        'GET    /api/v1/campaign/{id}/insights — Métricas',
        'PATCH  /api/v1/campaign/{id}/budget   — Orçamento',
        'POST   /api/v1/adset             — Criar Ad Set',
        'POST   /api/v1/ad               — Criar Anúncio',
      ].join('\n')}</div>
      <div style="margin-top:12px">
        <a href="/docs" target="_blank" class="btn btn-ghost btn-sm">📖 Abrir Swagger UI</a>
        <a href="/redoc" target="_blank" class="btn btn-ghost btn-sm">📄 Abrir ReDoc</a>
      </div>
    </div>
  `;

  document.getElementById('form-config').addEventListener('submit', (e) => {
    e.preventDefault();
    const key = document.getElementById('input-api-key').value.trim();
    CONFIG.setApiKey(key);
    toast('API Key salva no navegador!', 'success');
    checkApiHealth();
  });
}

async function testConnection() {
  try {
    const ok = await api.checkHealth();
    toast(ok ? '✓ API respondendo normalmente!' : 'API retornou erro.', ok ? 'success' : 'error');
  } catch (_) {
    toast('Não foi possível conectar à API.', 'error');
  }
}

// ================================================================
// STATUS BAR — Health check periódico
// ================================================================

async function checkApiHealth() {
  const dot  = document.getElementById('api-status-dot');
  const text = document.getElementById('api-status-text');

  if (!dot || !text) return;

  dot.className = 'status-dot loading';
  text.textContent = 'Verificando...';

  try {
    const ok = await api.checkHealth();
    dot.className  = ok ? 'status-dot online' : 'status-dot offline';
    text.textContent = ok ? 'API Online' : 'API Offline';
  } catch (_) {
    dot.className  = 'status-dot offline';
    text.textContent = 'API Offline';
  }
}

// ================================================================
// SIDEBAR TOGGLE (mobile)
// ================================================================

function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('open');
}

// ================================================================
// PAGE: AI CREATOR
// ================================================================

async function renderAICreator() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="page-header">
      <div>
        <h2>🤖 Criar Anúncio com IA</h2>
        <p>A IA gera copy, público e imagem automaticamente. Qualquer campo pode ser substituído manualmente.</p>
      </div>
    </div>

    <div class="alert alert-info">
      ℹ Preencha o contexto do produto. Deixe os campos de <strong>Override</strong> em branco para usar a IA.
      Preencha-os para substituir o que a IA geraria.
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start">
      <!-- Formulário -->
      <div>
        <div class="card">
          <div class="card-header"><span class="card-title">Contexto do Produto</span></div>
          <form id="form-ai-creator">
            <div class="form-group">
              <label>Automação *</label>
              <select class="form-control" name="automacao_id" required>${automacaoOptions()}</select>
            </div>
            <div class="form-group">
              <label>Nome do Produto/Serviço *</label>
              <input class="form-control" name="product_name" placeholder="ex: Curso de Marketing Digital" required />
            </div>
            <div class="form-group">
              <label>Descrição *</label>
              <textarea class="form-control" name="product_description" rows="3"
                placeholder="Descreva o produto, benefícios principais, diferenciais..." required></textarea>
            </div>
            <div class="form-group">
              <label>Público-Alvo *</label>
              <input class="form-control" name="target_audience"
                placeholder="ex: Empreendedores brasileiros 25-45 anos interessados em crescer online" required />
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Objetivo</label>
                <input class="form-control" name="objective" placeholder="ex: gerar leads, vender, tráfego" value="conversão" />
              </div>
              <div class="form-group">
                <label>Tom de Voz</label>
                <select class="form-control" name="tone">
                  <option value="profissional">Profissional</option>
                  <option value="casual">Casual</option>
                  <option value="urgente">Urgente</option>
                  <option value="empático">Empático</option>
                  <option value="divertido">Divertido</option>
                  <option value="autoridade">Autoridade</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>Diferenciais (opcional)</label>
              <input class="form-control" name="differentials" placeholder="ex: Garantia 30 dias, Suporte vitalício" />
            </div>
          </form>
        </div>

        <div class="card section-gap">
          <div class="card-header"><span class="card-title">Config. Meta API</span></div>
          <form id="form-ai-meta">
            <div class="form-row">
              <div class="form-group">
                <label>Page ID *</label>
                <input class="form-control" name="page_id" placeholder="ID da Página Facebook" required />
              </div>
              <div class="form-group">
                <label>URL da Landing Page *</label>
                <input class="form-control" name="link_url" type="url" placeholder="https://..." required />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Orçamento Diário (R$)</label>
                <input class="form-control" name="daily_budget" type="number" value="50" step="0.01" />
              </div>
              <div class="form-group">
                <label>Objetivo da Campanha</label>
                <select class="form-control" name="campaign_objective">
                  <option value="OUTCOME_TRAFFIC">Tráfego</option>
                  <option value="OUTCOME_LEADS">Leads</option>
                  <option value="OUTCOME_SALES">Vendas</option>
                  <option value="OUTCOME_AWARENESS">Awareness</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
                <input type="checkbox" name="generate_image" checked /> Gerar imagem com DALL-E 3
              </label>
            </div>
          </form>
        </div>

        <div class="card section-gap">
          <div class="card-header">
            <span class="card-title">Overrides Manuais</span>
            <span style="font-size:12px;color:var(--text-2)">Preencha para sobrescrever a IA</span>
          </div>
          <form id="form-ai-overrides">
            <div class="form-group">
              <label>URL da Imagem (sobrescreve DALL-E)</label>
              <input class="form-control" name="custom_image_url" type="url" placeholder="https://..." />
            </div>
            <div class="form-group">
              <label>Copy Manual (JSON — sobrescreve IA)</label>
              <textarea class="form-control" name="custom_copy" rows="4"
                placeholder='{"headline":"...","primary_text":"...","description":"...","cta":"..."}'></textarea>
            </div>
            <div class="form-group">
              <label>Targeting Manual (JSON — sobrescreve IA)</label>
              <textarea class="form-control" name="custom_targeting" rows="4"
                placeholder='{"geo_locations":{"countries":["BR"]},"age_min":18,"age_max":65}'></textarea>
            </div>
          </form>
        </div>

        <div style="display:flex;gap:10px;margin-top:16px;flex-wrap:wrap">
          <button class="btn btn-primary" onclick="previewAI()" id="btn-preview">🔍 Preview IA</button>
          <button class="btn btn-success" onclick="createFullAdAI()" id="btn-create">🚀 Criar Tudo com IA</button>
        </div>
      </div>

      <!-- Preview -->
      <div>
        <div class="card" id="ai-preview-card">
          <div class="card-header"><span class="card-title">Preview Gerado pela IA</span></div>
          <div id="ai-preview-content">
            <div class="empty-state">
              <div class="empty-icon">🤖</div>
              <p>Clique em <strong>Preview IA</strong> para ver o conteúdo que será gerado antes de criar.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function previewAI() {
  const context = getAIContext();
  if (!context) return;

  const btn = document.getElementById('btn-preview');
  btn.disabled = true;
  btn.textContent = '⏳ Gerando...';

  const preview = document.getElementById('ai-preview-content');
  preview.innerHTML = `<div class="page-loading"><div class="spinner"></div><p>IA gerando conteúdo...</p></div>`;

  try {
    const [copyRes, audienceRes] = await Promise.all([
      api.generateCopy({ context }),
      api.generateAudience({ context }),
    ]);

    const copy = copyRes.data || {};
    const audience = audienceRes.data || {};

    preview.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:14px;">
        <div class="card" style="background:var(--bg);box-shadow:none;border:1px solid var(--border)">
          <p style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Copy Gerado</p>
          <p><strong>Headline:</strong> ${copy.headline || '—'}</p>
          <p><strong>Texto:</strong> ${copy.primary_text || '—'}</p>
          <p><strong>Descrição:</strong> ${copy.description || '—'}</p>
          <p><strong>CTA:</strong> ${copy.cta || '—'}</p>
          <p><strong>Nome camp.:</strong> ${copy.campaign_name || '—'}</p>
        </div>
        <div class="card" style="background:var(--bg);box-shadow:none;border:1px solid var(--border)">
          <p style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Segmentação Gerada</p>
          <p><strong>Descrição:</strong> ${audience.description || '—'}</p>
          <p><strong>Alcance estimado:</strong> ${audience.estimated_reach_range || '—'}</p>
          <p><strong>Interesses sugeridos:</strong> ${(audience.suggested_interests || []).join(', ') || '—'}</p>
          <p style="margin-top:8px;font-size:11px;color:var(--text-2)">Targeting spec:</p>
          <div class="code-block" style="font-size:11px;max-height:120px;overflow:auto">${JSON.stringify(audience.targeting || {}, null, 2)}</div>
        </div>
        ${copy.image_prompt ? `
        <div class="card" style="background:var(--bg);box-shadow:none;border:1px solid var(--border)">
          <p style="font-size:11px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">Prompt de Imagem (DALL-E)</p>
          <p style="font-size:12px;color:var(--text-2);font-style:italic">${copy.image_prompt}</p>
        </div>` : ''}
      </div>
    `;
    toast('Preview gerado com sucesso!', 'success');
  } catch (err) {
    preview.innerHTML = `<div class="alert alert-danger">Erro: ${err.message}</div>`;
    toast(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Preview IA';
  }
}

async function createFullAdAI() {
  const context = getAIContext();
  if (!context) return;

  const metaForm = new FormData(document.getElementById('form-ai-meta'));
  const overrideForm = new FormData(document.getElementById('form-ai-overrides'));
  const automacaoForm = new FormData(document.getElementById('form-ai-creator'));

  const page_id  = metaForm.get('page_id');
  const link_url = metaForm.get('link_url');
  if (!page_id || !link_url) {
    toast('Informe Page ID e URL da landing page.', 'warning');
    return;
  }

  const body = {
    automacao_id: automacaoForm.get('automacao_id'),
    context,
    page_id,
    link_url,
    daily_budget: reaisToCentavos(metaForm.get('daily_budget') || '50'),
    campaign_objective: metaForm.get('campaign_objective'),
    campaign_status: 'PAUSED',
    generate_image: !!document.querySelector('[name=generate_image]').checked,
  };

  const customCopy      = overrideForm.get('custom_copy')?.trim();
  const customTargeting = overrideForm.get('custom_targeting')?.trim();
  const customImageUrl  = overrideForm.get('custom_image_url')?.trim();

  if (customCopy)      { try { body.custom_copy      = JSON.parse(customCopy); } catch(_) { toast('JSON de copy inválido.','error'); return; } }
  if (customTargeting) { try { body.custom_targeting = JSON.parse(customTargeting); } catch(_) { toast('JSON de targeting inválido.','error'); return; } }
  if (customImageUrl)  body.custom_image_url = customImageUrl;

  const btn = document.getElementById('btn-create');
  btn.disabled = true;
  btn.textContent = '⏳ Criando...';

  try {
    const res = await api.createFullAd(body);
    const d = res.data || {};
    const meta = d.meta_results || {};
    const ai   = d.ai_generated || {};

    toast(`✓ Anúncio criado! Campaign: ${meta.campaign_id}`, 'success', 6000);

    openModal('✅ Anúncio Criado com IA', `
      <div style="display:flex;flex-direction:column;gap:12px">
        <div class="alert alert-info">Campos gerados pela IA: <strong>${(ai.ai_generated_fields||[]).join(', ') || 'nenhum (override manual)'}</strong></div>
        <div>
          <p style="font-weight:700;margin-bottom:6px">IDs Meta:</p>
          <div class="code-block">${JSON.stringify(meta, null, 2)}</div>
        </div>
        <div>
          <p style="font-weight:700;margin-bottom:6px">Copy usado:</p>
          <p><strong>Headline:</strong> ${ai.copy?.headline || '—'}</p>
          <p><strong>Texto:</strong> ${ai.copy?.primary_text || '—'}</p>
          ${ai.image?.url ? `<img src="${ai.image.url}" style="width:100%;border-radius:8px;margin-top:8px" />` : ''}
        </div>
      </div>
    `);
  } catch (err) {
    toast(err.message, 'error', 7000);
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 Criar Tudo com IA';
  }
}

function getAIContext() {
  const form = document.getElementById('form-ai-creator');
  if (!form) return null;
  const fd = new FormData(form);
  const product_name        = fd.get('product_name')?.trim();
  const product_description = fd.get('product_description')?.trim();
  const target_audience     = fd.get('target_audience')?.trim();

  if (!product_name || !product_description || !target_audience) {
    toast('Preencha todos os campos obrigatórios do contexto.', 'warning');
    return null;
  }

  return {
    product_name,
    product_description,
    target_audience,
    objective:    fd.get('objective') || 'conversão',
    tone:         fd.get('tone') || 'profissional',
    differentials: fd.get('differentials') || null,
    language: 'pt-BR',
  };
}

// ================================================================
// PAGE: A/B TEST
// ================================================================

async function renderABTest() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="page-header">
      <div><h2>⚗ Teste A/B</h2><p>Crie variantes de copy e descubra qual converte mais.</p></div>
    </div>

    <div class="grid-2" style="align-items:start">
      <div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">Novo Teste A/B com IA</span>
            <span style="font-size:12px;color:var(--text-2)">A IA cria as variantes</span>
          </div>
          <div class="alert alert-info">
            🤖 A IA cria variantes com abordagens diferentes: benefício, urgência, prova social e curiosidade.
          </div>
          <form id="form-ab-ai">
            <div class="form-group">
              <label>Automação *</label>
              <select class="form-control" name="automacao_id" required>${automacaoOptions()}</select>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Campaign ID *</label>
                <input class="form-control" name="campaign_id" placeholder="ID da campanha" required />
              </div>
              <div class="form-group">
                <label>Ad Set ID *</label>
                <input class="form-control" name="adset_id" placeholder="ID do Ad Set pai" required />
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Page ID *</label>
                <input class="form-control" name="page_id" placeholder="ID da Página Facebook" required />
              </div>
              <div class="form-group">
                <label>URL da Landing Page *</label>
                <input class="form-control" name="link_url" type="url" placeholder="https://..." required />
              </div>
            </div>
            <div class="form-group">
              <label>Produto *</label>
              <input class="form-control" name="product_name" placeholder="Nome do produto" required />
            </div>
            <div class="form-group">
              <label>Descrição *</label>
              <textarea class="form-control" name="product_description" rows="2" placeholder="Descrição do produto" required></textarea>
            </div>
            <div class="form-group">
              <label>Público-Alvo *</label>
              <input class="form-control" name="target_audience" placeholder="Descreva o público" required />
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Nº de Variantes</label>
                <select class="form-control" name="num_variants">
                  <option value="2">2 variantes</option>
                  <option value="3">3 variantes</option>
                  <option value="4">4 variantes</option>
                </select>
              </div>
              <div class="form-group">
                <label>Métrica do Vencedor</label>
                <select class="form-control" name="optimization_metric">
                  <option value="ctr">CTR (taxa de cliques)</option>
                  <option value="cpc">CPC (custo por clique)</option>
                  <option value="clicks">Total de cliques</option>
                  <option value="reach">Alcance</option>
                </select>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Duração (horas)</label>
                <input class="form-control" name="duration_hours" type="number" value="24" min="1" />
              </div>
              <div class="form-group">
                <label>Aplicar vencedor auto?</label>
                <select class="form-control" name="auto_apply_winner">
                  <option value="true">Sim — pausar perdedores automaticamente</option>
                  <option value="false">Não — apenas informar</option>
                </select>
              </div>
            </div>
            <button class="btn btn-primary" type="button" onclick="submitABTestAI()">🤖 Criar com IA</button>
          </form>
        </div>
      </div>

      <div>
        <div class="card">
          <div class="card-header">
            <span class="card-title">Testes A/B Existentes</span>
            <button class="btn btn-ghost btn-sm" onclick="loadABTests()">↺ Atualizar</button>
          </div>
          <div class="form-group">
            <label>Automação</label>
            <div class="search-bar">
              <select class="form-control" id="ab-automacao-select">
                <option value="">— Selecione —</option>
                ${STATE.automacoes.map(a => `<option value="${a.automacao_id}">${a.automacao_id}</option>`).join('')}
              </select>
              <button class="btn btn-ghost" onclick="loadABTests()">Buscar</button>
            </div>
          </div>
          <div id="ab-tests-list">
            <div class="empty-state"><p>Selecione uma automação para ver os testes.</p></div>
          </div>
        </div>
      </div>
    </div>
  `;
}

async function submitABTestAI() {
  const fd = new FormData(document.getElementById('form-ab-ai'));
  const raw = Object.fromEntries(fd.entries());

  const body = {
    automacao_id: raw.automacao_id,
    campaign_id: raw.campaign_id,
    adset_id: raw.adset_id,
    page_id: raw.page_id,
    link_url: raw.link_url,
    num_variants: parseInt(raw.num_variants),
    optimization_metric: raw.optimization_metric,
    duration_hours: parseInt(raw.duration_hours),
    auto_apply_winner: raw.auto_apply_winner === 'true',
    context: {
      product_name: raw.product_name,
      product_description: raw.product_description,
      target_audience: raw.target_audience,
      objective: 'conversão',
      tone: 'profissional',
      language: 'pt-BR',
    },
  };

  const btn = document.querySelector('#form-ab-ai + button, [onclick="submitABTestAI()"]');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ Criando...'; }

  try {
    const res = await api.createABTestAI(body);
    const d = res.data || {};
    toast(`Teste A/B criado! ID: ${d.test_id}`, 'success');

    const variants = (d.variants || []).map((v, i) =>
      `<li><strong>${v.name}</strong> — Ad ID: ${v.ad_id}</li>`
    ).join('');

    openModal('✅ Teste A/B Criado', `
      <p><strong>Test ID:</strong> <code>${d.test_id}</code></p>
      <p><strong>Variantes criadas:</strong></p>
      <ul style="margin:8px 0 12px 20px">${variants}</ul>
      <div class="alert alert-info">
        Use o botão "Avaliar" após ${body.duration_hours}h para ver o vencedor.
      </div>
    `);

    loadABTests();
  } catch (err) {
    toast(err.message, 'error', 7000);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '🤖 Criar com IA'; }
  }
}

async function loadABTests() {
  const select = document.getElementById('ab-automacao-select');
  const el = document.getElementById('ab-tests-list');
  if (!select || !el) return;

  const automacao_id = select.value;
  if (!automacao_id) { el.innerHTML = `<div class="empty-state"><p>Selecione uma automação.</p></div>`; return; }

  el.innerHTML = `<div class="page-loading"><div class="spinner"></div></div>`;

  try {
    const res = await api.listABTests(automacao_id);
    const tests = res.data || [];

    if (!tests.length) {
      el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚗</div><p>Nenhum teste ainda.</p></div>`;
      return;
    }

    el.innerHTML = tests.map(t => `
      <div class="card" style="margin-bottom:10px;box-shadow:none;border:1px solid var(--border)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <strong>${t.name || t.test_id}</strong>
          ${statusBadge(t.status)}
        </div>
        <p style="font-size:12px;color:var(--text-2);margin-bottom:4px">ID: <code>${t.test_id}</code></p>
        <p style="font-size:12px;color:var(--text-2)">Variantes: ${(t.variants||[]).length} | Métrica: ${t.optimization_metric}</p>
        ${t.winner ? `<p style="color:var(--green);font-size:12px;margin-top:4px">🏆 Vencedor: ${t.winner.name}</p>` : ''}
        <div style="margin-top:8px;display:flex;gap:6px">
          <button class="btn btn-ghost btn-sm" onclick="evaluateABTest('${t.test_id}', true)">Avaliar</button>
          <button class="btn btn-ghost btn-sm" onclick="showABTestDetail('${t.test_id}')">Detalhes</button>
        </div>
      </div>
    `).join('');
  } catch (err) {
    el.innerHTML = `<div class="alert alert-danger">Erro: ${err.message}</div>`;
  }
}

async function evaluateABTest(test_id, autoApply = false) {
  try {
    const res = await api.evaluateABTest(test_id, autoApply);
    const d = res.data || {};
    const winner = d.winner || {};
    const ranking = d.ranking || [];

    openModal(`Resultado do Teste A/B`, `
      <div class="alert alert-info">
        🏆 <strong>Vencedor: ${winner.name || '—'}</strong>
        (${winner.metric}: ${parseFloat(winner.value || 0).toFixed(4)})
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>#</th><th>Variante</th><th>${winner.metric || 'métrica'}</th></tr></thead>
          <tbody>
            ${ranking.map(r => `
              <tr style="${r.rank===1?'background:#d4f4de;':''}">
                <td>${r.rank === 1 ? '🏆' : r.rank}</td>
                <td>${r.name}</td>
                <td>${Object.values(r).find((v,i) => i > 2 && typeof v === 'number') || 0}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      ${d.actions_applied?.length ? `
        <p style="margin-top:12px;font-size:12px;color:var(--text-2)">Ações aplicadas: ${d.actions_applied.join('; ')}</p>
      ` : ''}
    `);
    toast(res.message, 'success');
    loadABTests();
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function showABTestDetail(test_id) {
  try {
    const res = await api.getABTest(test_id);
    const d = res.data || {};
    openModal(`Detalhes — ${d.name}`, `
      <p><strong>Status:</strong> ${statusBadge(d.status)}</p>
      <p><strong>Métrica:</strong> ${d.optimization_metric}</p>
      <p><strong>Variantes:</strong></p>
      <ul style="margin:6px 0 10px 20px">
        ${(d.variants||[]).map(v => `<li>${v.name} — Ad: <code>${v.ad_id}</code></li>`).join('')}
      </ul>
      ${d.winner ? `<div class="alert alert-info">🏆 Vencedor: ${d.winner.name} (${d.winner.metric}: ${d.winner.metric_value})</div>` : ''}
    `, `
      <button class="btn btn-ghost" onclick="closeModal()">Fechar</button>
      <button class="btn btn-primary" onclick="evaluateABTest('${test_id}', true);closeModal()">Avaliar Agora</button>
    `);
  } catch (err) {
    toast(err.message, 'error');
  }
}

// ================================================================
// PAGE: OPTIMIZER
// ================================================================

async function renderOptimizer() {
  await loadAutomacoes();
  const content = document.getElementById('content');

  content.innerHTML = `
    <div class="page-header">
      <div><h2>⚡ Otimizador Automático</h2><p>Define regras e a IA executa as ações automaticamente.</p></div>
    </div>

    <div class="grid-2" style="align-items:start">
      <div>
        <div class="card">
          <div class="card-header"><span class="card-title">Configurar Otimização</span></div>
          <form id="form-optimizer">
            <div class="form-group">
              <label>Automação *</label>
              <select class="form-control" name="automacao_id" required>${automacaoOptions()}</select>
            </div>
            <div class="form-group">
              <label>Campaign ID *</label>
              <input class="form-control" name="campaign_id" placeholder="ID da campanha" required />
            </div>
            <div class="form-row">
              <div class="form-group">
                <label>Período de Análise</label>
                <select class="form-control" name="date_preset">
                  <option value="today">Hoje</option>
                  <option value="yesterday">Ontem</option>
                  <option value="last_7d" selected>Últimos 7 dias</option>
                  <option value="last_14d">Últimos 14 dias</option>
                  <option value="last_30d">Últimos 30 dias</option>
                </select>
              </div>
              <div class="form-group">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;padding-top:22px">
                  <input type="checkbox" name="dry_run" checked /> Modo simulação (dry run)
                </label>
              </div>
            </div>
          </form>
        </div>

        <div class="card section-gap">
          <div class="card-header">
            <span class="card-title">Regras de Otimização</span>
            <div style="display:flex;gap:6px">
              <button class="btn btn-ghost btn-sm" onclick="loadPreset('conservative')">Conservador</button>
              <button class="btn btn-ghost btn-sm" onclick="loadPreset('balanced')">Balanceado</button>
              <button class="btn btn-ghost btn-sm" onclick="loadPreset('aggressive')">Agressivo</button>
            </div>
          </div>
          <div id="rules-container"></div>
          <button class="btn btn-ghost btn-sm" style="margin-top:8px" onclick="addRule()">＋ Adicionar Regra</button>
        </div>

        <div style="display:flex;gap:10px;margin-top:16px">
          <button class="btn btn-primary" onclick="runOptimization()">⚡ Executar Otimização</button>
        </div>
      </div>

      <div>
        <div class="card" id="optimizer-result">
          <div class="card-header"><span class="card-title">Resultado da Otimização</span></div>
          <div class="empty-state">
            <div class="empty-icon">⚡</div>
            <p>Configure as regras e execute para ver o resultado.</p>
          </div>
        </div>
      </div>
    </div>
  `;

  loadPreset('balanced');
}

let _rules = [];

function addRule(rule = {}) {
  _rules.push({
    metric: rule.metric || 'ctr',
    condition: rule.condition || 'less_than',
    threshold: rule.threshold || 1.0,
    action: rule.action || 'notify',
    id: Date.now(),
  });
  renderRules();
}

function removeRule(id) {
  _rules = _rules.filter(r => r.id !== id);
  renderRules();
}

function renderRules() {
  const el = document.getElementById('rules-container');
  if (!el) return;

  if (!_rules.length) {
    el.innerHTML = `<p style="color:var(--text-2);font-size:13px">Nenhuma regra. Adicione uma ou use um preset.</p>`;
    return;
  }

  el.innerHTML = _rules.map((r, i) => `
    <div style="display:grid;grid-template-columns:1fr 1fr 80px 1fr auto;gap:6px;align-items:center;margin-bottom:8px">
      <select class="form-control" onchange="_rules[${i}].metric=this.value">
        ${['ctr','cpc','cpm','spend','clicks','reach','impressions'].map(m =>
          `<option value="${m}" ${m===r.metric?'selected':''}>${m.toUpperCase()}</option>`
        ).join('')}
      </select>
      <select class="form-control" onchange="_rules[${i}].condition=this.value">
        <option value="greater_than" ${r.condition==='greater_than'?'selected':''}>maior que</option>
        <option value="less_than" ${r.condition==='less_than'?'selected':''}>menor que</option>
      </select>
      <input class="form-control" type="number" step="0.01" value="${r.threshold}"
        onchange="_rules[${i}].threshold=parseFloat(this.value)" />
      <select class="form-control" onchange="_rules[${i}].action=this.value">
        <option value="notify" ${r.action==='notify'?'selected':''}>Notificar</option>
        <option value="pause" ${r.action==='pause'?'selected':''}>Pausar</option>
        <option value="increase_budget_10pct" ${r.action==='increase_budget_10pct'?'selected':''}>+10% Budget</option>
        <option value="increase_budget_20pct" ${r.action==='increase_budget_20pct'?'selected':''}>+20% Budget</option>
        <option value="decrease_budget_10pct" ${r.action==='decrease_budget_10pct'?'selected':''}>-10% Budget</option>
        <option value="decrease_budget_20pct" ${r.action==='decrease_budget_20pct'?'selected':''}>-20% Budget</option>
      </select>
      <button class="btn-icon" onclick="removeRule(${r.id})" title="Remover">✕</button>
    </div>
  `).join('');
}

async function loadPreset(preset) {
  try {
    const res = await api.getPresets();
    const rules = res.data?.[preset] || [];
    _rules = rules.map((r, i) => ({ ...r, id: Date.now() + i }));
    renderRules();
    toast(`Preset "${preset}" carregado.`, 'info');
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function runOptimization() {
  if (!_rules.length) { toast('Adicione ao menos uma regra.', 'warning'); return; }

  const fd = new FormData(document.getElementById('form-optimizer'));
  const body = {
    automacao_id: fd.get('automacao_id'),
    campaign_id: fd.get('campaign_id'),
    date_preset: fd.get('date_preset'),
    dry_run: !!document.querySelector('[name=dry_run]').checked,
    rules: _rules.map(({ id, ...r }) => r),
  };

  if (!body.automacao_id || !body.campaign_id) {
    toast('Preencha automação e campaign ID.', 'warning');
    return;
  }

  const resultEl = document.getElementById('optimizer-result');
  resultEl.innerHTML = `<div class="card-header"><span class="card-title">Resultado</span></div>
    <div class="page-loading"><div class="spinner"></div><p>Analisando...</p></div>`;

  try {
    const res = await api.optimize(body, true);
    const d = res.data || {};
    const triggered = (d.rules_evaluated || []).filter(r => r.triggered);
    const ai = d.ai_analysis || {};

    resultEl.innerHTML = `
      <div class="card-header">
        <span class="card-title">Resultado ${d.dry_run ? '(Simulação)' : ''}</span>
        <span class="badge ${triggered.length ? 'badge-active' : 'badge-gray'}">${triggered.length} ativada(s)</span>
      </div>

      ${d.dry_run ? '<div class="alert alert-warning">⚠ Modo simulação — nenhuma ação foi executada.</div>' : ''}

      <div class="insight-grid" style="margin-bottom:14px">
        ${['impressions','reach','clicks','spend','ctr','cpc'].map(k => {
          const v = d.insights?.[k];
          let val = v != null ? v : '—';
          if (k === 'spend' && val !== '—') val = `R$${parseFloat(val).toFixed(2)}`;
          if (['cpc'].includes(k) && val !== '—') val = `R$${parseFloat(val).toFixed(2)}`;
          if (k === 'ctr' && val !== '—') val = `${parseFloat(val).toFixed(2)}%`;
          return `<div class="insight-item"><div class="i-label">${k.toUpperCase()}</div><div class="i-value" style="font-size:16px">${val}</div></div>`;
        }).join('')}
      </div>

      ${ai.performance_grade ? `
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <span style="font-size:28px;font-weight:900;color:var(--blue)">${ai.performance_grade}</span>
          <p style="font-size:13px;color:var(--text-2)">${ai.summary || ''}</p>
        </div>
      ` : ''}

      ${triggered.length ? `
        <p style="font-weight:700;margin-bottom:8px">Regras Ativadas:</p>
        ${triggered.map(r => `
          <div style="padding:8px;background:var(--bg);border-radius:6px;margin-bottom:6px;font-size:13px">
            <span class="badge badge-active">✓</span>
            ${r.metric.toUpperCase()} ${r.condition} ${r.threshold}
            → <strong>${r.action}</strong>
            <span style="color:var(--text-2);margin-left:6px">(atual: ${parseFloat(r.actual_value).toFixed(4)})</span>
            ${r.action_applied && r.action_applied !== true ? `<br/><span style="color:var(--green);font-size:12px">${r.action_applied}</span>` : ''}
          </div>
        `).join('')}
      ` : '<p style="color:var(--text-2)">Nenhuma regra foi ativada com as métricas atuais.</p>'}

      ${ai.suggestions?.length ? `
        <p style="font-weight:700;margin-top:14px;margin-bottom:8px">Sugestões da IA:</p>
        ${ai.suggestions.map(s => `
          <div style="padding:8px;background:var(--blue-light);border-radius:6px;margin-bottom:6px;font-size:13px">
            <span class="badge badge-blue">${s.priority}</span> ${s.action}
            <p style="color:var(--text-2);font-size:12px;margin-top:4px">${s.reason}</p>
          </div>
        `).join('')}
      ` : ''}
    `;

    toast(d.summary || 'Otimização concluída.', triggered.length ? 'success' : 'info');
  } catch (err) {
    resultEl.innerHTML = `<div class="card-header"><span class="card-title">Erro</span></div>
      <div class="alert alert-danger">${err.message}</div>`;
    toast(err.message, 'error');
  }
}

// ================================================================
// PAGE: GUIA DE USO
// ================================================================

function renderGuia() {
  const content = document.getElementById('content');

  const steps = [
    {
      num: 1,
      icon: '⚙',
      title: 'Configure a API Key',
      tag: 'Primeiro passo obrigatório',
      tagColor: 'badge-active',
      route: 'configuracoes',
      routeLabel: 'Ir para Configurações',
      desc: 'Antes de qualquer coisa, informe a chave de autenticação da API. Ela está definida no <code>.env</code> do servidor como <code>API_SECRET_KEY</code>.',
      steps: [
        'Clique em <strong>⚙ Configurações</strong> no menu lateral.',
        'Cole o valor de <code>API_SECRET_KEY</code> do seu <code>.env</code> no campo <em>X-API-Key</em>.',
        'Clique em <strong>💾 Salvar</strong>.',
        'Clique em <strong>🔌 Testar Conexão</strong> — deve aparecer "API respondendo normalmente".',
      ],
      tip: 'A chave é salva apenas no seu navegador (localStorage). Você precisará refazer isso se limpar os dados do navegador.',
      code: null,
    },
    {
      num: 2,
      icon: '🔑',
      title: 'Registre suas credenciais Meta',
      tag: 'Multi-conta',
      tagColor: 'badge-blue',
      route: 'automacoes',
      routeLabel: 'Ir para Automações',
      desc: 'Cada "automação" representa uma conta de anúncios Meta. Você pode ter quantas quiser — uma por cliente, por exemplo.',
      steps: [
        'Vá em <strong>🔑 Automações</strong> no menu.',
        'Defina um <strong>automacao_id</strong> — é um nome interno seu (ex: <code>cliente_joao</code>).',
        'Preencha <strong>App ID</strong> e <strong>App Secret</strong> do seu app em <a href="https://developers.facebook.com" target="_blank">developers.facebook.com</a>.',
        'Cole o <strong>Access Token</strong> gerado no <a href="https://developers.facebook.com/tools/explorer/" target="_blank">Graph API Explorer</a> com permissão <code>ads_management</code>.',
        'Informe o <strong>Ad Account ID</strong> no formato <code>act_XXXXXXXXX</code> (veja em Gerenciador de Anúncios).',
        'Clique em <strong>💾 Salvar Automação</strong>.',
      ],
      tip: 'O Access Token expira. Quando isso acontecer, basta registrar novamente a automação com o novo token — o sistema atualiza no Firestore.',
      code: null,
    },
    {
      num: 3,
      icon: '🤖',
      title: 'Crie um anúncio completo com IA',
      tag: 'Caminho recomendado',
      tagColor: 'badge-active',
      route: 'ai-creator',
      routeLabel: 'Ir para Criar com IA',
      desc: 'O fluxo mais poderoso. A IA gera o copy, define o público e cria a imagem automaticamente. Você pode sobrescrever qualquer campo.',
      steps: [
        'Vá em <strong>🤖 Criar com IA</strong>.',
        'Selecione a automação (conta Meta) desejada.',
        'Preencha o <strong>contexto do produto</strong>: nome, descrição, público-alvo, objetivo e tom de voz.',
        'Clique em <strong>✨ Pré-visualizar IA</strong> para ver o que será gerado <em>antes</em> de criar.',
        'Se quiser usar seu próprio copy ou imagem, expanda a seção <em>Overrides Manuais</em> e preencha os campos.',
        'Informe <strong>Page ID</strong> (ID da sua página no Facebook), <strong>link de destino</strong> e orçamento diário.',
        'Clique em <strong>🚀 Criar com IA</strong>.',
      ],
      tip: 'A campanha e o anúncio são criados com status PAUSED — ative manualmente no Meta Ads Manager quando estiver pronto para veicular.',
      code: `// Exemplo de contexto ideal para a IA:
Produto: Curso Online de Tráfego Pago
Descrição: Aprenda a criar campanhas lucrativas do zero
Público: Empreendedores e freelancers 25-45 anos
Objetivo: Captar leads qualificados
Tom: Profissional com urgência`,
    },
    {
      num: 4,
      icon: '📢',
      title: 'Ou crie manualmente (controle total)',
      tag: 'Criação manual',
      tagColor: 'badge-gray',
      route: 'nova-campanha',
      routeLabel: 'Criar Campanha',
      desc: 'Prefere controle total? Crie campanha, ad set e anúncio em etapas separadas. Siga exatamente esta ordem.',
      steps: [
        '<strong>Passo 1 —</strong> Vá em <strong>＋ Nova Campanha</strong> e preencha nome, objetivo (ex: OUTCOME_SALES) e orçamento. Anote o <em>Campaign ID</em> retornado.',
        '<strong>Passo 2 —</strong> Vá em <strong>＋ Novo Ad Set</strong>. Use o Campaign ID do passo anterior. Configure público, orçamento e período.',
        '<strong>Passo 3 —</strong> Vá em <strong>＋ Novo Anúncio</strong>. Use o Ad Set ID do passo anterior. Cole a copy e a URL da imagem.',
      ],
      tip: 'Os IDs de campanha, ad set e anúncio aparecem no resultado de cada criação. Copie e salve antes de avançar para o próximo passo.',
      code: `// Objetivos disponíveis:
OUTCOME_AWARENESS    → Alcance e brand awareness
OUTCOME_TRAFFIC      → Tráfego para site/landing page
OUTCOME_ENGAGEMENT   → Curtidas, comentários, shares
OUTCOME_LEADS        → Formulário de lead
OUTCOME_APP_PROMOTION → Instalações de app
OUTCOME_SALES        → Conversões e vendas`,
    },
    {
      num: 5,
      icon: '⚗',
      title: 'Rode Testes A/B para descobrir o melhor copy',
      tag: 'IA opcional',
      tagColor: 'badge-blue',
      route: 'ab-test',
      routeLabel: 'Ir para Teste A/B',
      desc: 'Crie múltiplas variantes de copy no mesmo Ad Set e deixe a Meta distribuir. Depois avalie qual venceu.',
      steps: [
        'Vá em <strong>⚗ Teste A/B</strong>.',
        'Selecione a automação, informe o <strong>Ad Set ID</strong> (já deve existir) e o <strong>Page ID</strong>.',
        'Preencha o contexto do produto.',
        'Escolha o número de variantes (2 a 4) — a IA cria cada uma com uma abordagem diferente: <em>benefício, urgência, prova social, curiosidade</em>.',
        'Clique em <strong>Criar Teste A/B com IA</strong>.',
        'Após alguns dias rodando, clique em <strong>Avaliar</strong> no teste. O sistema compara as métricas e declara o vencedor.',
        'Ative <em>Pausar Perdedores</em> para parar automaticamente as variantes ruins.',
      ],
      tip: 'O resultado de cada teste A/B é salvo em Analytics → Resultados A/B. Com o tempo você descobre qual tipo de abordagem funciona melhor para cada nicho.',
      code: null,
    },
    {
      num: 6,
      icon: '⚡',
      title: 'Ative o Otimizador automático',
      tag: 'Automação real',
      tagColor: 'badge-active',
      route: 'optimizer',
      routeLabel: 'Ir para Otimizador',
      desc: 'Defina regras que executam ações automáticas: pausar campanhas ruins, aumentar ou reduzir orçamento conforme performance.',
      steps: [
        'Vá em <strong>⚡ Otimizador</strong>.',
        'Selecione a automação e informe o <strong>Campaign ID</strong>.',
        'Clique em <strong>Carregar Preset</strong> para usar regras prontas: <em>conservador, balanceado ou agressivo</em>.',
        'Ou adicione regras manualmente: escolha a métrica (CPC, CTR, CPM...), a condição e a ação (pausar, +10% budget, etc.).',
        '<strong>Marque "Modo Simulação"</strong> na primeira vez — o sistema mostra o que faria sem executar nada.',
        'Quando satisfeito, desmarque a simulação e clique em <strong>Executar Otimização</strong>.',
      ],
      tip: 'Para otimização contínua, chame o endpoint <code>POST /api/v1/optimize</code> via cron job (GitHub Actions, Cloud Scheduler, etc.) uma vez por dia.',
      code: `// Regras sugeridas para começar (preset balanceado):
CPC > 3.00    → Reduzir orçamento 10%
CTR < 1.0%    → Notificar (verificar copy)
CPM > 50.00   → Pausar campanha
CTR > 3.0%    → Aumentar orçamento 10%`,
    },
    {
      num: 7,
      icon: '📊',
      title: 'Acompanhe métricas e Analytics',
      tag: 'Melhoria contínua',
      tagColor: 'badge-blue',
      route: 'campanhas',
      routeLabel: 'Ver Campanhas',
      desc: 'Consulte insights em tempo real e analise os dados coletados pelo sistema para melhorar a automação ao longo do tempo.',
      steps: [
        'Vá em <strong>📢 Campanhas</strong> → selecione uma automação → clique em <strong>📊 Insights</strong> em qualquer campanha.',
        'Escolha o período (hoje, ontem, últimos 7 dias, 30 dias) e veja CTR, CPC, CPM, gasto e impressões.',
        'Para a série histórica, use o endpoint <code>GET /api/v1/analytics/metrics-history?campaign_id=XXX</code> ou salve snapshots via <code>POST /api/v1/analytics/metrics-snapshot</code>.',
        'Veja os dados coletados de IA em <code>GET /api/v1/analytics/ai-history</code> — inclui o que a IA gerou e o que você sobrescreveu.',
        'Após um anúncio rodar, vincule as métricas reais à geração de IA usando <code>POST /api/v1/analytics/ai-feedback/{ai_history_id}</code>.',
      ],
      tip: 'O <code>ai_history_id</code> é retornado no response de <em>Criar com IA</em>. Guarde-o para depois vincular as métricas reais e construir um histórico de performance.',
      code: null,
    },
  ];

  const stepsHtml = steps.map(s => `
    <div class="guia-step" id="guia-step-${s.num}">
      <div class="guia-step-header" onclick="toggleGuiaStep(${s.num})">
        <div class="guia-step-num">${s.num}</div>
        <div class="guia-step-info">
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <span style="font-size:18px">${s.icon}</span>
            <strong style="font-size:15px">${s.title}</strong>
            <span class="badge ${s.tagColor}" style="font-size:11px">${s.tag}</span>
          </div>
          <p style="color:var(--text-2);font-size:12px;margin:2px 0 0">${s.desc}</p>
        </div>
        <span class="guia-chevron" id="guia-chev-${s.num}">›</span>
      </div>
      <div class="guia-step-body" id="guia-body-${s.num}" style="display:none">
        <ol class="guia-list">
          ${s.steps.map(st => `<li>${st}</li>`).join('')}
        </ol>
        ${s.tip ? `
          <div class="alert alert-info" style="margin-top:12px;font-size:13px">
            💡 <strong>Dica:</strong> ${s.tip}
          </div>` : ''}
        ${s.code ? `
          <div class="code-block" style="margin-top:12px;font-size:12px;white-space:pre">${s.code}</div>` : ''}
        <div style="margin-top:16px">
          <button class="btn btn-primary btn-sm" onclick="navigate('${s.route}')">
            ${s.icon} ${s.routeLabel}
          </button>
        </div>
      </div>
    </div>
  `).join('');

  content.innerHTML = `
    <div class="page-header">
      <div>
        <h2>📖 Guia de Uso</h2>
        <p>Aprenda a usar cada funcionalidade da automação, passo a passo.</p>
      </div>
      <button class="btn btn-ghost btn-sm" onclick="expandAllGuia()">Expandir tudo</button>
    </div>

    <div class="alert alert-info" style="margin-bottom:20px">
      ⚡ <strong>Fluxo recomendado:</strong>
      Configurações → Registrar Automação → Criar com IA → Teste A/B → Otimizador → Acompanhar Métricas
    </div>

    <div class="guia-progress">
      ${steps.map(s => `
        <div class="guia-progress-step" title="Passo ${s.num}: ${s.title}" onclick="scrollToGuiaStep(${s.num})">
          <div class="guia-progress-dot">${s.num}</div>
          <span class="guia-progress-label">${s.icon}</span>
        </div>
      `).join('<div class="guia-progress-line"></div>')}
    </div>

    <div style="display:flex;flex-direction:column;gap:10px;margin-top:20px">
      ${stepsHtml}
    </div>

    <div class="card" style="margin-top:20px;border-left:4px solid var(--blue)">
      <div class="card-header"><span class="card-title">Referência rápida de endpoints</span></div>
      <div class="code-block" style="font-size:12px">${[
        '── Automações ──────────────────────────────────',
        'POST   /api/v1/automacao              Registrar credenciais Meta',
        'GET    /api/v1/automacoes             Listar automações',
        '',
        '── Campanhas ───────────────────────────────────',
        'POST   /api/v1/campaign              Criar campanha',
        'GET    /api/v1/campaigns             Listar campanhas de uma automação',
        'PATCH  /api/v1/campaign/{id}/pause   Pausar campanha',
        'PATCH  /api/v1/campaign/{id}/activate Ativar campanha',
        'PATCH  /api/v1/campaign/{id}/budget  Atualizar orçamento',
        'GET    /api/v1/campaign/{id}/insights Métricas (insights)',
        '',
        '── Ad Set & Anúncio ────────────────────────────',
        'POST   /api/v1/adset                 Criar Ad Set',
        'POST   /api/v1/ad                    Criar Anúncio',
        '',
        '── IA ──────────────────────────────────────────',
        'POST   /api/v1/ai/generate-copy      Gerar copy com GPT-4o',
        'POST   /api/v1/ai/generate-audience  Gerar segmentação com GPT-4o',
        'POST   /api/v1/ai/generate-image     Gerar imagem com DALL-E 3',
        'POST   /api/v1/ai/create-full-ad     Criar anúncio completo com IA',
        '',
        '── Teste A/B ───────────────────────────────────',
        'POST   /api/v1/ab-test/create        Criar teste (variantes manuais)',
        'POST   /api/v1/ab-test/create-with-ai Criar teste com IA',
        'GET    /api/v1/ab-tests              Listar testes',
        'POST   /api/v1/ab-test/{id}/evaluate Avaliar vencedor',
        '',
        '── Otimizador ──────────────────────────────────',
        'POST   /api/v1/optimize              Executar otimização',
        'GET    /api/v1/optimize/presets      Presets de regras',
        '',
        '── Analytics ───────────────────────────────────',
        'GET    /api/v1/analytics/summary          Resumo geral',
        'GET    /api/v1/analytics/ai-history       Histórico de gerações IA',
        'POST   /api/v1/analytics/ai-feedback/{id} Vincular métricas reais à IA',
        'GET    /api/v1/analytics/ab-results       Resultados de testes A/B',
        'GET    /api/v1/analytics/optimizer-actions Ações do otimizador',
        'GET    /api/v1/analytics/metrics-history  Série histórica de métricas',
        'POST   /api/v1/analytics/metrics-snapshot Salvar snapshot de métricas',
      ].join('\n')}</div>
      <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
        <a href="/docs" target="_blank" class="btn btn-ghost btn-sm">📖 Swagger UI (interativo)</a>
        <a href="/redoc" target="_blank" class="btn btn-ghost btn-sm">📄 ReDoc</a>
      </div>
    </div>
  `;
}

function toggleGuiaStep(num) {
  const body = document.getElementById(`guia-body-${num}`);
  const chev = document.getElementById(`guia-chev-${num}`);
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  chev.style.transform = open ? 'rotate(90deg)' : 'none';
  chev.style.transition = 'transform 0.2s';
}

function expandAllGuia() {
  document.querySelectorAll('[id^="guia-body-"]').forEach(el => {
    el.style.display = 'block';
  });
  document.querySelectorAll('[id^="guia-chev-"]').forEach(el => {
    el.style.transform = 'rotate(90deg)';
  });
}

function scrollToGuiaStep(num) {
  const el = document.getElementById(`guia-step-${num}`);
  if (!el) return;
  el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  // Abre o passo se estiver fechado
  const body = document.getElementById(`guia-body-${num}`);
  if (body && body.style.display === 'none') toggleGuiaStep(num);
}

// ================================================================
// INIT
// ================================================================

document.addEventListener('DOMContentLoaded', () => {
  // Fecha sidebar ao clicar fora (mobile)
  document.getElementById('main-wrapper').addEventListener('click', () => {
    document.getElementById('sidebar').classList.remove('open');
  });

  // Fechar modal com ESC
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
  });

  // Sidebar toggle
  document.getElementById('sidebar-toggle').addEventListener('click', (e) => {
    e.stopPropagation();
    toggleSidebar();
  });

  // Router
  window.addEventListener('hashchange', handleRoute);
  handleRoute();

  // Health check
  checkApiHealth();
  setInterval(checkApiHealth, 30000); // a cada 30s

  // Se não tem API key configurada, mostra alerta sutil
  if (!CONFIG.getApiKey()) {
    setTimeout(() => {
      toast('Configure a API Key em ⚙ Configurações para usar a aplicação.', 'warning', 6000);
    }, 500);
  }
});
