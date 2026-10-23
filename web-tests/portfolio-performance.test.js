import { describe, expect, it, vi, beforeEach } from "vitest";

import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { api } from "../src/obole/web/api.js";
import { C } from "../src/obole/web/theme.js";
import { readIndexSource } from "./helpers/load-app.js";

// #17.4 (Performance) : logique du mixin testée sans DOM. On vérifie la
// délégation à `api.js` (aucun fetch direct), la lecture des stats/groupes
// (source unique du payload), le tableau mensuel et le détail par titre.

function comp(overrides = {}) {
  return { ...portfolioMixin, ...overrides };
}

const PERF = {
  stat_groups: [
    { id: "marges", title: "Marges", metrics: [
      { key: "gross_margin", label: "Marge brute", unit: "pct" },
    ] },
    { id: "valorisation", title: "Valorisation", metrics: [
      { key: "per", label: "P/E", unit: "num" },
    ] },
  ],
  stats: {
    gross_margin: { value: 42.5, good: true },
    per: { value: null, good: null },
  },
  monthly: {
    months: 12,
    portfolio: { years: [2024], rows: [
      { year: 2024, months: { "1": 2.0, "2": null, "3": -1.0, "4": null, "5": null, "6": null,
        "7": null, "8": null, "9": null, "10": null, "11": null, "12": null }, total: 0.98 },
    ] },
    benchmark: { years: [2024], rows: [
      { year: 2024, months: { "1": 1.0, "2": null, "3": 0.5, "4": null, "5": null, "6": null,
        "7": null, "8": null, "9": null, "10": null, "11": null, "12": null }, total: 1.5 },
    ] },
  },
  risk_adjusted: {
    risk_free_pct: 0,
    periods: ["ttm", "max"],
    by_period: {
      ttm: { portfolio: { sharpe: 1.2, sortino: 1.8 }, benchmark: { sharpe: 0.9, sortino: 1.1 } },
      max: { portfolio: { sharpe: 0.8, sortino: 1.0 }, benchmark: { sharpe: 0.6, sortino: 0.7 } },
    },
    portfolio: { sharpe: 0.8, sortino: 1.0 },
    benchmark: { sharpe: 0.6, sortino: 0.7 },
  },
  contributions: { items: [{ ticker: "RI.PA", weight_pct: 60, perf_pct: 10, contribution_pct: 6 }],
    total_pct: 6 },
  table: [{ ticker: "RI.PA", name: null, weight_pct: 60, perf_pct: 10,
    contribution_pct: 6, market_value: 6000 }],
  retrospective: [
    { id: 1, ticker: "RI.PA", side: "buy", date: "2024-01-01", delta_pct: 5.0 },
  ],
};

describe("Performance — chargement (#17.4)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loadPortfolioPerformance délègue à api.portfolioPerformance", async () => {
    const spy = vi.spyOn(api, "portfolioPerformance").mockResolvedValue(PERF);
    const c = comp({ _pfMetaReady: true, pfBenchmark: "CW8.PA", pfPeriod: "max",
      portfolioAccountId: null, portfolioTag: "", $nextTick: (fn) => fn && fn(),
      drawPortfolioPerformance: vi.fn() });
    await c.loadPortfolioPerformance();
    expect(spy).toHaveBeenCalledWith(null, "CW8.PA", "max", "");
    expect(c.pfPerf).toBe(PERF);
    expect(c.pfPerfLoading).toBe(false);
  });

  it("un échec réseau pose l'erreur et n'altère pas le payload", async () => {
    vi.spyOn(api, "portfolioPerformance").mockRejectedValue(new Error("boom"));
    const c = comp({ _pfMetaReady: true, $nextTick: (fn) => fn && fn() });
    await c.loadPortfolioPerformance();
    expect(c.pfPerf).toBeNull();
    expect(c.pfPerfError).toMatch(/boom/);
  });

  it("replie la période de risque sur MAX si elle n'est plus couverte", async () => {
    const perf = { risk_adjusted: { periods: ["ttm", "max"] } };
    vi.spyOn(api, "portfolioPerformance").mockResolvedValue(perf);
    const c = comp({ _pfMetaReady: true, pfBenchmark: "CW8.PA", portfolioAccountId: null,
      portfolioTag: "", pfRiskPeriod: "5a", $nextTick: (fn) => fn && fn(),
      drawPortfolioPerformance: vi.fn() });
    await c.loadPortfolioPerformance();
    expect(c.pfRiskPeriod).toBe("max");
  });
});

