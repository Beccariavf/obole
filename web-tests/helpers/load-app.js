import { readFileSync } from "node:fs";

// Chemins injectés par `vitest.config.js` (voir `define`).
const APP_PATH = __APP_JS_PATH__;
const CONFIG_PATH = __CONFIG_PY_PATH__;
const WATCHLIST_JS_PATH = __WATCHLIST_JS_PATH__;
const CONVICTION_JS_PATH = __CONVICTION_JS_PATH__;

// #04 : `app.js` est désormais un module ES (plus de script classique évalué
// par `vm`). On importe les modules réels : le composant Alpine vient de
// `app.js`, les maths/seuils de `thresholds.js`, la charte de `theme.js`.
import { applyMeta, applyPortfolioMeta, periodLabel, olsLog, classify, scored, ratioGood, LABELS, RATIO_THRESHOLDS, LABEL_POLARITY, REG_YEARS_DEFAULT, REG_YEARS_FINANCIAL, BETA_MIN_POINTS, CORR_MIN_POINTS, POTENTIAL_HORIZONS, QUANT_GROUPS, METRIC_UNITS, FUNDAMENTAL_METRICS, DIVIDEND_GROUPS, DIVIDEND_COLORS, DIVIDEND_CAGR_HORIZONS, DIVIDEND_DEFAULT_WINDOW_YEARS, DIVIDEND_MIN_WINDOW_YEARS, CHART_HEIGHTS, PORTFOLIO_BENCHMARKS, PORTFOLIO_BENCHMARK_DEFAULT, PORTFOLIO_PERIODS, PORTFOLIO_PERIOD_DEFAULT, PORTFOLIO_DETAIL_HORIZONS, PORTFOLIO_DETAIL_HORIZON_DEFAULT, PORTFOLIO_TOP_N, PORTFOLIO_TAG_MAX, PORTFOLIO_CORR_MIN_OBS, PORTFOLIO_CORR_ANNOTATE_MAX, VALUATION_METRICS, VALUATION_GROUPS, VALUATION_HORIZON_YEARS, VALUATION_PERIODS, VALUATION_MATRIX, VALUATION_COLOR_RATIOS, WATCH_TIERS, WATCH_MIN_REF_POINTS, WATCH_MAX_ITEMS, MOMENTUM } from "../../src/obole/web/thresholds.js";
import { C } from "../../src/obole/web/theme.js";
import { obole } from "../../src/obole/web/app.js";
import { chartsMixin } from "../../src/obole/web/charts.js";
import { dividendMixin } from "../../src/obole/web/dividend.js";
import { valorisationMixin, fairPrice, safetyMargin, estimatedReturn, targetEntryPrice, matrixGrid, colorBucket, cagrFromSeries } from "../../src/obole/web/valorisation.js";
import { watchlistMixin, sortWatchRows, watchCoverage, tierLabel, fairPriceSourceLabel } from "../../src/obole/web/watchlist.js";

