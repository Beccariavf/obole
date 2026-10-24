// Obole — composant Alpine qui assemble les modules ES du front.
// Le front n'a PAS de build : ce fichier est chargé en <script type="module">,
// chaque domaine vit dans son module (search, screener, indices, charts, export,
// events, settings) et est fusionné ici dans l'objet `obole`. Les `fetch` sont
// centralisés dans `api.js`. Les seuils viennent de /api/meta (thresholds.js).
import { api } from "./api.js";
import { applyMeta } from "./thresholds.js";
import { searchMixin } from "./search.js";
import { screenerMixin } from "./screener.js";
import { indicesMixin } from "./indices.js";
import { chartsMixin } from "./charts.js";
import { cursorMixin } from "./cursor.js";
import { exportMixin } from "./exportcsv.js";
import { eventsMixin } from "./events.js";
import { settingsMixin } from "./settings.js";
import { sectionsMixin } from "./sections.js";
import { summaryMixin } from "./summary.js";
import { portfolioMixin } from "./portfolio.js";
import { portfolioDividendsMixin } from "./portfolio-dividends.js";
import { dividendMixin } from "./dividend.js";
import { valorisationMixin } from "./valorisation.js";
import { thesisMixin } from "./thesis.js";
import { checkpointsMixin } from "./suivi.js";
import { watchlistMixin } from "./watchlist.js";

// Enregistre le composant via alpine:init pour garantir qu'il est défini
// AVANT qu'Alpine n'initialise le DOM (évite la race entre les scripts defer).
document.addEventListener("alpine:init", () => {
  window.Alpine.data("obole", obole);
});