describe("Performance — stats pondérées (#17.4)", () => {
  it("pfStatGroups lit la taxonomie du payload (source unique)", () => {
    const c = comp({ pfPerf: PERF });
    const groups = c.pfStatGroups();
    expect(groups.map((g) => g.id)).toEqual(["marges", "valorisation"]);
    expect(groups[0].rows[0].key).toBe("gross_margin");
    expect(groups[0].rows[0].value).toBe(42.5);
  });

  it("une valeur nulle affiche « -- » (jamais un 0 trompeur)", () => {
    const c = comp({ pfPerf: PERF, fmt: (v) => String(v) });
    const row = c.pfStatGroups()[1].rows[0];
    expect(c.pfStatValue(row)).toBe("--");
  });

  it("un NIVEAU s'affiche sans signe, une VARIATION avec « + »", () => {
    // Revue #17.4 finding #5 : `pfStatValue` signait TOUT `unit === "pct"`, donc
    // les marges et retours sur capitaux s'affichaient « +42,5 % » alors qu'un
    // niveau n'est pas une variation — et la fiche entreprise ne les signe pas.
    // Le format vient désormais de `signed` (config.PORTFOLIO_STAT_GROUPS).
    const c = comp({ fmt: (v) => String(v) });
    // Niveau (marge brute) : aucun signe, même positif.
    expect(c.pfStatValue({ unit: "pct", value: 42.5, signed: false })).toBe("42.5 %");
    // Variation (pente, potentiel) : signe + sur une valeur positive.
    expect(c.pfStatValue({ unit: "pct", value: 42.5, signed: true })).toBe("+42.5 %");
    // Variation négative : le « - » vient du nombre, pas d'un préfixe.
    expect(c.pfStatValue({ unit: "pct", value: -7.2, signed: true })).toBe("-7.2 %");
  });

  it("pfStatGroups propage `signed` depuis la taxonomie", () => {
    const c = comp({
      pfPerf: {
        stat_groups: [
          { id: "marges", title: "Marges", metrics: [
            { key: "gross_margin", label: "Marge brute", unit: "pct" },
          ] },
          { id: "croissance", title: "Croissance", metrics: [
            { key: "slope", label: "Pente 20 ans", unit: "pct", signed: true },
          ] },
        ],
        stats: {
          gross_margin: { value: 42.5, good: true },
          slope: { value: 6.1, good: true },
        },
      },
    });
    const groups = c.pfStatGroups();
    expect(groups[0].rows[0].signed).toBe(false);
    expect(groups[1].rows[0].signed).toBe(true);
  });
});

describe("Performance — mensuels (#17.4)", () => {
  it("pfMonthlyChart : TTM = 12 derniers mois calendaires, portefeuille et benchmark alignés", () => {
    const c = comp({ pfPerf: PERF, pfPerfMonthSel: "ttm" });
    const ch = c.pfMonthlyChart();
    // TTM par défaut, donc aucune année sélectionnée dans le menu déroulant.
    expect(ch.selected).toBe("ttm");
    expect(ch.isTtm).toBe(true);
    expect(ch.activeYear).toBeNull();
    // Les années du sélecteur : présentes, ordre décroissant (une seule ici).
    expect(ch.years).toEqual([2024]);
    // 2024 : seuls 2 mois renseignés (janv +2 / mars -1) côté portefeuille.
    // L'année abrégée marque la première barre (ambiguïté TTM levée).
    expect(ch.labels).toEqual(["Janv 24", "Mars"]);
    expect(ch.portfolio).toEqual([2.0, -1.0]);
    // Benchmark aligné sur les mêmes mois (janv/mars), jamais décalé.
    expect(ch.benchmark).toEqual([1.0, 0.5]);
  });

  it("pfMonthlyChart : TTM ne dépasse pas 12 mois calendaires malgré un trou", () => {
    const rows = (vals) => ({ year: 2024, months: Object.fromEntries(
      vals.map((v, i) => [String(i + 1), v])), total: 0 });
    const c = comp({ pfPerfMonthSel: "ttm", pfPerf: { monthly: {
      months: 12,
      portfolio: { rows: [{ year: 2023, months: { "12": 1.0 }, total: 1.0 },
        rows([2.0, 1.0, 0.5, 0.3, 0.2, 0.1, 0.4, 0.6, 0.2, 0.1, 0.3, 0.5])] },
      benchmark: { rows: [] },
    } } });
    // Dernier point = 2024-12 ; fenêtre = 12 mois calendaires -> 2024-01..12.
    // 2023-12 est HORS fenêtre (13 mois en arrière), même s'il existe.
    expect(c.pfMonthlyChart().labels.length).toBe(12);
  });

  it("pfMonthlyChart : une année n'expose que ses mois présents (mois nul = trou)", () => {
    const c = comp({ pfPerf: PERF, pfPerfMonthSel: "2024" });
    const ch = c.pfMonthlyChart();
    expect(ch.selected).toBe("2024");
    expect(ch.isTtm).toBe(false);
    expect(ch.activeYear).toBe(2024);
    expect(ch.labels).toEqual(["Janv 24", "Mars"]);
    // Un mois absent n'est jamais un 0 : il n'entre pas dans la fenêtre.
    expect(ch.portfolio).not.toContain(0);
  });

  it("pfMonthlyChart : sélection d'année inconnue retombe sur TTM", () => {
    const c = comp({ pfPerf: PERF, pfPerfMonthSel: "1999" });
    const ch = c.pfMonthlyChart();
    expect(ch.selected).toBe("ttm");
    expect(ch.activeYear).toBeNull();
  });

  it("bascule TTM <-> année : la chip suit l'état", () => {
    const c = comp({ pfPerf: PERF, pfPerfMonthSel: "ttm",
      $nextTick: (fn) => fn && fn(), drawMonthlyChart: vi.fn() });
    expect(c.pfMonthlyChart().isTtm).toBe(true);
    c.setPfPerfMonth("2024");
    const ch = c.pfMonthlyChart();
    expect(ch.isTtm).toBe(false);
    expect(ch.activeYear).toBe(2024);
    c.setPfPerfMonth("ttm");
    expect(c.pfMonthlyChart().isTtm).toBe(true);
  });

  it("setPfPerfMonth mémorise et re-trace sans refetch (grain purement client)", () => {
    const draw = vi.fn();
    const c = comp({ pfPerfMonthSel: "ttm", $nextTick: (fn) => fn && fn(),
      drawMonthlyChart: draw });
    c.setPfPerfMonth("2024");
    expect(c.pfPerfMonthSel).toBe("2024");
    expect(draw).toHaveBeenCalledWith("pf-perf-monthly-plot");
    // Re-sélection identique : pas de redraw inutile.
    draw.mockClear();
    c.setPfPerfMonth("2024");
    expect(draw).not.toHaveBeenCalled();
  });

  it("pfMonthlyLegend : portefeuille bleu (accent), benchmark ambre (ma1)", () => {
    const c = comp({ pfBenchmark: "CW8.PA", pfBenchmarks: [], pfBenchmarkLabel: (t) => t,
      pfPerf: PERF, fmt: (v) => v.toFixed(2) });
    const les = c.pfMonthlyLegend();
    expect(les[0].label).toBe("Portefeuille");
    expect(les[1].color).toBe(C.ma1);
    expect(les[0].color).toBe(C.accent);
    // Valeur = rendement cumulé de la fenêtre (restaure le « total » du tableau).
    // TTM : portefeuille [2, -1] -> 1,02×0,99 = +0,98 % ; benchmark [1, 0,5] -> +1,505 %.
    expect(les[0].value).toBe("+0.98 %");
  });

  it("pfMonthCell rend « -- » sur un mois absent", () => {
    const c = comp({ fmt: (v) => String(v) });
    expect(c.pfMonthCell(null)).toBe("--");
    expect(c.pfMonthCell(2.0)).toBe("+2 %");
    expect(c.pfMonthCell(-1.0)).toBe("-1 %");
  });
});

