import { describe, expect, it } from "vitest";
import { loadApp, metaFromConfig, readConfigSource, readDividendSource } from "./helpers/load-app.js";

// Section Dividende : les cartes viennent de la taxonomie `config.DIVIDEND_GROUPS`
// (source unique via /api/meta). Ce fichier verrouille le filtrage par données
// disponibles, les KPI, la fréquence déduite, les CAGR, les pastilles et les
// rendements continus (dont l'alignement dates <-> série).
const app = loadApp();
app.applyMeta(metaFromConfig(readConfigSource()));

// Fiche de test : dividende long (par action) + séries annuelles + courbes continues.
function fiche({ withDividend = true } = {}) {
  const comp = app.obole();
  comp.$nextTick = (fn) => fn();
  comp.activeSection = "dividende";
  comp.data = {
    kind_payload: "stock",
    identity: { last_price: 100, currency: "EUR" },
    chart: {
      dates: ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"],
      price_raw: [100, 101, 102, 103, 104, 105],
      div_yield: [2, 2.1, 2.2, 2.3, 2.4, 2.5],
      sh_yield: [3, 3.1, 3.2, 3.3, 3.4, 3.5],
    },
    fundamentals: {
      kind: "industrial",
      years: [2023, 2024, 2025],
      metrics: {},
      growth: null,
      valuation: null,
      dividend: withDividend ? {
        yield_pct: 4.7,
        payout_pct: 98.6,
        shareholder_payout_pct: 101.9,
        buybacks_available: false,
        per_share: { 2020: 1.0, 2021: 1.1, 2022: 1.2, 2023: 1.3, 2024: 1.4, 2025: 1.5 },
        events: {
          "2024-06-15": 0.7, "2024-12-15": 0.6, "2025-06-15": 0.7, "2025-12-15": 0.7,
        },
        buyback_history: { 2023: 1000000, 2024: 2000000, 2025: 3000000 },
        dividend_paid_history: { 2023: 500000, 2024: 600000, 2025: 700000 },
        payout_history: {
          earnings_payout: { 2023: 60, 2024: 65, 2025: 70 },
          fcf_payout: { 2023: 40, 2024: 45, 2025: 50 },
        },
        last_payment_value: 1.25,
        last_payment_date: "2026-05-28",
        // Statistiques précalculées serveur (engine/dividends) : le front les
        // affiche telles quelles (source unique, aucun recalcul).
        stats: {
          increase_years: 5,
          no_cut_years: 5,
          cagr: { 5: 8.447, 10: null },
          frequency: "Semestriel",
          perf_pct: 50,
          growth: { 2021: 10, 2022: 9.09, 2023: 8.33, 2024: 7.69, 2025: 7.14 },
        },
      } : null,
      dividend_series: withDividend ? {
        years: [2023, 2024, 2025],
        metrics: {
          "Earnings Payout Ratio": [60, 65, 70],
          "FCF Payout Ratio": [40, 45, 50],
          "Dividends versés": [500000, 600000, 700000],
          "Rachats d'actions": [1000000, 2000000, 3000000],
        },
      } : null,
    },
  };
  return comp;
}

