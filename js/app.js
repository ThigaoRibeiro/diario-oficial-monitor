/**
 * app.js — Diário Oficial Monitor v3
 *
 * Funcionalidades:
 *  - Aba "Hoje"         : convocados do dia com filtro por prefeitura
 *  - Aba "Meu Nome"     : busca em todo o histórico de todas as prefeituras
 *  - Aba "Configurações": salva nome, seleciona prefeituras, adiciona novas
 *                         via dropdown de estados/cidades (IBGE API gratuita)
 */

"use strict";

// ═══════════════════════════════════════════════════════════════
// CONSTANTES
// ═══════════════════════════════════════════════════════════════
const DATA_BASE   = "./data";
const CONFIG_BASE = "./config";
const IBGE_BASE   = "https://servicodados.ibge.gov.br/api/v1/localidades";

const LS_NAME       = "dom_watch_name";
const LS_PREFS      = "dom_selected_prefs";
const LS_WATCH      = "dom_watch_active";
const LS_MY_PREFS   = "dom_my_prefs";     // prefeituras adicionadas manualmente

// ═══════════════════════════════════════════════════════════════
// ESTADO GLOBAL
// ═══════════════════════════════════════════════════════════════
let globalIndex      = [];
let prefeituras      = [];     // do config/prefeituras.json (scrapeadas)
let myPrefs          = [];     // adicionadas pelo usuário via IBGE (localStorage)
let allDates         = [];
let currentDateIdx   = 0;
let activePrefFilter = null;
let todayQuery       = "";
let watchName        = "";
let selectedPrefs    = [];

// Seleção IBGE
let ibgeEstados      = [];
let ibgeCidades      = [];
let ibgeSelectedCity = null;  // { nome, estado, uf }

// ═══════════════════════════════════════════════════════════════
// DOM
// ═══════════════════════════════════════════════════════════════
const $ = id => document.getElementById(id);

const elTabs        = document.querySelectorAll(".tab");
const elTabContents = document.querySelectorAll(".tab-content");

// Aba Hoje
const elDateDisplay = $("date-display");
const elBtnPrev     = $("btn-prev");
const elBtnNext     = $("btn-next");
const elPrefFilter  = $("pref-filter");
const elTodaySearch = $("today-search");
const elTodayClr    = $("today-search-clear");
const elStatCount   = $("stat-count");
const elStatPrefs   = $("stat-prefs");
const elStatPdfCard = $("stat-pdf-card");
const elStatPdfLink = $("stat-pdf-link");
const elHojeLoading = $("hoje-loading");
const elHojeEmpty   = $("hoje-empty");
const elHojeNoRes   = $("hoje-nores");
const elHojeCards   = $("hoje-cards");

// Aba Meu Nome
const elNameInput     = $("name-input");
const elBtnNameSearch = $("btn-name-search");
const elWatchToggle   = $("watch-toggle");
const elNameResHdr    = $("name-results-header");
const elNameResCount  = $("name-results-count");
const elNameLoading   = $("name-loading");
const elNameEmpty     = $("name-empty");
const elNameCards     = $("name-cards");

// Aba Config
const elConfigName    = $("config-name");
const elBtnSaveName   = $("btn-save-name");
const elNameSavedMsg  = $("name-saved-msg");
const elPrefList      = $("pref-list");
const elBtnClearLocal = $("btn-clear-local");
const elHeaderBadge   = $("header-watch-badge");
const elHeaderName    = $("header-watch-name");
const elHeaderSub     = $("header-subtitle");

// IBGE
const elSelectEstado  = $("select-estado");
const elSelectCidade  = $("select-cidade");
const elPortalUrlFld  = $("portal-url-field");
const elPortalUrl     = $("input-portal-url");
const elCityStatus    = $("city-status");
const elBtnAddPref    = $("btn-add-pref");
const elMyPrefsCard   = $("my-prefs-card");
const elMyPrefsList   = $("my-prefs-list");

// ═══════════════════════════════════════════════════════════════
// UTILITÁRIOS
// ═══════════════════════════════════════════════════════════════