describe("Performance — contribution par entreprise (#17.4)", () => {
  const CONTRIB = {
    contributions: {
      items: [
        { ticker: "AI.PA", name: "Air Liquide", contribution_pct: -2 },
        { ticker: "RI.PA", name: "Pernod Ricard", contribution_pct: 6 },
        { ticker: "MC.PA", name: null, contribution_pct: 1 },
        { ticker: "NA.PA", name: null, contribution_pct: null },
      ],
      total_pct: 5,
    },
  };

  it("pfContributionChart trie CROISSANT : le pire à gauche, le meilleur à droite", () => {
    const c = comp({ pfPerf: CONTRIB });
    const ch = c.pfContributionChart();
    // Croissant : -2, 1, 6 (la contribution null est écartée). Lecture de gauche
    // à droite = de la pire à la meilleure contribution.
    expect(ch.values).toEqual([-2, 1, 6]);
    // Repli nom -> ticker quand le nom manque.
    expect(ch.labels).toEqual(["Air Liquide", "MC.PA", "Pernod Ricard"]);
  });

  it("pfContributionChart colore par signe : bleu (accent) / rouge (bad)", () => {
    const c = comp({ pfPerf: CONTRIB });
    const ch = c.pfContributionChart();
    expect(ch.colors).toEqual([C.bad, C.accent, C.accent]);
  });

  it("pfContributionChart vide si le payload est absent", () => {
    const c = comp({ pfPerf: null });
    const ch = c.pfContributionChart();
    expect(ch.labels).toEqual([]);
    expect(ch.values).toEqual([]);
  });

  it("pfContributionTotalGood : true (bleu) / false (rouge) / null", () => {
    expect(comp({ pfPerf: { contributions: { total_pct: 3 } } }).pfContributionTotalGood()).toBe(true);
    expect(comp({ pfPerf: { contributions: { total_pct: -1 } } }).pfContributionTotalGood()).toBe(false);
    expect(comp({ pfPerf: { contributions: { total_pct: null } } }).pfContributionTotalGood()).toBeNull();
  });
});

describe("Performance — ratios ajustés au risque (#17.4)", () => {
  it("pfRiskAdjustedRows lit la période sélectionnée (défaut MAX)", () => {
    const c = comp({ pfPerf: PERF, pfRiskPeriod: "max", fmt: (v) => String(v) });
    const rows = c.pfRiskAdjustedRows();
    expect(rows[0].label).toBe("Ratio de Sharpe");
    // MAX : 0,8 / 0,6.
    expect(rows[0].pf).toBe("0.8");
    expect(rows[0].bench).toBe("0.6");
  });

  it("pfRiskAdjustedRows suit la période choisie (TTM)", () => {
    const c = comp({ pfPerf: PERF, pfRiskPeriod: "ttm", fmt: (v) => String(v) });
    const rows = c.pfRiskAdjustedRows();
    expect(rows[0].pf).toBe("1.2");
    expect(rows[1].bench).toBe("1.1");
  });

  it("pfRiskAdjustedRows retombe sur la forme historique si by_period manque", () => {
    const legacy = { risk_adjusted: {
      portfolio: { sharpe: 2.0, sortino: 2.5 }, benchmark: { sharpe: 1.0, sortino: 1.2 } } };
    const c = comp({ pfPerf: legacy, pfRiskPeriod: "max", fmt: (v) => String(v) });
    expect(c.pfRiskAdjustedRows()[0].pf).toBe("2");
  });

  it("pfRiskPeriods / pfRiskPeriodSelectable : sélecteur masqué si une seule période", () => {
    const two = comp({ pfPerf: PERF });
    expect(two.pfRiskPeriods()).toEqual(["ttm", "max"]);
    expect(two.pfRiskPeriodSelectable()).toBe(true);
    const one = comp({ pfPerf: { risk_adjusted: { periods: ["max"] } } });
    expect(one.pfRiskPeriodSelectable()).toBe(false);
  });

  it("setPfRiskPeriod mémorise sans refetch", () => {
    const c = comp({ pfRiskPeriod: "max" });
    c.setPfRiskPeriod("ttm");
    expect(c.pfRiskPeriod).toBe("ttm");
  });
});

