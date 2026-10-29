// Obole — seuils calibrés + maths portées côté client.
//
// Les seuils (labels, ratios, fenêtres, fiabilité β/ρ) ne sont PAS définis ici :
// ils sont reçus de `/api/meta` (source unique `config.py`) via `applyMeta()`.
// Ce module est chargé au démarrage avant tout calcul dépendant d'un seuil.

// Valeurs par défaut neutres AVANT chargement (bloquées par `metaReady`).
export let LABELS = { distance: [], ecart: [], perf: [], potential: [], beta: [], corr: [] };
export let LABEL_POLARITY = {};
export let RATIO_THRESHOLDS = {};
export let REG_YEARS_DEFAULT = 0;
export let REG_YEARS_FINANCIAL = 0;
export let BETA_MIN_POINTS = 0;
export let CORR_MIN_POINTS = 0;
export let POTENTIAL_HORIZONS = [];
// Taxonomie des cartes du Quantitatif (source unique config.QUANT_GROUPS via
// /api/meta) : le front ne décide plus quoi afficher, il lit ce plan.
export let QUANT_GROUPS = [];
// Taxonomie de la section Dividende (source unique config.DIVIDEND_GROUPS via
// /api/meta), même principe : le front lit le plan, il ne décide plus des cartes.
export let DIVIDEND_GROUPS = [];
// Polarité couleur des métriques du dividende (source unique config.DIVIDEND_COLORS).
export let DIVIDEND_COLORS = {};
// Horizons de CAGR du dividende affichés (source unique config.py via /api/meta).
// La fréquence de versement n'est PAS exposée ici : elle est calculée serveur
// (`engine/dividends.frequency`, config lue côté Python) et fournie au front
// dans `dividend.stats.frequency` — aucun seuil côté client.
export let DIVIDEND_CAGR_HORIZONS = [];
// Fenêtre par défaut des séries longues de la section Dividende (années) : le
// front n'affiche que les dernières années par défaut (le zoom sert à voir plus).
export let DIVIDEND_DEFAULT_WINDOW_YEARS = 0;
export let DIVIDEND_MIN_WINDOW_YEARS = 0;
// Hauteurs de tracé (standard UI, source unique config.py via /api/meta) : le CSS
// et le layout Plotly doivent coïncider. Aucune valeur écrite en dur côté JS.
export let CHART_HEIGHTS = { hero: 440, mini: 200, dividend_hero: 300, valuation_hero: 560, portfolio_resume: 360, portfolio_donut: 320, portfolio_drawdown: 300, portfolio_corr: 460, portfolio_corr_test: 110, portfolio_monthly: 300, portfolio_contrib: 300, portfolio_dividends: 300, portfolio_div_conc: 300, portfolio_div_conc_row: 34, portfolio_div_conc_pad: 40, detail: 420 };
// Taxonomie des tuiles KPI de l'onglet Dividende du PORTEFEUILLE (#17.5) :
// source unique `config.PORTFOLIO_DIVIDEND_GROUPS` via `/api/meta`. Le front rend
// les tuiles dans cet ordre, sans libellé ni unité en dur.
export let PORTFOLIO_DIVIDEND_GROUPS = [];
// Polarité couleur de ces KPI (source unique `config.PORTFOLIO_DIVIDEND_POLARITY`).
export let PORTFOLIO_DIVIDEND_POLARITY = {};
// Unités d'affichage des KPI du dividende portefeuille ("pct" | "money" | "pt").
export let PORTFOLIO_DIVIDEND_UNITS = {};
// Échelle (points de %) de la micro-barre « Écart » du tableau Dividende :
// amplitude purement visuelle, mais lue de `config.py` (aucun seuil en dur ici).
export let PORTFOLIO_DIVIDEND_GAP_SCALE_PP = 10;
// Unité d'affichage par métrique ("pct" | "mult"), source unique config.py via
// /api/meta. Une métrique absente est un montant ("money").
export let METRIC_UNITS = {};
// Taxonomie des comptes (document financier CSV) : [{name, category, role}],
// source unique `config.FUNDAMENTAL_METRICS` via `/api/meta`. Le front lit cette
// liste pour l'aperçu d'import — aucun nom de métrique en dur (miroir de
// `data/manual.SOURCE_METRICS` / `derived` côté serveur).
export let FUNDAMENTAL_METRICS = [];
// Synthèse « Résumé » (grille de lecture rapide) : seuils servis par
// `/api/summary-meta` (même source unique `config.py`). Aucun seuil en dur ici.
export let MARKET_CAP_LABELS = [];
export let ALTMAN_ZONES = [];
export let PIOTROSKI_ZONES = [];
export let SUMMARY_COLORS = {};
// Portefeuille (#17.1) : benchmarks, périodes et taille du Top/Flop — source
// unique `config.py` via `/api/portfolio/benchmarks`. Le front n'a aucun ticker
// en dur : il lit cette liste (ou laisse l'utilisateur saisir un ticker libre).
export let PORTFOLIO_BENCHMARKS = [];
export let PORTFOLIO_BENCHMARK_DEFAULT = "";
export let PORTFOLIO_PERIODS = [];
export let PORTFOLIO_PERIOD_DEFAULT = "";
// Horizons du graphe de détail par titre (modale Performance) : source unique
// `config.py` via `/api/portfolio/benchmarks`. Purement client (recadrage).
export let PORTFOLIO_DETAIL_HORIZONS = [];
export let PORTFOLIO_DETAIL_HORIZON_DEFAULT = "";
export let PORTFOLIO_TOP_N = 0;
// Étiquettes (#17.6) : borne du libellé, lue par le `maxlength` du champ.
export let PORTFOLIO_TAG_MAX = null;
// Risque (#17.3) : observations minimales par paire (matrice) et seuil au-delà
// duquel la heatmap masque les annotations (cellules illisibles -> infobulle).
export let PORTFOLIO_CORR_MIN_OBS = 0;
export let PORTFOLIO_CORR_ANNOTATE_MAX = 0;
// Section « Valorisation » (calculatrice de prix juste) : taxonomie, grille de
// matrice et ancrage couleur — source unique `config.py` via /api/meta.
export let VALUATION_METRICS = [];
export let VALUATION_GROUPS = [];
export let VALUATION_HORIZON_YEARS = 5;
export let VALUATION_TARGET_DEFAULT = 12;
export let VALUATION_PERIODS = [];
export let VALUATION_PERIOD_DEFAULT = 10;
export let VALUATION_MATRIX = { rows: 15, cols: 15, growth_step: 0.5, multiple_step: 1 };
export let VALUATION_COLOR_RATIOS = [0.5, 1.0];
// Bornes des points de contrôle suivis (#21) : source unique `config.py` via
// `/api/meta`. `null` tant que le payload n'est pas chargé (le serveur valide).
export let CHECKPOINT_LABEL_MAX = null;
// Watchlist (#25) : tiers fixes, point minimal d'une fenêtre de confiance et
// plafond de valeurs. Source unique `config.py` via `/api/meta` : le front ne
// connaît aucun de ces nombres en dur.
export let WATCH_TIERS = [];
export let WATCH_MIN_REF_POINTS = 0;
export let WATCH_MAX_ITEMS = 0;
// Clara Vallis (#30) : fenêtre de la foule, bornes de satisfaction et fenêtres
// du sélecteur. Source unique `config.py` via `/api/meta` — aucun seuil en dur
// dans le mixin momentum. Valeurs neutres tant que le payload n'est pas chargé.
export let MOMENTUM = { window: 0, low: 0, high: 0, table_windows: [] };