function escHtml(s) {
  if (!s) return "";
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function hl(text, q) {
  if (!q || !text) return escHtml(text);
  const re = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g,"\\$&")})`, "gi");
  return escHtml(text).replace(re, "<mark>$1</mark>");
}

function fmtDate(iso) {
  if (!iso) return "—";
  const [y,m,d] = iso.split("-");
  return new Date(+y,+m-1,+d).toLocaleDateString("pt-BR",{
    weekday:"long", day:"2-digit", month:"long", year:"numeric"
  });
}

function slug(s) {
  return s.normalize("NFD").replace(/[\u0300-\u036f]/g,"")
    .toLowerCase().replace(/\s+/g,"-").replace(/[^a-z0-9-]/g,"");
}

async function fetchJSON(url, opts = {}) {
  const r = await fetch(url, { cache: "no-cache", ...opts });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${url}`);
  return r.json();
}

function loadLS() {
  watchName    = localStorage.getItem(LS_NAME)  || "";
  selectedPrefs= JSON.parse(localStorage.getItem(LS_PREFS)    || "[]");
  myPrefs      = JSON.parse(localStorage.getItem(LS_MY_PREFS) || "[]");
  const act    = localStorage.getItem(LS_WATCH);
  if (elWatchToggle) elWatchToggle.checked = act === "true";
  if (elNameInput)   elNameInput.value  = watchName;
  if (elConfigName)  elConfigName.value = watchName;
}

// ═══════════════════════════════════════════════════════════════
// TABS
// ═══════════════════════════════════════════════════════════════

elTabs.forEach(tab => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    elTabs.forEach(t => t.classList.remove("active"));
    elTabContents.forEach(c => { c.classList.remove("active"); c.style.display = "none"; });
    tab.classList.add("active");
    const content = $(`tab-${target}`);
    if (content) { content.classList.add("active"); content.style.display = "block"; }
    if (target === "meu-nome" && watchName) elNameInput.value = watchName;
    if (target === "config") renderMyPrefsList();
  });
});

// ═══════════════════════════════════════════════════════════════
// CARDS
// ═══════════════════════════════════════════════════════════════

function renderCard(c, q, showPref = true) {
  const pref = showPref && c.prefeitura_nome
    ? `<span class="card-pref-badge">🏛️ ${escHtml(c.prefeitura_nome)} — ${escHtml(c.prefeitura_estado||"")}</span>`
    : "";
  const classif = c.classificacao != null
    ? `<span class="card-classif">${c.classificacao}º</span>` : "";
  const cargo = c.cargo && c.cargo !== "Não especificado"
    ? `<div class="card-cargo">🏛️ ${hl(c.cargo, q)}</div>` : "";
  const edital = c.edital
    ? `<div class="card-meta-item"><span>📄</span>${hl(c.edital,q)}</div>` : "";
  const local  = c.local
    ? `<div class="card-meta-item"><span>📍</span>${escHtml(c.local)}</div>` : "";
  const prazo  = c.prazo
    ? `<div class="badge-prazo">⏰ Prazo: ${escHtml(c.prazo)}</div>` : "";
  const dt     = c.date
    ? `<div class="card-meta-item"><span>📅</span>${fmtDate(c.date)}</div>` : "";

  return `<div class="card">
    ${pref}${classif}
    <div class="card-name">${hl(c.nome, q)}</div>
    ${cargo}
    <div class="card-meta">${edital}${local}${dt}</div>
    ${prazo}
  </div>`;
}

// ═══════════════════════════════════════════════════════════════
// ABA HOJE
// ═══════════════════════════════════════════════════════════════

function showHojeState(s) {
  elHojeLoading.style.display = s==="loading" ? "block" : "none";
  elHojeEmpty.style.display   = s==="empty"   ? "block" : "none";
  elHojeNoRes.style.display   = s==="nores"   ? "block" : "none";
  elHojeCards.style.display   = s==="cards"   ? "grid"  : "none";
}