describe("Performance — détail par titre (#17.4)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("openPerfDetail charge via /api/portfolio/security avec le benchmark global", async () => {
    const detail = { ticker: "RI.PA", benchmark: { ticker: "CW8.PA", label: "MSCI World" },
      chart: { dates: ["2024-01-01"], price_adj: [100] }, benchmark_curve: [400] };
    const spy = vi.spyOn(api, "portfolioSecurity").mockResolvedValue(detail);
    const c = comp({ pfBenchmark: "CW8.PA", $nextTick: (fn) => fn && fn(),
      drawPerfDetail: vi.fn() });
    await c.openPerfDetail("RI.PA");
    expect(spy).toHaveBeenCalledWith("RI.PA", "CW8.PA");
    expect(c.pfDetailOpen).toBe(true);
    expect(c.pfDetail).toBe(detail);
  });

  it("openPerfDetail repart du benchmark GLOBAL (la norme de l'espace)", async () => {
    const detail = { ticker: "RI.PA", benchmark: { ticker: "CW8.PA", label: "MSCI World" },
      chart: { dates: ["2024-01-01"], price_adj: [100] }, benchmark_curve: [400] };
    const spy = vi.spyOn(api, "portfolioSecurity").mockResolvedValue(detail);
    const c = comp({ pfBenchmark: "CW8.PA", pfDetailBenchmark: "ESE.PA",
      $nextTick: (fn) => fn && fn(), drawPerfDetail: vi.fn() });
    await c.openPerfDetail("RI.PA");
    // Un choix local précédent ne « colle » pas : on repart de la norme globale.
    expect(c.pfDetailBenchmark).toBe("CW8.PA");
    expect(spy).toHaveBeenCalledWith("RI.PA", "CW8.PA");
    expect(c.pfDetailOpen).toBe(true);
    expect(c.pfDetail).toBe(detail);
  });

  it("setPfDetailBenchmark recharge le détail SANS toucher à la norme globale", async () => {
    // Le sélecteur de la modale évite de quitter la fiche pour changer de
    // référence ; il ne persiste rien (le réglage global reste la norme).
    const spy = vi.spyOn(api, "portfolioSecurity").mockResolvedValue({ ticker: "RI.PA" });
    const save = vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true });
    const c = comp({ pfBenchmark: "CW8.PA", pfDetailBenchmark: "CW8.PA",
      pfDetail: { ticker: "RI.PA" }, $nextTick: (fn) => fn && fn(), drawPerfDetail: vi.fn() });
    await c.setPfDetailBenchmark("ese.pa"); // normalisé en majuscules
    expect(c.pfDetailBenchmark).toBe("ESE.PA");
    expect(spy).toHaveBeenCalledWith("RI.PA", "ESE.PA");
    expect(c.pfBenchmark).toBe("CW8.PA");
    expect(save).not.toHaveBeenCalled();
  });

  it("le sélecteur de la modale n'offre QUE la liste curée", () => {
    // Pas de ticker libre ici : « Autre… » vit dans le bandeau, où le choix est
    // mémorisé. La modale ne doit donc porter aucun bouton d'ajout.
    const html = readIndexSource();
    const modal = html.slice(html.indexOf('id="pf-security-plot"') - 3000);
    expect(modal).toContain('class="pf-ctl pf-detail-bench-select"');
    expect(modal).toContain("@change=\"setPfDetailBenchmark($event.target.value)\"");
    expect(modal).not.toContain("pf-bench-free");
    expect(modal).not.toContain("openPfBenchFree");
  });

  it("le popover de ticker libre n'alimente que le benchmark global", async () => {
    const save = vi.spyOn(api, "saveSettings").mockResolvedValue({ ok: true, data: {} });
    const reload = vi.fn().mockResolvedValue();
    const c = comp({ pfBenchFree: "mc.pa", pfBenchmark: "CW8.PA",
      portfolioSection: "performance", $nextTick: (fn) => fn && fn(),
      loadPortfolioPerformance: reload });
    await c.applyPfBenchFree();
    expect(save).toHaveBeenCalledWith({ portfolio_benchmark: "MC.PA" });
    expect(c.pfBenchmark).toBe("MC.PA");
    expect(reload).toHaveBeenCalledTimes(1);
    save.mockRestore();
  });

  it("selectPfEntry recadre sur la première séance >= date puis bascule", () => {
    const c = comp({
      pfDetail: { chart: { dates: ["2024-01-01", "2024-02-01", "2024-03-01"], price_adj: [1, 2, 3] } },
      pfDetailEntryIdx: null, $nextTick: (fn) => fn && fn(), drawPerfDetail: vi.fn(),
    });
    const row = { date: "2024-02-01" };
    c.selectPfEntry(row);
    expect(c.pfDetailEntryIdx).toBe(1);
    c.selectPfEntry(row); // re-clic : désélectionne
    expect(c.pfDetailEntryIdx).toBeNull();
  });

  it("selectPfEntry referme le menu des points d'entrée/sortie", () => {
    const c = comp({
      pfDetail: { chart: { dates: ["2024-01-01", "2024-02-01"], price_adj: [1, 2] } },
      pfDetailEntryIdx: null, pfEntryMenuOpen: true,
      $nextTick: (fn) => fn && fn(), drawPerfDetail: vi.fn(),
    });
    c.selectPfEntry({ date: "2024-01-01" });
    expect(c.pfEntryMenuOpen).toBe(false);
  });

  it("togglePfEntryMenu ouvre/ferme le menu flottant", () => {
    const c = comp({ pfEntryMenuOpen: false });
    c.togglePfEntryMenu();
    expect(c.pfEntryMenuOpen).toBe(true);
    c.togglePfEntryMenu();
    expect(c.pfEntryMenuOpen).toBe(false);
  });

  it("pfDetailEntries ne garde que les transactions du titre ouvert", () => {
    const c = comp({ pfPerf: PERF, pfDetail: { ticker: "RI.PA" } });
    expect(c.pfDetailEntries().length).toBe(1);
    c.pfDetail = { ticker: "AI.PA" };
    expect(c.pfDetailEntries().length).toBe(0);
  });

  // Capture les traces Plotly du graphe de détail (comme dividende/risque.test).
  function drawDetail(cfg) {
    const captured = {};
    const el = document.createElement("div");
    el.id = "pf-security-plot";
    document.body.appendChild(el);
    globalThis.Plotly = {
      react: (_el, traces, layout) => { captured.traces = traces; captured.layout = layout; },
      purge: () => {},
    };
    try {
      cfg.drawPerfDetail();
    } finally {
      delete globalThis.Plotly;
      el.remove();
    }
    return captured;
  }

  const DETAIL = {
    ticker: "RI.PA",
    benchmark: { ticker: "CW8.PA", label: "MSCI World" },
    chart: { dates: ["2024-01-01", "2024-02-01", "2024-03-01"], price_adj: [100, 120, 90] },
    benchmark_curve: [400, 440, 380],
  };

  it("drawPerfDetail trace la perf cumulée (%), rebasée à 0 au début — sans régression", () => {
    const c = comp({
      pfDetail: DETAIL, pfDetailEntryIdx: null, pfDetailBenchmark: "CW8.PA",
      pfDetailHorizon: "max", pfDetailHorizons: ["ttm", "3a", "5a", "10a", "max"],
      pfPerf: { retrospective: [] },
    });
    const { traces, layout } = drawDetail(c);
    // Plus aucune régression « droite d'Obole ».
    expect(traces.find((t) => /r[ée]gression|droite/i.test(t.name || ""))).toBeUndefined();
    // Au plus 0 : les deux séries rebasées à 0 % au début de la fenêtre.
    const title = traces.find((t) => t.name === "Titre");
    const bench = traces.find((t) => t.name === "MSCI World");
    expect(title.x).toEqual(["2024-01-01", "2024-02-01", "2024-03-01"]);
    expect(title.y[0]).toBeCloseTo(0, 9);
    expect(title.y[1]).toBeCloseTo(20, 9);
    expect(title.y[2]).toBeCloseTo(-10, 9);
    expect(bench.y[0]).toBeCloseTo(0, 9);
    expect(bench.y[1]).toBeCloseTo(10, 9);
    expect(bench.y[2]).toBeCloseTo(-5, 9);
    // Axe en pourcentage, linéaire (plus de « Base 100 »).
    expect(layout.yaxis.ticksuffix).toBe(" %");
    expect(layout.yaxis.title).toBeUndefined();
    // Aire sous le titre uniquement (comme le Résumé).
    expect(title.fill).toBe("tozeroy");
    expect(bench.fill).toBeUndefined();
  });

  it("drawPerfDetail indexe et recadre les triangles achat/vente (y rebasé en %)", () => {
    const c = comp({
      pfDetail: DETAIL, pfDetailEntryIdx: null, pfDetailBenchmark: "CW8.PA",
      pfDetailHorizon: "max", pfDetailHorizons: ["max"],
      pfPerf: { retrospective: [
        { ticker: "RI.PA", side: "buy", date: "2024-01-01", delta_pct: 5 },
        { ticker: "RI.PA", side: "sell", date: "2024-03-01", delta_pct: -2 },
      ] },
    });
    const { traces } = drawDetail(c);
    const up = traces.find((t) => t.marker && t.marker.symbol === "triangle-up");
    const down = traces.find((t) => t.marker && t.marker.symbol === "triangle-down");
    expect(up).toBeTruthy();
    expect(down).toBeTruthy();
    // Achat le 2024-01-01 (1re séance) -> 0 % ; vente le 2024-03-01 -> -10 %.
    expect(up.x).toEqual(["2024-01-01"]);
    expect(up.y).toEqual([0]);
    expect(down.x).toEqual(["2024-03-01"]);
    expect(down.y[0]).toBeCloseTo(-10, 9);
  });

  it("drawPerfDetail recadre sur le point d'entrée sélectionné (base 0 % recalculée)", () => {
    const c = comp({
      pfDetail: DETAIL, pfDetailEntryIdx: 1, pfDetailBenchmark: "CW8.PA",
      pfDetailHorizon: "max", pfDetailHorizons: ["max"],
      pfPerf: { retrospective: [] },
    });
    const { traces } = drawDetail(c);
    const title = traces.find((t) => t.name === "Titre");
    // Fenêtre [1..fin] : le titre repart de 0 % sur sa nouvelle base (120 -> 90).
    expect(title.x).toEqual(["2024-02-01", "2024-03-01"]);
    expect(title.y[0]).toBe(0);
    expect(title.y[1]).toBeCloseTo(-25, 9);
  });

  it("drawPerfDetail recadre sur l'horizon (le défaut config pilote la fenêtre)", () => {
    const long = {
      ticker: "RI.PA",
      benchmark: { ticker: "CW8.PA", label: "MSCI World" },
      chart: { dates: ["2000-01-01", "2010-01-01", "2024-01-01", "2024-06-01"],
        price_adj: [10, 20, 100, 90] },
      benchmark_curve: [100, 200, 400, 380],
    };
    // Horizon 5A (défaut) : seule la fenêtre des 5 dernières années est tracée.
    const c = comp({ pfDetail: long, pfDetailEntryIdx: null, pfDetailBenchmark: "CW8.PA",
      pfDetailHorizon: "5a", pfDetailHorizons: ["ttm", "3a", "5a", "10a", "max"],
      pfPerf: { retrospective: [] } });
    const { traces } = drawDetail(c);
    const title = traces.find((t) => t.name === "Titre");
    expect(title.x).toEqual(["2024-01-01", "2024-06-01"]);
    expect(title.y[0]).toBe(0);
  });

  it("pfDetailHorizonStart borne chaque horizon sur la dernière date", () => {
    const dates = ["2000-01-01", "2010-01-01", "2024-01-01", "2024-06-01"];
    const c = comp({ pfDetailHorizon: "5a" });
    // MAX -> début 0.
    expect(c.pfDetailHorizonStart(dates, "max")).toBe(0);
    // 5A depuis 2024-06 -> 2019-06, première séance >= = 2024-01-01 (idx 2).
    expect(c.pfDetailHorizonStart(dates, "5a")).toBe(2);
    // TTM -> 2023-06, idem idx 2.
    expect(c.pfDetailHorizonStart(dates, "ttm")).toBe(2);
  });

  it("pfDetailHorizonStart calcule en UTC (pas de décalage d'un jour)", () => {
    // 2024-03-01 reculé de 5 ans = 2019-03-01 : on doit viser CETTE séance, pas
    // 2019-03-02 (dérive d'un jour en arithmétique locale sur fuseau négatif).
    const dates = ["2019-03-01", "2019-03-02", "2024-03-01"];
    const c = comp({});
    expect(c.pfDetailHorizonStart(dates, "5a")).toBe(0);
  });

  it("setPfDetailHorizon efface le point d'entrée et redessine sans refetch", () => {
    const draw = vi.fn();
    const c = comp({ pfDetailHorizon: "5a", pfDetailEntryIdx: 2,
      $nextTick: (fn) => fn && fn(), drawPerfDetail: draw });
    c.setPfDetailHorizon("3a");
    expect(c.pfDetailHorizon).toBe("3a");
    expect(c.pfDetailEntryIdx).toBeNull();
    expect(draw).toHaveBeenCalled();
  });

  it("drawPerfDetail ancre les deux courbes sur la même date (benchmark tardif)", () => {
    // Le benchmark ne démarre qu'à la 2e séance : les deux courbes doivent
    // partager le 0 % à cette date, pas chacune à sa première valeur.
    const staggered = {
      ticker: "RI.PA",
      benchmark: { ticker: "CW8.PA", label: "MSCI World" },
      chart: { dates: ["2024-01-01", "2024-02-01", "2024-03-01"], price_adj: [100, 120, 90] },
      benchmark_curve: [null, 400, 380],
    };
    const c = comp({ pfDetail: staggered, pfDetailEntryIdx: null, pfDetailBenchmark: "CW8.PA",
      pfDetailHorizon: "max", pfDetailHorizons: ["max"], pfPerf: { retrospective: [] } });
    expect(c.pfDetailAnchorIdx(staggered.chart.dates, 0)).toBe(1);
    const { traces } = drawDetail(c);
    const title = traces.find((t) => t.name === "Titre");
    const bench = traces.find((t) => t.name === "MSCI World");
    // Ancrage commun = 2024-02-01 : benchmark 0 % là, titre = 0 % là aussi.
    expect(bench.y[1]).toBeCloseTo(0, 9);
    expect(title.y[1]).toBeCloseTo(0, 9);
    // Mars : titre (90/120-1) = -25 % ; benchmark (380/400-1) = -5 %.
    expect(title.y[2]).toBeCloseTo(-25, 9);
    expect(bench.y[2]).toBeCloseTo(-5, 9);
  });
});