// `LABELS`, `RATIO_THRESHOLDS`, etc. sont des `let` mutables réassignés par
// `applyMeta` : on les expose via des getters pour que les tests lisent la
// valeur COURANTE (un snapshot figeait l'état pré-chargement, vide).
export function loadApp() {
  return {
    applyMeta,
    applyPortfolioMeta,
    periodLabel,
    olsLog,
    classify,
    scored,
    ratioGood,
    obole,
    C,
    get LABELS() { return LABELS; },
    get RATIO_THRESHOLDS() { return RATIO_THRESHOLDS; },
    get LABEL_POLARITY() { return LABEL_POLARITY; },
    get REG_YEARS_DEFAULT() { return REG_YEARS_DEFAULT; },
    get REG_YEARS_FINANCIAL() { return REG_YEARS_FINANCIAL; },
    get BETA_MIN_POINTS() { return BETA_MIN_POINTS; },
    get CORR_MIN_POINTS() { return CORR_MIN_POINTS; },
    get POTENTIAL_HORIZONS() { return POTENTIAL_HORIZONS; },
    get QUANT_GROUPS() { return QUANT_GROUPS; },
    get METRIC_UNITS() { return METRIC_UNITS; },
    get FUNDAMENTAL_METRICS() { return FUNDAMENTAL_METRICS; },
    get DIVIDEND_GROUPS() { return DIVIDEND_GROUPS; },
    get DIVIDEND_COLORS() { return DIVIDEND_COLORS; },
    get DIVIDEND_CAGR_HORIZONS() { return DIVIDEND_CAGR_HORIZONS; },
    get DIVIDEND_DEFAULT_WINDOW_YEARS() { return DIVIDEND_DEFAULT_WINDOW_YEARS; },
    get DIVIDEND_MIN_WINDOW_YEARS() { return DIVIDEND_MIN_WINDOW_YEARS; },
    get CHART_HEIGHTS() { return CHART_HEIGHTS; },
    get MOMENTUM() { return MOMENTUM; },
    get PORTFOLIO_BENCHMARKS() { return PORTFOLIO_BENCHMARKS; },
    get PORTFOLIO_BENCHMARK_DEFAULT() { return PORTFOLIO_BENCHMARK_DEFAULT; },
    get PORTFOLIO_PERIODS() { return PORTFOLIO_PERIODS; },
    get PORTFOLIO_PERIOD_DEFAULT() { return PORTFOLIO_PERIOD_DEFAULT; },
    get PORTFOLIO_DETAIL_HORIZONS() { return PORTFOLIO_DETAIL_HORIZONS; },
    get PORTFOLIO_DETAIL_HORIZON_DEFAULT() { return PORTFOLIO_DETAIL_HORIZON_DEFAULT; },
    get PORTFOLIO_TOP_N() { return PORTFOLIO_TOP_N; },
    get PORTFOLIO_TAG_MAX() { return PORTFOLIO_TAG_MAX; },
    get PORTFOLIO_CORR_MIN_OBS() { return PORTFOLIO_CORR_MIN_OBS; },
    get PORTFOLIO_CORR_ANNOTATE_MAX() { return PORTFOLIO_CORR_ANNOTATE_MAX; },
    get VALUATION_METRICS() { return VALUATION_METRICS; },
    get VALUATION_GROUPS() { return VALUATION_GROUPS; },
    get VALUATION_HORIZON_YEARS() { return VALUATION_HORIZON_YEARS; },
    get VALUATION_PERIODS() { return VALUATION_PERIODS; },
    get VALUATION_MATRIX() { return VALUATION_MATRIX; },
    get VALUATION_COLOR_RATIOS() { return VALUATION_COLOR_RATIOS; },
    get WATCH_TIERS() { return WATCH_TIERS; },
    get WATCH_MIN_REF_POINTS() { return WATCH_MIN_REF_POINTS; },
    get WATCH_MAX_ITEMS() { return WATCH_MAX_ITEMS; },
    fairPrice, safetyMargin, estimatedReturn, targetEntryPrice, matrixGrid, colorBucket, cagrFromSeries,
    watchlistMixin,
    sortWatchRows,
    watchCoverage,
    tierLabel,
    fairPriceSourceLabel,
    valuationGroups: valorisationMixin.valuationGroups,
    valMatrix: valorisationMixin.valMatrix,
    valMetricDef: valorisationMixin.valMetricDef,
    valEstimatedReturn: valorisationMixin.valEstimatedReturn,
    valFairPrice: valorisationMixin.valFairPrice,
    valMedianValue: valorisationMixin.valMedianValue,
    valSafetyMargin: valorisationMixin.valSafetyMargin,
    valBeatsTarget: valorisationMixin.valBeatsTarget,
    initValuation: valorisationMixin.initValuation,
    valuationAvailable: valorisationMixin.valuationAvailable,
    valuationPills: valorisationMixin.valuationPills,
    _seriesAvailableRange: valorisationMixin._seriesAvailableRange,
    _stepCorners: valorisationMixin._stepCorners,
    valNum1: valorisationMixin.valNum1,
    canSaveValuation: valorisationMixin.canSaveValuation,
    metricUnit: chartsMixin.metricUnit,
    isWideCard: chartsMixin.isWideCard,
    dividendGroups: dividendMixin.dividendGroups,
    dividendKeyMetrics: dividendMixin.dividendKeyMetrics,
    dividendCardEmpty: dividendMixin.dividendCardEmpty,
    dividendCardSpan: dividendMixin.dividendCardSpan,
    dividendSeriesPills: dividendMixin.dividendSeriesPills,
    dividendPerfPills: dividendMixin.dividendPerfPills,
    yieldPills: dividendMixin.yieldPills,
    dividendWarnings: dividendMixin.dividendWarnings,
    _yieldStats: dividendMixin._yieldStats,
    detailRangeLabel: chartsMixin.detailRangeLabel,
    detailPreset: chartsMixin.detailPreset,
    openChartDetail: chartsMixin.openChartDetail,
    isDividendCard: chartsMixin.isDividendCard,
    defaultDateRange: dividendMixin.defaultDateRange,
    visibleRange: chartsMixin.visibleRange,
    initRange: chartsMixin.initRange,
    idxStartBeforeWindow: chartsMixin.idxStartBeforeWindow,
  };
}