export function obole() {
  return {
    query: "RI.PA",
    data: null,
    loading: false,
    error: "",
    // toggles graphe
    withDividends: true,    // dividendes réinvestis ON par défaut
    syncRegression: true,   // recalcule la droite sur la plage affichée
    showMA: false,          // moyennes mobiles (court/long, réglables dans Paramètres)
    logScale: true,
    rangeStart: null,       // index de plage (null = auto 20 ans)
    rangeEnd: null,
    winLocked: false,       // « fenêtre fixe » : verrouille la distance (années) des poignées
    winYears: 5,            // taille de la fenêtre fixe (années)
    _winPrevSync: null,     // état de synchro avant activation (restauré à la désactivation)
    periodFocused: false,   // la zone période a le focus clavier (flèches actives)
    live: null,             // indicateurs recalculés client (valo/potentiels/perf/écart-type)
    suggestions: [],        // résultats d'autocomplétion en cours
    showInfo: {},           // info-bulles cliquables (c.id -> true/false)
    _searchTimer: null,
    // Import CSV manuel
    showImportModal: false,
    importPreview: null,
    importPasteText: "",
    importing: false,
    importError: "",
    // Brouillons d'import en attente de validation (#23)
    draftsOpen: false,
    importDrafts: [],
    draftCount: 0,
    draftDetail: null,
    draftError: "",
    draftsBusy: false,
    // Indices personnalisés
    indicesOpen: false,
    indicesData: [],
    idxError: "",
    savingIndex: false,
    edt: { id: null, name: "", category_id: "", newCategory: "", tickers: [], query: "", suggestions: [] },
    _idxSearchTimer: null,
    // Stats « coup d'œil » de la liste « Mes indices » (index_id -> {stats, error})
    idxStats: {},
    summariesLoading: false,
    summaryError: "",  // échec global du calcul des stats (visible près des boutons)
    // Contexte « retour » : fiche membre ouverte depuis un indice.
    backTo: null,
    // Screener (J4 : filtres + tableau triable)
    screenerOpen: false,
    screenerError: "",
    screenerLoading: false,
    screenerSource: "",
    screenerRows: [],
    // Filtres globaux. La capitalisation n'est PLUS un champ à part : elle vit
    // dans `screenerRanges.market_cap` (une seule paire min/max, cf. UX #13).
    screenerFilters: {
      sectors: [],            // multi-select (optionnel)
      regression_window: null, // années (droite d'Obole) ; null = historique complet
    },
    // Pré-filtres par critère (E6) : bornes min/max optionnelles par critère.
    // Labels depuis `_screenCols()` (source unique) ; directions depuis /meta
    // (sort_desc). Aucun seuil en dur ici.
    screenerRanges: {
      market_cap: { min: null, max: null },
      z: { min: null, max: null },
      pente_pct: { min: null, max: null },
      ecart_type_pct: { min: null, max: null },
      pot_5y_pct: { min: null, max: null },
      pot_10y_pct: { min: null, max: null },
      roe_pct: { min: null, max: null },
      quality_score: { min: null, max: null },
      per: { min: null, max: null },
      p_b: { min: null, max: null },
      p_fcf: { min: null, max: null },
      fcf_yield_pct: { min: null, max: null },
    },
    // Tri multi-critères : liste de {key, dir} (1er = principal, puis…).
    screenerSort: [],
    screenerSortDesc: {},  // direction « bon premier » par critère (via /meta)
    screenerColors: {},    // seuils de couleur par critère (via /meta) — base des presets
    screenerSearched: false,  // un scan a-t-il déjà été lancé ?
    screenerRangesError: "",  // pré-filtres : bornes inversées (retour visuel)
    // UX #13 : panneau de filtres repliable (replié par défaut après un scan).
    screenerFiltersOpen: true,
    // Design A : état ouvert/fermé des groupes thématiques de filtres.
    screenerGroupsOpen: { taille: true, technique: true, rentabilite: false, valorisation: false },
    // #14 : mode de classement. "compromis" = score composite sur les critères
    // de tri actifs (≥ 2) ; "cascade" = tri lexicographique classique.
    screenerMode: "compromis",

    // Paramètres (mesures techniques : moyennes mobiles configurables)
    settingsOpen: false,
    settingsForm: { trend_ma_short: 11, trend_ma_long: 200 },
    settingDefs: {},
    settingGroups: [],
    settingsSaving: false,
    settingsError: "",
    // Sauvegarde / restauration des données utilisateur (modale Paramètres)
    backupBusy: false,
    backupMessage: "",
    backupError: "",
    _maShort: 11,   // MM courtes affichées (nom légende + tendance), à jour via settings
    _maLong: 200,   // MM longues affichées (nom légende + tendance), à jour via settings
    metaReady: false,  // seuils /api/meta chargés : bloque tout calcul dépendant d'un seuil
    _initialized: false,  // garde d'idempotence : `init()` est appelé deux fois par Alpine

    // État « Événements » : affiche/masque les annotations en un clic (front only).
    showEvents: true,
    // État « Transactions » (#17.4) : marqueurs achat/vente du PORTEFEUILLE sur le
    // graphe héro de la fiche entreprise (triangles), masqués par défaut. Alimentés
    // par `pfTransactionsForTicker()` (source portefeuille, PAS la table events).
    showTx: false,
    txMarkers: [],              // transactions du ticker courant (chargées à la coche)
    // Export CSV (droite de régression / simulation fenêtre glissante)
    exportOpen: false,
    exportForm: { mode: "regression", startDate: "", endDate: "", dividends: true, windowYears: 5 },
    exportError: "",

    // Événements (annotations datées des graphiques : date + libellé + note)
    eventsOpen: false,          // modale « Gérer les événements »
    eventForm: { id: null, date: "", label: "", description: "" },
    eventError: "",
    eventSaving: false,

    // Méthodes assemblées depuis les modules ES (un domaine = un module).
    ...searchMixin,
    ...screenerMixin,
    ...indicesMixin,
    ...chartsMixin,
    ...cursorMixin,
    ...exportMixin,
    ...eventsMixin,
    ...settingsMixin,
    ...sectionsMixin,
    ...summaryMixin,
    ...portfolioMixin,
    ...portfolioDividendsMixin,
    ...dividendMixin,
    ...valorisationMixin,
    ...thesisMixin,
    ...checkpointsMixin,
    ...watchlistMixin,

    async init() {
      // Alpine appelle automatiquement `init()` ; le template porte en plus
      // `x-init="init()"`. Sans garde, l'initialisation (et le chargement d'une
      // fiche par deep-link) se lancerait deux fois — la seconde écraserait la
      // section demandée. On la rend idempotente.
      if (this._initialized) return;
      this._initialized = true;
      // Bouton « retour » du navigateur : le hash porte la fiche + la section
      // (`#RI.PA/quantitatif`). On s'abonne avant le premier chargement.
      window.addEventListener("hashchange", () => this.onHashChange());
      // Thèse (#21) : détecter une modification faite ailleurs (IA via MCP, autre
      // onglet) au retour sur l'onglet / sur la fenêtre. Sans polling : une requête
      // par geste, et aucune hors de la section « Thèse & Société ».
      document.addEventListener("visibilitychange", () => this.onThesisWindowFocus());
      window.addEventListener("focus", () => this.onThesisWindowFocus());
      // Seuils calibrés d'abord (source unique /api/meta) : les calculs qui en
      // dépendent (labels, couleurs, fenêtres) attendent `metaReady`. On mémorise
      // la promesse pour que `load()` l'attende avant tout calcul de seuil.
      this._metaPromise = (async () => {
        try {
          const m = await api.meta();
          if (m) { applyMeta(m); this.metaReady = true; }
        } catch { /* seuils indisponibles : on ne calcule rien de seuil-dépendant */ }
        // Seuils de la synthèse (grille « Résumé ») : même source unique config.py,
        // endpoint distinct. Silencieux si l'appel échoue (grille sans couleur).
        await this.loadSummaryMeta();
        // Préférence d'affichage du plan de la thèse (#21.2) : lue une fois, au
        // démarrage (préférence locale au navigateur, globale — pas par ticker).
        this.loadThesisPlanPreference();
      })();
      await this._metaPromise;
      // Charge les réglages (MM) au démarrage pour afficher la bonne légende
      // dès la première fiche ; silencieux si l'appel échoue (défauts).
      try {
        const p = await api.settings();
        if (p && p.values) {
          this._maShort = p.values.trend_ma_short;
          this._maLong = p.values.trend_ma_long;
        }
      } catch { /* défauts MM */ }
      // Deep-link APRÈS les seuils (sinon `load()` refuse de calculer) :
      // `#RI.PA/quantitatif` ouvre directement la bonne fiche et la bonne
      // section. La section demandée est appliquée après le chargement des
      // données (cf. search.load / indices.loadIndex).
      const deep = this.parseHash();
      if (deep && deep.ticker) {
        this._pendingSection = deep.section;
        this.query = deep.ticker;
        this.load();
      } else if (deep && deep.section) {
        this.activeSection = deep.section;
      }
    },
  };
}
