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
  VALUATION_CHART,
  CHART_HEIGHTS,
  MARKOWITZ,
  REG_YEARS_DEFAULT,
  REG_YEARS_FINANCIAL,
  olsLog,
} from "./thresholds.js";
import { api } from "./api.js";
import { slug } from "./util.js";

// Arrondi d'affichage (2 décimales) : évite les flottants bruyants dans les champs.
function round2(v) {
  return v == null || isNaN(v) ? null : Math.round(Number(v) * 100) / 100;
}

// --- Graphe « Prix et valorisation » (#34) ----------------------------------
//
// Helpers PURS (aucun accès à `this`, aucune lecture Plotly) : la carte à
// couches est décrite par des données calculées ici, puis rendue par
// `drawValuationChart`. Les tests Vitest les verrouillent un par un.

// Statut de l'en-tête : cours vs valorisation courante. La valorisation n'est
// lue que si la métrique courante est strictement positive (`latestOk`) ; un
// multiple d'entreprise n'en produit aucune, une métrique absente non plus.
// Au-delà de `gapRatioLimit` points d'écart, le statut s'écrit en multiple
// (« cours ×N ») plutôt qu'en pourcentage ; un écart nul est neutre.
export function valuationStatus({
  price, valoNow, latest, latestOk, isEnterprise, label, gapRatioLimit,
}) {
  const base = { valoNow: null, gapPct: null, ratio: null, big: false, good: null, reason: null, label };
  if (isEnterprise) return { ...base, reason: "enterprise" };
  if (latest == null) return { ...base, reason: "absent" };
  if (!latestOk) return { ...base, reason: "negative" };
  if (valoNow == null || !(valoNow > 0) || price == null || !(price > 0)) {
    return { ...base, reason: "none" };
  }
  const ratio = price / valoNow;
  const gapPct = (ratio - 1) * 100;
  const limit = Number(gapRatioLimit);
  return {
    valoNow,
    gapPct,
    ratio,
    big: Number.isFinite(limit) && Math.abs(gapPct) > limit,
    good: gapPct === 0 ? null : gapPct < 0,
    reason: null,
    label,
  };
}

// Série de valorisation = métrique/action × multiple de la COURBE (médiane de
// la période), tracée en escalier (`shape: "hv"`). Seuls les exercices
// strictement positifs portent un point ; quand la métrique courante est ≤ 0,
// la courbe s'arrête au dernier exercice positif puis tient un palier plat
// jusqu'au premier exercice non positif (la rupture se lit sans point aberrant).
export function valuationSeries(dates, series, multiple, latestOk) {
  const empty = { x: [], y: [] };
  if (!dates || !series || multiple == null || !(multiple > 0)) return empty;
  const n = Math.min(dates.length, series.length);
  const x = [];
  const y = [];
  let prev = null;
  let lastPositive = -1;
  for (let i = 0; i < n; i++) {
    const v = series[i];
    if (v == null || !(v > 0)) continue;
    lastPositive = i;
    const value = v * multiple;
    if (prev === null || Math.abs(value - prev) > 1e-9 || i === n - 1) {
      x.push(dates[i]);
      y.push(value);
      prev = value;
    }
  }
  if (!x.length) return empty;
  if (!latestOk && lastPositive >= 0) {
    const cut = dates[lastPositive];
    while (x.length && x[x.length - 1] > cut) {
      x.pop();
      y.pop();
    }
    for (let i = lastPositive + 1; i < n; i++) {
      if (series[i] != null && series[i] <= 0) {
        x.push(dates[i]);
        y.push(y[y.length - 1]);
        break;
      }
    }
  }
  return { x, y };
}

// Scénarios à l'horizon : central = hypothèses saisies ; éventail = croissance
// et multiple décalés de `growthSpan` / `multipleSpan`. Les formules sont
// celles de la calculatrice (`projectedValue`), jamais réécrites ici.
export function valuationFan({
  latest, growth, multiple, horizon, netDebt = null, growthSpan, multipleSpan,
}) {
  return {
    central: projectedValue(latest, growth, multiple, horizon, netDebt),
    pessimistic: projectedValue(latest, growth - growthSpan, multiple - multipleSpan, horizon, netDebt),
    optimistic: projectedValue(latest, growth + growthSpan, multiple + multipleSpan, horizon, netDebt),
  };
}