describe("Dividende — taxonomie et filtrage", () => {
  it("sans dividende, la section est vide", () => {
    const comp = fiche({ withDividend: false });
    expect(comp.dividendGroups()).toEqual([]);
  });

  it("les cartes viennent de DIVIDEND_GROUPS (aucun type inventé)", () => {
    const comp = fiche();
    const types = comp.dividendGroups().flatMap((g) => g.cards.map((c) => c.type));
    for (const t of types) {
      expect(["kpi", "yield", "divbars", "divgrowth", "lines", "stacked"]).toContain(t);
    }
    // Le rendement continu n'apparaît que si la série existe dans le payload.
    expect(types).toContain("yield");
    expect(types).toContain("kpi");
    expect(types).toContain("stacked");
  });

  it("une carte yield est omise si la série est absente du payload", () => {
    const comp = fiche();
    comp.data.fundamentals.dividend.buybacks_available = true;
    delete comp.data.chart.sh_yield;
    const titles = comp.dividendGroups().flatMap((g) => g.cards.map((c) => c.title));
    expect(titles).not.toContain("Shareholder Yield");
    expect(titles).toContain("Dividend Yield");
  });

  it("Shareholder Yield n'est affiché QUE si des rachats existent", () => {
    // Décision produit révisée : sans rachats, la courbe se confondrait
    // exactement avec Dividend Yield (doublon) -> on l'omet.
    const comp = fiche(); // buybacks_available = false
    const titles = comp.dividendGroups().flatMap((g) => g.cards.map((c) => c.title));
    expect(titles).not.toContain("Shareholder Yield");
    expect(titles).toContain("Dividend Yield");
  });

  it("Shareholder Yield réapparaît dès qu'un rachat existe", () => {
    const comp = fiche();
    comp.data.fundamentals.dividend.buybacks_available = true;
    const titles = comp.dividendGroups().flatMap((g) => g.cards.map((c) => c.title));
    expect(titles).toContain("Shareholder Yield");
    expect(titles).toContain("Dividend Yield");
  });

  it("Shareholder Yield reste omis si sa série manque du payload", () => {
    const comp = fiche();
    comp.data.fundamentals.dividend.buybacks_available = true;
    delete comp.data.chart.sh_yield;
    const titles = comp.dividendGroups().flatMap((g) => g.cards.map((c) => c.title));
    expect(titles).not.toContain("Shareholder Yield");
    expect(titles).toContain("Dividend Yield");
  });
});

describe("Dividende — métriques clés", () => {
  it("expose yield, payout, régularité, CAGR, fréquence et dernier paiement", () => {
    const comp = fiche();
    const kpis = comp.dividendKeyMetrics();
    const titles = kpis.map((k) => k.title);
    expect(titles).toContain("Yield (TTM)");
    expect(titles).toContain("Payout (TTM)");
    expect(titles).toContain("Années d'augmentation");
    expect(titles).toContain("Années sans baisse");
    expect(titles).toContain("CAGR 5A");
    expect(titles).toContain("Fréquence");
    expect(titles).toContain("Dernier paiement");
  });

  it("le prochain paiement est toujours « — » (jamais fourni par la source)", () => {
    const comp = fiche();
    const next = comp.dividendKeyMetrics().find((k) => k.title === "Prochain paiement");
    expect(next).toBeDefined();
    expect(next.display).toBe("—");
  });

  it("la fréquence vient du serveur (stats.frequency), pas d'un calcul client", () => {
    const comp = fiche();
    const freq = comp.dividendKeyMetrics().find((k) => k.title === "Fréquence");
    expect(freq.display).toBe("Semestriel");
  });

  it("la régularité (années d'augmentation / sans baisse) vient du serveur", () => {
    const comp = fiche();
    const inc = comp.dividendKeyMetrics().find((k) => k.title === "Années d'augmentation");
    const noCut = comp.dividendKeyMetrics().find((k) => k.title === "Années sans baisse");
    expect(inc.display).toBe("5 ans");
    expect(noCut.display).toBe("5 ans");
    // Le front ne recalcule pas : il lit `dividend.stats` (source unique engine).
    expect(comp.data.fundamentals.dividend.stats.increase_years).toBe(5);
  });

  it("le CAGR vient du serveur (stats.cagr)", () => {
    const comp = fiche();
    const cagr5 = comp.dividendKeyMetrics().find((k) => k.title === "CAGR 5A");
    expect(cagr5.display).toBe("+8.45 %");
  });
});

