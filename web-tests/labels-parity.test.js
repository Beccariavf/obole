import { describe, expect, it } from "vitest";
import {
  appSource,
  loadApp,
  metaFromConfig,
  parsePyDividendColors,
  parsePyDividendGroups,
  parsePyLabelList,
  parsePyLabelPolarity,
  parsePyQuantGroups,
  parsePyRatioThresholds,
  parsePyStatGroups,
  readConfigSource,
  readStyleSource,
} from "./helpers/load-app.js";

// #06 : le front ne redéfinit plus aucun seuil — il les reçoit de /api/meta
// (source unique `config.py`) via `applyMeta`. Ce test vérifie que le payload
// construit depuis config.py est bien celui que le JS consomme, et qu'aucun
// seuil littéral ne subsiste dans app.js.
const LABEL_KEYS = ["distance", "ecart", "perf", "potential", "beta", "corr"];

describe("source unique des seuils (/api/meta -> app.js)", () => {
  const configSource = readConfigSource();
  const meta = metaFromConfig(configSource);

  it("app.js n'a plus aucun seuil littéral (labels, ratios, polarité)", () => {
    const src = appSource();
    // Les listes de labels et le dict de ratios ne doivent plus être définis
    // en dur (ils arrivent de /api/meta). On cherche les motifs qui trahiraient
    // une réintroduction de seuils côté client.
    expect(src).not.toMatch(/distance:\s*\[\[-2/);
    expect(src).not.toMatch(/"Marge opérationnelle":\s*\[5/);
    expect(src).not.toMatch(/good:\s*v\s*<\s*35/);
    expect(src).not.toMatch(/good:\s*v\s*>=\s*4/);
    // La polarité et les fenêtres ne sont plus des constantes littérales.
    expect(src).not.toMatch(/const\s+REG_YEARS_DEFAULT\s*=\s*20/);
    expect(src).not.toMatch(/const\s+BETA_MIN_POINTS\s*=\s*20/);
  });

  it("applyMeta charge les seuils de config.py dans le front", () => {
    const app = loadApp();
    app.applyMeta(meta);
    for (const key of LABEL_KEYS) {
      expect(app.LABELS[key]).toEqual(parsePyLabelList(configSource, labelPyName(key)));
    }
    expect(app.RATIO_THRESHOLDS).toEqual(parsePyRatioThresholds(configSource));
    expect(app.LABEL_POLARITY).toEqual(parsePyLabelPolarity(configSource));
    expect(app.REG_YEARS_DEFAULT).toBe(meta.reg_years_default);
    expect(app.REG_YEARS_FINANCIAL).toBe(meta.reg_years_financial);
    expect(app.BETA_MIN_POINTS).toBe(meta.beta_min_points);
    // ρ et horizons de potentiel sont AUSSI consommés (source unique complète).
    expect(app.CORR_MIN_POINTS).toBe(meta.corr_min_points);
    expect(app.POTENTIAL_HORIZONS).toEqual(meta.potential_horizons);
  });

  it("le payload /api/meta ne contient aucun champ mort", () => {
    // Tout champ sérialisé par la route doit être consommé par applyMeta : on
    // verrouille la liste pour qu'un champ ajouté côté serveur sans usage front
    // soit visible.
    expect(Object.keys(meta).sort()).toEqual([
      "beta_min_points", "chart_heights", "checkpoint_label_max", "corr_min_points",
      "dividend_cagr_horizons", "dividend_colors", "dividend_default_window_years",
      "dividend_groups", "dividend_min_window_years", "fundamental_metrics",
      "label_polarity", "labels", "metric_units", "portfolio_corr_annotate_max",
      "portfolio_corr_min_obs", "portfolio_tag_max", "potential_horizons", "quant_groups",
      "ratio_thresholds", "reg_years_default", "reg_years_financial",
      "valuation_color_ratios", "valuation_groups", "valuation_horizon_years",
      "valuation_matrix", "valuation_metrics", "valuation_period_default",
      "valuation_periods", "valuation_target_default",
    ]);
  });

  it("la taxonomie des comptes vient de config.py (source unique)", () => {
    const app = loadApp();
    app.applyMeta(meta);
    // Le front lit les colonnes éditables/calculées depuis /api/meta : aucun nom
    // de métrique n'est écrit en dur dans exportcsv.js.
    expect(app.FUNDAMENTAL_METRICS).toEqual(meta.fundamental_metrics);
    const roles = new Set(app.FUNDAMENTAL_METRICS.map((m) => m.role));
    expect([...roles].sort()).toEqual(["derived", "source"]);
    expect(app.FUNDAMENTAL_METRICS.some((m) => m.name === "Chiffre d'affaires")).toBe(true);
    expect(app.FUNDAMENTAL_METRICS.some((m) => m.name === "Marge nette" && m.role === "derived")).toBe(true);
    // L'union couvre le schéma financier (aperçu du template d'une banque).
    expect(app.FUNDAMENTAL_METRICS.some((m) => m.name === "Total de l'actif" && m.role === "source")).toBe(true);
  });

  it("la taxonomie du Quantitatif vient de config.py (source unique)", () => {
    const app = loadApp();
    app.applyMeta(meta);
    // Le front ne définit plus ses cartes : il reçoit le plan exact de config.py.
    expect(app.QUANT_GROUPS).toEqual(parsePyQuantGroups(configSource));
    // Principe de lisibilité verrouillé : AUCUN combo (une métrique par graphe).
    for (const g of app.QUANT_GROUPS) {
      for (const c of g.cards) {
        expect(["line", "bars", "shares", "cagr"]).toContain(c.type);
      }
    }
  });

  it("l'unité d'affichage des métriques vient de config.py (source unique)", () => {
    const app = loadApp();
    app.applyMeta(meta);
    expect(app.METRIC_UNITS).toEqual(meta.metric_units);
    // Le front lit l'unité depuis la source unique, pas d'un Set en dur.
    expect(app.metricUnit("ROE")).toBe("pct");
    expect(app.metricUnit("PER")).toBe("mult");
    expect(app.metricUnit("Chiffre d'affaires")).toBe("money");
  });

  it("la taxonomie du Dividende vient de config.py (source unique)", () => {
    const app = loadApp();
    app.applyMeta(meta);
    expect(app.DIVIDEND_GROUPS).toEqual(parsePyDividendGroups(configSource));
    expect(app.DIVIDEND_COLORS).toEqual(parsePyDividendColors(configSource));
    const types = app.DIVIDEND_GROUPS.flatMap((g) => g.cards.map((c) => c.type));
    for (const t of types) {
      expect(["kpi", "yield", "divbars", "divgrowth", "lines", "stacked"]).toContain(t);
    }
  });

  it("les horizons de CAGR du dividende viennent de config.py", () => {
    const app = loadApp();
    app.applyMeta(meta);
    expect(app.DIVIDEND_CAGR_HORIZONS).toEqual(meta.dividend_cagr_horizons);
  });

  it("la fenêtre par défaut et les hauteurs de tracé viennent de config.py", () => {
    const app = loadApp();
    app.applyMeta(meta);
    // Source unique : aucune valeur littérale côté JS (fenêtre 10/5 ans, hauteurs).
    expect(app.DIVIDEND_DEFAULT_WINDOW_YEARS).toBe(meta.dividend_default_window_years);
    expect(app.DIVIDEND_MIN_WINDOW_YEARS).toBe(meta.dividend_min_window_years);
    expect(app.CHART_HEIGHTS).toEqual(meta.chart_heights);
    // Étiquettes (#17.6) et seuils de risque (#17.3) : mêmes sources uniques.
    expect(app.PORTFOLIO_TAG_MAX).toBe(meta.portfolio_tag_max);
    expect(app.PORTFOLIO_CORR_MIN_OBS).toBe(meta.portfolio_corr_min_obs);
    expect(app.PORTFOLIO_CORR_ANNOTATE_MAX).toBe(meta.portfolio_corr_annotate_max);
  });

  it("le CSS des hauteurs coïncide avec config.py (conteneur = layout Plotly)", () => {
    const css = readStyleSource();
    // Les variables CSS des hauteurs doivent valoir les constantes config.py :
    // sinon Plotly laisse du blanc (conteneur plus haut) ou déborde.
    const h = meta.chart_heights;
    expect(css).toContain(`--chart-h-hero: ${h.hero}px`);
    expect(css).toContain(`--chart-h-mini: ${h.mini}px`);
    expect(css).toContain(`--chart-h-dividend-hero: ${h.dividend_hero}px`);
    expect(css).toContain(`--chart-h-val-hero: ${h.valuation_hero}px`);
    expect(css).toContain(`--chart-h-pf-resume: ${h.portfolio_resume}px`);
    expect(css).toContain(`--chart-h-pf-donut: ${h.portfolio_donut}px`);
    expect(css).toContain(`--chart-h-pf-drawdown: ${h.portfolio_drawdown}px`);
    expect(css).toContain(`--chart-h-pf-corr: ${h.portfolio_corr}px`);
    expect(css).toContain(`--chart-h-pf-corr-test: ${h.portfolio_corr_test}px`);
    expect(css).toContain(`--chart-h-pf-monthly: ${h.portfolio_monthly}px`);
    expect(css).toContain(`--chart-h-pf-contrib: ${h.portfolio_contrib}px`);
    expect(css).toContain(`--chart-h-detail: ${h.detail}px`);
    // Le conteneur des mini-charts et la modale lisent ces variables (pas de px en dur).
    expect(css).toMatch(/\.mini \.mini-chart[^}]*height: var\(--chart-h-mini\)/);
    expect(css).toMatch(/\.mini\.wide \.mini-chart[^}]*height: var\(--chart-h-dividend-hero\)/);
    expect(css).toMatch(/\.card\.mini \.pf-chart[^}]*height: var\(--chart-h-pf-resume\)/);
    expect(css).toMatch(/\.card\.mini \.pf-donut[^}]*height: var\(--chart-h-pf-donut\)/);
    expect(css).toMatch(/\.detail-chart[^}]*height: var\(--chart-h-detail\)/);
    expect(css).toMatch(/\.mini \.pf-corr-test-chart[^}]*height: var\(--chart-h-pf-corr-test\)/);
    // L'ancienne hauteur « mini wide » ne doit plus subsister (retirée).
    expect(css).not.toContain("mini-wide");
  });

  it("scored() calcule la couleur depuis la polarité de config.py", () => {
    const app = loadApp();
    app.applyMeta(meta);
    // écart-type : seuil 35 (config) — borne incluse/exclue identique au serveur.
    expect(app.scored(34.9, "ecart").good).toBe(true);
    expect(app.scored(35, "ecart").good).toBe(false);
    // perf : seuil 4 (config).
    expect(app.scored(4, "perf").good).toBe(true);
    expect(app.scored(3.9, "perf").good).toBe(false);
    // distance : décoté (z<0) = bon.
    expect(app.scored(-1, "distance").good).toBe(true);
    expect(app.scored(1, "distance").good).toBe(false);
  });

  // QUALITY_LABELS est calculé côté serveur (aucun miroir client) : on le
  // constate explicitement pour qu'une future duplication soit visible.
  it("QUALITY_LABELS n'a pas de miroir client (score calculé serveur)", () => {
    const app = loadApp();
    expect(app.LABELS.quality).toBeUndefined();
    expect(appSource()).not.toMatch(/QUALITY_LABELS/);
  });

  it("classify() ne lève pas si les seuils ne sont pas chargés", () => {
    // Garde-fou : si /api/meta échoue, LABELS restent vides. classify doit
    // renvoyer null (pas d'exception), et scored() rester neutre.
    const { classify } = loadApp();
    expect(() => classify(5, [])).not.toThrow();
    expect(classify(5, [])).toBeNull();
    expect(classify(5, undefined)).toBeNull();
  });

  it("portfolio_stat_groups : `signed` vient de config.py (variation vs niveau)", () => {
    // Revue #17.4 finding #5 : seules les VARIATIONS (pente, potentiels) sont
    // signées d'un « + » côté front. La décision vit dans config.py, pas dans le
    // JS : on parse la source Python et on vérifie qu'exactement ces trois clés
    // portent `signed`. Le payload consommé par `portfolio.js` vient du service
    // (`stat_groups`), pas de /api/meta — cf. test « aucun champ mort ».
    const pyGroups = parsePyStatGroups(configSource);
    const signedKeys = pyGroups
      .flatMap((g) => g.metrics.filter((m) => m.signed).map((m) => m.key))
      .sort();
    expect(signedKeys).toEqual(["pot_10y", "pot_5y", "slope"]);
    // Les niveaux (marges, ROE, ROCE, agilité) ne sont JAMAIS signés.
    const levelKeys = pyGroups
      .flatMap((g) => g.metrics.filter((m) => !m.signed).map((m) => m.key));
    expect(levelKeys).toContain("gross_margin");
    expect(levelKeys).toContain("roe");
    expect(levelKeys).toContain("agility");
  });
});

function labelPyName(jsKey) {
  return {
    distance: "DISTANCE_SIGMA_LABELS",
    ecart: "ECART_TYPE_LABELS",
    perf: "PERF_LABELS",
    potential: "POTENTIAL_LABELS",
    beta: "BETA_LABELS",
    corr: "CORR_LABELS",
  }[jsKey];
}
