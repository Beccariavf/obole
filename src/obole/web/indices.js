// Obole — indices personnalisés (CRUD, stats « coup d'œil »).
import { api } from "./api.js";

export const indicesMixin = {
  async openIndices() {
    this.indicesOpen = true;
    this.backTo = null;
    this.summaryError = "";
    this.resetEditor();
    await this.loadIndices();
    this.loadSummaries();
  },

  async loadIndices() {
    try {
      const data = await api.indices();
      if (data == null) return;
      this.indicesData = data;
    } catch { /* silencieux : la modale reste ouverte */ }
  },

  // Stats « coup d'œil » de tous les indices : calcul serveur à la volée
  // (séries cachées) — la modale affiche d'abord les définitions, puis les
  // stats remplissent toutes les lignes d'un coup quand la réponse arrive.

  async loadSummaries() {
    this.summariesLoading = true;
    try {
      const data = await api.indicesSummary();
      if (data == null) {
        this.summaryError = "Impossible de calculer les indicateurs des indices.";
        return;
      }
      this.summaryError = "";
      this.idxStats = this._summariesMap(data);
    } catch {
      this.summaryError = "Impossible de calculer les indicateurs des indices.";
    } finally { this.summariesLoading = false; }
  },

  // Recalcul forcé (purge prix membres + série cachée) : global (null) ou
  // scopé à une catégorie (bouton ↻). Réponse = stats fraîches.

  async refreshIndicesSummary(categoryId) {
    this.summariesLoading = true;
    this.summaryError = "";
    try {
      const data = await api.refreshIndicesSummary(categoryId);
      this.idxStats = { ...this.idxStats, ...this._summariesMap(data) };
    } catch (e) {
      this.summaryError = e.message;
    } finally {
      this.summariesLoading = false;
    }
  },

  _summariesMap(list) {
    const map = {};
    for (const s of list) map[s.index_id] = s;
    return map;
  },

  // Accès aux stats d'un indice dans la liste : null tant que non calculé.

  statSv(ix, key) {
    const s = this.idxStats[ix.id];
    return s && !s.error && s.stats ? s.stats[key] : null;
  },

  sumError(ix) {
    const s = this.idxStats[ix.id];
    return s && s.error ? s.error : "";
  },

  statDisplay(ix, key) {
    const sv = this.statSv(ix, key);
    if (!sv || sv.value == null) return "—";
    const unit = key === "distance_sigma" ? " σ" : " %";
    return this.fmt(sv.value) + unit;
  },

  closeIndices() { this.indicesOpen = false; },

  // --- Screener (J4 : filtres + tableau triable) ------------------------

  openIndex(ix) {
    this.indicesOpen = false;
    this.loadIndex(ix.id);
  },

  async loadIndex(id) {
    this.loading = true; this.error = ""; this.data = null;
    this.query = "";  // la fiche affiche l'indice : on efface le ticker précédent
    // Sans seuils (/api/meta), le tracé et les labels sont impossibles : erreur
    // explicite plutôt qu'un graphe vide silencieux.
    if (!this.metaReady) {
      this.loading = false;
      this.error = "Seuils indisponibles (/api/meta) — impossible de calculer l'analyse. Recharge la page.";
      return;
    }
    try {
      this.data = await api.index(id);
      this.initRange();
      this.compareKeys = [];  // nouvelle fiche : comparateur remis à zéro
      this.$nextTick(() => {
        try { this.applySectionsAfterLoad(); } catch (e) { console.error("applySections error:", e); }
      });
    } catch (e) {
      this.error = e.message;
    } finally {
      this.loading = false;
    }
  },

  openMember(m) {
    const idx = this.data?.identity;
    if (idx && idx.index_id != null) {
      this.backTo = { index_id: idx.index_id, name: idx.name };
    }
    this.loadTicker(m.ticker);
  },

  backToIndex() {
    const b = this.backTo;
    if (!b) return;
    this.backTo = null;  // on est revenu : le bouton n'a plus de sens ici
    // Retour au screener : on ROUVRE la modale en gardant l'état courant
    // (lignes affichées, filtres, source, tri mémorisés dans screener*) —
    // aucun re-fetch, le scan n'est pas relancé.
    if (b.source === "screener") {
      this.screenerOpen = true;
      return;
    }
    // Retour à la watchlist : on rouvre la modale avec son état (lignes,
    // tier filtré, tri) — aucun re-scan, comme le screener.
    if (b.source === "watchlist") {
      this.watchlistOpen = true;
      return;
    }
    this.loadIndex(b.index_id);
  },

  resetEditor() {
    this.edt = { id: null, name: "", category_id: "", newCategory: "", tickers: [], query: "", suggestions: [] };
    this.idxError = "";
  },

  startEdit(ix, cat) {
    this.edt = { id: ix.id, name: ix.name, category_id: String(cat.id), newCategory: "", tickers: [...ix.tickers], query: "", suggestions: [] };
    this.idxError = "";
    this.scrollIdxInput();
  },

  onIdxSearch() {
    clearTimeout(this._idxSearchTimer);
    const q = this.edt.query.trim();
    if (q.length < 2) { this.edt.suggestions = []; return; }
    this._idxSearchTimer = setTimeout(async () => {
      try {
        const res = await api.search(q);
        if (res == null) return;
        if (this.edt.query.trim() === q) this.edt.suggestions = res;
      } catch { this.edt.suggestions = []; }
    }, 250);
  },

  // Ramène le champ de recherche des membres à l'écran quand il sort du cadre
  // de la modale (ajout de membres, focus, ouverture en édition). On scrolle
  // le conteneur de la modale manuellement : plus fiable que scrollIntoView,
  // qui peut être interrompu par les re-rendus réactifs d'Alpine.

  scrollIdxInput() {
    requestAnimationFrame(() => {
      const input = document.querySelector(".idx-search-wrap input");
      const modal = input && input.closest(".modal");
      if (!input || !modal) return;
      const mRect = modal.getBoundingClientRect();
      const iRect = input.getBoundingClientRect();
      if (iRect.bottom > mRect.bottom) modal.scrollTop += iRect.bottom - mRect.bottom + 8;
      else if (iRect.top < mRect.top) modal.scrollTop -= mRect.top - iRect.top + 8;
    });
  },

  addMember(s) {
    const t = s.symbol.toUpperCase();
    if (!this.edt.tickers.includes(t)) this.edt.tickers.push(t);
    this.edt.query = ""; this.edt.suggestions = [];
    this.scrollIdxInput();
  },

  addFirstSuggestion() {
    if (this.edt.suggestions.length) this.addMember(this.edt.suggestions[0]);
  },

  removeMember(t) {
    this.edt.tickers = this.edt.tickers.filter((x) => x !== t);
  },

  async saveIndex() {
    const name = this.edt.name.trim();
    if (!name) { this.idxError = "Donne un nom à l'indice."; return; }
    this.idxError = "";
    let categoryId = this.edt.category_id;
    let categoryCreated = false;
    if (!categoryId) {
      const nc = this.edt.newCategory.trim();
      if (!nc) { this.idxError = "Choisis une catégorie existante ou saisis une nouvelle."; return; }
      try {
        const { ok, data } = await api.createCategory(nc);
        if (!ok) throw new Error(data.detail || "Erreur catégorie");
        categoryId = String(data.id);
        categoryCreated = true;
      } catch (e) { this.idxError = e.message; return; }
    }
    this.savingIndex = true;
    try {
      const payload = { category_id: Number(categoryId), name, tickers: this.edt.tickers };
      const { ok, data } = this.edt.id
        ? await api.updateIndex(this.edt.id, payload)
        : await api.createIndex(payload);
      if (!ok) throw new Error(data.detail || "Erreur d'enregistrement");
      await this.loadIndices();
      this.resetEditor();
      this.loadSummaries();  // l'indice (ou ses membres) a changé : stats à refléter
    } catch (e) {
      // Rollback : si on vient de créer une catégorie et que l'indice échoue,
      // on la supprime pour ne pas laisser une catégorie orpheline vide.
      if (categoryCreated) {
        try { await api.deleteCategory(categoryId); } catch { /* best effort */ }
      }
      this.idxError = e.message;
    } finally {
      this.savingIndex = false;
    }
  },

  async deleteIndex(ix) {
    if (!confirm(`Supprimer l'indice « ${ix.name} » ?`)) return;
    try {
      const { ok, data } = await api.deleteIndex(ix.id);
      if (!ok) throw new Error(data.detail);
      await this.loadIndices();
      this.loadSummaries();
    } catch (e) { this.idxError = e.message; }
  },

  async deleteCategory(cat) {
    if (!confirm(`Supprimer la catégorie « ${cat.name} » et ses indices ?`)) return;
    try {
      const { ok, data } = await api.deleteCategory(cat.id);
      if (!ok) throw new Error(data.detail);
      await this.loadIndices();
      this.loadSummaries();
    } catch (e) { this.idxError = e.message; }
  },

};