function renderHoje() {
  const date = allDates[currentDateIdx];
  elDateDisplay.textContent = date ? fmtDate(date) : "Sem dados";
  elBtnPrev.disabled = currentDateIdx >= allDates.length - 1;
  elBtnNext.disabled = currentDateIdx <= 0;

  const entries = globalIndex.filter(e => e.date === date);
  const filtered = activePrefFilter ? entries.filter(e=>e.prefeitura_id===activePrefFilter) : entries;

  // Chips de prefeitura
  const prefsForDate = [...new Set(entries.map(e=>e.prefeitura_id))];
  elPrefFilter.innerHTML = "";
  if (prefsForDate.length > 1) {
    const all = document.createElement("button");
    all.className = "pref-chip" + (!activePrefFilter ? " active" : "");
    all.textContent = "Todas";
    all.onclick = () => { activePrefFilter = null; renderHoje(); };
    elPrefFilter.appendChild(all);
    prefsForDate.forEach(pid => {
      const p = prefeituras.find(x=>x.id===pid) || { id:pid, nome:pid };
      const chip = document.createElement("button");
      chip.className = "pref-chip" + (activePrefFilter===pid ? " active" : "");
      chip.textContent = p.nome;
      chip.onclick = () => { activePrefFilter = pid; renderHoje(); };
      elPrefFilter.appendChild(chip);
    });
  }

  const total = filtered.reduce((s,e)=>s+(e.convocados_count||0),0);
  elStatCount.textContent = total;
  elStatPrefs.textContent = new Set(filtered.map(e=>e.prefeitura_id)).size;

  if (activePrefFilter && filtered.length===1 && filtered[0].pdf_url) {
    elStatPdfCard.style.display = "block";
    elStatPdfLink.href = filtered[0].pdf_url;
  } else { elStatPdfCard.style.display = "none"; }

  if (!filtered.length || total === 0) { showHojeState("empty"); return; }
  loadHojeCards(filtered);
}

async function loadHojeCards(entries) {
  showHojeState("loading");
  let all = [];
  for (const e of entries) {
    try {
      const data = await fetchJSON(`${DATA_BASE}/${e.prefeitura_id}/${e.date}.json`);
      (data.convocados||[]).forEach(c => all.push({
        ...c, date:e.date,
        prefeitura_nome:   e.prefeitura_nome,
        prefeitura_estado: e.prefeitura_estado,
        prefeitura_id:     e.prefeitura_id,
      }));
    } catch {}
  }
  const q = todayQuery;
  const f = q ? all.filter(c=>(c.nome||"").toLowerCase().includes(q)||(c.cargo||"").toLowerCase().includes(q)) : all;
  if (!f.length) { showHojeState(q?"nores":"empty"); return; }
  elHojeCards.innerHTML = f.map(c=>renderCard(c,q,entries.length>1||!activePrefFilter)).join("");
  showHojeState("cards");
}

elBtnPrev.addEventListener("click", ()=>{ if(currentDateIdx<allDates.length-1){currentDateIdx++;renderHoje();} });
elBtnNext.addEventListener("click", ()=>{ if(currentDateIdx>0){currentDateIdx--;renderHoje();} });
elTodaySearch.addEventListener("input", ()=>{
  todayQuery = elTodaySearch.value.trim().toLowerCase();
  elTodayClr.style.display = todayQuery ? "block" : "none";
  if (allDates.length) renderHoje();
});
elTodayClr.addEventListener("click", ()=>{
  elTodaySearch.value=""; todayQuery=""; elTodayClr.style.display="none";
  if(allDates.length) renderHoje(); elTodaySearch.focus();
});

// ═══════════════════════════════════════════════════════════════
// ABA MEU NOME
// ═══════════════════════════════════════════════════════════════