describe("Dividende — pastilles et état vide", () => {
  it("les pastilles de performance affichent Perf et CAGR", () => {
    const comp = fiche();
    const pills = comp.dividendPerfPills();
    expect(pills.map((p) => p.label)).toEqual(["Perf", "CAGR"]);
  });

  it("les pastilles de ratios lisent la dernière valeur disponible", () => {
    const comp = fiche();
    const card = { type: "lines", metrics: ["Earnings Payout Ratio", "FCF Payout Ratio"] };
    const pills = comp.dividendSeriesPills(card);
    expect(pills.map((p) => p.display)).toEqual(["70 %", "50 %"]);
  });

  it("une carte de dividende par action est vide avec moins de 2 années", () => {
    const comp = fiche();
    comp.data.fundamentals.dividend.per_share = { 2025: 1.0 };
    expect(comp.dividendCardEmpty({ type: "divbars" })).toBe(true);
    expect(comp.dividendCardEmpty({ type: "kpi" })).toBe(false);
  });

  it("la puce « N ans » reflète le nombre d'années réellement disponibles", () => {
    const comp = fiche();
    expect(comp.dividendCardSpan({ type: "divbars" })).toBe(6);
    expect(comp.dividendCardSpan({ type: "lines", metrics: ["Earnings Payout Ratio"] })).toBe(3);
  });
});

