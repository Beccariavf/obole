// Obole — espace Portefeuille : comptes, transactions, dividendes, positions.
//
// Espace DISTINCT de la fiche entreprise (pas une section) : modale plein écran
// avec rail interne, comme le Screener. Le rail et le registre de sections sont
// PROPRES à cet espace — on ne réutilise pas `sections.js` (couplé au deep-link
// de fiche `#<ticker>/<section>`), pour ne pas casser la navigation des fiches.
//
// Jalons livrés : #17.0 (socle, saisie) et #17.1 (Résumé : TWR vs benchmark,
// KPI, répartition des comptes, Top/Flop). Les sections Risque/Performance/
// Dividende sont livrées par les jalons 03 à 05 (marquées « à venir » ici).
// Tous les `fetch` passent par `api.js` ; aucun seuil littéral (benchmarks,
// périodes, taille du Top/Flop viennent de `/api/portfolio/benchmarks`).
import { api } from "./api.js";
import { C } from "./theme.js";
import {
  applyPortfolioMeta,
  periodLabel,
  PORTFOLIO_BENCHMARKS,
  PORTFOLIO_PERIODS,
  PORTFOLIO_DETAIL_HORIZONS,
  PORTFOLIO_DETAIL_HORIZON_DEFAULT,
  PORTFOLIO_TOP_N,
  PORTFOLIO_TAG_MAX,
  PORTFOLIO_CORR_ANNOTATE_MAX,
  CHART_HEIGHTS,
} from "./thresholds.js";
import { icon } from "./util.js";

// La section Performance (#17.4) se calcule toujours sur la durée MAX : pas de
// sélecteur de période dans son bandeau (choix produit figé, cf. fiche #17.4).
const PF_PERF_PERIOD = "max";

// Libellés courts des mois (affichage du graphe de rendements mensuels). Ce ne
// sont PAS des seuils : de simples étiquettes d'axe, sans équivalent en base.
const MONTHS_FR = ["Janv", "Févr", "Mars", "Avr", "Mai", "Juin",
  "Juill", "Août", "Sept", "Oct", "Nov", "Déc"];

export const PORTFOLIO_SECTIONS = [
  {
    id: "resume",
    label: "Résumé",
    svg: icon('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>'),
  },
  {
    id: "risque",
    label: "Risque",
    svg: icon('<path d="M12 3 3 20h18z"/><path d="M12 9v5M12 17h.01"/>'),
  },
  {
    id: "performance",
    label: "Performance",
    svg: icon('<path d="M3 17l5-5 4 3 8-8"/><path d="M16 7h4v4"/>'),
  },
  {
    id: "dividende",
    label: "Dividende",
    svg: icon('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.2"/>'),
  },
  {
    id: "positions",
    label: "Positions",
    svg: icon('<path d="M3 21h18M6.5 21v-7.5M12 21V4.5M17.5 21v-11"/>'),
  },
];

export const PORTFOLIO_DEFAULT_SECTION = "resume";

// Registre des CAPACITÉS par section : quels contrôles du bandeau de contexte
// (`.pf-context`) ont un sens pour chacune. Une seule source pour le template
// (`x-show`) — ajouter un onglet = une ligne ici, zéro markup dupliqué.
//   • positions  : périmètre seul (le formulaire a son propre select « Compte »,
//                  qui désigne la DESTINATION de la ligne, pas un filtre) ;
//   • resume     : les trois ;
//   • risque     : les trois ;
//   • performance: pas de période (calculée en MAX par principe) ;
//   • dividende  : ni période ni benchmark (annualisation, aucune référence).
export const SECTIONS_CONTROLS = {
  positions: { scope: true, period: false, bench: false },
  resume: { scope: true, period: true, bench: true },
  risque: { scope: true, period: true, bench: true },
  performance: { scope: true, period: false, bench: true },
  dividende: { scope: true, period: false, bench: false },
};

// Capacités d'une section (repli prudent : tout masqué si l'id est inconnu).
export function sectionControls(id) {
  return SECTIONS_CONTROLS[id] || { scope: false, period: false, bench: false };
}

// Chargeur agrégé de chaque section (nom de méthode du mixin), lu par
// `reloadActiveSection`. Positions n'en a pas : `reloadPortfolioData` porte
// déjà transactions/dividendes/positions.
const SECTION_LOADERS = {
  resume: "loadPortfolioSummary",
  risque: "loadPortfolioRisk",
  performance: "loadPortfolioPerformance",
  dividende: "loadPortfolioDividends",
};

// Repli de mesure pour le donut : si le conteneur n'est pas encore mesurable
// (avant layout), on trace quand même à une taille non nulle — le
// ResizeObserver corrige dès que la largeur réelle est connue. La hauteur vient
// de la source unique CHART_HEIGHTS (lue à l'appel, pas figée au chargement).
const DONUT_FALLBACK_W = 320;

// Sections dont le contenu est livré par les jalons suivants (#17.5).
export const PORTFOLIO_PLANNED = new Set([]);

export function portfolioSectionPlanned(id) {
  return PORTFOLIO_PLANNED.has(id);
}

const EMPTY_TX = {
  id: null,
  account_id: "",
  ticker: "",
  side: "buy",
  trade_date: "",
  quantity: "",
  price: "",
  fees: "",
  note: "",
  tag: "",
};

const EMPTY_DIV = { id: null, account_id: "", ticker: "", pay_date: "", amount: "" };