describe("Performance — marqueurs de transactions héro (#17.4)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loadTxMarkers filtre le portefeuille sur le ticker courant", async () => {
    vi.spyOn(api, "portfolioTransactions").mockResolvedValue([
      { ticker: "RI.PA", side: "buy", trade_date: "2024-01-01", quantity: 10, price: 100 },
      { ticker: "AI.PA", side: "sell", trade_date: "2024-02-01", quantity: 5, price: 200 },
    ]);
    const c = comp({ data: { identity: { ticker: "RI.PA" } }, showTx: false,
      isRatio: () => false, isBasket: () => false });
    await c.loadTxMarkers();
    expect(c.txMarkers.length).toBe(1);
    expect(c.txMarkers[0].side).toBe("buy");
  });

  it("loadTxMarkers est neutre pour un ratio (pas de portefeuille)", async () => {
    const spy = vi.spyOn(api, "portfolioTransactions");
    const c = comp({ data: { identity: {} }, isRatio: () => true, isBasket: () => false });
    await c.loadTxMarkers();
    expect(c.txMarkers).toEqual([]);
    expect(spy).not.toHaveBeenCalled();
  });

  it("_visibleTx borne à la fenêtre et tolère une semaine", () => {
    const c = comp({
      data: { chart: { dates: ["2024-01-05", "2024-01-08", "2024-01-20"] } },
      txMarkers: [
        { date: "2024-01-06", side: "buy" },   // week-end -> 1re séance >= = 2024-01-08
        { date: "2024-01-19", side: "sell" },  // dans la fenêtre
      ],
    });
    const vis = c._visibleTx(0, 2);
    expect(vis.length).toBe(2);
    expect(vis[0].idx).toBe(1);
  });
});

