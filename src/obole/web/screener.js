// Obole — screener : filtres, tri multi-critères, presets, tableau.
import { api } from "./api.js";

export const screenerMixin = {
  async openScreener() {
    this.screenerOpen = true;
    this.screenerError = "";
    this.screenerRows = [];
    this.screenerSource = "";
    this.screenerSearched = false;
    this.screenerSort = [];  // reset tri : le défaut vient de /meta (aucun en dur)
    this.screenerFiltersOpen = true;  // filtres visibles à l'ouverture (accueil)
    // Métadonnées de colonnes (directions de tri + seuils de couleur) : source unique.
    try {
      const meta = await api.screenerMeta();
      if (meta) {
        this.screenerSortDesc = meta.sort_desc || {};
        this.screenerColors = meta.colors || {};  // base des presets d'accueil
      }
    } catch { /* /meta KO : on bloque le tri (pas de direction inventée) */ }
    // Liaison backend : simple contrôle de santé (le détail n'est plus affiché).
    try {
      const { ok, status } = await api.screenerPing();
      if (!ok) { this.screenerError = "Liaison screener KO (" + status + ")"; return; }
    } catch {
      this.screenerError = "Liaison screener KO (réseau indisponible)";
    }
  },

  closeScreener() { this.screenerOpen = false; },

  // Lance un scan : POST /api/screener/run avec les filtres + tri courants.

  async searchScreener() {
    this.screenerLoading = true;
    this.screenerError = "";
    // Un SEUL `try/finally` couvre TOUTE la méthode : `screenerLoading` retombe
    // à false quel que soit le chemin de sortie (préparation des filtres qui
    // lève, erreur réseau, réponse HTTP KO, retour anticipé). La construction
    // du body y est incluse : une coercion de bornes qui échoue (cf. bug filtre
    // Capi qui réassignait un `const`) ne doit jamais laisser le spinner bloqué.
    try {
      let body;
      try {
        body = this._scanBody();
      } catch (e) {
        this.screenerError = "Scan screener KO (préparation des filtres : "
          + ((e && e.message) || "erreur inattendue") + ")";
        return;
      }
      let payload;
      try {
        const { ok, status, data } = await api.runScreener(body);
        if (!ok) {
          this.screenerError = "Scan screener KO (" + status + ") " + (data.detail || "");
          return;
        }
        payload = data;
      } catch {
        this.screenerError = "Scan screener KO (réseau indisponible)";
        return;
      }
      if (!payload) return;
      this.screenerRows = payload.rows || [];
      this.screenerSource = payload.source || "";
      this.screenerSearched = true;
      // UX #13 : après un scan, on replie les filtres pour laisser toute la
      // place aux résultats (divulgation progressive). Le récapitulatif en
      // chips reste visible, et « Filtres » les rouvre.
      this.screenerFiltersOpen = false;
    } finally {
      this.screenerLoading = false;
    }
  },

  // Construit le body du scan depuis l'état courant (filtres + tri + score).
  // Pur et déterministe, sans I/O. Extrait de `searchScreener` pour que
  // l'appelant puisse isoler un échec éventuel (jamais de spinner bloqué).

  _scanBody() {
    // Alpine x-model renvoie des chaînes (<input number>/<select>) ou null.
    // Chaîne vide OU null = pas de valeur -> null. Sinon on coercit en nombre.
    // UX #13 : la capitalisation est UNE SEULE paire (screenerRanges.market_cap).
    // Sa borne min sert de plancher à la passe 1 (restreint l'univers scanné,
    // donc la durée) ET de filtre passe 2 ; la borne max ne filtre qu'en
    // passe 2. Si aucune borne n'est posée, min_market_cap est omis -> défaut
    // serveur (1 Md€, scan rapide). Si un max est posé sans min, on ne pose
    // AUCUN plancher (0 -> univers complet) : le scan est plus large (donc
    // plus lent) mais jamais silencieusement amputé par un plancher invisible.
    const capiMinMd = this._num(this.screenerRanges.market_cap.min);
    const capiMaxMd = this._num(this.screenerRanges.market_cap.max);
    const capi = capiMinMd != null
      ? capiMinMd * 1e9
      : (capiMaxMd != null ? 0 : null);
    const win = this.screenerFilters.regression_window == null || this.screenerFilters.regression_window === ""
      ? null : Number(this.screenerFilters.regression_window);
    const body = {
      min_market_cap: capi,
      sectors: this.screenerFilters.sectors.length ? this.screenerFilters.sectors : null,
      regression_window: win,
    };
    if (body.min_market_cap === null) delete body.min_market_cap; // défaut serveur (1 Md€)
    if (body.regression_window === null) delete body.regression_window; // historique complet
    const filters = this._buildFilters();
    if (filters && Object.keys(filters).length) body.filters = filters;
    const sortPayload = this._sortPayload();
    if (sortPayload.length) body.sort_by = sortPayload;
    // #14 : le score composite porte sur les critères de tri actifs. En mode
    // « compromis » avec ≥ 2 critères, le front trie sur `score` (calculé
    // serveur) et envoie ces critères comme base du percentile.
    const scoreKeys = this._scoreKeys();
    if (scoreKeys.length >= 2) {
      body.score_keys = scoreKeys;
      if (this.screenerMode === "compromis") {
        body.sort_by = [["score", "desc"], ...sortPayload];
      }
    }
    return body;
  },

  // Construit `body.filters` ({critère: [min, max]}) depuis screenerRanges.
  // Pur et déterministe : chaque borne chaîne/vide/null -> nombre ou null ;
  // un filtre est omis si les deux bornes sont vides OU si min > max (on
  // évite un 422 serveur côté front). Jamais de NaN envoyé.

  _buildFilters() {
    const out = {};
    const inverted = [];
    for (const [key, r] of Object.entries(this.screenerRanges)) {
      let lo = this._num(r.min);
      let hi = this._num(r.max);
      if (lo == null && hi == null) continue;      // pas de borne -> on filtre pas
      if (lo != null && hi != null && lo > hi) {   // bornes inversées -> on ignore
        // mais on prévient l'utilisateur (sinon le scan semble trop large).
        const col = this._screenRangeCols().find(c => c.key === key);
        inverted.push(col ? col.label : key);
        continue;
      }
      // market_cap : saisie en Md€ (cohérente avec le tableau `fmtCap`),
      // convertie en EUR brut pour le serveur (×1 Md€ = 1e9). La conversion
      // réassigne les bornes : elles sont donc déclarées `let` (jamais
      // `const`, sinon TypeError -> spinner bloqué, cf. fix/screener-filtre-capi).
      if (key === "market_cap") {
        lo = lo == null ? null : lo * 1e9;
        hi = hi == null ? null : hi * 1e9;
      }
      out[key] = [lo, hi];
    }
    this.screenerRangesError = inverted.length
      ? "Bornes inversées : " + inverted.join(", ") + " (filtré ignoré)"
      : "";
    return out;
  },

  // Coerce une valeur de champ en nombre, ou null si vide/NaN.

  _num(v) {
    if (v == null || v === "") return null;
    const n = Number(v);
    return Number.isNaN(n) ? null : n;
  },

  // Vide tous les pré-filtres par critère (bornes min/max remises à null).

  resetScreenerRanges() {
    for (const key of Object.keys(this.screenerRanges)) {
      this.screenerRanges[key] = { min: null, max: null };
    }
    this.screenerRangesError = "";
    if (this.screenerRows.length) this.searchScreener();
  },

  // Pré-filtres par critère : sous-ensemble de `_screenCols()` (source unique
  // des libellés — PAS de duplication de label ici). Les labels viennent donc
  // de la même liste que les en-têtes ; seul l'ordre d'affichage diffère.

  _screenRangeCols() {
    const keys = [
      "market_cap", "z", "pente_pct", "ecart_type_pct", "roe_pct",
      "pot_5y_pct", "per", "p_fcf", "fcf_yield_pct", "quality_score",
    ];
    const cols = this._screenCols();
    const units = { market_cap: "Md€" };
    return keys
      .map(k => cols.find(c => c.key === k))
      .filter(Boolean)
      .map(c => ({ ...c, unit: units[c.key] || "" }));
  },

  // Design A : groupes thématiques des filtres. SOURCE UNIQUE du mapping
  // critère -> groupe (aucun libellé dupliqué : on réutilise `_screenCols()`).
  // `screenerGroupCols(id)` renvoie les colonnes du groupe, enrichies de leur
  // unité. Les clés inconnues sont ignorées (aucun crash si une colonne est
  // retirée de `_screenCols()`).

  _screenFilterGroups() {
    return [
      { id: "taille", label: "Taille", keys: ["market_cap"] },
      { id: "technique", label: "Technique", keys: ["z", "pente_pct", "ecart_type_pct", "pot_5y_pct", "pot_10y_pct"] },
      { id: "rentabilite", label: "Rentabilité", keys: ["roe_pct", "quality_score"] },
      { id: "valorisation", label: "Valorisation", keys: ["per", "p_b", "p_fcf", "fcf_yield_pct"] },
    ];
  },

  screenerGroupCols(groupId) {
    const g = this._screenFilterGroups().find(x => x.id === groupId);
    if (!g) return [];
    const cols = this._screenCols();
    const units = { market_cap: "Md€" };
    return g.keys
      .filter(k => this.screenerRanges[k])  // garde-fou : pas de borne sans état
      .map(k => cols.find(c => c.key === k))
      .filter(Boolean)
      .map(c => ({ ...c, unit: units[c.key] || "" }));
  },

  // Nombre de filtres posés dans un groupe (badge visible même replié : un
  // groupe fermé ne doit jamais cacher un filtre actif).

  screenerGroupCount(groupId) {
    const g = this._screenFilterGroups().find(x => x.id === groupId);
    if (!g) return 0;
    let n = 0;
    for (const k of g.keys) {
      const r = this.screenerRanges[k];
      if (r && (this._num(r.min) != null || this._num(r.max) != null)) n++;
    }
    return n;
  },

  screenerToggleGroup(groupId) {
    this.screenerGroupsOpen[groupId] = !this.screenerGroupsOpen[groupId];
  },

  // Clic sur un en-tête : 1er clic = critère principal, clic suivant = second
  // critère (chaîné, max 2). Re-clic sur un critère actif = inverse le sens.
  // Le sens par défaut vient de /meta (screenerSortDesc), source unique.

  toggleSortHeader(key) {
    const idx = this.screenerSort.findIndex(s => s.key === key);
    if (idx === -1) {
      if (this.screenerSort.length >= 2) return;  // tri chaîné limité à 2 critères
      const dir = this._defaultDir(key);
      if (dir === null) return;  // /meta indisponible : on n'invente pas de sens
      this.screenerSort.push({ key, dir });
    } else {
      const s = this.screenerSort[idx];
      s.dir = s.dir === "asc" ? "desc" : "asc";
    }
    if (this.screenerRows.length) this.searchScreener();
  },

  // Sens par défaut d'un critère, depuis /meta (screenerSortDesc) = source
  // unique. Si /meta a échoué (screenerSortDesc vide), on NE trie PAS (on
  // renvoie null) plutôt que d'inventer une direction : un tri dégradé desc
  // mettrait les pires valeurs en tête (PER/volatilité les plus hauts).

  _defaultDir(key) {
    if (!Object.keys(this.screenerSortDesc).length) return null;
    return this.screenerSortDesc[key] === false ? "asc" : "desc";
  },

  // Réinitialise le tri multi-critères (retourne à l'état par défaut).

  resetSort() {
    this.screenerSort = [];
    if (this.screenerRows.length) this.searchScreener();
  },

  _sortPayload() {
    return this.screenerSort.map(s => [s.key, s.dir]);
  },

  // #14 : critères servant de base au score composite (ceux du tri actif).
  // Le score n'a de sens qu'à partir de 2 critères (sinon = le tri simple).

  _scoreKeys() {
    return this.screenerSort.map(s => s.key).filter(k => k !== "score");
  },

  // Le score composite est-il applicable (≥ 2 critères actifs) ?

  screenerScoreActive() {
    return this._scoreKeys().length >= 2;
  },

  // Bascule Compromis (score) / Cascade (tri lexicographique) et relance.

  setScreenerMode(mode) {
    if (this.screenerMode === mode) return;
    this.screenerMode = mode;
    if (this.screenerRows.length) this.searchScreener();
  },

  // Clic sur une ligne : ouvre la fiche valeur, en gardant le contexte
  // screener pour permettre un retour « ← Retour au Screener » sans re-scan.
  // On ferme la modale pour laisser la place à la fiche.

  selectRow(t) {
    this.backTo = { source: "screener", name: "Screener" };
    this.screenerOpen = false;
    this.loadTicker(t);
  },

  _screenCols() {
    return [
      { key: "ticker", label: "Tick." },
      { key: "name", label: "Nom" },
      { key: "market_cap", label: "Capi" },
      { key: "z", label: "σ" },
      { key: "pente_pct", label: "Pente %" },
      { key: "ecart_type_pct", label: "Écart-type %" },
      { key: "pot_5y_pct", label: "Pot. 5a %" },
      { key: "pot_10y_pct", label: "Pot. 10a %" },
      { key: "trend_bullish", label: "Tendance" },
      { key: "roe_pct", label: "ROE %" },
      { key: "per", label: "PER" },
      { key: "p_b", label: "P/B" },
      { key: "p_fcf", label: "P/FCF" },
      { key: "fcf_yield_pct", label: "FCF yield %" },
      { key: "quality_score", label: "Qualité" },
      // #14 : score composite (rang par compromis). Neutre (sans couleur).
      { key: "score", label: "Score" },
    ];
  },

  // Colonnes du tableau APRÈS la colonne d'ancrage « Entreprise » (qui
  // fusionne ticker + nom, cf. UX #13). L'ancre est rendue en dur dans le
  // HTML (gelée) ; `ticker`/`name` ne sont donc plus des colonnes séparées.

  _screenTailCols() {
    return this._screenCols().filter(c => c.key !== "ticker" && c.key !== "name");
  },

  // Affiche la valeur d'une cellule selon le critère (mise en forme).

  _cellDisplay(row, key) {
    const v = row[key];
    if (v == null) return "—";
    if (key === "ticker") return v;
    if (key === "name") return v;
    if (key === "market_cap") return this.fmtCap(v);
    if (key === "trend_bullish") return v === true ? "Haussière" : v === false ? "Baissière" : "—";
    if (key === "z") return this.fmt(v) + "σ";
    if (["pente_pct", "ecart_type_pct", "roe_pct", "pot_5y_pct", "pot_10y_pct", "fcf_yield_pct"].includes(key))
      return this.fmt(v) + " %";
    if (["per", "p_b", "p_fcf", "quality_score"].includes(key)) return this.fmt(v);
    return this.fmt(v);
  },

  // Couleur d'une cellule : consomme `row.colors` (polarité calculée par l'API
  // depuis config.SCREEN_COLORS) — AUCUN seuil dupliqué côté client.

  _cellPolarity(row, key) {
    const c = row.colors && row.colors[key];
    return c === "good" ? "good" : c === "bad" ? "bad" : "neutral";
  },

  _sortClass(key) {
    const s = this.screenerSort.find(x => x.key === key);
    if (!s) return "";
    return s.dir === "asc" ? "sort-asc" : "sort-desc";
  },

  // Priorité (1, 2, …) d'un critère de tri, ou null s'il n'est pas actif.
  // Rend la cascade HONNÊTE : on voit que le 2e critère ne départage que les
  // égalités du 1er. En mode « compromis », le classement n'est PAS la cascade :
  // on masque donc les rangs (sinon l'affichage mentirait sur le tri réel).

  screenerSortRank(key) {
    if (this.screenerMode === "compromis" && this.screenerScoreActive()) return null;
    const i = this.screenerSort.findIndex(s => s.key === key);
    return i === -1 ? null : i + 1;
  },

  // Libellé récapitulatif du tri. En mode « compromis », on n'affiche PAS la
  // cascade (qui ne correspond pas au classement réel) mais les critères du
  // score : « Compromis sur ROE % · P/FCF ».

  screenerSortLabel() {
    if (!this.screenerSort.length) return "";
    const cols = this._screenCols();
    const labelOf = (k) => (cols.find(c => c.key === k) || { label: k }).label;
    const keys = this._scoreKeys();
    if (this.screenerMode === "compromis" && keys.length >= 2) {
      return "Compromis sur " + keys.map(labelOf).join(" · ");
    }
    return this.screenerSort
      .map((s, i) => `${i + 1}. ${labelOf(s.key)} ${s.dir === "asc" ? "▲" : "▼"}`)
      .join(" · ");
  },

  // Le tri affiché est-il une cascade (badges de rang pertinents) ?

  screenerSortIsCascade() {
    return !(this.screenerMode === "compromis" && this.screenerScoreActive());
  },

  // La colonne Score n'a de sens qu'en mode compromis avec ≥ 2 critères :
  // sinon elle n'afficherait que des « — » sur toutes les lignes.

  screenerScoreColumnVisible() {
    return this.screenerMode === "compromis" && this.screenerScoreActive();
  },

  // --- UX #13 : filtres repliables, chips, presets ------------------------

  screenerToggleFilters() {
    this.screenerFiltersOpen = !this.screenerFiltersOpen;
  },

  // Récapitulatif des filtres actifs (chips de l'état replié). Chaque borne
  // posée devient un chip ; la fenêtre de régression en devient un aussi.
  // Labels depuis `_screenCols()` (source unique), aucune valeur en dur.

  screenerActiveFilters() {
    const cols = this._screenCols();
    const labelOf = (k) => {
      const c = cols.find(x => x.key === k);
      return c ? c.label : k;
    };
    const unitOf = (k) => (k === "market_cap" ? " Md€" : "");
    const out = [];
    for (const [key, r] of Object.entries(this.screenerRanges)) {
      const lo = this._num(r.min);
      const hi = this._num(r.max);
      if (lo == null && hi == null) continue;
      const u = unitOf(key);
      let text;
      if (lo != null && hi != null) text = lo + " – " + hi + u;
      else if (lo != null) text = "≥ " + lo + u;
      else text = "≤ " + hi + u;
      out.push({ key, text: labelOf(key) + " " + text });
    }
    if (this.screenerFilters.regression_window != null && this.screenerFilters.regression_window !== "") {
      out.push({ key: "regression_window", text: "Fenêtre " + this.screenerFilters.regression_window + " ans" });
    }
    return out;
  },

  // Efface tous les filtres (fenêtre + bornes) puis relance si des résultats
  // sont déjà affichés. La fenêtre est remise à null AVANT `resetScreenerRanges()`
  // car celui-ci relance `searchScreener()` de façon synchrone : sinon le
  // re-scan utiliserait encore l'ancienne fenêtre (résultats incohérents avec
  // les chips, qui l'ont déjà effacée).

  clearScreenerFilters() {
    this.screenerFilters.regression_window = null;
    this.resetScreenerRanges();
    this.screenerFiltersOpen = true;
  },

  // Retour à l'accueil du screener (presets) sans fermer/rouvrir la modale :
  // efface les résultats et remet les filtres à zéro (les presets restent donc
  // accessibles pour enchaîner plusieurs scans).

  screenerBackHome() {
    this.screenerRows = [];
    this.screenerSearched = false;
    this.screenerError = "";
    this.screenerSort = [];
    this.screenerFilters.regression_window = null;
    this.resetScreenerRanges();
    this.screenerFiltersOpen = true;
  },

  // Presets d'accueil : composés UNIQUEMENT des seuils exposés par
  // `/api/screener/meta` (`colors`) — AUCUN nombre magique côté front. Si
  // /meta est indisponible (screenerColors vide), aucun preset n'est proposé
  // (on n'invente pas de seuil). Le sens du seuil pilote la borne :
  //   - "ge"     : bon au-dessus du seuil  -> min = seuil
  //   - "le"     : bon sous le seuil       -> max = seuil
  //   - "le_pos" : bon si 0 < v <= seuil   -> [0, seuil] (exclut les négatifs)

  screenerPresets() {
    const colors = this.screenerColors || {};
    if (!Object.keys(colors).length) return [];
    const bound = (key) => {
      const c = colors[key];
      if (!c) return null;
      if (c.sens === "ge") return [c.seuil, null];
      if (c.sens === "le_pos") return [0, c.seuil];
      return [null, c.seuil];
    };
    const defs = [
      {
        id: "decor",
        label: "Décotées de qualité",
        desc: "Cours sous la droite, rentables et solides.",
        keys: ["z", "roe_pct", "quality_score"],
      },
      {
        id: "cash",
        label: "Rendement en cash",
        desc: "Généreuses en free cash flow, payées raisonnablement.",
        keys: ["fcf_yield_pct", "p_fcf"],
      },
      {
        id: "growth",
        label: "Croissance + tendance",
        desc: "Droite ascendante et potentiel encore ouvert.",
        keys: ["pente_pct", "pot_5y_pct"],
      },
    ];
    return defs
      .map((d) => {
        const ranges = {};
        for (const k of d.keys) {
          const b = bound(k);
          if (b) ranges[k] = b;
        }
        return Object.keys(ranges).length === d.keys.length ? { ...d, ranges } : null;
      })
      .filter(Boolean);
  },

  // Applique un preset (pré-remplit les filtres) puis lance le scan.

  applyScreenerPreset(preset) {
    for (const [key, [lo, hi]] of Object.entries(preset.ranges)) {
      if (this.screenerRanges[key]) this.screenerRanges[key] = { min: lo, max: hi };
    }
    this.screenerSort = [];
    this.searchScreener();
  },

  // --- Paramètres (mesures techniques) ------------------------------------

};