async function searchByName(name) {
  if (!name.trim()) return;
  const q = name.trim().toLowerCase();
  elNameResHdr.style.display = "none";
  elNameEmpty.style.display  = "none";
  elNameCards.style.display  = "none";
  elNameLoading.style.display= "block";

  // Prefeituras a buscar: scrapeadas + minhas salvas manualmente
  const scrapeadas = prefeituras.filter(p=>p.ativo && (selectedPrefs.length===0 || selectedPrefs.includes(p.id)));
  let found = [];

  for (const pref of scrapeadas) {
    try {
      const idx = await fetchJSON(`${DATA_BASE}/${pref.id}/index.json`);
      for (const entry of idx) {
        if (!entry.has_convocacoes) continue;
        try {
          const data = await fetchJSON(`${DATA_BASE}/${pref.id}/${entry.date}.json`);
          (data.convocados||[]).filter(c=>(c.nome||"").toLowerCase().includes(q))
            .forEach(c=>found.push({...c, date:entry.date, prefeitura_nome:pref.nome, prefeitura_estado:pref.estado, prefeitura_id:pref.id}));
        } catch {}
      }
    } catch {}
  }

  found.sort((a,b)=>b.date.localeCompare(a.date));
  elNameLoading.style.display = "none";

  if (!found.length) { elNameEmpty.style.display="block"; return; }
  elNameResCount.textContent = `${found.length} resultado(s)`;
  elNameResHdr.style.display = "flex";
  elNameCards.innerHTML = found.map(c=>renderCard(c,name.trim(),true)).join("");
  elNameCards.style.display = "grid";
}

elBtnNameSearch.addEventListener("click", ()=>{ const v=elNameInput.value.trim(); if(v) searchByName(v); });
elNameInput.addEventListener("keydown", e=>{ if(e.key==="Enter") elBtnNameSearch.click(); });
elWatchToggle.addEventListener("change", ()=>{
  const name = elNameInput.value.trim() || watchName;
  localStorage.setItem(LS_WATCH, elWatchToggle.checked ? "true" : "false");
  if (elWatchToggle.checked && name) { watchName=name; localStorage.setItem(LS_NAME,name); }
  updateWatchBadge();
});

function updateWatchBadge() {
  const on = localStorage.getItem(LS_WATCH)==="true";
  if (on && watchName) { elHeaderBadge.style.display="block"; elHeaderName.textContent=watchName; }
  else elHeaderBadge.style.display="none";
}

// ═══════════════════════════════════════════════════════════════
// ABA CONFIG — NOME
// ═══════════════════════════════════════════════════════════════

elBtnSaveName.addEventListener("click", ()=>{
  const name = elConfigName.value.trim().toUpperCase();
  if (!name) return;
  watchName = name;
  localStorage.setItem(LS_NAME, name);
  elNameSavedMsg.style.display = "block";
  elNameInput.value = name;
  updateWatchBadge();
  setTimeout(()=>elNameSavedMsg.style.display="none", 2500);
});

elBtnClearLocal.addEventListener("click", ()=>{
  if (!confirm("Apagar nome salvo e prefeituras? Não é possível desfazer.")) return;
  [LS_NAME,LS_PREFS,LS_WATCH,LS_MY_PREFS].forEach(k=>localStorage.removeItem(k));
  watchName=""; selectedPrefs=[]; myPrefs=[];
  elConfigName.value=""; elNameInput.value="";
  elWatchToggle.checked=false;
  updateWatchBadge();
  renderPrefList();
  renderMyPrefsList();
  alert("Dados locais apagados.");
});

// ═══════════════════════════════════════════════════════════════
// ABA CONFIG — LISTA DE PREFEITURAS (scrapeadas)
// ═══════════════════════════════════════════════════════════════

function renderPrefList() {
  elPrefList.innerHTML = "";
  prefeituras.forEach(p => {
    const sel = selectedPrefs.includes(p.id);
    const item = document.createElement("div");
    item.className = "pref-list-item" + (sel?" selected":"") + (!p.ativo?" inactive":"");
    item.innerHTML = `
      <div>
        <div class="pref-item-name">🏛️ ${escHtml(p.nome)} — ${escHtml(p.estado||"")}</div>
        <div class="pref-item-info">${p.ativo?"✅ Ativo":"⚠️ Inativo — configure em config/prefeituras.json"}</div>
      </div>
      <div class="pref-item-check">${sel?"✓":""}</div>`;
    if (p.ativo) {
      item.addEventListener("click", ()=>{
        if(selectedPrefs.includes(p.id)) selectedPrefs=selectedPrefs.filter(id=>id!==p.id);
        else selectedPrefs.push(p.id);
        localStorage.setItem(LS_PREFS, JSON.stringify(selectedPrefs));
        renderPrefList();
      });
    }
    elPrefList.appendChild(item);
  });
}