describe("Performance — donut par titres (#17.4, revue #2)", () => {
  // jsdom ne fait aucun layout : on remplace `document.getElementById` par un
  // faux nœud dimensionné, comme pour le donut du Résumé.
  function fakeEl(w, h) {
    return { id: "pf-perf-donut", clientWidth: w, clientHeight: h };
  }

  function captureLayout(el = fakeEl(700, 320)) {
    const seen = {};
    globalThis.Plotly = {
      react: (id, traces, layout) => {
        seen.id = id;
        seen.traces = traces;
        seen.layout = layout;
      },
      purge: vi.fn(),
    };
    const spy = vi.spyOn(document, "getElementById").mockReturnValue(el);
    return { seen, spy };
  }

  const PERF_TABLE = {
    table: [
      { ticker: "RI.PA", name: "Pernod", market_value: 600 },
      { ticker: "AI.PA", name: "Air Liquide", market_value: 400 },
    ],
  };

  it("drawPerfDonut trace le disque sur la largeur du conteneur", () => {
    const { seen, spy } = captureLayout();
    const c = comp({ pfPerf: PERF_TABLE });
    c.drawPerfDonut("pf-perf-donut");
    expect(seen.layout.width).toBeGreaterThan(0);
    expect(seen.layout.height).toBeGreaterThan(0);
    expect(seen.traces[0].values).toEqual([600, 400]);
    spy.mockRestore();
  });

  it("drawPerfDonut ne lève pas si ResizeObserver est absent (jsdom)", () => {
    const { spy } = captureLayout();
    delete globalThis.ResizeObserver;
    const c = comp({ pfPerf: PERF_TABLE });
    expect(() => c.drawPerfDonut("pf-perf-donut")).not.toThrow();
    spy.mockRestore();
  });

  it("drawPerfDonut observe le conteneur et re-trace au changement de largeur", async () => {
    // Régression (revue #17.4 finding #2) : le donut Performance avait perdu le
    // ResizeObserver du donut Résumé. Sans lui, Plotly fige le SVG à la largeur
    // du premier rendu et le disque se décale au repli média <900px.
    const { spy } = captureLayout();
    let cb = null;
    globalThis.ResizeObserver = class {
      constructor(fn) { cb = fn; }
      observe() {}
      disconnect() {}
    };
    const c = comp({ pfPerf: PERF_TABLE });
    c.drawPerfDonut("pf-perf-donut");
    expect(typeof cb).toBe("function");
    // Largeur inchangée : pas de re-tracé (garde anti-boucle).
    const redraw = vi.spyOn(c, "_drawDonut");
    cb([{ target: fakeEl(700, 320) }]);
    await new Promise((r) => setTimeout(r, 20));
    expect(redraw).not.toHaveBeenCalled();
    // Largeur changée : re-tracé demandé, et il cible BIEN le donut Performance
    // (le traceur mémorisé par conteneur rejoue `_drawDonut` sur cet id).
    cb([{ target: fakeEl(812, 320) }]);
    await new Promise((r) => setTimeout(r, 20));
    expect(redraw).toHaveBeenCalledWith("pf-perf-donut", expect.anything(), expect.anything());
    delete globalThis.ResizeObserver;
    spy.mockRestore();
  });
});