// Échelle verticale : de 0 à 1,12 × le plus haut repère visible (cours,
// valorisation, prix juste, scénario central), plafonnée à `yCap` × le plus
// haut cours visible. Un repère hors cadre est signalé par une pastille
// collée en haut (« ↑ »), jamais tracé hors échelle.
export function valuationScale({ prices, valuationY, fair, central, yCap }) {
  const visible = (prices || []).filter((v) => v != null && Number.isFinite(v));
  if (!visible.length) return { yMax: null, highest: null };
  const highest = visible.reduce((a, b) => (b > a ? b : a), visible[0]);
  const candidates = [...visible];
  for (const v of valuationY || []) if (v != null && Number.isFinite(v)) candidates.push(v);
  if (fair != null && Number.isFinite(fair)) candidates.push(fair);
  if (central != null && Number.isFinite(central)) candidates.push(central);
  const peak = Math.max(0, ...candidates);
  let yMax = peak * 1.12;
  const cap = highest * (Number(yCap) > 0 ? Number(yCap) : 1);
  if (yMax > cap) yMax = cap;
  return { yMax, highest };
}

// Couloir sous/sur-évalué : sur la seule plage où la valorisation existe, les
// bornes basse et haute de l'écart au cours. Le rendu remplit entre la
// valorisation et la borne basse (bleu) puis entre la valorisation et la borne
// haute (rouge) — aucune couleur de jugement n'est choisie ici.
export function valuationCorridor({ dates, price, valo, latestOk }) {
  const vx = valo?.x || [];
  const vy = valo?.y || [];
  if (!vx.length || !dates || !price) return null;
  const i0 = dates.findIndex((d) => d >= vx[0]);
  if (i0 < 0) return null;
  let i1 = dates.length;
  if (!latestOk) {
    const stop = dates.findIndex((d) => d > vx[vx.length - 1]);
    i1 = stop < 0 ? dates.length : stop;
  }
  const x = dates.slice(i0, i1);
  if (!x.length) return null;
  const p = price.slice(i0, i1);
  const valoAt = [];
  let k = 0;
  for (let i = 0; i < x.length; i++) {
    while (k + 1 < vx.length && vx[k + 1] <= x[i]) k++;
    valoAt.push(vx[k] <= x[i] ? vy[k] : null);
  }
  return {
    x,
    valo: valoAt,
    lower: p.map((v, i) => (v == null || valoAt[i] == null ? null : Math.min(v, valoAt[i]))),
    upper: p.map((v, i) => (v == null || valoAt[i] == null ? null : Math.max(v, valoAt[i]))),
  };
}

// Espace vertical des pastilles d'une même colonne : au moins `minGapPx` entre
// deux, en poussant vers le bas celles qui se chevauchent. `yMax` et
// `heightPx` donnent l'échelle pixels ↔ unités de l'axe (y = 0 en bas).
export function spreadPills(items, { yMax, heightPx, minGapPx = 16 }) {
  if (!items || !items.length) return [];
  const span = Number(yMax) > 0 ? Number(yMax) : 1;
  const height = Number(heightPx) > 0 ? Number(heightPx) : 1;
  const toPx = (v) => (Number(v) / span) * height;
  const toY = (p) => (p / height) * span;
  let prev = null;
  return items
    .slice()
    .sort((a, b) => b.y - a.y)
    .map((item) => {
      let px = toPx(item.y);
      if (prev != null && px > prev - minGapPx) px = prev - minGapPx;
      px = Math.max(0, Math.min(height, px));
      prev = px;
      return { ...item, y: toY(px) };
    });
}

// Pastilles de la colonne de droite : scénario central (ambre) et, si la couche
// Scénarios est allumée et que l'éventail tient dans le cadre, ses deux bornes
// (grises). Les deux bornes vont ensemble : sans pessimiste (multiple ≤ 0) il
// n'y a pas d'éventail, donc aucune pastille orpheline. Une valeur au-delà de
// `yMax` est collée sous le plafond ; son texte porte le préfixe « ↑ ».
export function valuationPillItems({
  central, optimistic, pessimistic, showFan, fanFits, yMax, heightPx, minGapPx = 16,
}) {
  const raw = [];
  const clip = (v) => (yMax != null ? Math.min(v, yMax * 0.97) : v);
  if (central != null) raw.push({ key: "central", value: central, y: clip(central) });
  if (showFan && fanFits && pessimistic != null) {
    if (optimistic != null) raw.push({ key: "optimistic", value: optimistic, y: clip(optimistic) });
    raw.push({ key: "pessimistic", value: pessimistic, y: clip(pessimistic) });
  }
  return spreadPills(raw, { yMax, heightPx, minGapPx });
}

// Bâtons du dividende/action : une barre par année civile de la fenêtre. La
// fenêtre est celle du graphe (`startDate`) : une barre datée du 1er juillet
// antérieure au début de l'axe serait invisible, donc elle est écartée. La
// année civile EN COURS (dividende partiel) est un bâton CREUX — fond blanc,
// bord vert — pour ne pas la comparer aux exercices complets.
export function dividendBars(perShare, { years, currentYear, startDate = null }) {
  const empty = { has: false, x: [], y: [], current: [] };
  const cutoff = startDate || `${currentYear - years}-01-01`;
  const entries = Object.entries(perShare || {})
    .map(([year, value]) => [Number(year), Number(value)])
    .filter(([year, value]) => (
      Number.isFinite(year) &&
      Number.isFinite(value) &&
      value > 0 &&
      year <= currentYear &&
      `${year}-07-01` >= cutoff
    ))
    .sort((a, b) => a[0] - b[0]);
  if (!entries.length) return empty;
  return {
    has: true,
    x: entries.map(([year]) => `${year}-07-01`),
    y: entries.map(([, value]) => value),
    current: entries.map(([year]) => year === currentYear),
  };
}