describe("Dividende — rendements continus", () => {
  it("les stats de fenêtre (High/Médiane/Low) sont recalculées côté client", () => {
    const comp = fiche();
    const stats = comp._yieldStats([2, 2.1, 2.2, 2.3, 2.4, 2.5]);
    expect(stats.high).toBe(2.5);
    expect(stats.low).toBe(2);
    expect(stats.median).toBeCloseTo(2.25, 5);
  });

  it("les pastilles de rendement exposent High / Médiane / Low", () => {
    const comp = fiche();
    comp._yieldStatsCache = {};
    comp._yieldStatsCache["dividend-yield"] = { median: 2.25, high: 2.5, low: 2 };
    const pills = comp.yieldPills({ id: "dividend-yield" });
    expect(pills.map((p) => p.label)).toEqual(["High", "Médiane", "Low"]);
  });

  // Parité date <-> série : la courbe de rendement est alignée 1:1 sur les dates
  // (le serveur décime les deux avec le MÊME pas). On capture les traces Plotly
  // pour vérifier que `div_yield[i]` est bien apparié à `dates[i]`, sur la
  // fenêtre par défaut (10/5 ans — le zoom sert à voir plus loin).
  it("la courbe de rendement apparié div_yield[i] <-> dates[i] (alignement)", () => {
    const comp = fiche();
    let captured = null;
    globalThis.Plotly = { react: (el, traces) => { captured = traces[0]; } };
    comp._yieldStatsCache = {};
    // Série courte (< 5 ans) : la fenêtre par défaut couvre tout l'historique.
    const [i0, i1] = comp.defaultDateRange(comp.data.chart.dates);
    comp.drawYieldCard("mc-dividend-yield", { id: "dividend-yield", title: "Dividend Yield", series: "div_yield" });
    const dates = comp.data.chart.dates;
    expect(captured.x).toEqual(dates.slice(i0, i1 + 1));
    expect(captured.y).toEqual(comp.data.chart.div_yield.slice(i0, i1 + 1));
    // Chaque point y correspond au même index de dates : l'alignement est garanti.
    for (let i = 0; i < captured.x.length; i++) {
      const di = dates.indexOf(captured.x[i]);
      expect(comp.data.chart.div_yield[di]).toBe(captured.y[i]);
    }
  });

  it("le rendement pour l'actionnaire est aligné sur le même index que les dates", () => {
    const comp = fiche();
    let captured = null;
    globalThis.Plotly = { react: (el, traces) => { captured = traces[0]; } };
    comp._yieldStatsCache = {};
    comp.drawYieldCard("mc-shareholder-yield", { id: "shareholder-yield", title: "Shareholder Yield", series: "sh_yield" });
    expect(captured.x.length).toBe(comp.data.chart.sh_yield.length);
    for (let i = 0; i < captured.x.length; i++) {
      const di = comp.data.chart.dates.indexOf(captured.x[i]);
      expect(captured.y[i]).toBe(comp.data.chart.sh_yield[di]);
    }
  });

  it("la fenêtre par défaut limite les séries longues à 10 ans", () => {
    const comp = fiche();
    // 25 années : la fenêtre par défaut retient les 10 dernières.
    comp.data.chart.dates = Array.from({ length: 25 }, (_, i) => `${2000 + i}-01-01`);
    comp.data.chart.div_yield = Array.from({ length: 25 }, (_, i) => i);
    const [i0, i1] = comp.defaultDateRange(comp.data.chart.dates);
    expect(i1).toBe(24);
    expect(2024 - Number(comp.data.chart.dates[i0].slice(0, 4))).toBeLessThanOrEqual(10);
    expect(i0).toBeGreaterThan(0);
  });

  it("la fenêtre par défaut retombe sur 5 ans puis tout si l'historique est court", () => {
    const comp = fiche();
    expect(comp.defaultWindowYears(25)).toBe(10);
    expect(comp.defaultWindowYears(7)).toBe(5);
    expect(comp.defaultWindowYears(3)).toBe(3);
  });

  it("la carte Dividend Yield est la seule en pleine largeur (héro de section)", () => {
    const comp = fiche();
    // Le caractère « wide » vient de la taxonomie (config.DIVIDEND_GROUPS), pas
    // d'un type : seule la carte marquée `wide` l'est.
    expect(comp.isWideCard({ type: "yield", wide: true })).toBe(true);
    for (const c of [{ type: "yield" }, { type: "divbars" }, { type: "divgrowth" }, { type: "lines" }, { type: "stacked" }, { type: "kpi" }]) {
      expect(comp.isWideCard(c)).toBe(false);
    }
    // La taxonomie config marque bien Dividend Yield (et lui seul) en wide.
    const wideTitles = app.DIVIDEND_GROUPS.flatMap((g) => g.cards).filter((c) => c.wide).map((c) => c.title);
    expect(wideTitles).toEqual(["Dividend Yield"]);
  });

  it("le tracé des rendements utilise la hauteur héro de la section (300) hors zoom", () => {
    const comp = fiche();
    let captured = null;
    globalThis.Plotly = { react: (el, traces, layout) => { captured = layout; } };
    comp._yieldStatsCache = {};
    comp.drawYieldCard("mc-dividend-yield", { id: "dividend-yield", title: "Dividend Yield", series: "div_yield", wide: true });
    expect(captured.height).toBe(app.CHART_HEIGHTS.dividend_hero);
  });

  it("une carte de rendement NON wide garde la hauteur mini (pas de débordement)", () => {
    const comp = fiche();
    let captured = null;
    globalThis.Plotly = { react: (el, traces, layout) => { captured = layout; } };
    comp._yieldStatsCache = {};
    // Shareholder Yield n'est pas `wide` : le layout doit rester à 200 px pour
    // coïncider avec le conteneur CSS (sinon la courbe déborde sur les pastilles).
    comp.drawYieldCard("mc-shareholder-yield", { id: "shareholder-yield", title: "Shareholder Yield", series: "sh_yield" });
    expect(captured.height).toBe(app.CHART_HEIGHTS.mini);
  });

  it("les presets de zoom exposent YTD / 1A / 5A / 10A / MAX (sans 3A)", () => {
    const comp = fiche();
    comp.data.chart.dates = Array.from({ length: 40 }, (_, i) => `${1990 + i}-01-01`);
    comp.initRange();
    // 10A : borne gauche à ~10 ans du dernier point (nouveau preset).
    comp.detailPreset(10);
    const [s10, e10] = comp.visibleRange();
    expect(e10).toBe(39);
    expect(2029 - Number(comp.data.chart.dates[s10].slice(0, 4))).toBeLessThanOrEqual(10);
    // 5A reste plus court que 10A.
    comp.detailPreset(5);
    expect(comp.visibleRange()[0]).toBeGreaterThan(s10);
  });
});