export function appSource() {
  return readFileSync(APP_PATH, "utf8");
}

export function readConfigSource() {
  return readFileSync(CONFIG_PATH, "utf8");
}

// Source du module Dividende (vérifs « aucun seuil littéral » côté front).
export function readDividendSource() {
  return readFileSync(__DIVIDEND_JS_PATH__, "utf8");
}

// Source du module Valorisation (vérif « aucun seuil littéral » côté front).
export function readValorisationSource() {
  return readFileSync(__VALORISATION_JS_PATH__, "utf8");
}

// Source du module Watchlist (vérif « aucun seuil littéral » côté front, #25).
export function readWatchlistSource() {
  return readFileSync(WATCHLIST_JS_PATH, "utf8");
}

// Source du moteur de conviction (vérif « plus de percentile ni d'effectifs », #27).
export function readConvictionSource() {
  return readFileSync(CONVICTION_JS_PATH, "utf8");
}

// Source du CSS (vérif de cohérence des hauteurs avec config.py).
export function readStyleSource() {
  return readFileSync(__STYLE_CSS_PATH__, "utf8");
}

// Source de `index.html` (vérifs de template : absence de x-model, etc.).
export function readIndexSource() {
  return readFileSync(__INDEX_HTML_PATH__, "utf8");
}

// Extrait une liste Python `NAME = [ (borne, "label"), ... ]` de config.py.
// Volontairement strict : lève si la liste est absente ou vide.
export function parsePyLabelList(source, name) {
  const block = source.match(new RegExp(`${name}\\s*=\\s*\\[([\\s\\S]*?)\\n\\]`));
  if (!block) throw new Error(`Liste ${name} introuvable dans config.py`);
  const entries = [...block[1].matchAll(/\(([^,()]+),\s*"([^"]*)"\)/g)].map(
    ([, bound, label]) => [bound.trim() === "None" ? null : Number(bound), label],
  );
  if (entries.length === 0) throw new Error(`Aucun tuple parsé pour ${name}`);
  return entries;
}

// Extrait le dict Python `RATIO_THRESHOLDS = { "nom": (seuil, "sens"), ... }`.
export function parsePyRatioThresholds(source) {
  const block = source.match(/RATIO_THRESHOLDS\s*=\s*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("RATIO_THRESHOLDS introuvable dans config.py");
  const entries = [...block[1].matchAll(/"([^"]+)":\s*\(([\d.]+),\s*"(\w+)"\)/g)].map(
    ([, name, seuil, sens]) => [name, [Number(seuil), sens]],
  );
  if (entries.length === 0) throw new Error("Aucun seuil de ratio parsé");
  return Object.fromEntries(entries);
}