// Applique les seuils reçus de /api/meta (source unique config.py). Idempotent.
export function applyMeta(m) {
  if (!m) return;
  LABELS = m.labels || LABELS;
  LABEL_POLARITY = m.label_polarity || {};
  RATIO_THRESHOLDS = m.ratio_thresholds || {};
  REG_YEARS_DEFAULT = m.reg_years_default;
  REG_YEARS_FINANCIAL = m.reg_years_financial;
  BETA_MIN_POINTS = m.beta_min_points || 0;
  CORR_MIN_POINTS = m.corr_min_points || 0;
  POTENTIAL_HORIZONS = m.potential_horizons || [];
  MOMENTUM = m.momentum || MOMENTUM;
  QUANT_GROUPS = m.quant_groups || [];
  DIVIDEND_GROUPS = m.dividend_groups || [];
  DIVIDEND_COLORS = m.dividend_colors || {};
  DIVIDEND_CAGR_HORIZONS = m.dividend_cagr_horizons || [];
  DIVIDEND_DEFAULT_WINDOW_YEARS = m.dividend_default_window_years || 0;
  DIVIDEND_MIN_WINDOW_YEARS = m.dividend_min_window_years || 0;
  CHART_HEIGHTS = m.chart_heights || CHART_HEIGHTS;
  PORTFOLIO_DIVIDEND_GROUPS = m.portfolio_dividend_groups || [];
  PORTFOLIO_DIVIDEND_POLARITY = m.portfolio_dividend_polarity || {};
  PORTFOLIO_DIVIDEND_UNITS = m.portfolio_dividend_units || {};
  PORTFOLIO_DIVIDEND_GAP_SCALE_PP =
    m.portfolio_dividend_gap_scale_pp || PORTFOLIO_DIVIDEND_GAP_SCALE_PP;
  METRIC_UNITS = m.metric_units || {};
  FUNDAMENTAL_METRICS = m.fundamental_metrics || [];
  VALUATION_METRICS = m.valuation_metrics || [];
  VALUATION_GROUPS = m.valuation_groups || [];
  VALUATION_HORIZON_YEARS = m.valuation_horizon_years || VALUATION_HORIZON_YEARS;
  VALUATION_TARGET_DEFAULT = m.valuation_target_default || VALUATION_TARGET_DEFAULT;
  VALUATION_PERIODS = m.valuation_periods || [];
  VALUATION_PERIOD_DEFAULT = m.valuation_period_default || VALUATION_PERIOD_DEFAULT;
  VALUATION_MATRIX = m.valuation_matrix || VALUATION_MATRIX;
  VALUATION_COLOR_RATIOS = m.valuation_color_ratios || VALUATION_COLOR_RATIOS;
  CHECKPOINT_LABEL_MAX = m.checkpoint_label_max || CHECKPOINT_LABEL_MAX;
  WATCH_TIERS = (m.watch && m.watch.tiers) || [];
  WATCH_MIN_REF_POINTS = (m.watch && m.watch.min_ref_points) || 0;
  WATCH_MAX_ITEMS = (m.watch && m.watch.max_items) || 0;
  PORTFOLIO_TAG_MAX = m.portfolio_tag_max || PORTFOLIO_TAG_MAX;
  PORTFOLIO_CORR_MIN_OBS = m.portfolio_corr_min_obs || PORTFOLIO_CORR_MIN_OBS;
  PORTFOLIO_CORR_ANNOTATE_MAX = m.portfolio_corr_annotate_max || PORTFOLIO_CORR_ANNOTATE_MAX;
}