// Pied de carte : trois CAGR TOUJOURS présents — cours sur la fenêtre, métrique
// depuis son premier exercice, dividende sur ses années COMPLÈTES (l'année en
// cours est exclue). `cagr == null` = non calculable, affiché « — » par
// l'appelant : une ligne absente cacherait une donnée manquante.
export function valuationCagrRows({
  dates, priceSeries, metricSeries, dividendPerShare, fromIndex, windowYears,
  currentYear, isEnterprise, metricLabel,
}) {
  if (!dates || !dates.length) return [];
  const i0 = Math.max(0, Math.min(Number(fromIndex) || 0, dates.length - 1));
  const rows = [{
    key: "price",
    label: "Cours",
    cagr: cagrFromSeries(dates.slice(i0), (priceSeries || []).slice(i0)),
    span: `sur ${windowYears} ans`,
  }];
  if (isEnterprise) {
    rows.push({ key: "metric", label: metricLabel, cagr: null, span: "" });
  } else {
    let first = null;
    for (let i = 0; i < (metricSeries || []).length; i++) {
      if (metricSeries[i] != null && metricSeries[i] > 0) { first = dates[i]; break; }
    }
    rows.push({
      key: "metric",
      label: metricLabel,
      cagr: cagrFromSeries(dates, metricSeries),
      span: first ? `depuis ${String(first).slice(0, 4)}` : "",
    });
  }
  const completeYears = Object.keys(dividendPerShare || {})
    .map(Number)
    .filter((year) => (
      Number.isFinite(year) &&
      year < currentYear &&
      year >= currentYear - windowYears &&
      dividendPerShare[year] != null
    ))
    .sort((a, b) => a - b);
  const byYear = {};
  for (const year of completeYears) byYear[year] = dividendPerShare[year];
  rows.push({
    key: "dividend",
    label: "Dividende",
    cagr: completeYears.length ? cagrFromYearMap(byYear) : null,
    span: completeYears.length > 1
      ? `sur ${completeYears[completeYears.length - 1] - completeYears[0]} ans`
      : "",
  });
  return rows;
}