// Parse `config.FUNDAMENTAL_METRICS` puis `config.FINANCIAL_METRICS` (tuples
// (nom, rôle)), et renvoie l'UNION dédupliquée (miroir de `config.FUNDAMENTAL_METRICS_ALL`
// tel que sérialisé par `/api/meta`).
export function parsePyFundamentalMetrics(source) {
  const collect = (name) => {
    const block = source.match(new RegExp(`${name}[^=]*=\\s*\\(([\\s\\S]*?)\\n\\)`));
    if (!block) throw new Error(`${name} introuvable dans config.py`);
    return [...block[1].matchAll(/\(\s*"([^"]+)",\s*"(\w+)"\s*\)/g)].map(
      ([, metricName, role]) => ({ name: metricName, role }),
    );
  };
  const all = [...collect("FUNDAMENTAL_METRICS"), ...collect("FINANCIAL_METRICS")];
  const seen = new Set();
  const entries = all.filter((m) => {
    if (seen.has(m.name)) return false;
    seen.add(m.name);
    return true;
  });
  if (entries.length === 0) throw new Error("Aucune métrique fondamentale parsée");
  return entries;
}

// Extrait le dict Python `LABEL_POLARITY = { "kind": ("sens", seuil), ... }`.
export function parsePyLabelPolarity(source) {
  const block = source.match(/LABEL_POLARITY\s*:[^=]*=\s*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("LABEL_POLARITY introuvable dans config.py");
  const entries = [...block[1].matchAll(/"(\w+)":\s*\("(\w+)",\s*([\d.]+)\)/g)].map(
    ([, kind, sens, seuil]) => [kind, [sens, Number(seuil)]],
  );
  if (entries.length === 0) throw new Error("Aucune polarité de label parsée");
  return Object.fromEntries(entries);
}

// Extrait la taxonomie `PORTFOLIO_STAT_GROUPS = [ { "id": …, "metrics": [ {…} ] } ]`.
// Lecture structurelle indépendante de config.py : le test de parité compare ce
// parsing au payload `/api/meta` consommé par `portfolio.js`. On relève
// `signed` (variation vs niveau), qui pilote le préfixe « + » côté front.
export function parsePyStatGroups(source) {
  const block = source.match(/PORTFOLIO_STAT_GROUPS\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("PORTFOLIO_STAT_GROUPS introuvable dans config.py");
  const body = block[1].replace(/\s+/g, " ");
  const groups = [];
  const parts = body.split(/\{\s*"id":\s*"([^"]+)",\s*"title":\s*"([^"]+)",\s*"metrics":\s*\[/);
  for (let i = 1; i < parts.length; i += 3) {
    const id = parts[i];
    const metricsBlock = parts[i + 2] ?? "";
    const metrics = [...metricsBlock.matchAll(/\{\s*"key":\s*"([^"]+)"/g)].map((m) => {
      const seg = metricsBlock.slice(m.index);
      const signed = /"signed":\s*True/.test(seg.slice(0, seg.indexOf("}")));
      return { key: m[1], ...(signed ? { signed: true } : {}) };
    });
    groups.push({ id, metrics });
  }
  if (groups.length === 0) throw new Error("Aucun groupe de stats parsé");
  return groups;
}

// Extrait la taxonomie `QUANT_GROUPS = [ { "title": …, "cards": [ {…}, … ] }, … ]`.
// Parsing volontairement structurel (groupes repérés par `"cards":`), pour que le
// test de parité compare une lecture INDÉPENDANTE de config.py au payload front.
export function parsePyQuantGroups(source) {
  const block = source.match(/QUANT_GROUPS\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("QUANT_GROUPS introuvable dans config.py");
  const body = block[1].replace(/\s+/g, " ");
  const parts = body.split(/\{\s*"title":\s*"([^"]+)",\s*"cards":\s*\[/);
  const groups = [];
  for (let i = 1; i < parts.length; i += 2) {
    const title = parts[i];
    const seg = parts[i + 1];
    // Virgule finale et espaces internes tolérés (ruff formate les objets
    // multilignes en `{ "type": … }`).
    const cards = [
      ...seg.matchAll(
        /\{\s*"type":\s*"(\w+)",\s*"title":\s*"([^"]+)"(?:,\s*"metrics":\s*\[([^\]]*)\])?\s*,?\s*\}/g,
      ),
    ].map(([, type, cardTitle, metrics]) => {
      const card = { type, title: cardTitle };
      if (metrics !== undefined) {
        card.metrics = [...metrics.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
      }
      return card;
    });
    groups.push({ title, cards });
  }
  if (groups.length === 0) throw new Error("Aucun groupe Quantitatif parsé");
  return groups;
}

// Parse `config.METRIC_UNITS` (dict Python `nom -> "pct"|"mult"`).
export function parsePyMetricUnits(source) {
  const block = source.match(/METRIC_UNITS\s*:\s*dict\[str,\s*str\]\s*=\s*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("METRIC_UNITS introuvable dans config.py");
  const out = {};
  for (const m of block[1].matchAll(/"([^"]+)":\s*"([^"]+)"/g)) out[m[1]] = m[2];
  return out;
}

// Parse `config.DIVIDEND_GROUPS` (même forme que QUANT_GROUPS). Les cartes
// peuvent porter `metrics` (liste) ou `series` (nom de série continue).
export function parsePyDividendGroups(source) {
  const block = source.match(/DIVIDEND_GROUPS\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("DIVIDEND_GROUPS introuvable dans config.py");
  const body = block[1].replace(/\s+/g, " ");
  const parts = body.split(/\{\s*"title":\s*"([^"]+)",\s*"cards":\s*\[/);
  const groups = [];
  for (let i = 1; i < parts.length; i += 2) {
    const title = parts[i];
    const seg = parts[i + 1];
    const cards = [
      ...seg.matchAll(
        /\{\s*"type":\s*"(\w+)",\s*"title":\s*"([^"]+)"([^}]*?)\s*,?\s*\}/g,
      ),
    ].map(([, type, cardTitle, rest]) => {
      const card = { type, title: cardTitle };
      const metrics = rest.match(/"metrics":\s*\[([^\]]*)\]/);
      if (metrics) card.metrics = [...metrics[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
      const series = rest.match(/"series":\s*"([^"]+)"/);
      if (series) card.series = series[1];
      if (/"wide":\s*True/.test(rest)) card.wide = true;
      return card;
    });
    groups.push({ title, cards });
  }
  if (groups.length === 0) throw new Error("Aucun groupe Dividende parsé");
  return groups;
}

// Parse `config.DIVIDEND_COLORS` (dict `nom -> (sens, seuil)`).
export function parsePyDividendColors(source) {
  const block = source.match(/DIVIDEND_COLORS[^=]*=\s*\{([\s\S]*?)\n\}/);
  if (!block) throw new Error("DIVIDEND_COLORS introuvable dans config.py");
  const out = {};
  for (const m of block[1].matchAll(/"([^"]+)":\s*\((None|\w+),\s*(None|[\d.]+)\)/g)) {
    out[m[1]] = [m[2], m[3] === "None" ? null : Number(m[3])];
  }
  return out;
}

// Parse `config.PORTFOLIO_BENCHMARKS` (liste de dicts `{key, ticker, label}`).
export function parsePyPortfolioBenchmarks(source) {
  const block = source.match(/PORTFOLIO_BENCHMARKS\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("PORTFOLIO_BENCHMARKS introuvable dans config.py");
  const entries = [...block[1].matchAll(
    /"key":\s*"([^"]+)",\s*"ticker":\s*"([^"]+)",\s*"label":\s*"([^"]+)"/g,
  )].map(([, key, ticker, label]) => ({ key, ticker, label }));
  if (entries.length === 0) throw new Error("Aucun benchmark parsé");
  return entries;
}

// Construit le payload /api/portfolio/benchmarks à partir de config.py (miroir).
export function portfolioMetaFromConfig(source) {
  return {
    benchmarks: parsePyPortfolioBenchmarks(source),
    default: source.match(/PORTFOLIO_BENCHMARK_DEFAULT\s*=\s*"([^"]+)"/)[1],
    periods: [...source.match(/PORTFOLIO_PERIODS\s*=\s*\(([^)]*)\)/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]),
    period_default: source.match(/PORTFOLIO_PERIOD_DEFAULT\s*=\s*"([^"]+)"/)[1],
    detail_horizons: [...source.match(/PORTFOLIO_DETAIL_HORIZONS\s*=\s*\(([^)]*)\)/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]),
    detail_horizon_default: source.match(/PORTFOLIO_DETAIL_HORIZON_DEFAULT\s*=\s*"([^"]+)"/)[1],
    top_n: Number(source.match(/PORTFOLIO_TOP_N\s*=\s*(\d+)/)[1]),
  };
}