describe("Performance — détail par titre : écarts au benchmark courant (#15)", () => {
  // Régression (revue #17.4 finding #15) : `pfDetailEntries` lisait ses écarts
  // dans `pfPerf.retrospective`, calculée par le service avec le benchmark
  // GLOBAL. Après un changement de benchmark dans la modale, le graphe comparait
  // au nouveau tandis que le menu annonçait les écarts de l'ancien.
  const base = {
    ticker: "RI.PA",
    retrospective: [
      { id: 1, ticker: "RI.PA", side: "buy", date: "2024-01-03",
        return_pct: 10.0, benchmark_pct: 5.0, delta_pct: 5.0 },
    ],
  };

  it("recalcule delta_pct depuis le benchmark de la MODALE, pas du payload global", () => {
    // Titre : 100 -> 120 (+20 %). Benchmark de la modale : 200 -> 210 (+5 %).
    // Delta attendu = +15 %, PAS +5 % (valeur figée du payload global).
    const c = comp({
      pfPerf: base,
      pfDetail: {
        ticker: "RI.PA",
        chart: { dates: ["2024-01-03", "2024-06-03"], price_adj: [100, 120] },
        benchmark_curve: [200, 210],
      },
    });
    const [e] = c.pfDetailEntries();
    expect(e.return_pct).toBe(20);
    expect(e.benchmark_pct).toBe(5);
    expect(e.delta_pct).toBe(15);
  });

  it("suit un CHANGEMENT de benchmark : le delta se met à jour", () => {
    const detail = (bench) => ({
      pfPerf: base,
      pfDetail: {
        ticker: "RI.PA",
        chart: { dates: ["2024-01-03", "2024-06-03"], price_adj: [100, 120] },
        benchmark_curve: bench,
      },
    });
    // Benchmark A : +5 % -> delta +15 %.
    expect(comp(detail([200, 210])).pfDetailEntries()[0].delta_pct).toBe(15);
    // Benchmark B : +30 % (200 -> 260) -> delta -10 % : le signe s'inverse, ce
    // qui prouve que la valeur ne vient plus du payload global (toujours +5).
    expect(comp(detail([200, 260])).pfDetailEntries()[0].delta_pct).toBe(-10);
  });

  it("tolère un benchmark indisponible (delta null, jamais un 0 trompeur)", () => {
    const c = comp({
      pfPerf: base,
      pfDetail: {
        ticker: "RI.PA",
        chart: { dates: ["2024-01-03", "2024-06-03"], price_adj: [100, 120] },
        benchmark_curve: [null, null],
      },
    });
    const [e] = c.pfDetailEntries();
    expect(e.return_pct).toBe(20);
    expect(e.benchmark_pct).toBeNull();
    expect(e.delta_pct).toBeNull();
  });
});