// Notes factuelles sous le graphe (texte discret) : métrique négative ou
// absente, multiple d'entreprise, projection hors cadre, étage dividende absent.
export function valuationNotes({
  isEnterprise, latest, latestOk, hasValo, central, yMax, hasDividends, years,
}) {
  const notes = [];
  if (!latestOk && hasValo) notes.push({ key: latest == null ? "absent" : "negative" });
  if (!hasValo) notes.push({ key: isEnterprise ? "enterprise" : "empty" });
  if (central != null && yMax != null && central > yMax) {
    notes.push({ key: "out-of-frame", value: central });
  }
  if (!hasDividends) notes.push({ key: "no-dividend", years });
  return notes;
}

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
  // Couches du graphe « Prix et valorisation » (#34) : état du composant,
  // remis au défaut à chaque rechargement (pas de persistance). Scénarios
  // éteints par défaut ; couloir et dividende allumés.
  valLayers: { couloir: true, scenarios: false, dividendes: true },
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

  // Modèle du graphe : tout ce que la carte affiche (statut, pastilles, pied,
  // notes, tracés) vient d'ici — aucune formule n'est réécrite à l'écran.
  // Mémoïsé sur ses entrées : le template l'appelle plusieurs fois par rendu et
  // un changement de couche ne doit PAS le recalculer (seul le dessin change).
  _valChartCache: null,
  _valChartKey: null,

  valChartModel() {
    const calc = this.valuationCalc();
    const chart = this.data?.chart;
    const def = this.valMetricDef();
    if (!calc || !chart || !def || !Array.isArray(chart.dates) || !chart.dates.length) {
      return null;
    }
    const key = [
      this.data?.identity?.ticker, this.data?.identity?.last_price,
      def.key, def.latest, this.valPeriod, this.valMedian(), this.valGrowth,
      this.valMultiple, this.valTarget, this.valIncludeDividends,
      chart.dates.length, chart.dates[chart.dates.length - 1],
      JSON.stringify(calc.dividend_per_share || {}),
    ].join("|");
    if (this._valChartKey === key && this._valChartCache) return this._valChartCache;

    const cfg = VALUATION_CHART || {};
    const dates = chart.dates;
    const priceSeries = chart.price_raw || [];
    const price = this.valPrice();
    const median = this.valMedian();
    const isEnterprise = !!def.enterprise;
    const metric = chart[this._seriesKeyFor(def)] || null;
    // Les défauts viennent de `thresholds.js` (lui-même nourri par config.py) :
    // aucun nombre de repli n'est recopié ici.
    const windowYears = Number(cfg.years);
    const horizonYears = Number(VALUATION_HORIZON_YEARS);
    const lastDate = dates[dates.length - 1];
    const horizonDate = this._addYears(lastDate, horizonYears);
    const startDate = this._addYears(lastDate, -windowYears);
    let fromIndex = dates.findIndex((d) => d >= startDate);
    if (fromIndex < 0) fromIndex = 0;
    // Une métrique courante ≤ 0 (ou absente) interdit valorisation ET prix juste.
    const latestOk = def.latest != null && def.latest > 0;
    const valo = isEnterprise
      ? { x: [], y: [] }
      : valuationSeries(dates, metric, median, latestOk);
    const hasValo = valo.y.length > 0;
    const valoNow = hasValo && latestOk ? valo.y[valo.y.length - 1] : null;
    const fair = this.valFairPrice();
    const growth = Number(this.valGrowth) || 0;
    const multiple = Number(this.valMultiple);
    const fan = valuationFan({
      latest: def.latest,
      growth,
      multiple,
      horizon: horizonYears,
      netDebt: this.valNetDebtPerShare(),
      growthSpan: cfg.fan_growth_span,
      multipleSpan: cfg.fan_multiple_span,
    });
    // L'échelle ne regarde que la fenêtre affichée : une valorisation d'il y a
    // 15 ans, invisible, ne doit pas écraser l'axe.
    let valoFrom = hasValo ? valo.x.findIndex((d) => d >= dates[fromIndex]) : -1;
    if (valoFrom < 0) valoFrom = 0;
    const scale = valuationScale({
      prices: priceSeries.slice(fromIndex),
      valuationY: hasValo ? valo.y.slice(valoFrom) : [],
      fair,
      central: fan.central,
      yCap: cfg.y_cap,
    });
    const yMax = scale.yMax || 1;
    // L'éventail n'existe que si les DEUX bornes existent (un multiple
    // pessimiste ≤ 0 le supprime) et que le central tient dans le cadre.
    const fanFits = !!(
      fan.central != null &&
      fan.optimistic != null &&
      fan.pessimistic != null &&
      fan.central <= yMax
    );
    const corridor = hasValo
      ? valuationCorridor({ dates, price: priceSeries, valo, latestOk })
      : null;
    const currentYear = new Date(lastDate).getFullYear();
    const dividends = dividendBars(calc.dividend_per_share, {
      years: windowYears,
      currentYear,
      startDate,
    });
    const height = Number(CHART_HEIGHTS.valuation_hero) || Number(CHART_HEIGHTS.hero) || 560;
    const margin = { l: 50, r: 70, t: 22, b: 26 };
    const cagr = valuationCagrRows({
      dates,
      priceSeries,
      metricSeries: metric,
      dividendPerShare: calc.dividend_per_share,
      fromIndex,
      windowYears,
      currentYear,
      isEnterprise,
      metricLabel: def.label,
    });
    const notes = valuationNotes({
      isEnterprise,
      latest: def.latest,
      latestOk,
      hasValo,
      central: fan.central,
      yMax,
      hasDividends: dividends.has,
      years: windowYears,
    });
    const status = valuationStatus({
      price,
      valoNow,
      latest: def.latest,
      latestOk,
      isEnterprise,
      label: def.label,
      gapRatioLimit: cfg.gap_ratio_limit,
    });
    const model = {
      dates, priceSeries, price, median, def, metric, latestOk, isEnterprise,
      windowYears, horizonYears, lastDate, horizonDate, fromIndex, valo, hasValo,
      valoNow, fair, growth, multiple, fan, yMax, fanFits, corridor, dividends,
      height, margin, cagr, notes, status,
    };
    this._valChartKey = key;
    this._valChartCache = model;
    return model;
  },

  // En-tête de carte : « Cours X · valorisation Y · sous-évalué de Z % ».
  // Le verdict est porté par un fragment coloré (bleu sous-évalué, rouge
  // sur-évalué) ; sans valorisation calculable, le texte le dit explicitement.
  valChartStatus() {
    const m = this.valChartModel();
    if (!m) return { lead: "", text: "", kind: "" };
    const currency = this.data?.identity?.currency || "";
    const priceText = m.price == null ? "—" : `${this.fmt(m.price)} ${currency}`.trim();
    const st = m.status;
    if (st.reason === "absent" || st.reason === "negative") {
      return {
        lead: `Cours ${priceText}`,
        text: ` · valorisation non calculable (${m.def.label} ${st.reason === "absent" ? "absent" : "négatif"})`,
        kind: "",
      };
    }
    if (st.gapPct == null) return { lead: `Cours ${priceText}`, text: "", kind: "" };
    const lead = `Cours ${priceText} · valorisation ${this.fmt(st.valoNow)}`;
    if (st.gapPct === 0) return { lead, text: " · à sa valorisation", kind: "" };
    const direction = st.gapPct < 0 ? "sous" : "sur";
    const text = st.big
      ? `${direction}-évalué (cours ×${this.fmt(st.ratio)})`
      : `${direction}-évalué de ${this.fmt(Math.abs(st.gapPct))} %`;
    return { lead, text: ` · ${text}`, kind: st.good ? "good" : "bad" };
  },

  // Pastilles fixes et bascules disponibles : une pastille n'existe que si sa
  // couche existe (pas de couloir sans valorisation, pas de dividende sans
  // versement sur la fenêtre).
  valChartLegend() {
    const m = this.valChartModel();
    if (!m) return { valo: "", scenarios: false, dividends: false };
    return {
      valo: m.hasValo
        ? `Valorisation · ${m.def.label} × ${m.def.multiple} ${this.fmt(m.median)}`
        : "",
      // La bascule Scénarios n'existe que si l'éventail est réellement traçable
      // (les deux bornes existent et le central tient dans le cadre).
      scenarios: !!m.fanFits,
      dividends: m.dividends.has,
    };
  },

  // Pied de carte : trois CAGR (cours, métrique, dividende complet). Le chiffre
  // est bleu si ≥ 0, rouge sinon, « — » quand il n'est pas calculable.
  valChartFooter() {
    const m = this.valChartModel();
    if (!m) return [];
    return m.cagr.map((row) => ({
      ...row,
      text: row.cagr == null ? "—" : `${row.cagr >= 0 ? "+" : ""}${this.fmt(row.cagr)} %/an`,
      kind: row.cagr == null ? "neutral" : row.cagr >= 0 ? "good" : "bad",
    }));
  },

  valChartNotes() {
    const m = this.valChartModel();
    if (!m) return [];
    return m.notes
      .map((note) => {
        if (note.key === "negative") {
          return `${m.def.label} négatif : valorisation et prix juste non calculables ; la courbe s'arrête au dernier exercice positif.`;
        }
        if (note.key === "absent") {
          return `${m.def.label} absent : valorisation et prix juste non calculables ; la courbe s'arrête au dernier exercice positif.`;
        }
        if (note.key === "enterprise") {
          return "EV/EBITDA est un multiple d'entreprise : pas de courbe de valorisation ni de couloir.";
        }
        if (note.key === "empty") {
          return "Pas de valorisation tracée : métrique ou multiple indisponible.";
        }
        if (note.key === "out-of-frame") {
          return `Projection hors cadre (${this.fmt(note.value)}) : croissance retenue ${this.fmt(m.growth)} %/an.`;
        }
        if (note.key === "no-dividend") {
          return `Aucun dividende sur ${m.windowYears} ans : étage masqué.`;
        }
        return "";
      })
      .filter(Boolean);
  },

  // Bascule d'une couche : redessine le graphe depuis le modèle en cache, sans
  // aucune requête réseau.
  valToggleLayer(key) {
    if (!(key in this.valLayers)) return;
    this.valLayers = { ...this.valLayers, [key]: !this.valLayers[key] };
    this.drawValuationChart();
  },

  drawValuationChart(retry = 0) {
    const el = "val-chart";
    const node = document.getElementById(el);
    if (!node) return;
    const m = this.valChartModel();
    if (!m) return;
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
    const layers = this.valLayers || { couloir: true, scenarios: false, dividendes: true };
    const hasDiv = m.dividends.has && layers.dividendes;
    const price = m.price;
    const traces = [];

    // 1. Couloir sous/sur-évalué : deux aires entre le cours et la valorisation,
    // sur la seule plage où la valorisation existe. Le bleu marque le cours
    // SOUS la valorisation, le rouge au-dessus.
    if (m.hasValo && layers.couloir && m.corridor) {
      const c = m.corridor;
      traces.push(
        { x: c.x, y: c.valo, mode: "lines", line: { width: 0, shape: "hv" }, hoverinfo: "skip" },
        { x: c.x, y: c.lower, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: C.goodFill, hoverinfo: "skip" },
        { x: c.x, y: c.valo, mode: "lines", line: { width: 0, shape: "hv" }, hoverinfo: "skip" },
        { x: c.x, y: c.upper, mode: "lines", line: { width: 0 }, fill: "tonexty", fillcolor: C.badFill, hoverinfo: "skip" },
      );
    }

    // 2. Éventail (couche Scénarios) : bornes pessimiste/optimiste autour du
    // cours actuel, remplissage ambre très pâle. Une valeur hors cadre ne trace
    // pas d'éventail (sa pastille et une note le signalent).
    if (layers.scenarios && m.fanFits && price != null && m.fan.pessimistic != null) {
      traces.push(
        { x: [m.lastDate, m.horizonDate], y: [price, m.fan.pessimistic], mode: "lines", line: { color: C.valo, width: 1, dash: "dot" }, hoverinfo: "skip" },
        { x: [m.lastDate, m.horizonDate], y: [price, m.fan.optimistic], mode: "lines", line: { color: C.valo, width: 1, dash: "dot" }, fill: "tonexty", fillcolor: C.valoFill, hoverinfo: "skip" },
      );
    }

    // 3. Cours (bleu), valorisation (ambre, escalier), scénario central.
    traces.push({
      x: m.dates, y: m.priceSeries, name: "Cours", mode: "lines",
      line: { color: C.accent, width: 1.5 }, hovertemplate: "%{y:.2f}",
    });
    if (m.hasValo) {
      traces.push({
        x: m.valo.x, y: m.valo.y, name: "Valorisation", mode: "lines",
        line: { color: C.valo, width: 2.2, shape: "hv" }, hovertemplate: "%{y:.2f}",
      });
    }
    if (m.fan.central != null && m.fan.central <= m.yMax && price != null) {
      traces.push({
        x: [m.lastDate, m.horizonDate], y: [price, m.fan.central],
        name: "Central", mode: "lines+markers",
        line: { color: C.valo, width: 1.8, dash: "dot" },
        marker: { size: [0, 7], color: C.valo }, hovertemplate: "%{y:.2f}",
      });
    }

    // 4. Prix juste : un rond creux POSÉ SUR « aujourd'hui » — c'est un prix
    // d'achat actuel, jamais une ligne tracée dans le passé.
    if (m.fair != null) {
      traces.push({
        x: [m.lastDate], y: [m.fair], name: "Prix juste", mode: "markers",
        marker: { size: 9, color: C.surface, line: { color: C.accent, width: 2 } },
        hovertemplate: "%{y:.2f}",
      });
    }

    // 5. Dividende/action : bâtons verts dans un étage dédié (axe y2) ; l'année
    // civile en cours est un bâton CREUX (fond blanc, bord vert).
    if (hasDiv) {
      traces.push({
        x: m.dividends.x, y: m.dividends.y, type: "bar", yaxis: "y2",
        width: 1000 * 3600 * 24 * 230, name: "Dividende",
        marker: {
          color: m.dividends.current.map((cur) => (cur ? C.surface : C.teal)),
          line: {
            color: C.teal,
            width: m.dividends.current.map((cur) => (cur ? 1.2 : 0)),
          },
        },
        customdata: m.dividends.current.map((cur) => (cur ? " (année en cours)" : "")),
        hovertemplate: "%{y:.2f}%{customdata}",
      });
    }

    // Pastilles : repères du haut (« aujourd'hui », « horizon N ans »), valeurs
    // de la colonne de droite (au moins 16 px d'écart) et prix juste à gauche.
    const annotations = [
      { x: m.lastDate, y: 1, yref: "paper", text: "aujourd’hui", showarrow: false, xanchor: "right", yanchor: "bottom", xshift: -4, font: { size: 10, color: C.text } },
      { x: m.horizonDate, y: 1, yref: "paper", text: `horizon ${m.horizonYears} ans`, showarrow: false, xanchor: "left", yanchor: "bottom", xshift: 4, font: { size: 10, color: C.text } },
    ];
    const pill = (x, y, text, color, xanchor = "left") => ({
      x, y, text, showarrow: false, xanchor, yanchor: "middle",
      xshift: xanchor === "left" ? 6 : -6,
      bgcolor: C.surface, bordercolor: color, borderwidth: 1, borderpad: 2,
      font: { color, size: 11 },
    });
    const plotHeight = Math.max(1, m.height - m.margin.t - m.margin.b);
    const priceHeight = Math.max(1, plotHeight * (hasDiv ? 0.7 : 1));
    const rightPills = valuationPillItems({
      central: m.fan.central,
      optimistic: m.fan.optimistic,
      pessimistic: m.fan.pessimistic,
      showFan: layers.scenarios,
      fanFits: m.fanFits,
      yMax: m.yMax,
      heightPx: priceHeight,
      minGapPx: 16,
    });
    for (const item of rightPills) {
      const color = item.key === "central" ? C.valo : C.mutedPill;
      const text = (item.value > m.yMax ? "↑ " : "") + this.fmt(item.value);
      annotations.push(pill(m.horizonDate, item.y, text, color));
    }
    if (m.fair != null) {
      // Un prix juste hors cadre garde sa pastille, collée sous le plafond et
      // préfixée « ↑ » — jamais un point hors échelle.
      const fairY = Math.min(m.fair, m.yMax * 0.97);
      const fairText = (m.fair > m.yMax ? "↑ " : "") + "Prix juste " + this.fmt(m.fair);
      annotations.push(pill(m.lastDate, fairY, fairText, C.accent, "right"));
    }
    if (hasDiv) {
      annotations.push({ x: m.dates[m.fromIndex], y: 0.215, yref: "paper", xanchor: "left", yanchor: "bottom", text: "Dividende / action", showarrow: false, font: { size: 11, color: C.text } });
    }

    const shapes = [
      // Zone future très légèrement teintée, puis trait « aujourd'hui ».
      { type: "rect", x0: m.lastDate, x1: m.horizonDate, yref: "paper", y0: 0, y1: 1, fillcolor: C.valoZone, line: { width: 0 }, layer: "below" },
      { type: "line", x0: m.lastDate, x1: m.lastDate, yref: "paper", y0: 0, y1: 1, line: { color: C.axis, width: 1 } },
    ];

    Plotly.react(el, traces, {
      margin: m.margin,
      height: m.height,
      paper_bgcolor: C.surface,
      plot_bgcolor: C.surface,
      font: { family: "Inter, sans-serif", size: 11, color: C.text },
      showlegend: false,
      hovermode: "x unified",
      // Axe X ancré SOUS l'étage dividende quand il existe (sinon sous le prix).
      xaxis: {
        type: "date", anchor: hasDiv ? "y2" : "y",
        range: [m.dates[m.fromIndex], this._addYears(m.horizonDate, 0.6)],
        showgrid: false, linecolor: C.axis, ticks: "outside", tickcolor: C.axis,
        ticklen: 4, color: C.text,
      },
      // Prix + valorisation sur ≈ 70 % de la hauteur ; dividende sur ≈ 20 %.
      yaxis: {
        domain: hasDiv ? [0.3, 1] : [0, 1], range: [0, m.yMax],
        gridcolor: C.grid, zeroline: false, nticks: 6, color: C.text,
      },
      yaxis2: {
        domain: [0, 0.2], gridcolor: C.grid, zeroline: false, nticks: 3,
        visible: hasDiv, rangemode: "tozero", color: C.text,
      },
      shapes,
      annotations,
    }, { displayModeBar: false, responsive: true }).then(() => {
      // Filet : si Plotly a tracé à une largeur différente du conteneur (layout
      // figé pendant un masquage), on force une remise à l'échelle.
      const gd = document.getElementById(el);
      if (gd && gd._fullLayout && Math.abs(gd._fullLayout.width - gd.clientWidth) > 2) {
        Plotly.Plots.resize(gd);
      }
    });
    this._valObserve(node);
  },

  // Le graphe suit la largeur RÉELLE de son conteneur : `responsive: true`
  // n'écoute que `window.resize`, pas une bascule de mise en page (même patron
  // que `risk.js::_riskObserve`). Un seul observateur, rebranché si le nœud change.
  _valObserve(node) {
    if (typeof ResizeObserver === "undefined" || !node) return;
    if (this._valObs && this._valObsNode === node) return;
    if (this._valObs) this._valObs.disconnect();
    let lastW = node.clientWidth;
    this._valObs = new ResizeObserver((entries) => {
      const w = entries?.[0]?.target?.clientWidth || 0;
      if (!w || Math.abs(w - lastW) < 1) return; // anti-boucle
      lastW = w;
      const run = () => {
        try {
          Plotly.Plots.resize(node);
        } catch {
          /* tracé purgé entre-temps */
        }
      };
      if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
      else run();
    });
    this._valObsNode = node;
    this._valObs.observe(node);
  },

  // Ajoute `years` années à une date ISO (fin de l'axe de projection). Les
  // fractions sont converties en mois (0,6 an = 7 mois) : `setFullYear` seul
  // les tronquait, et la marge droite de l'axe était un no-op.
  _addYears(iso, years) {
    const d = new Date(iso);
    const whole = Math.trunc(years);
    d.setFullYear(d.getFullYear() + whole);
    const months = Math.round((years - whole) * 12);
    if (months) d.setMonth(d.getMonth() + months);
    return d.toISOString().slice(0, 10);
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

  // --- Table « monde de Markovitz » (#33) ----------------------------------
  //
  // Déplacée de l'onglet Momentum : elle mesure le COURS autour de la droite
  // (σ, z, pente, MM, confiance), recalculé CÔTÉ CLIENT sur la fenêtre choisie.
  // `MARKOWITZ` est une liaison VIVANTE de `thresholds.js` (réassignée par
  // `applyMeta`) : on la lit dans la méthode, jamais dans un objet figé.
  mkwSeries: "raw", // "raw" | "adj"
  mkwWindow: null, // null = fenêtre de référence ; années ; 0 = maximum

  mkwWindows() {
    return MARKOWITZ.table_windows || [];
  },

  mkwHasAdj() {
    return this.data?.kind_payload === "stock" && !!this.data?.chart?.price_adj;
  },

  // Cours de la série choisie : c'est LUI que la table mesure (σ autour de la
  // droite, z, pente).
  mkwPriceValues() {
    const c = this.data?.chart || {};
    return (this.mkwSeries === "adj" ? c.price_adj : c.price_raw) || c.price_raw || [];
  },

  mkwAvailable() {
    const dates = this.data?.chart?.dates || [];
    return dates.length >= 2 && this.mkwPriceValues().length >= 2;
  },

  // Indice de départ de la fenêtre de RÉFÉRENCE (celle de la valorisation) :
  // la date persistée si elle existe, sinon 20 ans (30 pour les financières).
  _mkwReferenceStart(end) {
    const dates = this.data?.chart?.dates || [];
    const refStart = this.data?.watch?.ref?.start;
    if (refStart) {
      const i = dates.findIndex((d) => d >= refStart);
      if (i >= 0) return i;
    }
    const years =
      this.data?.identity?.kind === "financial" ? REG_YEARS_FINANCIAL : REG_YEARS_DEFAULT;
    return this._mkwStartBefore(end, years);
  },

  // Indices [début, fin] de la fenêtre de la table sur `chart.dates`.
  // `null` = la fenêtre de RÉFÉRENCE, `0` = le maximum.
  mkwRange() {
    const dates = this.data?.chart?.dates || [];
    if (!dates.length) return [0, 0];
    const end = dates.length - 1;
    if (this.mkwWindow == null) return [this._mkwReferenceStart(end), end];
    if (!this.mkwWindow) return [0, end];
    return [this._mkwStartBefore(end, Number(this.mkwWindow)), end];
  },

  _mkwStartBefore(end, years) {
    const dates = this.data?.chart?.dates || [];
    const cutoff = new Date(dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - Number(years));
    for (let i = 0; i <= end; i++) {
      if (new Date(dates[i]) >= cutoff) return i;
    }
    return 0;
  },

  mkwMaLast(kind) {
    const c = this.data?.chart || {};
    const suffix = this.mkwSeries === "adj" ? "_adj" : "_raw";
    const arr = c[kind + suffix] || c[kind] || [];
    for (let i = arr.length - 1; i >= 0; i--) if (arr[i] != null) return arr[i];
    return null;
  },

  // Mesures brutes de la table (nombres), séparées du formatage pour les tests.
  mkwStats() {
    const dates = this.data?.chart?.dates || [];
    const values = this.mkwPriceValues();
    if (!dates.length || !values.length) return null;
    const [i0, i1] = this.mkwRange();
    const times = [];
    const prices = [];
    for (let i = i0; i <= i1; i++) {
      if (values[i] == null || values[i] <= 0) continue;
      times.push((new Date(dates[i]) - new Date(dates[i0])) / (365.25 * 864e5));
      prices.push(values[i]);
    }
    if (times.length < 2) return null;
    const { a, b, sigma } = olsLog(times, prices);
    const last = prices[prices.length - 1];
    const tNow = times[times.length - 1];
    // 1 − R² = SS_res / SS_tot. `olsLog` ne renvoie que sigma : on reconstruit
    // SS_res depuis sigma (ddof = 1) et SS_tot depuis les log-prix.
    const ys = prices.map(Math.log);
    const mean = ys.reduce((s, v) => s + v, 0) / ys.length;
    const ssTot = ys.reduce((s, v) => s + (v - mean) ** 2, 0);
    const confidence = ssTot > 0 ? (sigma * sigma * (ys.length - 1)) / ssTot : 0;
    return {
      sigma,
      z: sigma > 0 ? (Math.log(last) - (a + b * tNow)) / sigma : null,
      slope: b,
      confidence,
      maShort: this.mkwMaLast("ma_short"),
      maLong: this.mkwMaLast("ma_long"),
    };
  },

  mkwRows() {
    const s = this.mkwStats();
    if (!s) return [];
    const pct = (v) => this.fmt(v) + " %";
    return [
      { key: "sigma", label: "σ (bande)", value: pct((Math.exp(s.sigma) - 1) * 100) },
      { key: "z", label: "z", value: s.z == null ? "—" : this.fmt(s.z) },
      { key: "slope", label: "Pente", value: pct((Math.exp(s.slope) - 1) * 100) },
      { key: "ma_short", label: "MM court", value: s.maShort == null ? "—" : this.fmt(s.maShort) },
      { key: "ma_long", label: "MM long", value: s.maLong == null ? "—" : this.fmt(s.maLong) },
      { key: "confidence", label: "Confiance (1−R²)", value: this.fmt(s.confidence) },
    ];
  },
};