// Construit le payload /api/meta à partir de config.py (miroir de la route).
export function metaFromConfig(source) {
  return {
    labels: {
      distance: parsePyLabelList(source, "DISTANCE_SIGMA_LABELS"),
      ecart: parsePyLabelList(source, "ECART_TYPE_LABELS"),
      perf: parsePyLabelList(source, "PERF_LABELS"),
      potential: parsePyLabelList(source, "POTENTIAL_LABELS"),
      beta: parsePyLabelList(source, "BETA_LABELS"),
      corr: parsePyLabelList(source, "CORR_LABELS"),
    },
    label_polarity: parsePyLabelPolarity(source),
    ratio_thresholds: parsePyRatioThresholds(source),
    reg_years_default: Number(source.match(/REGRESSION_YEARS_DEFAULT\s*=\s*(\d+)/)[1]),
    reg_years_financial: Number(source.match(/REGRESSION_YEARS_FINANCIAL\s*=\s*(\d+)/)[1]),
    beta_min_points: Number(source.match(/BETA_MIN_POINTS\s*=\s*(\d+)/)[1]),
    corr_min_points: Number(source.match(/CORR_MIN_POINTS\s*=\s*(\d+)/)[1]),
    potential_horizons: [...source.match(/POTENTIAL_HORIZONS\s*=\s*\(([^)]*)\)/)[1].matchAll(/\d+/g)].map((m) => Number(m[0])),
    momentum: {
      window: Number(source.match(/MOMENTUM_WINDOW\s*=\s*(\d+)/)[1]),
      low: Number(source.match(/MOMENTUM_SATISFACTION_LOW\s*=\s*([\d.]+)/)[1]),
      high: Number(source.match(/MOMENTUM_SATISFACTION_HIGH\s*=\s*([\d.]+)/)[1]),
      table_windows: [...source.match(/MOMENTUM_TABLE_WINDOWS\s*=\s*\(([^)]*)\)/)[1].matchAll(/\d+/g)].map((m) => Number(m[0])),
    },
    quant_groups: parsePyQuantGroups(source),
    dividend_groups: parsePyDividendGroups(source),
    dividend_colors: parsePyDividendColors(source),
    dividend_cagr_horizons: [
      ...source.match(/DIVIDEND_CAGR_HORIZONS\s*=\s*\(([^)]*)\)/)[1].matchAll(/\d+/g),
    ].map((m) => Number(m[0])),
    dividend_default_window_years: Number(
      source.match(/DIVIDEND_DEFAULT_WINDOW_YEARS\s*=\s*(\d+)/)[1],
    ),
    dividend_min_window_years: Number(source.match(/DIVIDEND_MIN_WINDOW_YEARS\s*=\s*(\d+)/)[1]),
    chart_heights: {
      hero: Number(source.match(/CHART_HEIGHT_HERO\s*=\s*(\d+)/)[1]),
      mini: Number(source.match(/CHART_HEIGHT_MINI\s*=\s*(\d+)/)[1]),
      dividend_hero: Number(source.match(/CHART_HEIGHT_DIVIDEND_HERO\s*=\s*(\d+)/)[1]),
      valuation_hero: Number(source.match(/CHART_HEIGHT_VALUATION_HERO\s*=\s*(\d+)/)[1]),
      portfolio_resume: Number(source.match(/CHART_HEIGHT_PORTFOLIO_RESUME\s*=\s*(\d+)/)[1]),
      portfolio_donut: Number(source.match(/CHART_HEIGHT_PORTFOLIO_DONUT\s*=\s*(\d+)/)[1]),
      portfolio_drawdown: Number(source.match(/CHART_HEIGHT_PORTFOLIO_DRAWDOWN\s*=\s*(\d+)/)[1]),
      portfolio_corr: Number(source.match(/CHART_HEIGHT_PORTFOLIO_CORR\s*=\s*(\d+)/)[1]),
      portfolio_corr_test: Number(
        source.match(/CHART_HEIGHT_PORTFOLIO_CORR_TEST\s*=\s*(\d+)/)[1],
      ),
      portfolio_monthly: Number(source.match(/CHART_HEIGHT_PORTFOLIO_MONTHLY\s*=\s*(\d+)/)[1]),
      portfolio_contrib: Number(source.match(/CHART_HEIGHT_PORTFOLIO_CONTRIB\s*=\s*(\d+)/)[1]),
      detail: Number(source.match(/CHART_HEIGHT_DETAIL\s*=\s*(\d+)/)[1]),
    },
    metric_units: { ...parsePyMetricUnits(source), ...parsePyDividendMetricUnits(source) },
    fundamental_metrics: parsePyFundamentalMetrics(source),
    valuation_metrics: parsePyValuationMetrics(source),
    valuation_groups: parsePyValuationGroups(source),
    valuation_horizon_years: Number(source.match(/VALUATION_HORIZON_YEARS\s*=\s*(\d+)/)[1]),
    valuation_target_default: Number(
      source.match(/VALUATION_TARGET_YIELD_DEFAULT\s*=\s*([\d.]+)/)[1],
    ),
    valuation_periods: [...source.match(/VALUATION_PERIODS\s*=\s*\(([^)]*)\)/)[1].matchAll(/\d+/g)]
      .map((m) => Number(m[0])),
    valuation_period_default: Number(source.match(/VALUATION_PERIOD_DEFAULT\s*=\s*(\d+)/)[1]),
    valuation_matrix: {
      rows: Number(source.match(/VALUATION_MATRIX_ROWS\s*=\s*(\d+)/)[1]),
      cols: Number(source.match(/VALUATION_MATRIX_COLS\s*=\s*(\d+)/)[1]),
      growth_step: Number(source.match(/VALUATION_MATRIX_GROWTH_STEP\s*=\s*([\d.]+)/)[1]),
      multiple_step: Number(source.match(/VALUATION_MATRIX_MULTIPLE_STEP\s*=\s*([\d.]+)/)[1]),
    },
    valuation_color_ratios: [
      ...source.match(/VALUATION_COLOR_RATIOS\s*=\s*\(([^)]*)\)/)[1].matchAll(/[\d.]+/g),
    ].map((m) => Number(m[0])),
    checkpoint_label_max: Number(source.match(/CHECKPOINT_LABEL_MAX\s*=\s*(\d+)/)[1]),
    portfolio_tag_max: Number(source.match(/PORTFOLIO_TAG_MAX\s*=\s*(\d+)/)[1]),
    portfolio_corr_min_obs: Number(source.match(/PORTFOLIO_CORR_MIN_OBS\s*=\s*(\d+)/)[1]),
    portfolio_corr_annotate_max: Number(source.match(/PORTFOLIO_CORR_ANNOTATE_MAX\s*=\s*(\d+)/)[1]),
    watch: {
      tiers: parsePyWatchTiers(source),
      min_ref_points: Number(source.match(/REGRESSION_MIN_POINTS\s*=\s*(\d+)/)[1]),
      max_items: Number(source.match(/WATCHLIST_MAX_ITEMS\s*=\s*(\d+)/)[1]),
    },
  };
}