// Applique les métadonnées du portefeuille (source unique config.py via
// `/api/portfolio/benchmarks`) : benchmarks, périodes, défaut, Top/Flop.
export function applyPortfolioMeta(m) {
  if (!m) return;
  PORTFOLIO_BENCHMARKS = m.benchmarks || [];
  PORTFOLIO_BENCHMARK_DEFAULT = m.default || "";
  PORTFOLIO_PERIODS = m.periods || [];
  PORTFOLIO_PERIOD_DEFAULT = m.period_default || "";
  PORTFOLIO_DETAIL_HORIZONS = m.detail_horizons || [];
  PORTFOLIO_DETAIL_HORIZON_DEFAULT = m.detail_horizon_default || "";
  PORTFOLIO_TOP_N = m.top_n || 0;
}

// Libellé court d'une période (« ytd » -> « YTD », « ttm » -> « TTM », « 3a » -> « 3A »).
export function periodLabel(period) {
  if (period === "ytd") return "YTD";
  if (period === "ttm") return "TTM";
  if (period === "max") return "MAX";
  return String(period).toUpperCase();
}

// Applique les seuils de la synthèse (source unique config.py via /api/summary-meta).
export function applySummaryMeta(m) {
  if (!m) return;
  MARKET_CAP_LABELS = m.market_cap_labels || MARKET_CAP_LABELS;
  ALTMAN_ZONES = m.altman_zones || ALTMAN_ZONES;
  PIOTROSKI_ZONES = m.piotroski_zones || PIOTROSKI_ZONES;
  SUMMARY_COLORS = m.summary_colors || SUMMARY_COLORS;
}