// ═══════════════════════════════════════════════════════════════
// ABA CONFIG — MINHAS PREFEITURAS (adicionadas via IBGE)
// ═══════════════════════════════════════════════════════════════

function renderMyPrefsList() {
  myPrefs = JSON.parse(localStorage.getItem(LS_MY_PREFS)||"[]");
  if (!myPrefs.length) { elMyPrefsCard.style.display="none"; return; }
  elMyPrefsCard.style.display="block";
  elMyPrefsList.innerHTML = "";

  myPrefs.forEach((p, i) => {
    const item = document.createElement("div");
    item.className = "pref-list-item";
    item.innerHTML = `
      <div>
        <div class="pref-item-name">📌 ${escHtml(p.nome)} — ${escHtml(p.estado)}</div>
        <div class="pref-item-info">
          ${p.portal_url ? `<a href="${escHtml(p.portal_url)}" target="_blank" rel="noopener">🔗 ${escHtml(p.portal_url)}</a>` : "URL não configurada"}
        </div>
      </div>
      <button class="btn-remove" data-index="${i}" title="Remover">🗑️</button>`;
    elMyPrefsList.appendChild(item);
  });

  elMyPrefsList.querySelectorAll(".btn-remove").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.index, 10);
      myPrefs.splice(idx, 1);
      localStorage.setItem(LS_MY_PREFS, JSON.stringify(myPrefs));
      renderMyPrefsList();
    });
  });
}

// ═══════════════════════════════════════════════════════════════
// IBGE — ESTADOS E CIDADES
// ═══════════════════════════════════════════════════════════════

async function loadEstados() {
  elSelectEstado.innerHTML = `<option value=""><span class="inline-spin"></span> Carregando estados...</option>`;
  try {
    ibgeEstados = await fetchJSON(`${IBGE_BASE}/estados?orderBy=nome`);
    elSelectEstado.innerHTML = `<option value="">Selecione o estado...</option>`;
    ibgeEstados.forEach(e => {
      const opt = document.createElement("option");
      opt.value = e.sigla;
      opt.textContent = `${e.nome} (${e.sigla})`;
      opt.dataset.nome = e.nome;
      elSelectEstado.appendChild(opt);
    });
  } catch {
    elSelectEstado.innerHTML = `<option value="">Erro ao carregar — tente recarregar a página</option>`;
  }
}

async function loadCidades(uf) {
  elSelectCidade.innerHTML = `<option value="">Carregando cidades...</option>`;
  elSelectCidade.disabled = true;
  ibgeSelectedCity = null;
  elBtnAddPref.disabled = true;
  elCityStatus.style.display = "none";
  elPortalUrlFld.style.display = "none";

  try {
    ibgeCidades = await fetchJSON(`${IBGE_BASE}/estados/${uf}/municipios?orderBy=nome`);
    elSelectCidade.innerHTML = `<option value="">Selecione a cidade...</option>`;
    ibgeCidades.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c.id;
      opt.textContent = c.nome;
      opt.dataset.nome = c.nome;
      elSelectCidade.appendChild(opt);
    });
    elSelectCidade.disabled = false;
  } catch {
    elSelectCidade.innerHTML = `<option value="">Erro ao carregar cidades</option>`;
  }
}