// Parse une saisie numérique à la française. Les champs sont en `type="text"`
// (un `<input type="number">` refuse la virgule : le navigateur vide le champ).
// Accepte « 60,50 », « 1 234,56 », « 1.5 » ; renvoie un nombre ou `null` si la
// saisie n'est pas un nombre valide. Les espaces (y compris insécables) sont des
// séparateurs de milliers ; le séparateur décimal est la virgule (ou le point).
export function parseDecimal(raw) {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;
  s = s.replace(/[\s\u00a0\u202f]/g, "");
  const hasComma = s.includes(",");
  const hasDot = s.includes(".");
  if (hasComma && hasDot) {
    // Les deux présents : le dernier est le séparateur décimal.
    if (s.lastIndexOf(",") > s.lastIndexOf(".")) {
      s = s.replace(/\./g, "").replace(",", ".");
    } else {
      s = s.replace(/,/g, "");
    }
  } else if (hasComma) {
    s = s.replace(",", ".");
  }
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

// Met un nombre en forme pour un champ de saisie (virgule décimale, sans
// séparateur de milliers) — utilisé à l'édition d'une ligne existante.
export function formatDecimalInput(n) {
  if (n == null) return "";
  return String(n).replace(".", ",");
}

export const portfolioMixin = {
  // --- État -----------------------------------------------------------------
  portfolioOpen: false,
  portfolioSections: PORTFOLIO_SECTIONS,
  portfolioSection: PORTFOLIO_DEFAULT_SECTION,
  portfolioAccountsList: [],
  portfolioAccountId: null, // null = vue consolidée « Tous »
  portfolioTagsList: [], // étiquettes distinctes (#17.6)
  portfolioTag: "", // étiquette active ("" = toutes) — portefeuille virtuel
  portfolioTransactions: [],
  portfolioDividends: [],
  portfolioPositions: [],
  portfolioLoading: false,
  portfolioError: "",
  txForm: { ...EMPTY_TX },
  divForm: { ...EMPTY_DIV },
  // Onglet de saisie actif dans la carte « Saisir » : "tx" | "div".
  portfolioFormMode: "tx",
  portfolioNewAccountName: "",
  _portfolioBusy: false,
  // Édition en ligne de l'étiquette d'une position (positions) : ticker en cours.
  pfTagEditing: null,
  pfTagDraft: "",

  // --- Risque (#17.3) : drawdown + corrélation ------------------------------
  pfRisk: null,
  pfRiskLoading: false,
  pfRiskError: "",
  _pfRiskSeq: 0,               // jeton anti-course des requêtes de Risque
  // Test de corrélation : saisie d'un ticker candidat -> ligne + impact.
  pfCorrTestTicker: "",
  pfCorrTest: null,
  pfCorrTestLoading: false,
  pfCorrTestError: "",
  _pfCorrTestSeq: 0,   // jeton anti-course des requêtes de test de corrélation
  // Recherche par nom pour le test de corrélation (suggestions de tickers).
  pfCorrTestSuggestions: [],
  _pfCorrTestSearchTimer: null,

  // --- Performance (#17.4) : stats pondérées, mensuels, rétrospective -------
  pfPerf: null,                // payload de /api/portfolio/performance
  pfPerfLoading: false,
  pfPerfError: "",
  _pfPerfSeq: 0,               // jeton anti-course des requêtes de Performance
  // Détail par titre (C) : fenêtre cliquable depuis le grand tableau.
  pfDetail: null,              // payload /api/portfolio/security du titre ouvert
  pfDetailOpen: false,
  pfDetailLoading: false,
  pfDetailError: "",
  // Benchmark PROPRE à la modale de détail : on peut comparer à un AUTRE indice
  // sans quitter la fiche ni changer la norme globale. Restreint à la liste
  // curée (`pfBenchmarks`, source unique config.py) — pas de ticker libre ici.
  pfDetailBenchmark: "",
  pfDetailEntryIdx: null,      // point d'entrée sélectionné (index dans la série)
  pfEntryMenuOpen: false,      // menu flottant des points d'entrée/sortie ouvert
  pfDetailHorizon: "",         // horizon du graphe de détail (défaut = config, 5a)
  pfDetailHorizons: [],        // horizons disponibles (source unique config.py)
  pfPerfMonthSel: "ttm",       // rendements mensuels : "ttm" (défaut) ou une année
  pfRiskPeriod: "max",         // période des ratios ajustés au risque (défaut MAX)

  // --- Résumé (#17.1) : TWR vs benchmark, KPI, répartition, Top/Flop --------
  pfBenchmarks: [],            // liste curée (source unique /api/portfolio/benchmarks)
  pfPeriods: [],               // raccourcis de période (même source)
  pfTopNVal: 0,                // taille du Top/Flop (réactif pour Alpine)
  pfBenchmark: "",             // benchmark affiché (dernier choix mémorisé)
  pfBenchFree: "",             // saisie du ticker libre (liée par x-model)
  pfBenchFreeOpen: false,      // popover « ticker libre » ouvert
  pfPeriod: "",                // période affichée
  pfSummary: null,             // payload de /api/portfolio/summary
  pfSummaryLoading: false,
  pfSummaryError: "",
  _pfSummarySeq: 0,            // jeton anti-course des requêtes de Résumé
  pfChartFull: false,          // courbe agrandie (plein écran) — état PROPRE
  pfBreakdown: "accounts",     // dimension du donut : "accounts" | "holdings"
  pfBreakdownMenuOpen: false,  // menu déroulant de la dimension ouvert
  _pfDetailPrevFocus: null,    // focus restitué à la fermeture
  _pfMetaReady: false,         // métadonnées portefeuille chargées

  // Charge la liste des benchmarks (source unique config.py) + le dernier
  // benchmark mémorisé (réglage persisté). Idempotent.
  async loadPortfolioMeta() {
    if (!this._pfMetaReady) {
      try {
        const m = await api.portfolioBenchmarks();
        if (m) {
          applyPortfolioMeta(m);
          this.pfBenchmarks = PORTFOLIO_BENCHMARKS;
          this.pfPeriods = PORTFOLIO_PERIODS;
          this.pfTopNVal = PORTFOLIO_TOP_N;
          this.pfDetailHorizons = PORTFOLIO_DETAIL_HORIZONS;
          this.pfDetailHorizon = PORTFOLIO_DETAIL_HORIZON_DEFAULT;
          this.pfBenchmark = m.default || "";
          this.pfPeriod = m.period_default || "";
          this._pfMetaReady = true;
        }
      } catch {
        this.pfSummaryError = "Benchmarks indisponibles (réseau).";
        return;
      }
    }
    // Derniers choix mémorisés (réglages `portfolio_benchmark` et
    // `portfolio_period`), prioritaires sur les défauts de `config.py`.
    try {
      const p = await api.settings();
      const saved = p?.values?.portfolio_benchmark;
      if (saved) this.pfBenchmark = saved;
      const savedPeriod = p?.values?.portfolio_period;
      if (savedPeriod) this.pfPeriod = savedPeriod;
    } catch {
      /* réglages indisponibles : on garde le défaut */
    }
  },

  // Charge le résumé pour le compte / benchmark / période courants.
  async loadPortfolioSummary() {
    if (!this._pfMetaReady) await this.loadPortfolioMeta();
    if (!this._pfMetaReady) return;
    const seq = ++this._pfSummarySeq;
    this.pfSummaryLoading = true;
    this.pfSummaryError = "";
    try {
      const summary = await api.portfolioSummary(
        this.portfolioAccountId,
        this.pfBenchmark,
        this.pfPeriod,
        this.portfolioTag,
      );
      if (seq !== this._pfSummarySeq) return; // réponse périmée (course)
      this.pfSummary = summary;
      this.$nextTick(() => this.drawPortfolioSummary());
      // Noms de société (Top/Flop) résolus APRÈS le premier rendu : le Résumé
      // s'affiche immédiatement, les libellés se complètent ensuite (best-effort).
      this.loadPortfolioNames();
    } catch (e) {
      if (seq !== this._pfSummarySeq) return;
      this.pfSummary = null;
      const msg = e?.message || "erreur réseau";
      // Messages serveur -> formulation lisible. « vide » d'abord : sinon la
      // règle « benchmark » reformulerait « Benchmark vide » en « introuvable ».
      if (/vide/i.test(msg)) {
        this.pfSummaryError = "Aucun benchmark choisi — saisis un ticker libre.";
      } else if (/benchmark/i.test(msg)) {
        this.pfSummaryError =
          `Benchmark introuvable : « ${this.pfBenchmark} » — corrige le ticker libre.`;
      } else {
        this.pfSummaryError = `Résumé indisponible : ${msg}.`;
      }
    } finally {
      if (seq === this._pfSummarySeq) this.pfSummaryLoading = false;
    }
  },

  // Complète les noms des lignes Top/Flop en différé (après le premier rendu) :
  // le backend les sert via `/api/portfolio/names` (seul endroit qui tolère le
  // réseau). Un échec laisse le ticker affiché — jamais bloquant, jamais un crash.
  async loadPortfolioNames() {
    const rows = [...(this.pfSummary?.top || []), ...(this.pfSummary?.flop || [])];
    const missing = [...new Set(rows.filter((r) => !r.name).map((r) => r.ticker))];
    if (!missing.length) return;
    try {
      const res = await api.portfolioNames(missing);
      const names = res?.names || {};
      for (const row of rows) {
        if (!row.name && names[row.ticker]) row.name = names[row.ticker];
      }
    } catch {
      /* noms facultatifs : on garde l'affichage par ticker */
    }
  },

  // Recharge la section VISIBLE et elle seule : le bandeau de contexte est
  // commun, mais une section masquée n'a pas à payer un appel réseau.
  async reloadActiveSection() {
    const name = SECTION_LOADERS[this.portfolioSection];
    if (!name) return;
    await this[name]();
  },

  // Capacités du bandeau pour la section courante (registre SECTIONS_CONTROLS).
  portfolioControls() {
    return sectionControls(this.portfolioSection);
  },

  // Une requête de section est en vol : le bandeau le signale (`aria-busy`).
  pfContextBusy() {
    return !!(
      this.portfolioLoading ||
      this.pfSummaryLoading ||
      this.pfRiskLoading ||
      this.pfPerfLoading ||
      this.pfDivLoading
    );
  },

  // Changement de période : mémorisé (dernier choix = norme, comme le benchmark)
  // puis recalcul de la section visible.
  async setPfPeriod(period) {
    if (period === this.pfPeriod) return;
    this.pfPeriod = period;
    try {
      await api.saveSettings({ portfolio_period: period });
    } catch {
      /* la mémorisation échoue : le calcul continue avec la valeur en mémoire */
    }
    await this.reloadActiveSection();
  },

  // Changement de benchmark : mémorisé (dernier choix = norme), puis recalcul
  // de la section visible.
  async setPfBenchmark(ticker) {
    const value = (ticker || "").trim().toUpperCase();
    if (!value || value === this.pfBenchmark) return;
    this.pfBenchmark = value;
    try {
      await api.saveSettings({ portfolio_benchmark: value });
    } catch {
      /* la mémorisation échoue : le calcul continue avec la valeur en mémoire */
    }
    await this.reloadActiveSection();
    // La modale de détail suit la nouvelle norme : on y aligne son benchmark
    // local avant de recharger, sinon le graphe resterait sur l'ancien choix.
    if (this.pfDetailOpen && this.pfDetail?.ticker) {
      this.pfDetailBenchmark = value;
      this.pfDetailEntryIdx = null;
      await this.loadPerfDetail(this.pfDetail.ticker);
    }
  },

  // Popover « ticker libre » : ancré dans le bandeau de contexte (aucune modale
  // empilée, un seul niveau de focus). Clavier d'abord : le champ est vidé et
  // focalisé à l'ouverture, `Escape` referme et restitue le focus au déclencheur.
  openPfBenchFree() {
    this._pfBenchFreePrevFocus =
      typeof document !== "undefined" ? document.activeElement : null;
    this.pfBenchFree = "";
    this.pfBenchFreeOpen = true;
    this.$nextTick(() => {
      const el = document.getElementById("pf-bench-free-input");
      if (el) el.focus();
    });
  },

  closePfBenchFree() {
    if (!this.pfBenchFreeOpen) return;
    this.pfBenchFreeOpen = false;
    const prev = this._pfBenchFreePrevFocus;
    this._pfBenchFreePrevFocus = null;
    if (prev && typeof prev.focus === "function") prev.focus();
  },

  // Applique le ticker saisi dans le popover (état `pfBenchFree`, lié par
  // `x-model`) : évite toute lecture DOM depuis le template (bouton + Entrée).
  applyPfBenchFree() {
    const ticker = this.pfBenchFree;
    this.closePfBenchFree();
    return this.setPfBenchmark(ticker);
  },

  pfBenchmarkLabel(ticker) {
    const b = (this.pfBenchmarks || []).find((x) => x.ticker === ticker);
    return b ? `${b.label} (${b.ticker})` : ticker;
  },

  pfPeriodLabel(period) {
    return periodLabel(period);
  },

  pfTopN() {
    // Valeur réactive (lue du payload) : une constante de module importée
    // n'est pas re-traquée par Alpine, elle s'afficherait « Top 0 ».
    return this.pfTopNVal || 0;
  },

  pfPct(v) {
    if (v == null) return "—";
    return (v > 0 ? "+" : "") + this.fmt(v) + " %";
  },

  // Montant signé (gain latent en €) : « +101,69 € » / « −17,33 € ».
  pfSigned(v) {
    if (v == null) return "";
    return (v > 0 ? "+" : "") + this.fmt(v) + " €";
  },

  // Initiales du nom pour le « logo » (deux premières lettres significatives).
  pfInitials(row) {
    const raw = row?.name || row?.ticker || "";
    // Un ticker « RI.PA » -> base « RI » (la place boursière n'est pas un mot).
    const base = (row?.name ? raw : raw.split(".")[0]);
    const words = base.replace(/[^A-Za-zÀ-ÿ0-9 ]/g, " ").trim().split(/\s+/).filter(Boolean);
    if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
    return (base.slice(0, 2) || "?").toUpperCase();
  },

  // Ouvre la fiche de la valeur (le portefeuille se ferme) — continuité avec la
  // navigation de la fiche entreprise.
  openPortfolioTicker(ticker) {
    if (!ticker) return;
    this.closePortfolio();
    this.backTo = null;
    this.query = ticker;
    this.load();
  },

  // KPI du résumé sous forme de lignes prêtes à rendre (titre, valeur, pastille).
  pfKpis() {
    const k = this.pfSummary?.kpis || {};
    const ccy = "€";
    const money = (v) => (v == null ? "—" : this.portfolioMoney(v) + " " + ccy);
    const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + this.fmt(v) + " %");
    const good = (v) => (v == null ? null : v >= 0);
    return {
      total_value: {
        value: money(k.total_value),
        sub: k.invested ? `sur ${money(k.invested)} investis` : "",
        label: k.total_return_pct == null ? "" : pct(k.total_return_pct),
        sub2: "Total Return",
        good: good(k.total_return_pct),
      },
      total_return: {
        value: money(k.total_return),
        sub: "plus-value latente + dividendes",
        label: k.annualized_pct == null ? "" : pct(k.annualized_pct),
        sub2: "TRI annualisé",
        good: good(k.annualized_pct),
      },
      dividends: {
        value: money(k.dividends),
        sub: "de dividendes perçus",
        label: k.dividend_yield_pct == null ? "" : this.fmt(k.dividend_yield_pct) + " %",
        sub2: "de rendement",
        good: null,
      },
    };
  },

  // Badge de performance de la période courante : bleu si le portefeuille
  // FAIT AU MOINS AUSSI BIEN que le benchmark, rouge sinon (bleu = bien).
  pfPerfBadge() {
    const k = this.pfSummary?.kpis || {};
    if (k.period_return_pct == null) return { text: "—", good: null };
    const bench = k.benchmark_period_pct;
    const good = bench == null ? k.period_return_pct >= 0 : k.period_return_pct >= bench;
    return {
      text: (k.period_return_pct > 0 ? "+" : "") + this.fmt(k.period_return_pct) + " %",
      good,
    };
  },

  pfChartEmpty() {
    return !(this.pfSummary?.dates || []).length;
  },

  // Le Flop n'est affiché que s'il apporte une information : s'il liste des
  // lignes DIFFÉRENTES du Top. Avec ≤ `top_n` positions valorisables, Top et
  // Flop sont les mêmes lignes inversées (redondant) → on masque le Flop.
  pfShowFlop() {
    const s = this.pfSummary;
    if (!s) return false;
    const flop = s.flop || [];
    if (!flop.length) return false;
    const topTickers = new Set((s.top || []).map((r) => r.ticker));
    return flop.some((r) => !topTickers.has(r.ticker));
  },

  // Nom de trace du portefeuille : « Performance (Perf: X %) (CAGR: Y %) ».
  // Reprend la convention de la maquette (perf de la période + annualisé).
  pfPortfolioTraceName() {
    const k = this.pfSummary?.kpis || {};
    const perf = k.period_return_pct == null ? "—" : this.fmt(k.period_return_pct) + " %";
    const cagr = k.annualized_pct == null ? "" : ` (CAGR: ${this.fmt(k.annualized_pct)} %)`;
    return `Performance (Perf: ${perf})${cagr}`;
  },

  // Nom de trace du benchmark : « Nom (TICKER) (Perf: X %) ».
  pfBenchmarkTraceName() {
    const s = this.pfSummary;
    const ticker = s?.benchmark?.ticker || this.pfBenchmark;
    const label = s?.benchmark?.label || ticker;
    const perf = s?.kpis?.benchmark_period_pct;
    const p = perf == null ? "—" : this.fmt(perf) + " %";
    return `${label} (${ticker}) (Perf: ${p})`;
  },

  // Légende HTML du graphe de performance (SOUS le tracé, jamais dedans) : une
  // pastille de couleur + le nom de la série + sa perf de période. Remplace la
  // légende Plotly, illisible superposée aux courbes.
  pfSeriesLegend() {
    const k = this.pfSummary?.kpis || {};
    const s = this.pfSummary;
    const ticker = s?.benchmark?.ticker || this.pfBenchmark;
    const label = s?.benchmark?.label || ticker;
    const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + this.fmt(v) + " %");
    return [
      { key: "portfolio", label: "Portefeuille", color: C.accent, value: pct(k.period_return_pct) },
      { key: "benchmark", label: `${label} (${ticker})`, color: C.ma1, value: pct(k.benchmark_period_pct) },
    ];
  },

  pfMoney(v) {
    return v == null ? "—" : this.portfolioMoney(v);
  },

  // Date « Depuis le JJ/MM/AAAA » du compte affiché.
  pfSince() {
    const since = this.pfSummary?.account?.since;
    if (!since) return "—";
    return new Date(since).toLocaleDateString("fr-FR");
  },

  // --- Tracé Plotly (courbe + donut) ---------------------------------------

  // Layout commun aux tracés du résumé (source unique des hauteurs via
  // CHART_HEIGHTS, aucun nombre en dur). **Pas de légende Plotly** : les noms de
  // séries (portefeuille + benchmark) sont rendus en HTML SOUS le graphe
  // (`pfSeriesLegend`) — dans la zone de tracé ils se superposaient aux courbes
  // et devenaient illisibles, surtout en carte étroite.
  _pfLayout(el, height, extra = {}) {
    return {
      margin: { l: 48, r: 16, t: 12, b: 28 }, height,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false },
      yaxis: { gridcolor: C.grid, showline: false, ticksuffix: " %" },
      showlegend: false,
      ...extra,
    };
  },

  drawPortfolioSummary() {
    this.drawPortfolioChart("pf-summary-plot");
    this.drawPortfolioDonut("pf-summary-donut");
    if (this.pfChartFull) this.drawPortfolioChart("pf-detail-plot", true);
  },

  drawPortfolioChart(el, detail = false) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    const s = this.pfSummary;
    if (!s || !s.dates.length) return;
    // Fenêtre de la période : on coupe les séries à `period_start` (sinon les
    // chips de période ne changent que le badge/KPI, pas la courbe tracée).
    const i0 = s.period_start ? s.dates.indexOf(s.period_start) : 0;
    const from = i0 > 0 ? i0 : 0;
    const dates = s.dates.slice(from);
    const traces = [
      {
        x: dates, y: s.portfolio.slice(from), name: this.pfPortfolioTraceName(), mode: "lines",
        line: { color: C.accent, width: 2 },
        fill: "tozeroy", fillcolor: "rgba(37,99,235,.08)",
      },
      {
        x: dates, y: s.benchmark_curve.slice(from), name: this.pfBenchmarkTraceName(),
        mode: "lines", line: { color: C.ma1, width: 2 },
      },
    ];
    const height = detail ? CHART_HEIGHTS.detail : CHART_HEIGHTS.portfolio_resume;
    Plotly.react(el, traces, this._pfLayout(el, height), { displayModeBar: false, responsive: true });
  },

  // Donut de répartition des comptes. La zone de tracé est le conteneur lui-même
  // (marges nulles, largeur/hauteur mesurées) : sans cela, Plotly fige le SVG à
  // la largeur du PREMIER rendu et le disque se décale dès que la carte change
  // de largeur (repli média 1 colonne, fenêtre élargie). Le recentrage est
  // ensuite garanti par un ResizeObserver (voir `_pfObserveDonut`).
  //
  // Libellés DANS le disque (`textposition: "inside"`, orientation horizontale) :
  // en « outside », les noms de comptes longs des parts étroites débordaient du
  // SVG (Plotly met `overflow: hidden`) et étaient rognés — mesuré jusqu'à
  // −77 px à gauche avec 5 comptes. À l'intérieur, rien ne sort du cadre.
  // Répartition du donut selon la dimension choisie : par COMPTES (défaut) ou par
  // TITRES. Renvoie les libellés/valeurs + un titre ; `rows` vide = pas de donut.
  pfBreakdownData() {
    const s = this.pfSummary;
    if (this.pfBreakdown === "holdings") {
      const holdings = (s ? s.holdings : []) || [];
      return {
        title: "Répartition des titres",
        labels: holdings.map((h) => h.name || h.ticker),
        values: holdings.map((h) => h.value),
        empty: holdings.length === 0,
      };
    }
    const accounts = (s ? s.accounts : []) || [];
    return {
      title: "Répartition des comptes",
      labels: accounts.map((a) => a.name),
      values: accounts.map((a) => a.value),
      empty: accounts.length === 0,
    };
  },

  // Dimensions proposées par le menu déroulant du donut. Ajouter une dimension
  // (ex. un futur regroupement par TAGS) = ajouter une entrée ici + l'agrégat
  // correspondant dans `pfSummary` ; ni le template ni le tracé ne changent.
  pfBreakdownOptions() {
    return [
      { key: "accounts", label: "Comptes" },
      { key: "holdings", label: "Titres" },
    ];
  },

  pfBreakdownLabel() {
    const opt = this.pfBreakdownOptions().find((o) => o.key === this.pfBreakdown);
    return opt ? opt.label : "";
  },

  togglePfBreakdownMenu() {
    this.pfBreakdownMenuOpen = !this.pfBreakdownMenuOpen;
  },

  setPfBreakdown(dim) {
    this.pfBreakdownMenuOpen = false;
    if (this.pfBreakdown === dim) return;
    this.pfBreakdown = dim;
    this.$nextTick(() => this.drawPortfolioDonut("pf-summary-donut"));
  },

  drawPortfolioDonut(el) {
    if (typeof document === "undefined") return;
    const node = document.getElementById(el);
    if (!node) return;
    const data = this.pfBreakdownData();
    if (data.empty) {
      // Dimension sans position valorisable : on purge le tracé précédent (sinon
      // le disque de l'autre dimension reste affiché sous le message vide).
      if (typeof Plotly !== "undefined") Plotly.purge(el);
      return;
    }
    this._drawDonut(el, data.labels, data.values);
  },

  // Tracé de donut PARTAGÉ par le Résumé et la Performance (revue #17.4, #24) :
  // deux copies de cette layout avaient divergé, et c'est de là qu'est né le bug
  // d'observateur (#2). Le traceur est mémorisé par conteneur pour que
  // `_pfObserveDonut` sache quoi rejouer sans comparer des identifiants en dur.
  _drawDonut(el, labels, values) {
    const node = el ? document.getElementById(el) : null;
    if (!node || typeof Plotly === "undefined") return;
    if (!labels.length) {
      Plotly.purge(el);
      return;
    }
    const width = node.clientWidth || DONUT_FALLBACK_W;
    const height = node.clientHeight || CHART_HEIGHTS.portfolio_donut;
    const palette = [C.accent, C.teal, C.ma2, C.ma1];
    Plotly.react(el, [{
      type: "pie", hole: 0.62, labels, values,
      textinfo: "label+percent", textposition: "inside",
      insidetextorientation: "horizontal",
      marker: { colors: labels.map((_, i) => palette[i % palette.length]) },
      sort: false,
      // Domain plein cadre : le disque occupe tout le conteneur, donc son centre
      // est le centre du SVG (et non un point flottant recalculé par Plotly).
      domain: { x: [0, 1], y: [0, 1] },
    }], {
      margin: { l: 0, r: 0, t: 0, b: 0 }, width, height,
      autosize: false,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      showlegend: false,
    }, { displayModeBar: false, responsive: false });
    this._pfDonutW = { ...(this._pfDonutW || {}), [el]: width };
    // Traceur mémorisé : `_pfRedrawDonut` le rejoue au redimensionnement sans
    // comparer d'identifiant en dur (finding #24).
    this._pfDonutDraw = {
      ...(this._pfDonutDraw || {}),
      [el]: () => this._drawDonut(el, labels, values),
    };
    this._pfObserveDonut(width, el, node);
  },

  // Re-trace le donut quand la largeur de SON conteneur change. Plotly
  // (`responsive`) n'écoute que `window.resize` : le repli média et l'ouverture
  // de la modale changent la largeur de la carte SANS événement fenêtre.
  //
  // Un observateur, une largeur ET le NŒUD observé par conteneur (clés = id du
  // div). Deux raisons :
  //  - les deux donuts (Résumé, Performance) coexistent et ne doivent pas se
  //    voler le slot unique (le Résumé, chargé en premier, captait l'observateur
  //    et la Performance n'était jamais ré-observée — finding #2) ;
  //  - `#pf-perf-donut` vit sous `<template x-if>` : Alpine DÉTRUIT et recrée le
  //    div au passage à vide/erreur puis rechargement. Garder l'ancien
  //    observateur le laisserait branché sur un nœud détaché (finding #19), donc
  //    on reconnecte dès que le nœud a changé.
  _pfObserveDonut(width, el, node) {
    if (typeof ResizeObserver === "undefined" || !node || !el) return;
    this._pfDonutObs = this._pfDonutObs || {};
    this._pfDonutW = this._pfDonutW || {};
    this._pfDonutNodes = this._pfDonutNodes || {};
    const current = this._pfDonutObs[el];
    // Même nœud déjà observé : rien à refaire (évite les doublons de callbacks).
    if (current && this._pfDonutNodes[el] === node) return;
    if (current) current.disconnect(); // nœud remplacé par Alpine : on rebranche
    const obs = new ResizeObserver((entries) => {
      const w = entries?.[0]?.target?.clientWidth || 0;
      if (!w || Math.abs(w - (this._pfDonutW[el] || 0)) < 1) return; // anti-boucle
      const run = () => this._pfRedrawDonut(el);
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
      else run();
    });
    this._pfDonutObs[el] = obs;
    this._pfDonutNodes[el] = node;
    obs.observe(node);
  },

  // Rejoue le TRACEUR du donut `el`. Le traceur est lu dans `_pfDonutDraw`
  // (mémorisé au premier tracé) : plus d'identifiant comparé en dur, donc un
  // troisième donut n'exigerait pas de toucher cette méthode.
  _pfRedrawDonut(el) {
    const draw = this._pfDonutDraw?.[el];
    if (draw) draw();
  },

  // Déconnexion des observateurs (fermeture de l'espace : pas de fuite).
  _pfDisconnectDonut() {
    for (const [el, obs] of Object.entries(this._pfDonutObs || {})) {
      obs.disconnect();
      delete this._pfDonutObs[el];
    }
    this._pfDonutObs = {};
    this._pfDonutW = {};
    this._pfDonutNodes = {};
    this._pfDonutDraw = {};
  },

  // --- Étiquettes / portefeuilles virtuels (#17.6) --------------------------

  pfTagMax() {
    return PORTFOLIO_TAG_MAX || null;
  },

  // Message d'état vide contextualisé : quand un portefeuille virtuel est actif,
  // on explique POURQUOI l'écran est vide et comment en sortir (sinon un filtre
  // d'étiquette sans donnée ressemble à une panne).
  pfNoDataHint(fallback) {
    if (this.portfolioTag) {
      return `Aucune donnée pour l'étiquette « ${this.portfolioTag} » sur ce périmètre. `
        + `Choisis « Toutes les étiquettes » pour élargir.`;
    }
    return fallback;
  },

  // Étiquettes distinctes proposées en autocomplétion (datalist) — source =
  // transactions de la portée courante (pas de table de référence).
  pfTagOptions() {
    return this.portfolioTagsList || [];
  },

  // Bascule l'édition en ligne de l'étiquette d'une position.
  startEditPositionTag(pos) {
    this.pfTagEditing = pos.ticker;
    this.pfTagDraft = (pos.tags && pos.tags[0]) || "";
  },

  cancelEditPositionTag() {
    this.pfTagEditing = null;
    this.pfTagDraft = "";
  },

  async savePositionTag(pos) {
    const tag = (this.pfTagDraft || "").trim();
    await this._applyPositionTag(pos.ticker, tag || null);
  },

  async _applyPositionTag(ticker, tag) {    this._portfolioBusy = true;
    this.portfolioError = "";
    try {
      const res = await api.setPositionTag({
        account_id: this.portfolioAccountId,
        ticker,
        tag,
      });
      if (!res.ok) {
        this.portfolioError = res.data.detail || "Étiquetage impossible";
        return;
      }
      this.pfTagEditing = null;
      this.pfTagDraft = "";
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Étiquetage impossible (réseau).";
    } finally {
      this._portfolioBusy = false;
    }
  },

  // --- Risque (#17.3) : drawdown + matrice de corrélation -------------------

  async loadPortfolioRisk() {
    if (!this._pfMetaReady) await this.loadPortfolioMeta();
    if (!this._pfMetaReady) return;
    const seq = ++this._pfRiskSeq;
    this.pfRiskLoading = true;
    this.pfRiskError = "";
    try {
      const risk = await api.portfolioRisk(
        this.portfolioAccountId,
        this.pfBenchmark,
        this.pfPeriod,
        this.portfolioTag,
      );
      if (seq !== this._pfRiskSeq) return; // réponse périmée (course)
      this.pfRisk = risk;
      this.$nextTick(() => this.drawPortfolioRisk());
      // Un test de corrélation en cours suit la même portée : on le relance
      // (nouvelle matrice, nouveaux tickers).
      if (this.pfCorrTestTicker.trim()) await this.runCorrTest();
    } catch (e) {
      if (seq !== this._pfRiskSeq) return;
      this.pfRisk = null;
      this.pfRiskError = `Risque indisponible : ${e?.message || "erreur réseau"}.`;
    } finally {
      if (seq === this._pfRiskSeq) this.pfRiskLoading = false;
    }
  },

  drawPortfolioRisk() {
    this.drawDrawdownChart("pf-risk-drawdown");
    this.drawCorrelationHeatmap("pf-risk-corr");
    this.drawCorrTestRow("pf-risk-corr-test");
  },

  // --- Transactions du graphe héro (#17.4) ----------------------------------
  // Charge les transactions du TICKER courant (toutes portées, dépend du
  // portefeuille — PAS la table `events`) pour dessiner les marqueurs du graphe
  // héro. Silencieux/neutre hors action (ratio, indice) : ils n'ont pas de
  // portefeuille. PAARESSEUX : appelé uniquement à la première activation de la
  // case « Transactions » (aucune requête à vide pour qui ne l'utilise pas).
  async loadTxMarkers() {
    this.txMarkers = [];
    if (!this.data || this.isRatio() || this.isBasket()) return;
    const ticker = (this.data.identity?.ticker || "").toUpperCase();
    if (!ticker) return;
    try {
      const tx = await api.portfolioTransactions(null, null);
      this.txMarkers = (tx || [])
        .filter((t) => String(t.ticker).toUpperCase() === ticker)
        .map((t) => ({
          date: t.trade_date,
          side: t.side,
          quantity: t.quantity,
          price: t.price,
        }));
    } catch {
      /* portefeuille indisponible : aucun marqueur, la fiche reste intacte */
    }
    if (this.showTx) this.$nextTick(() => { try { this.drawChart(); } catch { /* graphe absent */ } });
  },

  // Marqueurs de transactions dans la fenêtre visible [i0, i1] : première séance
  // ≥ la date de la transaction (le jour exact peut être férié/week-end), et
  // tolérance d'une semaine pour ne pas épingler un point hors fenêtre au bord.
  _visibleTx(i0, i1) {
    const d = this.data?.chart?.dates;
    if (!d) return [];
    const WEEK_MS = 7 * 864e5;
    const out = [];
    for (const tx of this.txMarkers || []) {
      let lo = i0, hi = i1, idx = -1;
      while (lo <= hi) {
        const mid = (lo + hi) >> 1;
        if (d[mid] >= tx.date) { idx = mid; hi = mid - 1; } else { lo = mid + 1; }
      }
      if (idx < 0) continue;
      if (new Date(d[idx]) - new Date(tx.date) > WEEK_MS) continue;
      out.push({ ...tx, idx });
    }
    return out;
  },

  // Bascule de la case « Transactions » : charge les marqueurs à la première
  // activation (paresseux), puis redessine. `loadTxMarkers` redessine lui-même
  // si la case est active.
  onToggleTx() {
    if (this.showTx && !this.txMarkers.length) this.loadTxMarkers();
    else this.$nextTick(() => { try { this.drawChart(); } catch { /* graphe absent */ } });
  },

  // --- Détail par titre (C) -------------------------------------------------
  // Ouvre la fenêtre de détail d'une ligne du grand tableau : graphe dédié
  // (perf cumulée titre vs benchmark, rebasée à 0 %) + sélecteur d'horizon et de
  // points d'entrée/sortie avec écart au benchmark.
  async openPerfDetail(ticker) {
    if (!ticker) return;
    this.pfDetailOpen = true;
    this.pfDetailEntryIdx = null;
    this.pfEntryMenuOpen = false;
    this.pfDetail = null;
    // On repart du benchmark GLOBAL : c'est la norme de l'espace portefeuille.
    // Le sélecteur de la modale n'offre ensuite que la liste curée (pas de
    // ticker libre) et n'écrit JAMAIS le réglage persisté.
    this.pfDetailBenchmark = this.pfBenchmark;
    await this.loadPerfDetail(ticker);
  },

  // Charge (ou recharge) le détail d'un titre pour le benchmark COURANT de la
  // modale (`pfDetailBenchmark`). Séparé de `openPerfDetail` : changer de
  // benchmark réutilise le ticker déjà ouvert sans rouvrir la fenêtre.
  async loadPerfDetail(ticker) {
    if (!ticker) return;
    this.pfDetailLoading = true;
    this.pfDetailError = "";
    try {
      this.pfDetail = await api.portfolioSecurity(ticker, this.pfDetailBenchmark);
      this.$nextTick(() => this.drawPerfDetail());
    } catch (e) {
      this.pfDetail = null;
      this.pfDetailError = `Détail indisponible : ${e?.message || "erreur réseau"}.`;
    } finally {
      this.pfDetailLoading = false;
    }
  },

  // Changement de benchmark DANS la modale : local, jamais persisté (la norme
  // globale ne bouge pas). Recharge le détail du même titre et remet à zéro le
  // point d'entrée sélectionné (les écarts changent de référence).
  async setPfDetailBenchmark(ticker) {
    const value = (ticker || "").trim().toUpperCase();
    if (!value || value === this.pfDetailBenchmark) return;
    this.pfDetailBenchmark = value;
    this.pfDetailEntryIdx = null;
    this.pfEntryMenuOpen = false;
    await this.loadPerfDetail(this.pfDetail?.ticker);
  },

  closePerfDetail() {
    this.pfDetailOpen = false;
    this.pfDetail = null;
    this.pfDetailEntryIdx = null;
    this.pfEntryMenuOpen = false;
  },

  // Transactions du titre détaillé, alignées sur le ticker courant.
  //
  // Les écarts (`return_pct`/`benchmark_pct`/`delta_pct`) sont RECALCULÉS depuis
  // les séries de la modale (`pfDetail.chart.price_adj` + `pfDetail.benchmark_curve`,
  // déjà alignées sur les mêmes dates) au lieu d'être lus dans
  // `pfPerf.retrospective`. Celle-ci est calculée côté service avec le benchmark
  // GLOBAL : après avoir choisi un autre benchmark dans le sélecteur local de la
  // modale, le graphe comparait au nouveau pendant que le menu annonçait les
  // écarts de l'ancien — deux réponses contradictoires dans le même écran
  // (revue #17.4, finding #15).
  pfDetailEntries() {
    const tk = (this.pfDetail?.ticker || "").toUpperCase();
    const rows = (this.pfPerf?.retrospective || []).filter((r) => r.ticker === tk);
    const chart = this.pfDetail?.chart;
    const bench = this.pfDetail?.benchmark_curve || [];
    if (!rows.length || !chart?.dates?.length) return rows;
    const dates = chart.dates;
    const series = chart.price_adj || [];
    // Dernière valeur disponible d'une série (même convention que le moteur).
    const last = (arr) => {
      for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null && arr[i] > 0) return arr[i];
      return null;
    };
    const ret = (start, end) =>
      start == null || end == null || start <= 0 ? null : (end / start - 1) * 100;
    const endPx = last(series);
    const endBench = last(bench);
    return rows.map((row) => {
      const idx = this.pfEntryIdx(row);
      // Transaction datée après la fin de l'historique : aucun point d'ancrage
      // dans les séries du détail. On neutralise les écarts au lieu de laisser
      // ceux du payload global (mesurés contre l'AUTRE benchmark — finding #22).
      if (idx < 0 || idx >= dates.length) {
        return { ...row, return_pct: null, benchmark_pct: null, delta_pct: null };
      }
      const startPx = series[idx];
      const startBench = bench[idx];
      const returnPct = ret(startPx, endPx);
      const benchPct = ret(startBench, endBench);
      const delta =
        returnPct == null || benchPct == null ? null : returnPct - benchPct;
      const r2 = (v) => (v == null ? null : Math.round(v * 100) / 100);
      return {
        ...row,
        return_pct: r2(returnPct),
        benchmark_pct: r2(benchPct),
        delta_pct: r2(delta),
      };
    });
  },

  // Titre de la modale : nom de la ligne (grand tableau) sinon le ticker.
  pfDetailTitle() {
    const tk = this.pfDetail?.ticker || "";
    const row = (this.pfPerf?.table || []).find((r) => r.ticker === tk);
    return (row?.name || tk) + " — détail";
  },

  // Légende HTML du graphe de détail : titre (bleu) + benchmark (ambre), chacune
  // avec sa perf CUMULÉE sur la fenêtre affichée (comme le Résumé).
  pfDetailLegend() {
    const c = this.pfDetail?.chart;
    if (!c) return [];
    const dates = c.dates;
    const start = this.pfDetailWindowStart(dates);
    const anchor = this.pfDetailAnchorIdx(dates, start);
    // Perf cumulée depuis l'ancrage commun (même base que le graphe) jusqu'à la
    // dernière valeur disponible de la fenêtre.
    const perf = (arr) => {
      const base = arr[anchor];
      if (base == null || base <= 0) return null;
      const win = arr.slice(anchor).filter((v) => v != null && v > 0);
      if (win.length < 2) return null;
      return (win[win.length - 1] / base - 1) * 100;
    };
    const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + this.fmt(v) + " %");
    return [
      { key: "titre", label: "Titre", color: C.accent, value: pct(perf(c.price_adj)) },
      { key: "benchmark", label: this.pfDetail?.benchmark?.label || this.pfDetailBenchmark,
        color: C.ma1, value: pct(perf(this.pfDetail.benchmark_curve || [])) },
    ];
  },

  // Indice d'ancrage du rebasage : première séance >= `start` où le TITRE et le
  // BENCHMARK sont tous deux disponibles (> 0). Ancrer les deux courbes sur le
  // même point garantit qu'elles partagent le 0 % — comparatif honnête même si
  // le benchmark démarre après le titre (ETF récent, ticker libre). Repli sur
  // `start` si aucun point commun (aucun alignement possible).
  pfDetailAnchorIdx(dates, start) {
    const series = this.pfDetail?.chart?.price_adj || [];
    const bench = this.pfDetail?.benchmark_curve || [];
    for (let i = start; i < dates.length; i++) {
      if (series[i] != null && series[i] > 0 && bench[i] != null && bench[i] > 0) return i;
    }
    return start;
  },

  // Chips d'horizon du graphe de détail (source unique config.py). Valeur =
  // horizon, libellé = periodLabel (TTM/3A/5A/10A/MAX).
  pfDetailHorizonChips() {
    return this.pfDetailHorizons.map((h) => ({ value: h, label: this.pfPeriodLabel(h) }));
  },

  // Changement d'horizon : le point d'entrée sélectionné prime et est effacé pour
  // montrer l'horizon demandé ; recadrage pur client (aucun refetch).
  setPfDetailHorizon(horizon) {
    if (horizon === this.pfDetailHorizon) return;
    this.pfDetailHorizon = horizon;
    this.pfDetailEntryIdx = null;
    this.$nextTick(() => this.drawPerfDetail());
  },

  // Sélection d'un point d'entrée : le graphe ne montre qu'à partir de ce point et
  // affiche l'écart au benchmark depuis là. Re-cliquer désélectionne (vue pleine).
  // Le menu flottant se referme toujours après le choix.
  selectPfEntry(row) {
    const idx = this.pfEntryIdx(row);
    this.pfDetailEntryIdx = this.pfDetailEntryIdx === idx ? null : idx;
    this.pfEntryMenuOpen = false;
    this.$nextTick(() => this.drawPerfDetail());
  },

  // Menu flottant des points d'entrée/sortie (patron `pf-breakdown-menu`) :
  // ouverture/fermeture discrète, sans toucher au graphe (jamais redimensionné).
  togglePfEntryMenu() {
    this.pfEntryMenuOpen = !this.pfEntryMenuOpen;
  },

  // Index de la première séance >= date de la transaction (aligné sur la série du
  // graphe de détail). -1 si la date est postérieure à l'historique.
  pfEntryIdx(row) {
    const dates = this.pfDetail?.chart?.dates || [];
    for (let i = 0; i < dates.length; i++) if (dates[i] >= row.date) return i;
    return -1;
  },

  // Index de début de la fenêtre du graphe de détail pour un horizon donné,
  // relatif à la DERNIÈRE date (comme `period_start_index` côté serveur). `max`
  // = tout ; `ttm` = 12 mois ; `Na` = N années (jour clampé au dernier du mois).
  // Arithmétique en UTC : passer par l'heure locale décalerait d'un jour dans les
  // fuseaux à offset négatif (bissextiles), rendant la fenêtre incohérente avec
  // `period_start_index` côté serveur.
  pfDetailHorizonStart(dates, horizon) {
    if (!dates.length || horizon === "max") return 0;
    const last = new Date(dates[dates.length - 1]);
    const years = horizon === "ttm" ? 1 : parseInt(horizon, 10);
    const target = new Date(last);
    target.setUTCFullYear(last.getUTCFullYear() - years);
    const iso = target.toISOString().slice(0, 10);
    const i = dates.findIndex((d) => d >= iso);
    return i < 0 ? 0 : i;
  },

  // Fenêtre du graphe de détail : recadrée sur un point d'entrée sélectionné si
  // présent (priorité), sinon sur l'horizon courant.
  pfDetailWindowStart(dates) {
    if (this.pfDetailEntryIdx != null) return this.pfDetailEntryIdx;
    return this.pfDetailHorizonStart(dates, this.pfDetailHorizon);
  },

  // Graphe du détail (calqué sur le Résumé) : deux courbes de performance
  // CUMULÉE (%, rebasées à 0 au début de la fenêtre) — titre (bleu + aire) vs
  // benchmark (ambre) — sur l'horizon choisi. Les triangles achat/vente du titre
  // sont superposés. Aucune régression (contrairement à la fiche).
  drawPerfDetail() {
    const el = "pf-security-plot";
    const node = typeof document !== "undefined" ? document.getElementById(el) : null;
    if (!node || typeof Plotly === "undefined" || !this.pfDetail) return;
    const c = this.pfDetail.chart;
    const dates = c.dates;
    const series = c.price_adj;   // perf passée du titre (dividendes réinvestis)
    const bench = this.pfDetail.benchmark_curve || [];
    const start = this.pfDetailWindowStart(dates);
    const xs = dates.slice(start);
    // Ancrage COMMUN : les deux courbes partagent le même 0 % (première séance où
    // titre ET benchmark sont tous deux disponibles). Évite un comparatif faussé
    // si le benchmark démarre après le titre.
    const anchor = this.pfDetailAnchorIdx(dates, start);

    // Performance cumulée (%) rebasée à 0 sur l'ancrage commun : les deux séries
    // sont rapportées au même instant de référence.
    const rebase = (arr) => {
      const base = arr[anchor];
      if (base == null || base <= 0) return xs.map(() => null);
      return dates.slice(start).map((_d, k) => {
        const v = arr[start + k];
        return v == null || v <= 0 ? null : (v / base - 1) * 100;
      });
    };
    const ys = rebase(series);
    const benchBase = rebase(bench);

    // Triangles achat/vente du titre (mêmes conventions que la case « Transactions »
    // du héro), alignés sur les dates de la fenêtre courante.
    const buys = { x: [], y: [] }, sells = { x: [], y: [] };
    for (const e of this.pfDetailEntries()) {
      const idx = this.pfEntryIdx(e);
      if (idx < start || idx < 0 || idx >= dates.length) continue;
      const v = ys[idx - start];
      if (v == null) continue;
      (e.side === "sell" ? sells : buys).x.push(dates[idx]);
      (e.side === "sell" ? sells : buys).y.push(v);
    }
    const tri = (bucket, symbol, color) => ({
      x: bucket.x, y: bucket.y, mode: "markers", type: "scatter",
      marker: { symbol, size: 11, color, line: { width: 0 } },
      hoverinfo: "skip", showlegend: false,
    });
    const txTraces = [];
    if (buys.x.length) txTraces.push(tri(buys, "triangle-up", C.accent));
    if (sells.x.length) txTraces.push(tri(sells, "triangle-down", C.bad));

    const benchLabel = this.pfDetail?.benchmark?.label || this.pfDetailBenchmark;
    Plotly.react(el, [
      { x: xs, y: ys, name: "Titre", mode: "lines",
        line: { color: C.accent, width: 2 }, fill: "tozeroy", fillcolor: "rgba(37,99,235,.08)" },
      { x: xs, y: benchBase, name: benchLabel, mode: "lines",
        line: { color: C.ma1, width: 2 } },
      ...txTraces,
    ], {
      margin: { l: 48, r: 16, t: 12, b: 28 },
      height: CHART_HEIGHTS.portfolio_drawdown,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false },
      yaxis: { gridcolor: C.grid, showline: false, ticksuffix: " %" },
      showlegend: false, hovermode: false,
    }, { displayModeBar: false, responsive: true });
  },

  // --- Performance (#17.4) --------------------------------------------------
  async loadPortfolioPerformance() {
    if (!this._pfMetaReady) await this.loadPortfolioMeta();
    if (!this._pfMetaReady) return;
    const seq = ++this._pfPerfSeq;
    this.pfPerfLoading = true;
    this.pfPerfError = "";
    try {
      const perf = await api.portfolioPerformance(
        this.portfolioAccountId,
        this.pfBenchmark,
        PF_PERF_PERIOD,
        this.portfolioTag,
      );
      if (seq !== this._pfPerfSeq) return; // réponse périmée (course)
      this.pfPerf = perf;
      // Repli sur MAX si la période mémorisée n'est plus couverte par le payload.
      const periods = perf?.risk_adjusted?.periods || [];
      if (periods.length && !periods.includes(this.pfRiskPeriod)) {
        this.pfRiskPeriod = periods.includes("max") ? "max" : periods[periods.length - 1];
      }
      this.$nextTick(() => this.drawPortfolioPerformance());
    } catch (e) {
      if (seq !== this._pfPerfSeq) return;
      this.pfPerf = null;
      this.pfPerfError = `Performance indisponible : ${e?.message || "erreur réseau"}.`;
    } finally {
      if (seq === this._pfPerfSeq) this.pfPerfLoading = false;
    }
  },

  // Trace le donut « Répartition des titres » de la Performance (mêmes lignes que
  // le Résumé, dimension « holdings »). Le donut est le camembert de référence :
  // les stats portent sur exactement ces lignes.
  drawPortfolioPerformance() {
    this.drawPerfDonut("pf-perf-donut");
    this.drawMonthlyChart("pf-perf-monthly-plot");
    this.drawContributionChart("pf-perf-contrib-plot");
  },

  // Barres groupées « Rendements mensuels » : portefeuille (bleu) vs benchmark
  // (ambre, comme le Résumé/Risque), par mois de la fenêtre choisie (TTM/année).
  // Axe Y en % avec ligne zéro ; un mois absent est un trou (pas de barre).
  drawMonthlyChart(el) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    if (typeof Plotly === "undefined") return;
    const c = this.pfMonthlyChart();
    if (!c.labels.length) { Plotly.purge(el); return; }
    const bar = (y, name, color) => ({
      x: c.labels, y, name, type: "bar", marker: { color },
    });
    Plotly.react(el, [bar(c.portfolio, this.pfMonthlyLegend()[0].label, C.accent),
      bar(c.benchmark, this.pfMonthlyLegend()[1].label, C.ma1)], {
      margin: { l: 44, r: 12, t: 6, b: 40 }, height: CHART_HEIGHTS.portfolio_monthly,
      barmode: "group", bargap: 0.25, bargroupgap: 0.08,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false, type: "category" },
      yaxis: { gridcolor: C.grid, showline: false, zeroline: true,
        zerolinecolor: C.neutral, ticksuffix: " %" },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  },

  // Contribution par entreprise : barres verticales proportionnelles à la
  // contribution (%), triées CROISSANT — la pire contribution à gauche, la
  // meilleure à droite (lecture « de la plus mauvaise à la meilleure »).
  // Positif = bleu (C.accent), négatif = rouge (C.bad) — charte bleu=bien/rouge=mal.
  pfContributionChart() {
    const items = (this.pfPerf?.contributions?.items || [])
      .filter((c) => c.contribution_pct != null)
      .slice()
      .sort((a, b) => a.contribution_pct - b.contribution_pct);
    return {
      labels: items.map((c) => c.name || c.ticker),
      values: items.map((c) => c.contribution_pct),
      colors: items.map((c) => (c.contribution_pct >= 0 ? C.accent : C.bad)),
    };
  },

  // Polarité du Total de contribution (True = bleu, False = rouge, None = neutre).
  pfContributionTotalGood() {
    const v = this.pfPerf?.contributions?.total_pct;
    return v == null ? null : v >= 0;
  },

  // Barres verticales de contribution par entreprise, tracées avec EXACTEMENT
  // le gabarit du graphe « Rendements mensuels » voisin (marges, grille, zéro,
  // suffixe %, police) : les deux cartes doivent se lire comme une paire, pas
  // comme deux familles de graphes différentes.
  drawContributionChart(el) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    if (typeof Plotly === "undefined") return;
    const c = this.pfContributionChart();
    if (!c.labels.length) { Plotly.purge(el); return; }
    // Noms longs : on incline les libellés SEULEMENT quand c'est nécessaire
    // (le graphe voisin des mois garde ses étiquettes droites, ses libellés
    // étant courts) — la grammaire du graphe reste identique, seule la place
    // manquante justifie l'inclinaison.
    const long = c.labels.some((l) => String(l).length > 12);
    Plotly.react(el, [{
      x: c.labels, y: c.values, type: "bar", name: "Contribution",
      marker: { color: c.colors },
      hovertemplate: "%{x}<br>%{y:.2f} %<extra></extra>",
    }], {
      margin: { l: 44, r: 12, t: 6, b: long ? 56 : 40 }, height: CHART_HEIGHTS.portfolio_contrib,
      // Bâtons plus fins que ceux des mensuels (peu de titres = colonnes très
      // larges sans ça) : même grammaire, mais silhouette plus légère.
      bargap: 0.6,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false, type: "category",
        tickangle: long ? -30 : 0, automargin: true },
      yaxis: { gridcolor: C.grid, showline: false, zeroline: true,
        zerolinecolor: C.neutral, ticksuffix: " %" },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
  },

  // Donut de la Performance : répartition par TITRES (poids de marché), sur les
  // lignes du grand tableau (source unique du payload).
  drawPerfDonut(el) {
    const items = (this.pfPerf?.table || []).filter((r) => r.market_value > 0);
    this._drawDonut(
      el,
      items.map((r) => r.name || r.ticker),
      items.map((r) => r.market_value),
    );
  },

  // Groupes de stats prêts à rendre : pour chaque groupe de `stat_groups`
  // (source unique config.py), les lignes {label, value, good, unit}.
  pfStatGroups() {
    const s = this.pfPerf;
    if (!s) return [];
    const stats = s.stats || {};
    return (s.stat_groups || []).map((g) => ({
      id: g.id,
      title: g.title,
      rows: (g.metrics || []).map((m) => {
        const cell = stats[m.key] || {};
        return {
          key: m.key,
          label: m.label,
          unit: m.unit,
          // `signed` vient de config.PORTFOLIO_STAT_GROUPS, transporté par le
          // payload du service (`stat_groups`), pas par /api/meta : seules les
          // VARIATIONS sont signées, jamais les niveaux.
          signed: m.signed === true,
          value: cell.value,
          good: cell.good,
        };
      }),
    }));
  },

  // Formatage d'une valeur de stat selon son unité (source unique : le backend).
  pfStatValue(row) {
    const v = row.value;
    if (v == null) return "--";
    if (row.unit === "pct") {
      // Le « + » est réservé aux VARIATIONS (pente, potentiels) — porté par le
      // champ `signed` de config.PORTFOLIO_STAT_GROUPS. Un niveau (marge, ROE,
      // ROCE, agilité) s'affiche sans signe, comme sur la fiche entreprise.
      const sign = row.signed === true && v > 0 ? "+" : "";
      return sign + this.fmt(v) + " %";
    }
    if (row.unit === "money") return this.portfolioMoney(v) + " €";
    if (row.unit === "score") return this.fmt(v);
    return this.fmt(v);
  },

  pfPerfEmpty() {
    return !(this.pfPerf?.table || []).length;
  },

  // Série chronologique aplatie des rendements mensuels : [{key:"YYYY-MM",
  // year, month, pf, bench}], portefeuille ET benchmark alignés. Source unique =
  // le payload `monthly` ; un mois absent est `null` (jamais un 0 trompeur).
  pfMonthlySeries() {
    const m = this.pfPerf?.monthly;
    if (!m) return [];
    const map = new Map();
    const put = (rows, field) => {
      for (const r of (rows || [])) {
        for (let mo = 1; mo <= 12; mo++) {
          const v = r.months?.[String(mo)];
          if (v == null) continue;
          const key = `${r.year}-${String(mo).padStart(2, "0")}`;
          const cell = map.get(key) || { key, year: r.year, month: mo, pf: null, bench: null };
          cell[field] = v;
          map.set(key, cell);
        }
      }
    };
    put(m.portfolio?.rows, "pf");
    put(m.benchmark?.rows, "bench");
    return [...map.values()].sort((a, b) => (a.key < b.key ? -1 : 1));
  },

  // Graphe « Rendements mensuels » : période sélectionnable (TTM ou une année
  // civile), et séries alignées prêtes à tracer. Deux contrôles seulement —
  // une chip « TTM » et un sélecteur d'année : une chip par année débordait de
  // l'en-tête de carte dès quelques années d'historique (même correctif que le
  // héros Dividende).
  // - TTM (défaut) : les 12 derniers mois CALENDAIRES (chevauche au plus deux
  //   années civiles) — un mois manquant ne rallonge PAS la fenêtre ;
  // - une année : ses mois présents (partiels inclus).
  pfMonthlyChart() {
    const series = this.pfMonthlySeries();
    const years = [...new Set(series.map((p) => p.year))].sort((a, b) => b - a);
    const raw = this.pfPerfMonthSel;
    const selected = raw === "ttm" || !years.includes(Number(raw)) ? "ttm" : raw;
    const slice = selected === "ttm"
      ? this._pfTtmWindow(series)
      : series.filter((p) => p.year === Number(selected));
    return {
      years,
      selected,
      isTtm: selected === "ttm",
      activeYear: selected === "ttm" ? null : Number(selected),
      labels: slice.map((p, i) => this.pfMonthLabel(p, i === 0)),
      portfolio: slice.map((p) => p.pf),
      benchmark: slice.map((p) => p.bench),
    };
  },

  // Fenêtre TTM : les 12 derniers mois CALENDAIRES de la série (compteur de mois
  // `année×12 + mois`). Un trou mensuel ne rallonge donc jamais la fenêtre.
  _pfTtmWindow(series) {
    if (!series.length) return [];
    const last = series[series.length - 1];
    const cutoff = last.year * 12 + last.month - 11;
    return series.filter((p) => p.year * 12 + p.month >= cutoff);
  },

  // Étiquette d'axe : nom du mois, complété de l'année abrégée à la première barre
  // et à chaque changement d'année (ambiguïté levée en mode TTM).
  pfMonthLabel(p, first) {
    const name = MONTHS_FR[p.month - 1];
    return first || p.month === 1 ? `${name} ${String(p.year).slice(2)}` : name;
  },

  // Légende HTML du graphe mensuel (pastilles), cohérente Résumé/Risque :
  // portefeuille en bleu (C.accent), benchmark en ambre (C.ma1). La valeur de
  // chaque série = rendement CUMULÉ de la fenêtre affichée (restaure le « total »
  // du tableau mensuel disparu). Pas d'unité dans le libellé (nom « Label (TICKER) »).
  pfMonthlyLegend() {
    const c = this.pfMonthlyChart();
    const compound = (arr) => {
      let g = 1, has = false;
      for (const v of arr) { if (v == null) continue; g *= 1 + v / 100; has = true; }
      return has ? (g - 1) * 100 : null;
    };
    const pct = (v) => (v == null ? "—" : (v > 0 ? "+" : "") + this.fmt(v) + " %");
    return [
      { key: "portfolio", label: "Portefeuille", color: C.accent, value: pct(compound(c.portfolio)) },
      { key: "benchmark", label: this.pfBenchmarkLabel(this.pfBenchmark), color: C.ma1,
        value: pct(compound(c.benchmark)) },
    ];
  },

  // Changement d'année du graphe mensuel : mémorise puis re-trace. Le grain de
  // période est purement client (choix d'affichage), aucun refetch.
  setPfPerfMonth(value) {
    if (value === this.pfPerfMonthSel) return;
    this.pfPerfMonthSel = value;
    this.$nextTick(() => this.drawMonthlyChart("pf-perf-monthly-plot"));
  },

  pfMonthCell(v) {
    if (v == null) return "--";
    return (v > 0 ? "+" : "") + this.fmt(v) + " %";
  },

  pfMonthPolarity(v) {
    return v == null ? null : v >= 0;
  },

  // Ratios ajustés au risque pour la période SÉLECTIONNÉE (défaut MAX), en deux
  // colonnes (portefeuille / benchmark). Les valeurs viennent de `by_period`
  // (pré-calculées serveur) : basculer de période = pur redraw, aucun refetch.
  pfRiskAdjustedRows() {
    const ra = this.pfPerf?.risk_adjusted;
    if (!ra) return [];
    const per = ra.by_period?.[this.pfRiskPeriod] || ra;
    const num = (v) => (v == null ? "--" : this.fmt(v));
    return [
      { label: "Ratio de Sharpe", pf: num(per.portfolio?.sharpe), bench: num(per.benchmark?.sharpe) },
      { label: "Ratio de Sortino", pf: num(per.portfolio?.sortino), bench: num(per.benchmark?.sortino) },
    ];
  },

  // Périodes réellement disponibles pour les ratios (source = payload serveur).
  pfRiskPeriods() {
    return this.pfPerf?.risk_adjusted?.periods || [];
  },

  // Sélecteur masqué s'il n'y a qu'une seule période (rien à choisir).
  pfRiskPeriodSelectable() {
    return this.pfRiskPeriods().length > 1;
  },

  // Changement de période des ratios : mémorise puis re-rend (aucun refetch).
  setPfRiskPeriod(period) {
    if (period === this.pfRiskPeriod) return;
    this.pfRiskPeriod = period;
  },

  pfRiskEmpty() {
    return !(this.pfRisk?.dates || []).length;
  },

  // Lignes du panneau « Métriques » : perte max, baisse en cours, récupération,
  // volatilité, meilleur/pire mois — valeurs du portefeuille vs benchmark.
  pfRiskMetricRows() {
    const m = this.pfRisk?.metrics || {};
    const b = this.pfRisk?.benchmark_metrics || {};
    const pct = (v) => (v == null ? "—" : this.fmt(v) + " %");
    const days = (v) => (v == null ? "—" : Math.round(v) + " j");
    return [
      { label: "Perte maximale", pf: pct(m.max_drawdown_pct), bench: pct(b.max_drawdown_pct) },
      { label: "Baisse en cours", pf: pct(m.current_drawdown_pct), bench: pct(b.current_drawdown_pct) },
      {
        label: "Récupération la plus longue",
        pf: days(m.longest_recovery_days),
        bench: days(b.longest_recovery_days),
      },
      { label: "Volatilité réalisée", pf: pct(m.volatility_pct), bench: pct(b.volatility_pct) },
      { label: "Meilleur mois", pf: pct(m.best_month_pct), bench: "—" },
      { label: "Pire mois", pf: pct(m.worst_month_pct), bench: "—" },
    ];
  },

  // Légende HTML du graphe de drawdown (SOUS le tracé) : pastille de couleur +
  // nom de la série + sa perte max sur la période. Remplace la légende Plotly
  // qui flottait dans la zone de tracé et chevauchait les courbes.
  pfRiskLegend() {
    const m = this.pfRisk?.metrics || {};
    const b = this.pfRisk?.benchmark_metrics || {};
    const pct = (v) => (v == null ? "—" : this.fmt(v) + " %");
    return [
      { key: "portfolio", label: "Portefeuille", color: C.bad, value: pct(m.max_drawdown_pct) },
      {
        key: "benchmark",
        label: this.pfBenchmarkLabel(this.pfRisk?.benchmark?.ticker),
        color: C.ma1,
        value: pct(b.max_drawdown_pct),
      },
    ];
  },

  // Tracé du drawdown : aire rouge sous la courbe du portefeuille (rouge = mal),
  // courbe du benchmark en ambre pour comparer. **Pas de légende Plotly** : les
  // noms de séries sont rendus en HTML SOUS le tracé (`pfRiskLegend`) — dans la
  // zone de tracé ils chevauchaient la ligne 0 % et les courbes.
  drawDrawdownChart(el) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    const r = this.pfRisk;
    if (!r || !r.dates.length) return;
    const traces = [
      {
        x: r.dates, y: r.drawdown, name: "Portefeuille", mode: "lines",
        line: { color: C.bad, width: 1.6 },
        fill: "tozeroy", fillcolor: C.badFill,
      },
      {
        x: r.dates, y: r.benchmark_drawdown, name: this.pfBenchmarkLabel(r.benchmark?.ticker),
        mode: "lines", line: { color: C.ma1, width: 1.4 },
      },
    ];
    const layout = {
      margin: { l: 48, r: 16, t: 34, b: 28 },
      height: CHART_HEIGHTS.portfolio_drawdown,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      xaxis: { gridcolor: C.grid, showline: false, zeroline: false },
      yaxis: { gridcolor: C.grid, showline: false, zeroline: false, ticksuffix: " %" },
      showlegend: false,
    };
    Plotly.react(el, traces, layout, { displayModeBar: false, responsive: true });
  },

  // Heatmap de corrélation : échelle SÉQUENTIELLE monochrome blanc → bleu de
  // l'interface (`C.accent`). Diagonale = 1 (bleu plein). Les titres sont regroupés
  // par corrélation
  // (clustering serveur) : les blocs sautent aux yeux. Les annotations (valeurs)
  // sont masquées au-delà de la borne config (les cellules deviennent illisibles)
  // — l'infobulle du survol prend le relais.
  //
  // Rendu « précis » (retour utilisateur, réf. visuelle) : un léger `xgap`/`ygap`
  // sépare les cellules (grille lisible) et chaque cellule de la diagonale est
  // détourée d'un trait accent. Les axes sont NUMÉRIQUES (0..n-1) avec les
  // tickers en libellés : c'est ce qui permet d'aligner les formes de la
  // diagonale sur les cellules (impossible sur un axe catégoriel).
  drawCorrelationHeatmap(el) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    const corr = this.pfRisk?.correlation;
    if (!corr || !corr.tickers.length) {
      if (typeof Plotly !== "undefined") Plotly.purge(el);
      return;
    }
    const labels = corr.tickers;
    const idx = labels.map((_, i) => i);
    const annotate = labels.length <= (PORTFOLIO_CORR_ANNOTATE_MAX || 0);
    const z = corr.matrix.map((row) => row.map((v) => (v == null ? null : v)));
    const text = corr.matrix.map((row) =>
      row.map((v) => (v == null ? "" : (v > 0 ? "+" : "") + v.toFixed(2))),
    );
    const height = Math.max(
      CHART_HEIGHTS.portfolio_corr,
      labels.length * 24 + 90,
    );
    const diagonal = idx.map((i) => ({
      type: "rect", xref: "x", yref: "y", layer: "above",
      x0: i - 0.5, x1: i + 0.5, y0: i - 0.5, y1: i + 0.5,
      line: { color: C.accentLight, width: 2 }, fillcolor: "rgba(0,0,0,0)",
    }));
    Plotly.react(el, [{
      type: "heatmap",
      x: idx, y: idx, z, text,
      // Échelle SÉQUENTIELLE : blanc (0, faible) → bleu de l'UI `C.accent` (1,
      // forte). Les corrélations négatives sont bornées au blanc (aucun signal de
      // co-mouvement). Une seule teinte (bleu) : « plus c'est bleu, plus les
      // lignes bougent ensemble », dans le bleu de référence du produit.
      zmin: 0, zmax: 1,
      xgap: 2, ygap: 2,
      colorscale: C.corrScale,
      hovertemplate: "%{customdata[0]} ~ %{customdata[1]} : %{z:.2f}<extra></extra>",
      customdata: idx.flatMap((i) => idx.map((j) => [labels[i], labels[j]])),
      showscale: true,
      colorbar: { ticksuffix: "", thickness: 12, len: 0.9, outlinewidth: 0 },
      texttemplate: annotate ? "%{text}" : "",
      textfont: { size: annotate ? 10 : 0 },
    }], {
      margin: { l: 92, r: 16, t: 12, b: 92 },
      height,
      shapes: diagonal,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 10, color: C.text },
      xaxis: {
        tickmode: "array", tickvals: idx, ticktext: labels,
        tickangle: -45, showgrid: false, range: [-0.5, labels.length - 0.5],
      },
      yaxis: {
        autorange: "reversed", tickmode: "array", tickvals: idx, ticktext: labels,
        showgrid: false,
      },
    }, { displayModeBar: false, responsive: true });
  },

  // Corrélation moyenne du périmètre : valeur calculée SERVEUR (`risk.corr_avg`,
  // source unique `engine.mean_offdiagonal`) — plus de réimplémentation JS.
  pfCorrAverage() {
    const avg = this.pfRisk?.corr_avg;
    return avg == null ? null : avg;
  },

  pfCorrAverageLabel() {
    const avg = this.pfCorrAverage();
    if (avg == null) return "";
    return (avg > 0 ? "+" : "") + this.fmt(avg);
  },

  pfCorrExcluded() {
    return this.pfRisk?.correlation?.excluded || [];
  },

  // --- Test de corrélation (#17.3) : impact d'un ticker candidat ------------

  // Saisie LIVE : temporisation (debounce) pour ne pas déclencher un appel réseau
  // à CHAQUE frappe (chaque test peut coûter un appel Yahoo si le cours n'est pas
  // en cache). On NE touche PAS la casse ici (réécrire la valeur déplacerait le
  // curseur à la fin — gênant pour corriger le milieu d'un code) : la
  // normalisation majuscules a lieu au lancement du calcul. Champ vidé -> effacé.
  // Saisie du champ. Une seule voie asynchrone (pas de double debounce qui
  // pouvait lancer un test AVANT que la recherche par nom ne réponde) :
  //  1. recherche `/api/search` (nom OU code) après 300 ms ;
  //  2. si la saisie correspond EXACTEMENT à un code (`MC.PA`), on teste tout de
  //     suite (comportement « live » sur un ticker connu) ;
  //  3. sinon on affiche les suggestions — l'utilisateur choisit, ce qui lance
  //     le test sur le ticker retenu. Évite l'erreur parasite « introuvable »
  //     pendant la frappe d'un nom. Sous 2 caractères : rien.
  onCorrTestInput() {
    clearTimeout(this._pfCorrTestSearchTimer);
    const q = (this.pfCorrTestTicker || "").trim();
    if (!q) {
      // Invalide toute requête en vol : un résultat tardif ne doit pas repeupler
      // un champ vidé.
      this._pfCorrTestSeq = (this._pfCorrTestSeq || 0) + 1;
      this.pfCorrTest = null;
      this.pfCorrTestError = "";
      this.pfCorrTestLoading = false;
      this.pfCorrTestSuggestions = [];
      return;
    }
    if (q.length < 2) {
      this.pfCorrTestSuggestions = [];
      return;
    }
    this._pfCorrTestSearchTimer = setTimeout(() => this.resolveCorrTestInput(q), 300);
  },

  async resolveCorrTestInput(q) {
    let results;
    try {
      results = (await api.search(q)) || [];
    } catch {
      results = [];
    }
    // Ignore une réponse obsolète si la saisie a changé depuis.
    if ((this.pfCorrTestTicker || "").trim() !== q) return;
    const upper = q.toUpperCase();
    const exact = results.find((s) => (s.symbol || "").toUpperCase() === upper);
    if (exact) {
      // Code exact : on teste directement (pas besoin de la liste).
      this.pfCorrTestSuggestions = [];
      await this.runCorrTest();
      return;
    }
    this.pfCorrTestSuggestions = results;
  },

  // Choix d'une suggestion : on fige le ticker, on ferme la liste et on lance le
  // test immédiatement.
  async pickCorrTestSuggestion(s) {
    this.pfCorrTestTicker = s.symbol;
    this.pfCorrTestSuggestions = [];
    await this.runCorrTest();
  },

  // Entrée : si des suggestions existent, on privilégie le ticker EXACT tapé
  // (l'utilisateur a saisi un code), sinon la première ; sans suggestion (ou code
  // nu), on teste directement la saisie.
  async submitCorrTest() {
    const q = (this.pfCorrTestTicker || "").trim().toUpperCase();
    if (this.pfCorrTestSuggestions.length) {
      const exact = this.pfCorrTestSuggestions.find((s) => s.symbol.toUpperCase() === q);
      return this.pickCorrTestSuggestion(exact || this.pfCorrTestSuggestions[0]);
    }
    return this.runCorrTest();
  },

  async runCorrTest() {
    if (this._pfCorrTestSearchTimer) {
      clearTimeout(this._pfCorrTestSearchTimer);
      this._pfCorrTestSearchTimer = null;
    }
    this.pfCorrTestSuggestions = [];
    const code = (this.pfCorrTestTicker || "").trim().toUpperCase();
    if (!code) {
      this.pfCorrTest = null;
      this.pfCorrTestError = "";
      return;
    }
    // Garde anti-course : on marque chaque requête d'un jeton. Une réponse dont
    // le jeton n'est plus le courant (saisie vidée, ticker changé, portée rechargée
    // entre-temps) est IGNORÉE — sinon un résultat périmé écraserait l'état actuel.
    const token = (this._pfCorrTestSeq = (this._pfCorrTestSeq || 0) + 1);
    this.pfCorrTestLoading = true;
    this.pfCorrTestError = "";
    try {
      const result = await api.portfolioCorrelationTest(
        this.portfolioAccountId,
        this.pfBenchmark,
        this.pfPeriod,
        this.portfolioTag,
        code,
      );
      if (token !== this._pfCorrTestSeq) return; // réponse périmée
      this.pfCorrTest = result;
      this.$nextTick(() => this.drawCorrTestRow("pf-risk-corr-test"));
    } catch (e) {
      if (token !== this._pfCorrTestSeq) return; // erreur périmée
      this.pfCorrTest = null;
      this.pfCorrTestError = e?.message || "erreur réseau";
    } finally {
      if (token === this._pfCorrTestSeq) this.pfCorrTestLoading = false;
    }
  },

  // Impact global du candidat sur la « corrélation moyenne » — une BAISSE est
  // bonne (le titre diversifie), une HAUSSE mauvaise (il redouble l'existant).
  // `good` pilote la couleur (True = bleu = bien) ; `null` = neutre (delta nul).
  pfCorrTestImpact() {
    const t = this.pfCorrTest;
    if (!t || t.delta == null) return null;
    const signed = (v) => (v > 0 ? "+" : "") + this.fmt(v);
    return {
      good: t.delta < 0 ? true : t.delta > 0 ? false : null,
      text:
        `corrélation moyenne ${this.fmt(t.current_avg)} → ${this.fmt(t.new_avg)} ` +
        `(${signed(t.delta)})`,
    };
  },

  pfCorrTestImpactClass() {
    return this.polarity(this.pfCorrTestImpact()?.good);
  },

  // Ligne (1×N) du candidat, ALIGNÉE sous les colonnes de la matrice (mêmes
  // marges, mêmes tickers, même échelle séquentielle). Aucune échelle affichée :
  // on lit la couleur, pas la légende (redondante avec la matrice).
  drawCorrTestRow(el) {
    if (typeof document === "undefined" || !document.getElementById(el)) return;
    const t = this.pfCorrTest;
    if (!t || !t.tickers.length) {
      if (typeof Plotly !== "undefined") Plotly.purge(el);
      return;
    }
    const idx = t.tickers.map((_, i) => i);
    const annotate = t.tickers.length <= (PORTFOLIO_CORR_ANNOTATE_MAX || 0);
    const z = [t.row.map((v) => (v == null ? null : v))];
    const text = [
      t.row.map((v) => (v == null ? "" : (v > 0 ? "+" : "") + v.toFixed(2))),
    ];
    Plotly.react(
      el,
      [
        {
          type: "heatmap",
          x: idx, y: [0], z, text,
          zmin: 0, zmax: 1, xgap: 2, ygap: 2,
          colorscale: C.corrScale,
          hovertemplate: "%{customdata} : %{z:.2f}<extra></extra>",
          customdata: [t.tickers],
          showscale: false,
          texttemplate: annotate ? "%{text}" : "",
          textfont: { size: annotate ? 10 : 0 },
        },
      ],
      {
        margin: { l: 92, r: 16, t: 6, b: 52 },
        height: CHART_HEIGHTS.portfolio_corr_test,
        paper_bgcolor: "transparent", plot_bgcolor: "transparent",
        font: { family: "Inter, sans-serif", size: 10, color: C.text },
        xaxis: {
          tickmode: "array", tickvals: idx, ticktext: t.tickers,
          tickangle: -45, showgrid: false, range: [-0.5, t.tickers.length - 0.5],
        },
        yaxis: { showticklabels: false, showgrid: false },
      },
      { displayModeBar: false, responsive: true },
    );
  },

  // --- Plein écran de la courbe (état PROPRE, ne touche pas le héro) -------
  openPfChartFull() {
    if (!this.pfSummary || !this.pfSummary.dates.length) return;
    this.pfChartFull = true;
    this._pfDetailPrevFocus = typeof document !== "undefined" ? document.activeElement : null;
    this.$nextTick(() => {
      this.drawPortfolioChart("pf-detail-plot", true);
      const modal = document.getElementById("pf-detail-modal");
      if (modal) modal.focus();
    });
  },

  closePfChartFull() {
    this.pfChartFull = false;
    const prev = this._pfDetailPrevFocus;
    this._pfDetailPrevFocus = null;
    if (prev && typeof prev.focus === "function") prev.focus();
  },

  // --- Ouverture / chargement ----------------------------------------------
  async openPortfolio() {
    this.portfolioOpen = true;
    this.portfolioSection = PORTFOLIO_DEFAULT_SECTION;
    this.portfolioError = "";
    this.resetTxForm();
    this.resetDivForm();
    await this.loadPortfolio();
  },

  closePortfolio() {
    this._pfDisconnectDonut();
    this.portfolioOpen = false;
  },

  async loadPortfolio() {
    this.portfolioLoading = true;
    this.portfolioError = "";
    try {
      const accounts = await api.portfolioAccounts();
      this.portfolioAccountsList = accounts || [];
      await this.reloadPortfolioData();
    } catch (e) {
      this.portfolioError = `Portefeuille indisponible : ${e?.message || "erreur réseau"}.`;
    } finally {
      this.portfolioLoading = false;
    }
  },

  // Recharge transactions + dividendes + positions pour le compte/étiquette courant.
  async reloadPortfolioData() {
    const id = this.portfolioAccountId;
    const tag = this.portfolioTag || null;
    try {
      const [tx, div, pos, tags] = await Promise.all([
        api.portfolioTransactions(id, tag),
        api.portfolioDividends(id),
        api.portfolioPositions(id, tag),
        api.portfolioTags(id),
      ]);
      this.portfolioTransactions = tx || [];
      this.portfolioDividends = div || [];
      this.portfolioPositions = pos || [];
      this.portfolioTagsList = tags?.tags || [];
      this.portfolioError = "";
      // L'étiquette courante a pu disparaître du compte (transactions retirées
      // ou réétiquetées) : on retombe sur « toutes » plutôt que de vider l'écran
      // silencieusement. La relance est bornée (le tag est remis à "" avant).
      if (this.portfolioTag && !this.portfolioTagsList.includes(this.portfolioTag)) {
        this.portfolioTag = "";
        return this.reloadPortfolioData();
      }
    } catch (e) {
      this.portfolioError = `Chargement des données impossible : ${e?.message || "erreur réseau"}.`;
    }
    // La section VISIBLE dépend de ces données : on la recharge, et elle seule
    // (une section masquée n'a pas à payer un appel réseau — le bandeau de
    // contexte est commun, les agrégats ne le sont pas).
    await this.reloadActiveSection();
  },

  async setPortfolioAccount(id) {
    // La `<select>` renvoie `""` (vue consolidée) ou l'id en chaîne : on
    // normalise en `null` / `number` — sinon `?account_id=null` part tel quel
    // (422) et l'écran se vide alors que des données existent.
    this.portfolioAccountId = id === "" || id == null ? null : Number(id);
    // L'étiquette courante peut ne pas exister dans le nouveau compte : on la
    // remet à « toutes » (le sélecteur ne propose que les étiquettes du compte),
    // pour ne jamais afficher un périmètre vide sans explication.
    this.portfolioTag = "";
    this.pfTagEditing = null;
    this.resetTxForm();
    this.resetDivForm();
    await this.reloadPortfolioData();
  },

  // Sélection d'une étiquette (#17.6) : "Tous les portefeuilles" ("") ou une
  // étiquette (« portefeuille virtuel »). Recalcule données + résumé + risque.
  async setPortfolioTag(tag) {
    const value = tag || "";
    if (value === this.portfolioTag) return;
    this.portfolioTag = value;
    this.pfTagEditing = null;
    await this.reloadPortfolioData();
  },

  portfolioAccountName(id) {
    const acc = this.portfolioAccountsList.find((a) => a.id === id);
    return acc ? acc.name : "—";
  },

  // --- Rail interne ---------------------------------------------------------
  portfolioSectionPlanned,
  portfolioSectionUsable(id) {
    return PORTFOLIO_SECTIONS.some((s) => s.id === id) && !portfolioSectionPlanned(id);
  },
  portfolioSectionTitle(id) {
    const s = PORTFOLIO_SECTIONS.find((x) => x.id === id);
    if (!s) return "";
    return portfolioSectionPlanned(id) ? `${s.label} — à venir` : s.label;
  },
  setPortfolioSection(id) {
    if (!this.portfolioSectionUsable(id) || id === this.portfolioSection) return;
    this.portfolioSection = id;
    // Les tracés Plotly ne se dessinent que sur un conteneur VISIBLE : on
    // redessine à l'ouverture de la section.
    if (id === "resume") this.$nextTick(() => this.drawPortfolioSummary());
    if (id === "risque") this.loadPortfolioRisk();
    if (id === "performance") this.loadPortfolioPerformance();
    if (id === "dividende") this.loadPortfolioDividends();
  },

  // Bascule Transaction / Dividende dans la carte de saisie. Annule l'édition
  // en cours du formulaire que l'on quitte (pour ne pas garder un `id` orphelin).
  setPortfolioFormMode(mode) {
    if (mode !== "tx" && mode !== "div") return;
    if (mode === this.portfolioFormMode) return;
    this.portfolioFormMode = mode;
    this.portfolioError = "";
    if (mode === "tx") this.resetDivForm();
    else this.resetTxForm();
  },

  // --- Comptes --------------------------------------------------------------
  async createPortfolioAccount() {
    const name = (this.portfolioNewAccountName || "").trim();
    if (!name) {
      this.portfolioError = "Le nom du compte est requis.";
      return;
    }
    try {
      const { ok, data } = await api.createPortfolioAccount({ name });
      if (!ok) {
        this.portfolioError = data.detail || "Création impossible";
        return;
      }
      this.portfolioNewAccountName = "";
      this.portfolioError = "";
      this.portfolioAccountsList = (await api.portfolioAccounts()) || [];
      this.portfolioAccountId = data.id;
      this.resetTxForm();
      this.resetDivForm();
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Création impossible (réseau).";
    }
  },

  async deletePortfolioAccount(acc) {
    if (!confirm(`Supprimer le compte « ${acc.name} » et toutes ses lignes ?`)) return;
    try {
      const { ok, data } = await api.deletePortfolioAccount(acc.id);
      if (!ok) {
        this.portfolioError = data.detail || "Suppression impossible";
        return;
      }
      if (this.portfolioAccountId === acc.id) this.portfolioAccountId = null;
      this.portfolioAccountsList = (await api.portfolioAccounts()) || [];
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Suppression impossible (réseau).";
    }
  },

  // --- Transactions ---------------------------------------------------------
  resetTxForm() {
    this.txForm = { ...EMPTY_TX, account_id: this.portfolioAccountId || "" };
  },

  startEditTransaction(tx) {
    this.txForm = {
      id: tx.id,
      account_id: tx.account_id,
      ticker: tx.ticker,
      side: tx.side,
      trade_date: tx.trade_date,
      quantity: formatDecimalInput(tx.quantity),
      price: formatDecimalInput(tx.price),
      fees: formatDecimalInput(tx.fees),
      note: tx.note || "",
      tag: tx.tag || "",
    };
    this.portfolioFormMode = "tx";
  },

  _txFormValid() {
    const f = this.txForm;
    if (!f.account_id) return false;
    if (!(f.ticker || "").trim()) return false;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.trade_date || "")) return false;
    const qty = parseDecimal(f.quantity);
    if (qty == null || qty <= 0) return false;
    const price = parseDecimal(f.price);
    if (price == null || price < 0) return false;
    const fees = f.fees === "" || f.fees == null ? 0 : parseDecimal(f.fees);
    if (fees == null || fees < 0) return false;
    return true;
  },

  async saveTransaction() {
    if (!this._txFormValid()) {
      this.portfolioError =
        "Compte, ticker, date (AAAA-MM-JJ), quantité > 0, prix ≥ 0 et frais valides requis.";
      return;
    }
    const f = this.txForm;
    const body = {
      account_id: Number(f.account_id),
      ticker: f.ticker.trim(),
      side: f.side,
      trade_date: f.trade_date,
      quantity: parseDecimal(f.quantity),
      price: parseDecimal(f.price),
      fees: f.fees === "" || f.fees == null ? 0 : parseDecimal(f.fees),
      note: (f.note || "").trim() || null,
      tag: (f.tag || "").trim() || null,
    };
    this._portfolioBusy = true;
    this.portfolioError = "";
    try {
      const res = f.id != null
        ? await api.updatePortfolioTransaction(f.id, body)
        : await api.createPortfolioTransaction(body);
      if (!res.ok) {
        this.portfolioError = res.data.detail || "Enregistrement impossible";
        return;
      }
      this.resetTxForm();
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Enregistrement impossible (réseau).";
    } finally {
      this._portfolioBusy = false;
    }
  },

  async deleteTransaction(tx) {
    if (!confirm(`Supprimer la transaction ${tx.side === "buy" ? "d'achat" : "de vente"} ${tx.ticker} du ${tx.trade_date} ?`)) return;
    try {
      const { ok, data } = await api.deletePortfolioTransaction(tx.id);
      if (!ok) {
        this.portfolioError = data.detail || "Suppression impossible";
        return;
      }
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Suppression impossible (réseau).";
    }
  },

  // --- Dividendes -----------------------------------------------------------
  resetDivForm() {
    this.divForm = { ...EMPTY_DIV, account_id: this.portfolioAccountId || "" };
  },

  startEditDividend(div) {
    this.divForm = {
      id: div.id,
      account_id: div.account_id,
      ticker: div.ticker,
      pay_date: div.pay_date,
      amount: formatDecimalInput(div.amount),
    };
    this.portfolioFormMode = "div";
  },

  _divFormValid() {
    const f = this.divForm;
    if (!f.account_id) return false;
    if (!(f.ticker || "").trim()) return false;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.pay_date || "")) return false;
    const amount = parseDecimal(f.amount);
    if (amount == null || amount < 0) return false;
    return true;
  },

  async saveDividend() {
    if (!this._divFormValid()) {
      this.portfolioError = "Compte, ticker, date (AAAA-MM-JJ) et montant ≥ 0 requis.";
      return;
    }
    const f = this.divForm;
    const body = {
      account_id: Number(f.account_id),
      ticker: f.ticker.trim(),
      pay_date: f.pay_date,
      amount: parseDecimal(f.amount),
    };
    this._portfolioBusy = true;
    this.portfolioError = "";
    try {
      const res = f.id != null
        ? await api.updatePortfolioDividend(f.id, body)
        : await api.createPortfolioDividend(body);
      if (!res.ok) {
        this.portfolioError = res.data.detail || "Enregistrement impossible";
        return;
      }
      this.resetDivForm();
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Enregistrement impossible (réseau).";
    } finally {
      this._portfolioBusy = false;
    }
  },

  async deleteDividend(div) {
    if (!confirm(`Supprimer le dividende ${div.ticker} du ${div.pay_date} ?`)) return;
    try {
      const { ok, data } = await api.deletePortfolioDividend(div.id);
      if (!ok) {
        this.portfolioError = data.detail || "Suppression impossible";
        return;
      }
      await this.reloadPortfolioData();
    } catch {
      this.portfolioError = "Suppression impossible (réseau).";
    }
  },

  // --- Formatage ------------------------------------------------------------
  // Devise affichée dans les en-têtes monétaires : celle du compte sélectionné,
  // ou EUR (défaut) en vue consolidée « Tous ».
  portfolioCurrency() {
    const acc = this.portfolioAccountsList.find((a) => a.id === this.portfolioAccountId);
    return acc?.currency || "EUR";
  },
  portfolioQty(q) {
    return Number(q).toLocaleString("fr-FR", { maximumFractionDigits: 4 });
  },
  portfolioMoney(v) {
    if (v == null) return "—";
    return Number(v).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  },
};