// Couleur d'une ligne de la synthèse depuis `SUMMARY_COLORS` (source unique).
// Même convention que le screener : "ge" (plus = mieux), "le" (moins = mieux),
// "le_pos" (strictement positif et <= seuil). Aucun seuil littéral côté client.
export function summaryGood(key, value) {
  const t = SUMMARY_COLORS[key];
  if (!t || value == null || isNaN(value)) return null;
  const [sens, seuil] = t;
  if (seuil == null) return null;
  if (sens === "ge") return value >= seuil;
  if (sens === "le") return value <= seuil;
  if (sens === "le_pos") return value > 0 && value <= seuil;
  return null;
}

// Libellé de zone (Altman Z / Piotroski) : première borne inférieure franchie.
// `zones` = [[borne_inf, "label"], ..., [null, "label_final"]] (décroissant).
export function zoneLabel(value, zones) {
  if (value == null || isNaN(value) || !zones || !zones.length) return null;
  for (const [lower, label] of zones) {
    if (lower == null || value >= lower) return label;
  }
  return zones[zones.length - 1][1];
}

// Catégorie de capitalisation depuis `MARKET_CAP_LABELS` (source unique).
export function marketCapLabel(cap) {
  if (cap == null || isNaN(cap) || !MARKET_CAP_LABELS.length) return null;
  for (const [lower, label] of MARKET_CAP_LABELS) {
    if (lower == null || cap >= lower) return label;
  }
  return null;
}

// --- Régression OLS de ln(P) sur le temps (portage de engine/regression.py) ---
export function olsLog(times, prices) {
  const n = times.length;
  let st = 0, sy = 0, stt = 0, sty = 0;
  const ys = prices.map(Math.log);
  for (let i = 0; i < n; i++) { st += times[i]; sy += ys[i]; stt += times[i] * times[i]; sty += times[i] * ys[i]; }
  const b = (n * sty - st * sy) / (n * stt - st * st);
  const a = (sy - b * st) / n;
  let ss = 0;
  for (let i = 0; i < n; i++) { const r = ys[i] - (a + b * times[i]); ss += r * r; }
  const sigma = Math.sqrt(ss / (n - 1));
  return { a, b, sigma };
}

// Rendements log quotidiens alignés de A et B sur la tranche [i0, i1].
function _logReturns(seriesA, seriesB, i0, i1) {
  const ra = [], rb = [];
  for (let i = i0 + 1; i <= i1; i++) {
    const a0 = seriesA[i - 1], a1 = seriesA[i], b0 = seriesB[i - 1], b1 = seriesB[i];
    if (a0 == null || a1 == null || b0 == null || b1 == null || a0 <= 0 || a1 <= 0 || b0 <= 0 || b1 <= 0) continue;
    ra.push(Math.log(a1 / a0));
    rb.push(Math.log(b1 / b0));
  }
  return [ra, rb];
}