// Parse `config.VALUATION_METRICS` (liste de dicts avec key/label/multiple/unit +
// multiple_step propre à la base). Découpage sur les frontières `"key":` (et non
// sur les accolades) : robuste aux accolades imbriquées et à tout bloc sans clé.
export function parsePyValuationMetrics(source) {
  const block = source.match(/VALUATION_METRICS[^=]*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("VALUATION_METRICS introuvable dans config.py");
  const cards = block[1].split(/"key":\s*"/).slice(1).map((seg) => {
    const key = seg.slice(0, seg.indexOf('"'));
    const label = seg.match(/"label":\s*"([^"]+)"/)?.[1];
    if (!label) throw new Error(`Libellé introuvable pour la métrique « ${key} »`);
    const step = seg.match(/"multiple_step":\s*([\d.]+)/);
    return { key, label, ...(step ? { multiple_step: Number(step[1]) } : {}) };
  });
  if (cards.length === 0) throw new Error("Aucune métrique de valorisation parsée");
  return cards;
}

// Parse `config.VALUATION_GROUPS` (cartes `vline` avec `series`, + `pills` optionnel
// au niveau du groupe : "cagr" = pastille de croissance, absent = High/Médiane/Low).
export function parsePyValuationGroups(source) {
  const block = source.match(/VALUATION_GROUPS\s*=\s*\[([\s\S]*?)\n\]/);
  if (!block) throw new Error("VALUATION_GROUPS introuvable dans config.py");
  const body = block[1].replace(/\s+/g, " ");
  const parts = body.split(/\{\s*"title":\s*"([^"]+)",\s*(?:"pills":\s*"([^"]+)",\s*)?"cards":\s*\[/);
  const groups = [];
  // split avec 2 groupes de capture : titre à parts[i], pills à parts[i+1],
  // corps à parts[i+2] (pas de +2 comme avant).
  for (let i = 1; i < parts.length; i += 3) {
    const title = parts[i];
    const pills = parts[i + 1];
    const seg = parts[i + 2];
    const cards = [...seg.matchAll(/\{\s*"type":\s*"(\w+)",\s*"title":\s*"([^"]+)"([^}]*?)\}/g)]
      .map(([, type, cardTitle, rest]) => {
        const series = rest.match(/"series":\s*"([^"]+)"/);
        const unit = rest.match(/"unit":\s*"([^"]+)"/);
        const card = { type, title: cardTitle };
        if (series) card.series = series[1];
        if (unit) card.unit = unit[1];
        return card;
      });
    const group = { title, cards };
    if (pills) group.pills = pills;
    groups.push(group);
  }
  if (groups.length === 0) throw new Error("Aucun groupe Valorisation parsé");
  return groups;
}