describe("Donuts — observateurs indépendants (#2, ordre réel Résumé -> Performance)", () => {
  // Le Résumé est TOUJOURS chargé avant la Performance
  // (`reloadPortfolioData` attend `loadPortfolioSummary`). Avec un observateur
  // mono-slot, le donut du Résumé captait le seul slot et la Performance n'était
  // jamais ré-observée : le disque se décalait au repli <900px. Ce test reproduit
  // cet ordre et vérifie que les DEUX conteneurs sont observés.
  const PERF_TABLE = {
    table: [
      { ticker: "RI.PA", name: "Pernod", market_value: 600 },
      { ticker: "AI.PA", name: "Air Liquide", market_value: 400 },
    ],
  };
  const SUMMARY = { accounts: [{ name: "PEA", value: 100 }] };

  function instrument() {
    const observed = [];
    const disconnected = [];
    globalThis.ResizeObserver = class {
      constructor(fn) { this.fn = fn; }
      observe(node) { observed.push(node.id); }
      disconnect() { disconnected.push(true); }
    };
    globalThis.Plotly = { react: vi.fn(), purge: vi.fn() };
    const spy = vi.spyOn(document, "getElementById").mockImplementation((id) => ({
      id, clientWidth: 700, clientHeight: 320,
    }));
    return { observed, disconnected, spy };
  }

  it("Résumé puis Performance : les deux conteneurs sont observés", () => {
    const { observed, spy } = instrument();
    const c = comp({ pfSummary: SUMMARY, pfPerf: PERF_TABLE });
    c.drawPortfolioDonut("pf-summary-donut");
    c.drawPerfDonut("pf-perf-donut");
    expect(observed).toContain("pf-summary-donut");
    expect(observed).toContain("pf-perf-donut");
    spy.mockRestore();
  });

  it("chaque donut garde sa propre largeur (pas de slot partagé)", () => {
    const { spy } = instrument();
    const c = comp({ pfSummary: SUMMARY, pfPerf: PERF_TABLE });
    c.drawPortfolioDonut("pf-summary-donut");
    c.drawPerfDonut("pf-perf-donut");
    expect(c._pfDonutW["pf-summary-donut"]).toBeGreaterThan(0);
    expect(c._pfDonutW["pf-perf-donut"]).toBeGreaterThan(0);
    spy.mockRestore();
  });

  it("_pfDisconnectDonut déconnecte TOUS les observateurs", () => {
    const { disconnected, spy } = instrument();
    const c = comp({ pfSummary: SUMMARY, pfPerf: PERF_TABLE });
    c.drawPortfolioDonut("pf-summary-donut");
    c.drawPerfDonut("pf-perf-donut");
    c._pfDisconnectDonut();
    expect(disconnected.length).toBe(2);
    expect(c._pfDonutObs).toEqual({});
    spy.mockRestore();
  });
});

describe("Donuts — nœud recréé par Alpine (#19)", () => {
  // `#pf-perf-donut` vit sous `<template x-if="!pfPerfEmpty()">` : au passage
  // vide/erreur puis rechargement, Alpine DÉTRUIT et RECRÉE le div. Un
  // observateur mémorisé par id resterait branché sur le nœud détaché et le bug
  // #2 reviendrait. On vérifie qu'un nœud différent force une reconnexion.
  const PERF_TABLE = {
    table: [{ ticker: "RI.PA", name: "Pernod", market_value: 600 }],
  };

  it("un nouveau nœud (même id) est ré-observé, l'ancien est déconnecté", () => {
    const observed = [];
    const disconnected = [];
    globalThis.ResizeObserver = class {
      observe(node) { observed.push(node); }
      disconnect() { disconnected.push(true); }
    };
    globalThis.Plotly = { react: vi.fn(), purge: vi.fn() };
    const nodeA = { id: "pf-perf-donut", clientWidth: 700, clientHeight: 320 };
    const nodeB = { id: "pf-perf-donut", clientWidth: 700, clientHeight: 320 };
    let current = nodeA;
    const spy = vi.spyOn(document, "getElementById").mockImplementation(() => current);

    const c = comp({ pfPerf: PERF_TABLE });
    c.drawPerfDonut("pf-perf-donut");
    expect(observed).toEqual([nodeA]);

    // Alpine recrée le div : nouveau nœud, même id.
    current = nodeB;
    c.drawPerfDonut("pf-perf-donut");
    expect(observed).toEqual([nodeA, nodeB]); // le nouveau est observé
    expect(disconnected.length).toBe(1);       // l'ancien est libéré
    spy.mockRestore();
  });

  it("le même nœud n'est pas ré-observé (pas de doublon de callback)", () => {
    const observed = [];
    globalThis.ResizeObserver = class {
      observe(node) { observed.push(node); }
      disconnect() {}
    };
    globalThis.Plotly = { react: vi.fn(), purge: vi.fn() };
    const node = { id: "pf-perf-donut", clientWidth: 700, clientHeight: 320 };
    const spy = vi.spyOn(document, "getElementById").mockReturnValue(node);

    const c = comp({ pfPerf: PERF_TABLE });
    c.drawPerfDonut("pf-perf-donut");
    c.drawPerfDonut("pf-perf-donut");
    expect(observed.length).toBe(1);
    spy.mockRestore();
  });
});
