// Obole — section « Valorisation » : calculatrice de prix juste + courbes continues.
//
// Deux responsabilités, dans un seul domaine :
//  1. La CALCULATRICE (partie 1) : les paramètres sont saisis par l'utilisateur,
//     et le calcul (prix juste, rendement estimé, marge, matrice) est fait ICI,
//     en live, sans appel réseau — comme la régression. `engine/valuation_calc.py`
//     est la référence serveur ; le test de parité verrouille l'égalité des deux.
//  2. Les COURBES CONTINUES (partie 2) : elles suivent le patron du Dividend Yield
//     (séries décimées serveur, alignées 1:1 sur `chart.dates`). Aucun recalcul,
//     seules les stats de fenêtre (High/Médiane/Low) sont lues à la volée.
import { C } from "./theme.js";
import {
  VALUATION_METRICS,
  VALUATION_GROUPS,
  VALUATION_HORIZON_YEARS,
  VALUATION_PERIODS,
  VALUATION_PERIOD_DEFAULT,
  VALUATION_MATRIX,
  VALUATION_COLOR_RATIOS,
  CHART_HEIGHTS,
} from "./thresholds.js";
import { api } from "./api.js";
import { slug } from "./util.js";

// Arrondi d'affichage (2 décimales) : évite les flottants bruyants dans les champs.
function round2(v) {
  return v == null || isNaN(v) ? null : Math.round(Number(v) * 100) / 100;
}

// Fond doré TRÈS pâle sous la courbe de valorisation et sa projection (rendu
// Baggr) : opacité faible pour rester un repère, pas un aplat.
const VALO_FILL = "rgba(245,158,11,.08)";

// --- Miroir de engine/valuation_calc.py (parité verrouillée par un test) ------

// Prix juste = Métrique × Multiple médian. `netDebtPerShare` = bridge EV ->
// capitaux propres (multiple d'entreprise uniquement). None si non calculable.
export function fairPrice(metricValue, multiple, netDebtPerShare = null) {
  if (metricValue == null || multiple == null) return null;
  if (metricValue <= 0 || multiple <= 0) return null;
  let value = metricValue * multiple;
  if (netDebtPerShare != null) value -= netDebtPerShare;
  return value;
}

// Marge de sécurité = (Prix juste − Cours) / Prix juste, en %.
export function safetyMargin(fair, price) {
  if (fair == null || price == null || fair === 0) return null;
  return ((fair - price) / fair) * 100;
}

// Rendement annuel estimé = (Valeur projetée / Cours)^(1/H) − 1 + dividende.
export function estimatedReturn(
  metricValue, price, growthPct, multiple, horizon, dividendYieldPct = 0, netDebtPerShare = null,
) {
  if (metricValue == null || multiple == null || price == null) return null;
  if (metricValue <= 0 || multiple <= 0 || price <= 0 || horizon <= 0) return null;
  let projected = metricValue * Math.pow(1 + growthPct / 100, horizon) * multiple;
  if (netDebtPerShare != null) projected -= netDebtPerShare;
  if (projected <= 0) return null;
  return (Math.pow(projected / price, 1 / horizon) - 1) * 100 + dividendYieldPct;
}

// Valeur projetée par action = Métrique₀ × (1 + g)^H × multiple − dette nette/action.
export function projectedValue(metricValue, growthPct, multiple, horizon, netDebtPerShare = null) {
  if (metricValue == null || multiple == null) return null;
  if (metricValue <= 0 || multiple <= 0 || horizon <= 0) return null;
  let value = metricValue * Math.pow(1 + growthPct / 100, horizon) * multiple;
  if (netDebtPerShare != null) value -= netDebtPerShare;
  return value;
}

// Prix d'entrée qui fait EXACTEMENT atteindre la cible : inverse de
// `estimatedReturn`. Valeur projetée / (1 + (cible − dividende)/100)^H. None si
// non calculable (valeur projetée ≤ 0, horizon ≤ 0, cible nette ≤ −100 %).
export function targetEntryPrice(
  metricValue, growthPct, multiple, horizon, targetPct, dividendYieldPct = 0,
  netDebtPerShare = null,
) {
  const projected = projectedValue(metricValue, growthPct, multiple, horizon, netDebtPerShare);
  if (projected == null || projected <= 0 || horizon <= 0) return null;
  const netTarget = (targetPct - dividendYieldPct) / 100;
  if (netTarget <= -1) return null;
  return projected / Math.pow(1 + netTarget, horizon);
}

