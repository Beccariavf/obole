// Obole — recherche, chargement des fiches (action/ratio/indice) et navigation.
import { api } from "./api.js";

export const searchMixin = {
  ratioSegments() { return this.query.split("/").map((s) => s.trim()); },

  activeSegment() {
    const parts = this.ratioSegments();
    return parts[parts.length - 1];  // segment en cours de saisie
  },

  onSearchInput() {
    clearTimeout(this._searchTimer);
    const seg = this.activeSegment();
    if (seg.length < 2) { this.suggestions = []; return; }
    this._searchTimer = setTimeout(() => this.fetchSuggestions(seg), 250); // debounce
  },

  async fetchSuggestions(seg) {
    try {
      const results = await api.search(seg);
      if (results == null) { this.suggestions = []; return; }
      // Ignore une réponse obsolète si le segment actif a changé depuis.
      if (this.activeSegment() === seg) this.suggestions = results;
    } catch {
      this.suggestions = [];
    }
  },

  pick(s) {
    if (this.query.includes("/")) {
      // L'utilisateur compose un ratio (il a tapé « / » lui-même) : on complète
      // SEULEMENT le segment courant, sans rien ajouter ni lancer. Il garde la
      // main et lance via Entrée / Analyser quand « A / B » est complet.
      const parts = this.ratioSegments();
      parts[parts.length - 1] = s.symbol;
      this.query = parts.join(" / ");
      this.suggestions = [];
    } else {
      // Cas normal (pas de ratio) : on charge directement l'actif choisi.
      this.query = s.symbol;
      this.suggestions = [];
      this.backTo = null;  // nouvelle recherche manuelle : on quitte l'indice
      this.load();
    }
  },

  pickFirstOrLoad() {
    if (this.suggestions.length) { this.pick(this.suggestions[0]); }
    else {
      this.backTo = null;  // recherche manuelle (Entrée) : on quitte l'indice
      this.load();
    }
  },

  isRatioQuery() {
    const parts = this.ratioSegments().filter((p) => p.length);
    return this.query.includes("/") && parts.length >= 2;
  },

  async load() {
    const raw = this.query.trim();
    if (!raw) return;
    // Les seuils viennent de /api/meta : on attend leur chargement avant tout
    // calcul dépendant d'un seuil (labels, couleurs, fenêtres). Le flag évite
    // d'attendre une promesse déjà résolue.
    if (this._metaPromise && !this.metaReady) { try { await this._metaPromise; } catch {} }
    // Sans seuils, tout calcul de label/couleur est impossible : on affiche une
    // erreur explicite plutôt que de rendre un graphe vide silencieusement.
    if (!this.metaReady) {
      this.error = "Seuils indisponibles (/api/meta) — impossible de calculer l'analyse. Recharge la page.";
      return;
    }
    this.suggestions = [];
    this.loading = true; this.error = ""; this.data = null;
    try {
      if (this.isRatioQuery()) {
        const [a, b] = this.ratioSegments().filter((p) => p.length);
        this.data = await api.ratio(a, b);
      } else {
        this.data = await api.stock(raw);
      }
      // #25.1 : une référence persistée est une droite de VALORISATION (prix
      // bruts). On ouvre la fiche sur cette vue — dividendes off, synchro on,
      // pas de fenêtre fixe — pour que la droite, les KPI et la watchlist lisent
      // la même régression. L'utilisateur peut ensuite recocher les dividendes
      // ou décocher la synchro pour explorer (le KPI redevient live).
      if (this.data?.watch?.ref?.start) {
        this.withDividends = false;
        this.syncRegression = true;
        this.winLocked = false;
        this._winPrevSync = null;
      }
      this.initRange();
      this.compareKeys = [];  // nouvelle fiche : comparateur remis à zéro
      // Les marqueurs de transactions ne se chargent qu'à l'activation de la case
      // « Transactions » (paresseux). Si elle est DÉJÀ active, on recharge pour le
      // nouveau ticker ; sinon aucune requête à vide à chaque fiche.
      if (this.showTx && typeof this.loadTxMarkers === "function") this.loadTxMarkers();
      // Calculatrice de valorisation : (re)initialise ses paramètres depuis les
      // valeurs enregistrées (ou les défauts) pour la fiche qui vient d'arriver.
      if (typeof this.initValuation === "function") this.initValuation();
      this.$nextTick(() => {
        // Fiche chargée : on applique la section demandée (deep-link) ou on
        // revient sur « Résumé », puis on (re)dessine ce qui est visible.
        try { this.applySectionsAfterLoad(); } catch (e) { console.error("applySections error:", e); }
      });
    } catch (e) {
      this.error = e.message;
    } finally {
      this.loading = false;
    }
  },

  async refresh() {
    if (!this.data) return;
    const id = this.data.identity;
    // Un indice purge ses membres + sa série cachée via un seul endpoint.
    if (this.isBasket()) {
      await api.refreshIndex(id.index_id);
      await this.loadIndex(id.index_id);
      return;
    }
    // Un ratio purge ses deux actifs ; une action son ticker.
    const tickers = id.ticker_a ? [id.ticker_a, id.ticker_b] : [id.ticker];
    await Promise.all(tickers.map((t) => api.refreshTicker(t)));
    this.load();
  },

  isBasket() { return this.data?.kind_payload === "basket"; },

  loadTicker(t) {
    this.query = t;
    this.load();
  },
};