describe("Dividende — aucune logique de seuil dupliquée côté front", () => {
  it("le front ne recalcule ni fréquence, ni régularité, ni CAGR (source unique serveur)", () => {
    const src = readDividendSource();
    // La fréquence et la régularité sont calculées par engine/dividends et lues
    // dans `dividend.stats` : aucun seuil (fenêtre, compteur) ne doit subsister.
    expect(src).not.toMatch(/366/);
    expect(src).not.toMatch(/count\s*>=/);
    expect(src).not.toMatch(/Trimestriel|Semestriel/);
    // Pas de recalcul de CAGR / hausse : ces helpers ont été retirés.
    expect(src).not.toMatch(/_divCagr|_divIncreaseYears|_divNoCutYears|_divFrequency/);
  });
});

describe("Dividende — badge de fiabilité", () => {
  it("signale les rachats absents et l'historique de payout court", () => {
    const comp = fiche(); // buybacks_available = false, 3 années de séries
    const warnings = comp.dividendWarnings();
    expect(warnings.some((w) => w.includes("Rachats"))).toBe(true);
    expect(warnings.some((w) => w.includes("3 an"))).toBe(true);
  });

  it("aucun badge quand la source est complète", () => {
    const comp = fiche();
    comp.data.fundamentals.dividend.buybacks_available = true;
    comp.data.fundamentals.dividend_series.years = [2020, 2021, 2022, 2023, 2024, 2025];
    comp.data.fundamentals.dividend_series.metrics["Earnings Payout Ratio"] = [1, 2, 3, 4, 5, 6];
    expect(comp.dividendWarnings()).toEqual([]);
  });
});

describe("Dividende — zoom : plage partagée avec le héro", () => {
  it("le preset écrit rangeStart/rangeEnd (même source que le curseur du héro)", () => {
    const comp = fiche();
    comp.data.chart.dates = Array.from({ length: 20 }, (_, i) => `${2005 + i}-01-01`);
    comp.initRange();
    comp.detailPreset(3);
    // 3 ans avant le dernier point -> plage partagée, pas un état séparé.
    expect(comp.rangeEnd).toBe(19);
    expect(comp.rangeStart).toBeGreaterThan(0);
    expect(comp.rangeStart).toBeLessThan(19);
    expect(comp.detailRange).toBeUndefined();
    // Le libellé reflète la MÊME plage que le héro (visibleRange).
    const [s, e] = comp.visibleRange();
    expect(comp.rangeStart).toBe(s);
    expect(comp.rangeEnd).toBe(e);
    expect(comp.detailRangeLabel()).toContain(String(2005 + s));
  });

  it("le preset MAX couvre tout l'historique", () => {
    const comp = fiche();
    comp.initRange();
    comp.detailPreset("max");
    expect(comp.rangeStart).toBe(0);
    expect(comp.rangeEnd).toBe(comp.data.chart.dates.length - 1);
  });

  it("l'ouverture de la modale ancre la plage sur la fenêtre par défaut de la carte", () => {
    // 25 ans d'historique : le héro est à 20 ans par défaut, mais la carte
    // Dividende n'affiche que 10 ans -> la modale doit s'ouvrir sur ces 10 ans
    // (pas de saut visuel), tout en écrivant la plage PARTAGÉE.
    const comp = fiche();
    comp.data.chart.dates = Array.from({ length: 25 }, (_, i) => `${2000 + i}-01-01`);
    comp.initRange(); // plage héro 20 ans
    comp.$nextTick = (fn) => fn();
    comp.openChartDetail({ id: "dividend-yield", type: "yield", title: "Dividend Yield", series: "div_yield" });
    const [s, e] = comp.visibleRange();
    expect(e).toBe(24);
    expect(s).toBeGreaterThan(0);
    // La borne gauche correspond à la fenêtre par défaut (10 ans), pas aux 20 du héro.
    expect(2024 - Number(comp.data.chart.dates[s].slice(0, 4))).toBeLessThanOrEqual(10);
  });
});