function onCidadeSelect() {
  const opt = elSelectCidade.selectedOptions[0];
  if (!opt || !opt.value) {
    ibgeSelectedCity = null;
    elBtnAddPref.disabled = true;
    elCityStatus.style.display = "none";
    elPortalUrlFld.style.display = "none";
    return;
  }

  const ufOpt    = elSelectEstado.selectedOptions[0];
  const uf       = ufOpt.value;
  const ufNome   = ufOpt.dataset.nome || uf;
  const cityNome = opt.dataset.nome;
  const cityId   = slug(cityNome);

  ibgeSelectedCity = { nome: cityNome, estado: uf, id: cityId };

  // Verifica se já existe nas prefeituras scrapeadas
  const exists = prefeituras.find(p =>
    p.id === cityId ||
    slug(p.nome) === cityId ||
    (p.nome.toLowerCase().includes(cityNome.toLowerCase()))
  );

  const alreadySaved = myPrefs.some(p => p.id === cityId);

  elPortalUrlFld.style.display = "block";
  elCityStatus.style.display = "block";

  if (alreadySaved) {
    elCityStatus.className = "city-status added";
    elCityStatus.innerHTML = `📌 <strong>${escHtml(cityNome)}</strong> já está na sua lista.`;
    elBtnAddPref.disabled = true;
  } else if (exists) {
    elCityStatus.className = "city-status found";
    elCityStatus.innerHTML = `✅ <strong>${escHtml(cityNome)}</strong> já é monitorada automaticamente pelo scraper! Marque-a na lista acima.`;
    elBtnAddPref.disabled = true;
  } else {
    elCityStatus.className = "city-status not-found";
    elCityStatus.innerHTML = `⚠️ <strong>${escHtml(cityNome)}</strong> — ${escHtml(ufNome)}<br>
      Ainda não temos o scraper configurado para esta cidade. Adicione à sua lista para lembrar de verificar manualmente ou nos ajude a configurar o portal.`;
    elBtnAddPref.disabled = false;
  }
}

elSelectEstado.addEventListener("change", ()=>{
  const uf = elSelectEstado.value;
  if (uf) loadCidades(uf);
  else {
    elSelectCidade.innerHTML = `<option value="">Selecione o estado primeiro</option>`;
    elSelectCidade.disabled = true;
    elBtnAddPref.disabled = true;
    elCityStatus.style.display = "none";
    elPortalUrlFld.style.display = "none";
  }
});

elSelectCidade.addEventListener("change", onCidadeSelect);

elBtnAddPref.addEventListener("click", ()=>{
  if (!ibgeSelectedCity) return;
  const city = {
    ...ibgeSelectedCity,
    portal_url: elPortalUrl.value.trim() || null,
    adicionado: new Date().toISOString().split("T")[0],
  };
  myPrefs.push(city);
  localStorage.setItem(LS_MY_PREFS, JSON.stringify(myPrefs));

  elCityStatus.className = "city-status added";
  elCityStatus.innerHTML = `✅ <strong>${escHtml(city.nome)}</strong> adicionada à sua lista!`;
  elBtnAddPref.disabled = true;
  elPortalUrl.value = "";
  renderMyPrefsList();
});

// ═══════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════

async function init() {
  loadLS();
  updateWatchBadge();

  // Carrega config + IBGE em paralelo
  const [prefsResult, ibgeResult, idxResult] = await Promise.allSettled([
    fetchJSON(`${CONFIG_BASE}/prefeituras.json`),
    loadEstados(),
    fetchJSON(`${DATA_BASE}/global-index.json`),
  ]);

  prefeituras  = prefsResult.status  === "fulfilled" ? prefsResult.value  : [];
  globalIndex  = idxResult.status    === "fulfilled" ? idxResult.value    : [];

  renderPrefList();
  renderMyPrefsList();

  // Datas únicas
  const dateSet = new Set(globalIndex.map(e=>e.date));
  allDates = [...dateSet].sort((a,b)=>b.localeCompare(a));

  // Subtitle do header
  const active = prefeituras.filter(p=>p.ativo).map(p=>p.nome).join(", ");
  elHeaderSub.textContent = active
    ? `Monitorando: ${active}`
    : "Configure as prefeituras em ⚙️ Configurações";

  if (!allDates.length) { showHojeState("empty"); return; }
  currentDateIdx = 0;
  showHojeState("loading");
  renderHoje();

  if (localStorage.getItem(LS_WATCH)==="true" && watchName) elWatchToggle.checked=true;
}

init();