// CAGR (croissance annualisée) d'une série alignée sur des dates ISO. Renvoie le
// taux en %, ou null si les bornes ne sont pas exploitables (base ≤ 0, span nul).
export function cagrFromSeries(dates, series) {
  if (!dates || !series) return null;
  const pts = [];
  for (let i = 0; i < series.length; i++) {
    const v = series[i];
    if (v != null && v > 0) pts.push([new Date(dates[i]), v]);
  }
  if (pts.length < 2) return null;
  const spanYears = (pts[pts.length - 1][0] - pts[0][0]) / (365.25 * 864e5);
  if (spanYears <= 0) return null;
  return (Math.pow(pts[pts.length - 1][1] / pts[0][1], 1 / spanYears) - 1) * 100;
}

// CAGR d'une série annuelle {année: valeur} (ex. dividende par action).
export function cagrFromYearMap(byYear) {
  const years = Object.keys(byYear || {}).map(Number).sort((a, b) => a - b);
  if (years.length < 2) return null;
  const first = byYear[years[0]];
  const last = byYear[years[years.length - 1]];
  const span = years[years.length - 1] - years[0];
  if (first <= 0 || last <= 0 || span <= 0) return null;
  return (Math.pow(last / first, 1 / span) - 1) * 100;
}

// Grille centrée (croissances lignes, multiples colonnes).
export function matrixGrid(centerGrowth, centerMultiple, rows, cols, growthStep, multipleStep) {
  const growths = [];
  const multiples = [];
  for (let i = 0; i < rows; i++) {
    growths.push(Math.round((centerGrowth + (i - Math.floor(rows / 2)) * growthStep) * 1e4) / 1e4);
  }
  for (let j = 0; j < cols; j++) {
    multiples.push(Math.round((centerMultiple + (j - Math.floor(cols / 2)) * multipleStep) * 1e4) / 1e4);
  }
  return { growths, multiples };
}

// Bucket de couleur d'une cellule (0=rouge, 1=brun, 2=jaune, 3=vert), ancré cible.
export function colorBucket(value, targetPct, ratios) {
  if (value == null || targetPct <= 0) return null;
  if (value < 0) return 0;
  if (value < ratios[0] * targetPct) return 1;
  if (value < ratios[1] * targetPct) return 2;
  return 3;
}

