// Obole — accès réseau centralisé.
//
// SEUL module du front autorisé à appeler `fetch` : tous les autres modules
// passent par cette couche. Aucun bundler (modules ES natifs). Chaque fonction
// encapsule un endpoint ; celles qui ont besoin des en-têtes HTTP (backup)
// renvoient la `Response`, les autres renvoient la donnée JSON ou lèvent une
// Error porteuse du `detail` serveur.

async function _json(res) {
  try { return await res.json(); } catch { return {}; }
}

// GET -> JSON, lève une Error(detail) si la réponse n'est pas 2xx.
async function _loadOrThrow(url) {
  const r = await fetch(url);
  if (!r.ok) {
    const j = await _json(r);
    throw new Error(j.detail || `Erreur ${r.status}`);
  }
  return r.json();
}

// Envoie un corps JSON et renvoie {ok, status, data} (l'appelant décide).
async function _send(url, method, body) {
  const r = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { ok: r.ok, status: r.status, data: await _json(r) };
}

export const api = {
  // --- Métadonnées / réglages ---------------------------------------------
  async meta() {
    const r = await fetch("/api/meta");
    return r.ok ? r.json() : null;
  },
  async settings() {
    const r = await fetch("/api/settings");
    return r.ok ? r.json() : null;
  },
  async summaryMeta() {
    const r = await fetch("/api/summary-meta");
    return r.ok ? r.json() : null;
  },
  saveSettings(values) {
    return _send("/api/settings", "PUT", { values });
  },

  // --- Recherche / fiches --------------------------------------------------
  async search(q) {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
    return r.ok ? r.json() : null;
  },
  stock(ticker) { return _loadOrThrow(`/api/stock/${encodeURIComponent(ticker)}`); },
  ratio(a, b) {
    return _loadOrThrow(`/api/ratio?a=${encodeURIComponent(a)}&b=${encodeURIComponent(b)}`);
  },
  async refreshTicker(ticker) {
    await fetch(`/api/refresh/${encodeURIComponent(ticker)}`, { method: "POST" });
  },
  async refreshIndex(id) {
    await fetch(`/api/index/${id}/refresh`, { method: "POST" });
  },

  // --- Indices personnalisés ----------------------------------------------
  async indices() {
    const r = await fetch("/api/indices");
    return r.ok ? r.json() : null;
  },
  index(id) { return _loadOrThrow(`/api/index/${encodeURIComponent(id)}`); },
  // Backtest de fiabilité (#31) : fenêtre visible + série affichée. Une seule
  // route par nature de référence ; le service tranche la fenêtre côté serveur.
  momentumBacktest(kind, ref, start, end, series) {
    const base = kind === "basket" ? "/api/index" : "/api/stock";
    const q = new URLSearchParams({ start, end, series }).toString();
    return _loadOrThrow(`${base}/${encodeURIComponent(ref)}/momentum-backtest?${q}`);
  },
  async indicesSummary() {
    const r = await fetch("/api/indices/summary");
    return r.ok ? r.json() : null;
  },
  async refreshIndicesSummary(categoryId) {
    const r = await fetch("/api/indices/summary/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(categoryId != null ? { category_id: categoryId } : {}),
    });
    if (!r.ok) throw new Error((await _json(r)).detail || "Erreur de recalcul");
    return r.json();
  },
  createCategory(name) { return _send("/api/indices/categories", "POST", { name }); },
  createIndex(payload) { return _send("/api/indices", "POST", payload); },
  updateIndex(id, payload) { return _send(`/api/indices/${id}`, "PUT", payload); },
  async deleteIndex(id) {
    const r = await fetch(`/api/indices/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  async deleteCategory(id) {
    const r = await fetch(`/api/indices/categories/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },

  // --- Screener ------------------------------------------------------------
  async screenerMeta() {
    const r = await fetch("/api/screener/meta");
    return r.ok ? r.json() : null;
  },
  async screenerPing() {
    const r = await fetch("/api/screener/ping");
    return { ok: r.ok, status: r.status };
  },
  runScreener(body) { return _send("/api/screener/run", "POST", body); },

  // --- Watchlist (#25) ------------------------------------------------------
  watchlist() { return _loadOrThrow("/api/watchlist"); },
  runWatchlist(body) { return _send("/api/watchlist/run", "POST", body || {}); },
  setWatchTier(ticker, tier) {
    return _send(`/api/watchlist/items/${encodeURIComponent(ticker)}`, "PUT", { tier });
  },
  removeWatchItem(ticker) {
    return _send(`/api/watchlist/items/${encodeURIComponent(ticker)}`, "DELETE", {});
  },
  setWatchRef(ticker, start) {
    return _send(`/api/watchlist/ref/${encodeURIComponent(ticker)}`, "PUT", { start });
  },
  clearWatchRef(ticker) {
    return _send(`/api/watchlist/ref/${encodeURIComponent(ticker)}`, "DELETE", {});
  },

  // --- Portefeuille (#17) --------------------------------------------------
  portfolioAccounts() {
    return _loadOrThrow("/api/portfolio/accounts");
  },
  createPortfolioAccount(payload) {
    return _send("/api/portfolio/accounts", "POST", payload);
  },
  async deletePortfolioAccount(id) {
    const r = await fetch(`/api/portfolio/accounts/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  portfolioTransactions(accountId, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/transactions${q ? "?" + q : ""}`);
  },
  createPortfolioTransaction(payload) {
    return _send("/api/portfolio/transactions", "POST", payload);
  },
  updatePortfolioTransaction(id, payload) {
    return _send(`/api/portfolio/transactions/${id}`, "PUT", payload);
  },
  async deletePortfolioTransaction(id) {
    const r = await fetch(`/api/portfolio/transactions/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  portfolioDividends(accountId) {
    const q = accountId != null ? `?account_id=${encodeURIComponent(accountId)}` : "";
    return _loadOrThrow(`/api/portfolio/dividends${q}`);
  },
  createPortfolioDividend(payload) {
    return _send("/api/portfolio/dividends", "POST", payload);
  },
  updatePortfolioDividend(id, payload) {
    return _send(`/api/portfolio/dividends/${id}`, "PUT", payload);
  },
  async deletePortfolioDividend(id) {
    const r = await fetch(`/api/portfolio/dividends/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  portfolioPositions(accountId, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/positions${q ? "?" + q : ""}`);
  },
  portfolioTags(accountId) {
    const q = accountId != null ? `?account_id=${encodeURIComponent(accountId)}` : "";
    return _loadOrThrow(`/api/portfolio/tags${q}`);
  },
  // Étiquette toutes les transactions d'un titre (positions) — 0 fetch hors api.js.
  setPositionTag(payload) {
    return _send("/api/portfolio/positions/tag", "POST", payload);
  },
  portfolioBenchmarks() {
    return _loadOrThrow("/api/portfolio/benchmarks");
  },
  portfolioSummary(accountId, benchmark, period, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (benchmark) p.set("benchmark", benchmark);
    if (period) p.set("period", period);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/summary${q ? "?" + q : ""}`);
  },
  portfolioRisk(accountId, benchmark, period, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (benchmark) p.set("benchmark", benchmark);
    if (period) p.set("period", period);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/risk${q ? "?" + q : ""}`);
  },
  portfolioPerformance(accountId, benchmark, period, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (benchmark) p.set("benchmark", benchmark);
    if (period) p.set("period", period);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/performance${q ? "?" + q : ""}`);
  },
  // Page Dividende du portefeuille (#17.5) : revenu par année/mois/payeur, KPI
  // agrégés et tableau par ligne. Aucune période : annualisation sur tout
  // l'historique de détention.
  portfolioDividendPage(accountId, tag) {
    const p = new URLSearchParams();
    if (accountId != null) p.set("account_id", accountId);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/dividend-metrics${q ? "?" + q : ""}`);
  },
  portfolioSecurity(ticker, benchmark) {
    const p = new URLSearchParams();
    p.set("ticker", ticker);
    if (benchmark) p.set("benchmark", benchmark);
    return _loadOrThrow(`/api/portfolio/security?${p.toString()}`);
  },
  portfolioCorrelationTest(accountId, benchmark, period, tag, ticker) {
    const p = new URLSearchParams();
    if (ticker) p.set("ticker", ticker);
    if (accountId != null) p.set("account_id", accountId);
    if (benchmark) p.set("benchmark", benchmark);
    if (period) p.set("period", period);
    if (tag) p.set("tag", tag);
    const q = p.toString();
    return _loadOrThrow(`/api/portfolio/risk/correlation-test${q ? "?" + q : ""}`);
  },

  // Noms de société d'une liste de tickers (complément paresseux du Résumé) :
  // appelé APRÈS le premier rendu, tolère le réseau côté serveur.
  portfolioNames(tickers) {
    const q = new URLSearchParams({ tickers: (tickers || []).join(",") });
    return _loadOrThrow(`/api/portfolio/names?${q}`);
  },

  // --- Valorisation : calculatrice de prix juste (#20) ---------------------
  saveValuation(ticker, payload) {
    return _send(`/api/valuation/${encodeURIComponent(ticker)}`, "PUT", payload);
  },

  async clearValuation(ticker) {
    const r = await fetch(`/api/valuation/${encodeURIComponent(ticker)}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },

  // --- Thèses d'entreprise (#21) ------------------------------------------
  // Contenu = markdown (chaîne). `_loadOrThrow` pour la lecture (une absence est
  // une erreur porteuse du `detail`), `_send` pour l'écriture (l'appelant décide).
  thesis(ticker) {
    return _loadOrThrow(`/api/thesis/${encodeURIComponent(ticker)}`);
  },
  saveThesis(ticker, content) {
    return _send(`/api/thesis/${encodeURIComponent(ticker)}`, "PUT", { content });
  },
  async deleteThesis(ticker) {
    const r = await fetch(`/api/thesis/${encodeURIComponent(ticker)}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  // La route est un POST (`@app.post("/api/thesis/{ticker}/prompt")`) : le cas
  // d'usage exécute une analyse complète (lecture des données), ce n'est pas une
  // simple lecture. Un GET ici renvoyait 405 — panne silencieuse du bouton.
  thesisPrompt(ticker) {
    return _send(`/api/thesis/${encodeURIComponent(ticker)}/prompt`, "POST", {});
  },
  async uploadThesisAsset(formData) {
    const r = await fetch("/api/thesis/assets", { method: "POST", body: formData });
    if (!r.ok) {
      const j = await _json(r);
      throw new Error(j.detail || `Upload refusé (${r.status})`);
    }
    return r.json();
  },

  // --- Points de contrôle suivis (#21, bande « Suivi ») -------------------
  // Liste indépendante du document markdown de la thèse. `_loadOrThrow` pour la
  // lecture, `_send` pour les mutations (l'appelant décide du sort d'un échec).
  checkpoints(ticker) {
    return _loadOrThrow(`/api/checkpoints/${encodeURIComponent(ticker)}`);
  },
  addCheckpoint(ticker, label) {
    return _send(`/api/checkpoints/${encodeURIComponent(ticker)}`, "POST", { label });
  },
  saveCheckpoint(id, label, done) {
    return _send(`/api/checkpoints/${id}`, "PUT", { label, done });
  },
  async deleteCheckpoint(id) {
    const r = await fetch(`/api/checkpoints/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },

  // --- Données manuelles / sauvegarde -------------------------------------
  importManual(ticker, entries) {
    return _send(`/api/manual/${encodeURIComponent(ticker)}`, "POST", entries);
  },
  // --- Import piloté (#23) : brouillons soumis à validation humaine --------
  proposeImport(target, ref, csvText) {
    return _send("/api/imports/propose", "POST", { target, ref, csv_text: csvText });
  },
  importDrafts() { return _loadOrThrow("/api/imports"); },
  importDraft(id) { return _loadOrThrow(`/api/imports/${id}`); },
  applyImportDraft(id) { return _send(`/api/imports/${id}/apply`, "POST", {}); },
  async discardImportDraft(id) {
    const r = await fetch(`/api/imports/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  backup() { return fetch("/api/backup"); },
  async restore(formData) {
    const r = await fetch("/api/restore", { method: "POST", body: formData });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
  async purgeCache() {
    const r = await fetch("/api/cache/purge", { method: "POST" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },

  // --- Événements ----------------------------------------------------------
  async events(kind, query) {
    const r = await fetch(`/api/events/${kind}${query}`);
    return r.ok ? r.json() : null;
  },
  saveEvent(url, method, body) { return _send(url, method, body); },
  async deleteEvent(id) {
    const r = await fetch(`/api/events/${id}`, { method: "DELETE" });
    return { ok: r.ok, status: r.status, data: await _json(r) };
  },
};