// Parse `config.DIVIDEND_METRIC_UNITS` (même forme que METRIC_UNITS).
export function parsePyDividendMetricUnits(source) {
  const block = source.match(/DIVIDEND_METRIC_UNITS\s*:\s*dict\[str,\s*str\]\s*=\s*\{([\s\S]*?)\n\}/);
  if (!block) return {};
  const out = {};
  for (const m of block[1].matchAll(/"([^"]+)":\s*"([^"]+)"/g)) out[m[1]] = m[2];
  return out;
}


// Parse `config.WATCH_TIERS` (tuple de dicts id/label/hint). Découpage sur les
// frontières `{"id":` : robuste aux apostrophes et aux accents des libellés.
export function parsePyWatchTiers(source) {
  const block = source.match(/WATCH_TIERS[^=]*=\s*\(([\s\S]*?)\n\)/);
  if (!block) throw new Error("WATCH_TIERS introuvable dans config.py");
  const tiers = block[1].split(/\{"id":\s*/).slice(1).map((seg) => {
    const id = Number(seg.slice(0, seg.indexOf(",")));
    const label = seg.match(/"label":\s*"([^"]+)"/)?.[1];
    const hint = seg.match(/"hint":\s*"([^"]+)"/)?.[1];
    if (!label || !hint) throw new Error(`Tier ${id} : label/hint introuvable`);
    return { id, label, hint };
  });
  if (tiers.length === 0) throw new Error("Aucun tier de watchlist parsé");
  return tiers;
}