export const valorisationMixin = {
  // --- État de la calculatrice -------------------------------------------
  valView: "graph",       // "graph" | "matrix"
  valMetric: null,        // clé de VALUATION_METRICS
  valPeriod: null,        // années (VALUATION_PERIODS)
  valGrowth: null,        // %/an
  valMultiple: null,      // multiple de sortie estimé
  valTarget: null,        // rendement cible %/an (benchmark)
  valIncludeDividends: true,
  valSaving: false,
  valError: "",

  // Données de la calculatrice pour la fiche courante (None pour ratio/indice).
  valuationCalc() {
    return this.data?.fundamentals?.valuation_calc || null;
  },

  // La calculatrice n'existe que pour une action dont les comptes sont calculables.
  valuationAvailable() {
    const c = this.valuationCalc();
    return !!(c && c.metrics && c.metrics.length);
  },

  // Métriques disponibles (celles réellement calculables pour ce titre).
  valuationMetrics() {
    return this.valuationCalc()?.metrics || [];
  },

  valMetricDef() {
    const metrics = this.valuationMetrics();
    return metrics.find((m) => m.key === this.valMetric) || metrics[0] || null;
  },

  // Périodes proposées (source unique config.py via /api/meta).
  valPeriods() {
    return VALUATION_PERIODS;
  },

  // Appelé à chaque changement de paramètre : redessine ce qui est visible.
  valOnParam() {
    if (this.valView === "graph") this.drawValuationChart();
    // La matrice est rendue par le template (x-for) : rien à redessiner.
  },

  // Changement de BASE ou de PÉRIODE : le multiple médian change, donc on
  // ré-amorce le champ « Multiple final estimé » sur la nouvelle médiane. Sans
  // ça, l'indice « médiane N A » afficherait la médiane de la nouvelle base
  // tandis que le champ garderait l'ancienne valeur (affichage contradictoire et
  // rendement silencieusement faux).
  valOnBase() {
    const m = this.valMedian();
    if (m != null) this.valMultiple = round2(m);
    this.valOnParam();
  },

  // Initialise les paramètres depuis les valeurs enregistrées, sinon des défauts
  // calculés : croissance = consensus analystes (ou CAGR), multiple = médiane de
  // la période, cible = défaut config.
  initValuation() {
    const calc = this.valuationCalc();
    if (!calc) return;
    const saved = calc.saved || {};
    const metrics = calc.metrics || [];
    const savedMetric = metrics.find((m) => m.key === saved.metric);
    const metric = savedMetric || metrics[0] || null;
    this.valMetric = metric ? metric.key : null;
    this.valPeriod = saved.period || calc.period_default || VALUATION_PERIOD_DEFAULT;
    this.valTarget = saved.target_yield != null ? Number(saved.target_yield) : calc.target_default;
    this.valIncludeDividends = saved.include_dividends != null ? saved.include_dividends : true;
    const median = metric ? (metric.median || {})[String(this.valPeriod)] : null;
    this.valMultiple = saved.multiple != null ? Number(saved.multiple)
      : round2(median != null ? median : (metric ? metric.current_multiple : null));
    this.valGrowth = saved.growth != null ? Number(saved.growth) : round2(this.defaultGrowth());
  },

  // Croissance par défaut : consensus analystes BNPA (info) si dispo, sinon CAGR.
  defaultGrowth() {
    const est = this.data?.fundamentals?.estimates;
    if (est && est.eps_growth != null) return est.eps_growth;
    const g = this.data?.fundamentals?.growth || {};
    return g.cagr_eps_5y ?? g.cagr_eps_3y ?? 0;
  },

  // Consensus « Prévisions » affiché sous le champ croissance (info, pas calcul).
  // Le consensus yfinance porte sur le BNPA : on ne l'affiche que pour la base
  // « Bénéfices/Actions » — sur une autre base (CA, Actif net…), il induirait en
  // erreur puisqu'il ne mesure pas la même chose.
  valForecast() {
    if (this.valMetricDef()?.key !== "eps") return null;
    const est = this.data?.fundamentals?.estimates;
    return est && est.eps_growth != null ? est.eps_growth : null;
  },

  // Médiane du multiple pour la période choisie.
  valMedian() {
    const m = this.valMetricDef();
    if (!m) return null;
    return (m.median || {})[String(this.valPeriod)] ?? null;
  },

  // Valeur médiane = métrique par action × multiple médian de la période : valeur
  // intrinsèque historique, affichée en info secondaire. Le KPI de tête est le
  // PRIX D'ENTRÉE atteignant la cible (`valFairPrice`).
  valMedianValue() {
    return fairPrice(this.valLatestMetric(), this.valMedian(), this.valNetDebtPerShare());
  },

  // Multiple courant (m0 de la formule).
  valCurrentMultiple() {
    return this.valMetricDef()?.current_multiple ?? null;
  },

  // Métrique par action la plus récente (Métrique₀ de la formule).
  valLatestMetric() {
    return this.valMetricDef()?.latest ?? null;
  },

  valPrice() {
    return this.data?.identity?.last_price ?? null;
  },

  // Rendement du dividende retenu : celui du titre si la case est cochée, sinon 0.
  valDividendYield() {
    if (!this.valIncludeDividends) return 0;
    const y = this.valuationCalc()?.dividend_yield;
    return y != null ? y : 0;
  },

  // --- Résultats (recalculés en live) -------------------------------------

  // Bridge EV -> capitaux propres (multiple d'entreprise seulement).
  valNetDebtPerShare() {
    const def = this.valMetricDef();
    return def && def.enterprise ? (def.net_debt_per_share ?? null) : null;
  },

  // Prix juste = prix d'entrée qui fait atteindre la cible (dérive des hypothèses
  // saisies : croissance, multiple de sortie, horizon, dividende).
  valFairPrice() {
    return targetEntryPrice(
      this.valLatestMetric(),
      Number(this.valGrowth) || 0,
      Number(this.valMultiple),
      VALUATION_HORIZON_YEARS,
      Number(this.valTarget),
      this.valDividendYield(),
      this.valNetDebtPerShare(),
    );
  },

  valEstimatedReturn() {
    return estimatedReturn(
      this.valLatestMetric(),
      this.valPrice(),
      Number(this.valGrowth) || 0,
      Number(this.valMultiple),
      VALUATION_HORIZON_YEARS,
      this.valDividendYield(),
      this.valNetDebtPerShare(),
    );
  },

  valSafetyMargin() {
    return safetyMargin(this.valFairPrice(), this.valPrice());
  },

  // Le rendement estimé bat-il la cible ? Pilote la couleur du KPI.
  valBeatsTarget() {
    const r = this.valEstimatedReturn();
    const t = Number(this.valTarget);
    if (r == null || !t) return null;
    return r >= t;
  },

  // --- Matrice -------------------------------------------------------------

  // Cache de la matrice : la grille (225 évaluations) est recalculée à chaque
  // frappe dans les champs. On la mémorise sur la clé de ses entrées pour ne pas
  // reconstruire 15×15 cellules à chaque appel du template (qui l'appelle ~230×
  // par rendu, une fois par cellule via `valCellClass`).
  _valMatrixCache: null,
  _valMatrixKey: null,

  valMatrix() {
    const def = this.valMetricDef();
    if (!def) return null;
    const key = [
      def.key, def.multiple_step, this.valLatestMetric(), this.valPrice(), this.valGrowth,
      this.valMultiple, this.valTarget, this.valDividendYield(), this.valNetDebtPerShare(),
    ].join("|");
    if (this._valMatrixKey === key && this._valMatrixCache) return this._valMatrixCache;
    const grid = matrixGrid(
      Number(this.valGrowth) || 0,
      Number(this.valMultiple),
      VALUATION_MATRIX.rows,
      VALUATION_MATRIX.cols,
      VALUATION_MATRIX.growth_step,
      // Pas des colonnes PROPRE à la base (P/CA, P/B exigent un pas fin) ;
      // repli sur le pas global si la métrique ne le porte pas.
      def.multiple_step ?? VALUATION_MATRIX.multiple_step,
    );
    const latest = this.valLatestMetric();
    const price = this.valPrice();
    const div = this.valDividendYield();
    const bridge = this.valNetDebtPerShare();
    const rows = grid.growths.map((g) => ({
      growth: g,
      cells: grid.multiples.map((m) => {
        const value = estimatedReturn(latest, price, g, m, VALUATION_HORIZON_YEARS, div, bridge);
        return { multiple: m, value, bucket: colorBucket(value, Number(this.valTarget), VALUATION_COLOR_RATIOS) };
      }),
    }));
    // Valeurs les plus proches des paramètres courants = cellule active.
    const activeGrowth = this._closest(grid.growths, Number(this.valGrowth));
    const activeMultiple = this._closest(grid.multiples, Number(this.valMultiple));
    const matrix = { multiples: grid.multiples, rows, activeGrowth, activeMultiple };
    this._valMatrixKey = key;
    this._valMatrixCache = matrix;
    return matrix;
  },

  _closest(list, value) {
    let best = list[0];
    for (const v of list) {
      if (Math.abs(v - value) < Math.abs(best - value)) best = v;
    }
    return best;
  },

  // --- Persistance ---------------------------------------------------------

  // Payload envoyé au serveur : les paramètres + le prix juste calculé (le
  // serveur le recalcule pour la synthèse « Résumé »).
  valPayload() {
    return {
      metric: this.valMetric,
      period: Number(this.valPeriod),
      growth: Number(this.valGrowth) || 0,
      multiple: Number(this.valMultiple) || 0,
      target_yield: Number(this.valTarget) || 0,
      dividend_yield: this.valDividendYield(),
      include_dividends: !!this.valIncludeDividends,
      fair_price: this.valFairPrice(),
      net_debt_per_share: this.valNetDebtPerShare(),
    };
  },

  // Le prix juste (prix d'entrée atteignant la cible) n'est calculable que si la
  // métrique par action, le multiple final et la cible le permettent : sinon
  // l'enregistrement (qui fixe le prix juste) est impossible -> bouton désactivé
  // + message explicite.
  canSaveValuation() {
    return this.valFairPrice() != null;
  },

  async saveValuation() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (!this.canSaveValuation()) {
      this.valError = "Prix juste non calculable (multiple final, croissance ou donnée manquante) — ajuste les paramètres.";
      return;
    }
    this.valSaving = true;
    this.valError = "";
    try {
      const { ok, data } = await api.saveValuation(ticker, this.valPayload());
      if (!ok) { this.valError = data?.detail || "Enregistrement impossible"; return; }
      // Le Résumé doit refléter le nouveau prix juste : on recharge la fiche.
      await this.load();
    } catch {
      this.valError = "Enregistrement impossible (réseau).";
    } finally {
      this.valSaving = false;
    }
  },

  async resetValuation() {
    const ticker = this.data?.identity?.ticker;
    if (!ticker) return;
    if (!window.confirm("Effacer le prix juste enregistré ? Le Résumé reviendra à la droite de régression.")) {
      return;
    }
    this.valSaving = true;
    this.valError = "";
    try {
      await api.clearValuation(ticker);
      this.initValuation();
      await this.load();
    } catch {
      this.valError = "Réinitialisation impossible (réseau).";
    } finally {
      this.valSaving = false;
    }
  },

  // Export CSV : paramètres + séries par action + matrice de rendement.
  // Même chemin que l'export de la section Résumé (`exportcsv.js`) : séparateur
  // « , », cellule échappée (`_csvCell`, décimales à point) et téléchargement via
  // `_downloadCsv` — un seul format de fichier dans toute l'application.
  downloadValuation() {
    const def = this.valMetricDef();
    if (!def) return;
    const cell = this._csvCell;
    const lines = [];
    lines.push("# Obole — Calculatrice de prix juste");
    lines.push(`# ticker: ${this.data?.identity?.ticker || ""}`);
    lines.push("parametre,valeur");
    lines.push(`donnees_utilisees,${cell(def.label)}`);
    lines.push(`periode_historique_ans,${cell(Number(this.valPeriod))}`);
    lines.push(`croissance_estimee_pct_an,${cell(Number(this.valGrowth))}`);
    lines.push(`multiple_final_estime,${cell(Number(this.valMultiple))}`);
    lines.push(`rendement_cible_pct_an,${cell(Number(this.valTarget))}`);
    lines.push(`inclure_dividendes,${this.valIncludeDividends ? "oui" : "non"}`);
    lines.push(`prix_juste,${cell(this.valFairPrice())}`);
    lines.push(`valeur_mediane,${cell(this.valMedianValue())}`);
    lines.push(`rendement_estime_pct_an,${cell(this.valEstimatedReturn())}`);
    lines.push(`marge_de_securite_pct,${cell(this.valSafetyMargin())}`);
    lines.push("");
    lines.push("annee,metrique_par_action");
    for (const [year, value] of Object.entries(def.per_share || {})) {
      lines.push(`${year},${cell(value)}`);
    }
    const matrix = this.valMatrix();
    if (matrix) {
      lines.push("");
      lines.push(["croissance\\multiple"].concat(matrix.multiples.map(cell)).join(","));
      for (const row of matrix.rows) {
        lines.push([cell(row.growth)].concat(row.cells.map((c) => cell(c.value))).join(","));
      }
    }
    this._downloadCsv(lines.join("\n"), "prix-juste");
  },

  // --- Rendu : Graphique (partie 1) ---------------------------------------

  drawValuationChart(retry = 0) {
    const calc = this.valuationCalc();
    const chart = this.data?.chart;
    if (!calc || !chart) return;
    const el = "val-chart";
    const node = document.getElementById(el);
    if (!node) return;
    // Plotly dimensionne sur la largeur du conteneur : si la section est encore
    // masquée (`x-show`, largeur 0), il retombe sur sa largeur par défaut
    // (700px) et le graphe n'occupe plus qu'une partie de la carte. On diffère
    // donc le tracé tant que le conteneur n'a pas une largeur exploitable.
    if (node.clientWidth === 0 && retry < 20) {
      const raf = typeof requestAnimationFrame === "function"
        ? requestAnimationFrame : (fn) => setTimeout(fn, 16);
      raf(() => this.drawValuationChart(retry + 1));
      return;
    }
    const dates = chart.dates;
    const def = this.valMetricDef();
    // Cours brut (bleu vif) + valorisation théorique (métrique × multiple médian,
    // or) + dividende/action (brun) + projection pointillée.
    const priceSeries = chart.price_raw;
    const metric = def ? chart[this._seriesKeyFor(def)] : null;
    const median = this.valMedian();
    // La ligne « valorisation théorique = métrique × multiple » n'a de sens que
    // pour un multiple de capitalisation ; EV/EBITDA est un multiple d'entreprise
    // (numérateur ≠ cours) -> on ne la trace pas pour lui.
    const isEnterprise = !!def && def.enterprise;
    const valoSeries = metric && median != null && !isEnterprise
      ? metric.map((v) => (v == null ? null : v * median)) : [];
    const traces = [
      { x: dates, y: priceSeries, name: "Prix", mode: "lines", line: { color: C.accent, width: 1.6 } },
    ];
    if (valoSeries.length) {
      // Courbe de valorisation : OR (C.ma1, repris de l'exemple Baggr) et LISSÉE
      // (spline à tension douce) — la métrique par action évolue par paliers
      // annuels ; on trace ses COINS pour que le lissage arrondisse les
      // transitions sans faire onduler la courbe. Marqueurs annuels discrets +
      // FOND doré très pâle sous la courbe : on lit d'un coup si le cours (bleu)
      // est sous (sous-évalué) ou au-dessus de la valorisation.
      const corners = this._stepCorners(dates, valoSeries) || { x: dates, y: valoSeries };
      traces.push({ x: corners.x, y: corners.y, name: `Valorisation (${def.label} × ${this.fmt(median)})`,
        mode: "lines+markers", line: { color: C.ma1, width: 2.4, shape: "spline", smoothing: 0.3 },
        marker: { size: 5, color: C.ma1 }, fill: "tozeroy", fillcolor: VALO_FILL });
    }
    const divPs = this._dividendPsSeries(dates, calc.dividend_per_share);
    if (divPs) {
      traces.push({ x: dates, y: divPs, name: "Dividende/Action",
        mode: "lines+markers", line: { color: C.brown, width: 1.8 }, marker: { size: 5 } });
    }
    const fair = this.valFairPrice();
    const shapes = [];
    if (fair != null) {
      shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, y0: fair, y1: fair,
        line: { color: C.accent, width: 1, dash: "dot" } });
    }
    // Projection pointillée : du cours actuel vers le prix projeté à l'horizon.
    const price = this.valPrice();
    const projected = projectedValue(
      this.valLatestMetric(), Number(this.valGrowth) || 0, Number(this.valMultiple),
      VALUATION_HORIZON_YEARS, this.valNetDebtPerShare(),
    );
    const annotations = [];
    const lastDate = dates[dates.length - 1];
    const projDate = this._addYears(lastDate, VALUATION_HORIZON_YEARS);
    if (projected != null && price != null) {
      // Prolongement doré (Baggr) : la projection vers l'horizon devient une
      // ligne POINTILLÉE DORÉE, et le fond doré se poursuit dessous jusqu'à la
      // date de projection — une seule ligne rejoint la cible projetée.
      traces.push({
        x: [lastDate, projDate], y: [price, projected],
        name: "Projection", mode: "lines+markers",
        line: { color: C.ma1, width: 2, dash: "dot" },
        marker: { size: 7, color: C.ma1 },
        fill: "tozeroy", fillcolor: VALO_FILL,
      });
    }
    // Badges : prix juste (ligne pointillée) et prix projeté (fin de projection).
    if (fair != null) {
      annotations.push({ x: 0.99, y: fair, xref: "paper", yref: "y", text: this.fmt(fair),
        showarrow: false, xanchor: "right", yanchor: "bottom",
        bgcolor: C.accent, font: { color: "#fff", size: 11 }, borderpad: 3 });
    }
    if (projected != null) {
      annotations.push({ x: projDate, y: projected, text: this.fmt(projected),
        showarrow: false, xanchor: "left", yanchor: "middle",
        bgcolor: C.accent, font: { color: "#fff", size: 11 }, borderpad: 3 });
    }
    Plotly.react(el, traces, {
      margin: { l: 52, r: 48, t: 16, b: 34 },
      height: CHART_HEIGHTS.valuation_hero || CHART_HEIGHTS.hero,
      paper_bgcolor: "transparent", plot_bgcolor: "transparent",
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      xaxis: { gridcolor: C.grid, type: "date", nticks: 8 },
      yaxis: { gridcolor: C.grid },
      showlegend: true, legend: { orientation: "h", y: -0.18, font: { size: 10 } },
      shapes, annotations,
    }, { displayModeBar: false, responsive: true }).then(() => {
      // Filet : si Plotly a tracé à une largeur différente du conteneur (layout
      // figé pendant un masquage), on force une remise à l'échelle.
      const gd = document.getElementById(el);
      if (gd && gd._fullLayout && Math.abs(gd._fullLayout.width - gd.clientWidth) > 2) {
        Plotly.Plots.resize(gd);
      }
    });
  },

  // Ajoute `years` années à une date ISO (fin de l'axe de projection).
  _addYears(iso, years) {
    const d = new Date(iso);
    d.setFullYear(d.getFullYear() + years);
    return d.toISOString().slice(0, 10);
  },

  // Légende de la partie 1 : CAGR (croissance annualisée) des trois séries —
  // EPS/action, dividende/action et prix — affichés sous le graphe.
  valuationCagrLegend() {
    const chart = this.data?.chart;
    const def = this.valMetricDef();
    if (!chart || !def) return [];
    const out = [];
    const metric = chart[this._seriesKeyFor(def)];
    const metricCagr = cagrFromSeries(chart.dates, metric);
    // Pour un multiple d'entreprise (EV/EBITDA), la série suivie est le MULTIPLE
    // (pas une métrique par action) : on l'étiquette comme tel pour ne pas laisser
    // croire à un CAGR d'EBITDA/action.
    if (metricCagr != null) out.push({ label: def.enterprise ? def.multiple : def.label, cagr: metricCagr });
    const divCagr = cagrFromYearMap(this.valuationCalc()?.dividend_per_share);
    if (divCagr != null) out.push({ label: "Dividende/Action", cagr: divCagr });
    const priceCagr = cagrFromSeries(chart.dates, chart.price_raw);
    if (priceCagr != null) out.push({ label: "Prix", cagr: priceCagr });
    return out;
  },

  // Série du dividende par action, alignée sur les dates du cours (report par
  // palier) : la ligne suit les exercices connus.
  _dividendPsSeries(dates, perShare) {
    const byYear = perShare || {};
    const years = Object.keys(byYear).map(Number).sort((a, b) => a - b);
    if (!years.length) return null;
    return dates.map((iso) => {
      const y = new Date(iso).getFullYear();
      let val = null;
      for (const yy of years) { if (yy <= y) val = byYear[yy]; }
      return val;
    });
  },

  _seriesKeyFor(def) {
    return { eps: "eps_ps", fcf: "fcf_ps", book: "book_ps", sales: "sales_ps", ebitda: "ev_ebitda" }[def.key];
  },

  // --- Rendu : Matrice (partie 1) -----------------------------------------

  valBucketClass(bucket) {
    return bucket == null ? "" : "vb-" + bucket;
  },

  // Nombre à UNE décimale (matrice) : format local fr-FR, séparateur décimal
  // virgule. `fmt()` global garde ses 2 décimales ; la matrice resserre ses
  // colonnes pour tenir en pleine largeur (15 colonnes visibles d'un coup).
  valNum1(v) {
    return v == null || isNaN(v) ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 1 });
  },

  // Classe d'une cellule de la matrice : bucket de couleur + marqueur de cellule
  // active (croissance × multiple les plus proches des paramètres courants).
  valCellClass(growth, cell) {
    const m = this.valMatrix();
    const classes = [this.valBucketClass(cell.bucket)];
    if (m && m.activeGrowth === growth && m.activeMultiple === cell.multiple) {
      classes.push("val-active-cell");
    }
    return classes.filter(Boolean).join(" ");
  },

  // --- Rendu : courbes continues (partie 2) --------------------------------

  valuationGroups() {
    const chart = this.data?.chart;
    if (!chart) return [];
    const groups = [];
    for (const grp of VALUATION_GROUPS) {
      const cards = grp.cards
        .filter((c) => chart[c.series])
        .map((c) => ({ ...c, section: "valorisation", pills: grp.pills || "stats", id: slug(c.title) }));
      if (cards.length) groups.push({ title: grp.title, pills: grp.pills || "stats", cards });
    }
    return groups;
  },

  drawValuationLines() {
    this.valuationGroups().forEach((grp) => {
      grp.cards.forEach((c) => {
        const el = "mc-" + c.id;
        if (!document.getElementById(el)) return;
        try { this.drawValueLine(el, c); } catch (e) { console.error("val line error:", c.id, e); }
      });
    });
  },

  // Courbe continue (patron Dividend Yield) : série serveur alignée sur les dates,
  // fenêtre par défaut + pastilles High/Médiane/Low recalculées sur la fenêtre.
  // `range` = [i0, i1] (modale zoom) ; sinon fenêtre par défaut de la carte.
  drawValueLine(el, card, range = null) {
    const chart = this.data.chart;
    const series = chart[card.series];
    if (!series) return;
    // Fenêtre demandée (plage curseur en modale, sinon fenêtre par défaut), puis
    // BORNAGE sur la disponibilité réelle de la série : on ne trace que du premier
    // au dernier point non nul. Sans ce bornage, une série de ~5 ans s'étirait sur
    // la fenêtre calendaire par défaut (10 ans), laissant un grand vide à gauche.
    const [reqStart, reqEnd] = range || this.defaultDateRange(chart.dates);
    const [availStart, availEnd] = this._seriesAvailableRange(series);
    const i0 = Math.max(reqStart, availStart);
    const i1 = Math.min(reqEnd, availEnd);
    if (i1 < i0) return;
    const xs = chart.dates.slice(i0, i1 + 1);
    const ys = series.slice(i0, i1 + 1);
    const stats = this._yieldStats(ys);
    // CAGR de la fenêtre affichée : alimente la pastille du groupe « Croissance »
    // (c'est la valeur qui correspond à la saisie « Croissance estimée »).
    stats.cagr = cagrFromSeries(xs, ys);
    const suffix = card.unit === "mult" ? "×" : "";
    const shapes = [];
    if (stats.median != null) shapes.push(this._hLine(stats.median, C.neutral));
    // Courbes de CROISSANCE (groupe « Croissance », pastille CAGR) : série en
    // paliers annuels -> on trace ses COINS (un point par exercice) en spline
    // pour arrondir les transitions (rendu Baggr), couleur bleue inchangée. Les
    // multiples (série quotidienne) restent nets et denses.
    const isStep = card.pills === "cagr";
    const corners = isStep ? this._stepCorners(xs, ys) : null;
    const lineStyle = { color: C.accent, width: 2 };
    if (isStep) { lineStyle.shape = "spline"; lineStyle.smoothing = 0.3; }
    // Marqueurs annuels discrets (cercles blancs bordés de la couleur de ligne) :
    // on voit où tombent les exercices, sans alourdir la courbe lissée.
    const marker = { size: 6, color: "#fff", line: { color: C.accent, width: 1.5 } };
    const trace = corners
      ? { x: corners.x, y: corners.y, mode: "lines+markers", line: lineStyle, marker,
          fill: "tozeroy", fillcolor: "rgba(37,99,235,.06)", name: card.title }
      : { x: xs, y: ys, mode: "lines", line: lineStyle,
          fill: "tozeroy", fillcolor: "rgba(37,99,235,.06)", name: card.title };
    Plotly.react(el, [trace], this.miniLayout({
      xaxis: { gridcolor: C.grid, type: "date", nticks: 6 },
      shapes, height: range ? CHART_HEIGHTS.detail : CHART_HEIGHTS.mini,
      yaxis: { gridcolor: C.grid, ticksuffix: suffix },
    }), { displayModeBar: false, responsive: true });
    // Le cache alimente les pastilles de la CARTE : on ne l'écrase pas en modale.
    if (!range) this._valStatsCache[card.id] = stats;
  },

  // Réduit une série en ESCALIER (dense, une valeur par jour) à ses COINS : un
  // point par changement de valeur (exercice comptable), plus le dernier point
  // pour fermer le tracé. Plotly « spline » arrondit alors les transitions
  // (rendu Baggr) — un spline sur la série dense ne lisse rien, les sauts étant
  // entre points adjacents.
  _stepCorners(xs, ys) {
    const ox = [];
    const oy = [];
    let prev = null;
    for (let i = 0; i < ys.length; i++) {
      const v = ys[i];
      if (v == null || v !== v) continue;
      if (prev === null || v !== prev) { ox.push(xs[i]); oy.push(v); prev = v; }
    }
    if (!ox.length) return null;
    const lastX = xs[xs.length - 1];
    const lastY = ys[ys.length - 1];
    if (lastY != null && lastX !== ox[ox.length - 1]) { ox.push(lastX); oy.push(lastY); }
    return { x: ox, y: oy };
  },

  // Bornes [premier, dernier] index de la série réellement disponible (non nulle).
  // Sert à ne pas étirer une courbe courte sur toute la fenêtre calendaire.
  _seriesAvailableRange(series) {
    let start = -1;
    let end = -1;
    for (let i = 0; i < series.length; i++) {
      const v = series[i];
      if (v != null && v === v) {
        if (start < 0) start = i;
        end = i;
      }
    }
    if (start < 0) return [0, series.length - 1];
    return [start, end];
  },

  _valStatsCache: {},

  // CAGR de la fenêtre VISIBLE pour la carte ouverte en modale (plein écran).
  // Réservé aux courbes « par action » du groupe Croissance (`pills === "cagr"`)
  // — celles qui alimentent la valorisation ; `null` sinon (un multiple n'a pas
  // de sens en croissance annualisée). Le bornage sur la disponibilité réelle de
  // la série est le même que `drawValueLine` : pas d'étirement d'une courbe courte.
  detailCagr() {
    const card = this.detailCard;
    if (!card || card.pills !== "cagr") return null;
    const chart = this.data?.chart;
    const series = chart && chart[card.series];
    if (!series) return null;
    const [reqStart, reqEnd] = this.visibleRange();
    const [availStart, availEnd] = this._seriesAvailableRange(series);
    const i0 = Math.max(reqStart, availStart);
    const i1 = Math.min(reqEnd, availEnd);
    if (i1 <= i0) return null;
    return cagrFromSeries(chart.dates.slice(i0, i1 + 1), series.slice(i0, i1 + 1));
  },

  valuationPills(card) {
    const stats = this._valStatsCache[card.id];
    if (!stats) return [];
    // Groupe « Croissance » : la pastille est le CAGR de la fenêtre affichée —
    // c'est la croissance par an de la métrique par action, la valeur qui alimente
    // la saisie « Croissance estimée ». (Les groupes de multiples gardent High/
    // Médiane/Low.) Croissance ≥ 0 = bien (bleu), < 0 = mal (rouge).
    if (card.pills === "cagr") {
      if (stats.cagr == null) return [];
      return [{ label: "Croissance", display: this.fmt(stats.cagr) + " %/an", good: stats.cagr >= 0 }];
    }
    if (stats.median == null) return [];
    const suffix = card.unit === "mult" ? "×" : "";
    const fmt = (v) => this.fmt(v) + suffix;
    return [
      { label: "High", display: fmt(stats.high), good: null },
      { label: "Médiane", display: fmt(stats.median), good: null },
      { label: "Low", display: fmt(stats.low), good: null },
    ];
  },
};