// Bêta de A sur B (amplitude) : β = cov(r_a, r_b) / var(r_b). Miroir engine/ratio.beta.
export function betaLive(seriesA, seriesB, i0, i1) {
  const [ra, rb] = _logReturns(seriesA, seriesB, i0, i1);
  const n = ra.length;
  if (n < BETA_MIN_POINTS) return null;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += ra[i]; mb += rb[i]; }
  ma /= n; mb /= n;
  let cov = 0, varb = 0;
  for (let i = 0; i < n; i++) { const da = ra[i] - ma, db = rb[i] - mb; cov += da * db; varb += db * db; }
  if (varb === 0) return null;
  return cov / varb;
}

// Corrélation de Pearson (solidité du lien) : ρ = cov / (σ_a·σ_b). Miroir engine/ratio.correlation.
export function corrLive(seriesA, seriesB, i0, i1) {
  const [ra, rb] = _logReturns(seriesA, seriesB, i0, i1);
  const n = ra.length;
  if (n < CORR_MIN_POINTS) return null;
  let ma = 0, mb = 0;
  for (let i = 0; i < n; i++) { ma += ra[i]; mb += rb[i]; }
  ma /= n; mb /= n;
  let cov = 0, va = 0, vb = 0;
  for (let i = 0; i < n; i++) { const da = ra[i] - ma, db = rb[i] - mb; cov += da * db; va += da * da; vb += db * db; }
  if (va === 0 || vb === 0) return null;
  return cov / Math.sqrt(va * vb);
}

// Renvoie le label de la première borne sup (exclue) non franchie.
// Défensif : un tableau vide (seuils /api/meta non chargés) ne doit pas lever.
export function classify(value, thresholds) {
  if (!thresholds || !thresholds.length) return null;
  for (const [upper, label] of thresholds) { if (upper === null || value < upper) return label; }
  return thresholds[thresholds.length - 1][1];
}

// Couleur d'un point selon le seuil du ratio (bleu=bon / rouge=mauvais / neutre).
export function ratioGood(metric, value) {
  const t = RATIO_THRESHOLDS[metric];
  if (!t || value == null || isNaN(value)) return null;
  const [seuil, sens] = t;
  return sens === "ge" ? value >= seuil : value <= seuil;
}

// Couleur d'un label prix depuis la polarité reçue de /api/meta (source unique).
function _labelGood(kind, value) {
  const p = LABEL_POLARITY[kind];
  if (!p) return null;
  const [sens, seuil] = p;
  return sens === "lt" ? value < seuil : value >= seuil;
}

// Construit un ScoredValue {value, label, good} comme côté serveur.
export function scored(value, kind, round = 1) {
  if (value == null || isNaN(value)) return { value: null, label: null, good: null };
  const v = Number(value.toFixed(round === 0 ? 0 : round));
  switch (kind) {
    case "distance": return { value: v, label: classify(v, LABELS.distance), good: _labelGood("distance", v) };
    case "ecart": return { value: v, label: classify(v, LABELS.ecart), good: _labelGood("ecart", v) };
    case "perf": return { value: v, label: classify(v, LABELS.perf), good: _labelGood("perf", v) };
    case "potential": return { value: v, label: classify(v, LABELS.potential), good: _labelGood("potential", v) };
    // β A~B (amplitude) : neutre ; β<0 -> inversés (miroir de label_beta).
    case "beta": return { value: v, label: v < 0 ? "Inversés" : classify(v, LABELS.beta), good: null };
    // ρ A~B (solidité) : neutre ; classe sur |ρ| ; ρ<0 -> suffixe (miroir de label_correlation).
    case "corr": return { value: v, label: classify(Math.abs(v), LABELS.corr) + (v < 0 ? " (inverse)" : ""), good: null };
  }
}
