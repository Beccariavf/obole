import { describe, expect, it, vi, beforeEach } from "vitest";

import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { api } from "../src/obole/web/api.js";
import { C } from "../src/obole/web/theme.js";

// #17.6 (étiquettes) et #17.3 (risque) : logique du mixin testée sans DOM.
// On vérifie la délégation à `api.js` (aucun fetch direct) et les helpers de
// présentation (métriques, exclusion de corrélation).

function comp(overrides = {}) {
  return { ...portfolioMixin, ...overrides };
}

describe("étiquettes — sélection de portefeuille virtuel (#17.6)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("setPortfolioTag change l'étiquette et recharge la portée", async () => {
    const c = comp({ portfolioTag: "", reloadPortfolioData: vi.fn().mockResolvedValue() });
    await c.setPortfolioTag("Actions dividende");
    expect(c.portfolioTag).toBe("Actions dividende");
    expect(c.reloadPortfolioData).toHaveBeenCalledTimes(1);
  });

  it("setPortfolioTag ignore une étiquette inchangée", async () => {
    const c = comp({ portfolioTag: "Div", reloadPortfolioData: vi.fn() });
    await c.setPortfolioTag("Div");
    expect(c.reloadPortfolioData).not.toHaveBeenCalled();
  });

  it("setPortfolioTag normalise la valeur vide en « toutes »", async () => {
    const c = comp({ portfolioTag: "Div", reloadPortfolioData: vi.fn().mockResolvedValue() });
    await c.setPortfolioTag("");
    expect(c.portfolioTag).toBe("");
  });

  it("setPortfolioAccount réinitialise l'étiquette (elle peut ne pas exister dans le compte)", async () => {
    const c = comp({
      portfolioAccountId: null,
      portfolioTag: "Div",
      reloadPortfolioData: vi.fn().mockResolvedValue(),
    });
    await c.setPortfolioAccount("4");
    expect(c.portfolioAccountId).toBe(4);
    expect(c.portfolioTag).toBe("");
  });

  it("reloadPortfolioData retombe sur « toutes » si l'étiquette courante a disparu", async () => {
    vi.spyOn(api, "portfolioTransactions").mockResolvedValue([]);
    vi.spyOn(api, "portfolioDividends").mockResolvedValue([]);
    vi.spyOn(api, "portfolioPositions").mockResolvedValue([]);
    // Le compte ne porte plus « Div » : la liste scoped ne la contient pas.
    vi.spyOn(api, "portfolioTags").mockResolvedValue({ tags: ["Croissance"] });
    const c = comp({ portfolioAccountId: 1, portfolioTag: "Div", loadPortfolioSummary: vi.fn() });
    await c.reloadPortfolioData();
    expect(c.portfolioTag).toBe("");
  });

  it("reloadPortfolioData interroge les étiquettes du compte courant (scope)", async () => {
    vi.spyOn(api, "portfolioTransactions").mockResolvedValue([]);
    vi.spyOn(api, "portfolioDividends").mockResolvedValue([]);
    vi.spyOn(api, "portfolioPositions").mockResolvedValue([]);
    const tagSpy = vi.spyOn(api, "portfolioTags").mockResolvedValue({ tags: [] });
    const c = comp({ portfolioAccountId: 7, portfolioTag: "", loadPortfolioSummary: vi.fn() });
    await c.reloadPortfolioData();
    expect(tagSpy).toHaveBeenCalledWith(7);
  });

  it("pfNoDataHint contextualise le message quand une étiquette est active", () => {
    expect(comp({ portfolioTag: "Div" }).pfNoDataHint("fallback")).toMatch(/« Div »/);
    expect(comp({ portfolioTag: "" }).pfNoDataHint("fallback")).toBe("fallback");
  });

  it("savePositionTag délègue à api.setPositionTag avec le compte courant", async () => {
    const spy = vi
      .spyOn(api, "setPositionTag")
      .mockResolvedValue({ ok: true, data: {} });
    const c = comp({
      portfolioAccountId: 7,
      pfTagDraft: "Croissance",
      pfTagEditing: "RI.PA",
      reloadPortfolioData: vi.fn().mockResolvedValue(),
    });
    await c.savePositionTag({ ticker: "RI.PA" });
    expect(spy).toHaveBeenCalledWith({ account_id: 7, ticker: "RI.PA", tag: "Croissance" });
    expect(c.pfTagEditing).toBeNull();
  });

  it("savePositionTag envoie null pour une étiquette vidée", async () => {
    const spy = vi.spyOn(api, "setPositionTag").mockResolvedValue({ ok: true, data: {} });
    const c = comp({
      portfolioAccountId: null,
      pfTagDraft: "   ",
      reloadPortfolioData: vi.fn().mockResolvedValue(),
    });
    await c.savePositionTag({ ticker: "AI.PA" });
    expect(spy).toHaveBeenCalledWith({ account_id: null, ticker: "AI.PA", tag: null });
  });
});

describe("risque — helpers de présentation (#17.3)", () => {
  it("pfRiskEmpty reflète l'absence de série", () => {
    expect(comp({ pfRisk: { dates: [] } }).pfRiskEmpty()).toBe(true);
    expect(comp({ pfRisk: { dates: ["2024-01-01"] } }).pfRiskEmpty()).toBe(false);
    expect(comp({ pfRisk: null }).pfRiskEmpty()).toBe(true);
  });

  it("l'échelle séquentielle va du blanc (faible) au bleu des boutons (forte)", () => {
    // Échelle monochrome bleu : borne 0.0 = blanc (corrélation nulle), borne
    // 1.0 = `C.accent` (le bleu de l'UI, corrélation 100 %). Aucune autre teinte.
    const scale = C.corrScale;
    expect(scale[0][0]).toBe(0);
    expect(scale[0][1].toUpperCase()).toBe("#FFFFFF");
    expect(scale[scale.length - 1][0]).toBe(1);
    expect(scale[scale.length - 1][1].toUpperCase()).toBe(C.accent.toUpperCase());
    // Toutes les couleurs sont des nuances de bleu/neutres (pas de rouge/vert).
    for (const [, hex] of scale) {
      const r = parseInt(hex.slice(1, 3), 16);
      const g = parseInt(hex.slice(3, 5), 16);
      const b = parseInt(hex.slice(5, 7), 16);
      expect(b, `${hex} doit être plus bleu que rouge`).toBeGreaterThanOrEqual(r);
      expect(g, `${hex} doit être plus bleu que vert`).toBeLessThanOrEqual(b);
    }
  });

  it("drawCorrelationHeatmap trace avec l'échelle séquentielle de theme.js (0..1)", () => {
    const captured = {};
    const el = document.createElement("div");
    el.id = "corr-test";
    document.body.appendChild(el);
    globalThis.Plotly = {
      react: (_el, traces, layout) => { captured.trace = traces[0]; captured.layout = layout; },
      purge: () => {},
    };
    try {
      comp({
        pfRisk: { correlation: { tickers: ["A", "B"], matrix: [[1.0, 0.8], [0.8, 1.0]], excluded: [] } },
      }).drawCorrelationHeatmap("corr-test");
    } finally {
      delete globalThis.Plotly;
      el.remove();
    }
    expect(captured.trace.colorscale).toBe(C.corrScale);
    // Bornes séquentielles : 0 = blanc, 1 = bleu foncé (les négatifs sont bornés
    // au blanc). Plus de `zmid` (échelle divergente abandonnée).
    expect(captured.trace.zmin).toBe(0);
    expect(captured.trace.zmax).toBe(1);
    expect(captured.trace.zmid).toBeUndefined();
  });

  it("drawCorrelationHeatmap sépare les cellules et détoure la diagonale", () => {
    const captured = {};
    const el = document.createElement("div");
    el.id = "corr-tex";
    document.body.appendChild(el);
    globalThis.Plotly = {
      react: (_el, traces, layout) => { captured.trace = traces[0]; captured.layout = layout; },
      purge: () => {},
    };
    try {
      comp({
        pfRisk: {
          correlation: { tickers: ["A", "B", "C"], matrix: [[1, 0.5, 0.2], [0.5, 1, 0.1], [0.2, 0.1, 1]], excluded: [] },
        },
      }).drawCorrelationHeatmap("corr-tex");
    } finally {
      delete globalThis.Plotly;
      el.remove();
    }
    // Grille de cellules : un léger intervalle entre elles (= « texture » précise).
    expect(captured.trace.xgap).toBeGreaterThan(0);
    expect(captured.trace.ygap).toBeGreaterThan(0);
    // Axes numériques (0..n-1) avec les tickers en libellés : permet des formes
    // alignées sur les cellules.
    expect(captured.trace.x).toEqual([0, 1, 2]);
    expect(captured.trace.y).toEqual([0, 1, 2]);
    expect(captured.layout.xaxis.ticktext).toEqual(["A", "B", "C"]);
    // Diagonale détourée : un rectangle par cellule (bordure accent).
    expect(captured.layout.shapes).toHaveLength(3);
    expect(captured.layout.shapes[0]).toMatchObject({
      x0: -0.5, x1: 0.5, y0: -0.5, y1: 0.5,
      line: { color: C.accentLight },
    });
  });

  it("pfRiskMetricRows formate portefeuille vs benchmark", () => {
    const c = comp({
      pfRisk: {
        metrics: {
          max_drawdown_pct: -12.34,
          current_drawdown_pct: -3,
          longest_recovery_days: 200,
          volatility_pct: 18.5,
          best_month_pct: 6,
          worst_month_pct: -7,
        },
        benchmark_metrics: {
          max_drawdown_pct: -20,
          current_drawdown_pct: 0,
          longest_recovery_days: 90,
          volatility_pct: 15,
        },
      },
      fmt: (v) => v.toFixed(2),
    });
    const rows = c.pfRiskMetricRows();
    expect(rows.find((r) => r.label === "Perte maximale").pf).toBe("-12.34 %");
    expect(rows.find((r) => r.label === "Perte maximale").bench).toBe("-20.00 %");
    expect(rows.find((r) => r.label === "Récupération la plus longue").pf).toBe("200 j");
    expect(rows.find((r) => r.label === "Meilleur mois").bench).toBe("—");
  });

  it("pfRiskMetricRows tolère un payload absent (valeurs « — »)", () => {
    const rows = comp({ fmt: (v) => String(v), pfRisk: null }).pfRiskMetricRows();
    expect(rows.every((r) => r.pf === "—")).toBe(true);
  });

  it("pfRiskLegend décrit les deux séries avec leur perte max", () => {
    const c = comp({
      pfRisk: {
        metrics: { max_drawdown_pct: -12.34 },
        benchmark_metrics: { max_drawdown_pct: -20 },
        benchmark: { ticker: "CW8.PA", label: "MSCI World" },
      },
      fmt: (v) => v.toFixed(2),
      pfBenchmarkLabel: () => "CW8.PA",
    });
    const legend = c.pfRiskLegend();
    expect(legend).toHaveLength(2);
    expect(legend[0]).toMatchObject({ label: "Portefeuille", color: C.bad, value: "-12.34 %" });
    expect(legend[1]).toMatchObject({ label: "CW8.PA", color: C.ma1, value: "-20.00 %" });
  });

  it("pfRiskLegend tolère un payload absent", () => {
    const legend = comp({ fmt: (v) => String(v), pfRisk: null, pfBenchmarkLabel: () => "—" }).pfRiskLegend();
    expect(legend.map((e) => e.value)).toEqual(["—", "—"]);
  });

  it("drawDrawdownChart n'expose pas de légende Plotly (rendue en HTML sous le tracé)", () => {
    const captured = {};
    const el = document.createElement("div");
    el.id = "dd-test";
    document.body.appendChild(el);
    globalThis.Plotly = { react: (_el, _t, layout) => { captured.layout = layout; } };
    try {
      comp({
        pfRisk: {
          dates: ["2024-01-01", "2024-01-02"],
          drawdown: [0, -5], benchmark_drawdown: [0, -3],
          metrics: {}, benchmark_metrics: {}, benchmark: { ticker: "CW8.PA" },
        },
        pfBenchmarkLabel: (t) => t,
      }).drawDrawdownChart("dd-test");
    } finally {
      delete globalThis.Plotly;
      el.remove();
    }
    expect(captured.layout.showlegend).toBe(false);
    expect(captured.layout.legend).toBeUndefined();
  });

  it("pfCorrAverage lit la valeur SERVEUR (source unique, pas de recalcul JS)", () => {
    expect(comp({ pfRisk: { corr_avg: 0.1712 } }).pfCorrAverage()).toBe(0.1712);
    expect(comp({ pfRisk: { corr_avg: null } }).pfCorrAverage()).toBeNull();
    expect(comp({ pfRisk: null }).pfCorrAverage()).toBeNull();
  });

  it("pfCorrAverageLabel formate la moyenne (virgule, signe)", () => {
    const c = comp({
      pfRisk: { corr_avg: 0.5 },
      fmt: (v) => Number(v).toFixed(2).replace(".", ","),
    });
    expect(c.pfCorrAverageLabel()).toBe("+0,50");
    expect(comp({ pfRisk: null }).pfCorrAverageLabel()).toBe("");
  });

  it("pfCorrExcluded renvoie la liste serveur (ou vide)", () => {
    expect(comp({ pfRisk: { correlation: { excluded: [{ ticker: "X", obs: 3 }] } } }).pfCorrExcluded())
      .toEqual([{ ticker: "X", obs: 3 }]);
    expect(comp({ pfRisk: null }).pfCorrExcluded()).toEqual([]);
  });
});

describe("test de corrélation — ligne + impact (#17.3)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("runCorrTest délègue à api.portfolioCorrelationTest avec la portée et le ticker", async () => {
    const spy = vi.spyOn(api, "portfolioCorrelationTest").mockResolvedValue({
      ticker: "MC.PA", tickers: ["A", "B"], row: [0.2, 0.4],
      obs: 250, current_avg: 0.17, new_avg: 0.21, delta: 0.04, warning: null,
    });
    const c = comp({
      _pfMetaReady: true,
      portfolioAccountId: 3,
      portfolioTag: "Div",
      pfBenchmark: "CW8.PA",
      pfPeriod: "1a",
      pfCorrTestTicker: "mc.pa",
      $nextTick: (fn) => fn(),
      drawCorrTestRow: vi.fn(),
    });
    await c.runCorrTest();
    expect(spy).toHaveBeenCalledWith(3, "CW8.PA", "1a", "Div", "MC.PA");
    expect(c.pfCorrTest.ticker).toBe("MC.PA");
    expect(c.pfCorrTestError).toBe("");
  });

  it("runCorrTest capture l'erreur réseau et vide le résultat", async () => {
    vi.spyOn(api, "portfolioCorrelationTest").mockRejectedValue(new Error("Ticker vide."));
    const c = comp({
      pfCorrTestTicker: "X",
      $nextTick: (fn) => fn(),
    });
    await c.runCorrTest();
    expect(c.pfCorrTest).toBeNull();
    expect(c.pfCorrTestError).toMatch(/Ticker vide/);
  });

  it("onCorrTestInput débouce puis résout la saisie (300 ms)", async () => {
    vi.useFakeTimers();
    try {
      const spy = vi
        .spyOn(api, "search")
        .mockResolvedValue([{ symbol: "MC.PA", name: "LVMH", exchange: "PAR" }]);
      const c = comp({ pfCorrTestTicker: "lvmh", pfCorrTestSuggestions: [], runCorrTest: vi.fn() });
      c.onCorrTestInput();
      expect(spy).not.toHaveBeenCalled(); // debounce
      vi.advanceTimersByTime(300);
      await vi.waitFor(() => expect(spy).toHaveBeenCalledWith("lvmh"));
      // Le nom ne correspond à aucun code exact -> suggestions affichées.
      await vi.waitFor(() => expect(c.pfCorrTestSuggestions).toHaveLength(1));
      expect(c.runCorrTest).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("onCorrTestInput efface tout si le champ est vidé", () => {
    const c = comp({
      pfCorrTestTicker: "   ",
      _pfCorrTestSeq: 3,
      pfCorrTest: { ticker: "X" },
      pfCorrTestError: "boom",
      pfCorrTestSuggestions: [{ symbol: "X" }],
      runCorrTest: vi.fn(),
    });
    c.onCorrTestInput();
    expect(c.pfCorrTest).toBeNull();
    expect(c.pfCorrTestError).toBe("");
    expect(c.pfCorrTestSuggestions).toEqual([]);
    // Le jeton avance : une réponse en vol devient périmée.
    expect(c._pfCorrTestSeq).toBe(4);
  });

  it("onCorrTestInput vide les suggestions sous 2 caractères", () => {
    const c = comp({ pfCorrTestTicker: "l", pfCorrTestSuggestions: [{ symbol: "X" }] });
    c.onCorrTestInput();
    expect(c.pfCorrTestSuggestions).toEqual([]);
  });

  it("resolveCorrTestInput teste direct si la saisie EST un code (exact)", async () => {
    vi.spyOn(api, "search").mockResolvedValue([{ symbol: "MC.PA", name: "LVMH" }]);
    const run = vi.fn().mockResolvedValue();
    const c = comp({ pfCorrTestTicker: "mc.pa", runCorrTest: run });
    await c.resolveCorrTestInput("mc.pa");
    expect(run).toHaveBeenCalledTimes(1);
    expect(c.pfCorrTestSuggestions).toEqual([]);
  });

  it("runCorrTest ignore une réponse périmée (jeton anti-course)", async () => {
    let resolveReq;
    const p = new Promise((res) => { resolveReq = res; });
    vi.spyOn(api, "portfolioCorrelationTest").mockReturnValue(p);
    const c = comp({ pfCorrTestTicker: "MC.PA", $nextTick: (fn) => fn(), drawCorrTestRow: vi.fn() });
    const run = c.runCorrTest();
    // Entre-temps : une nouvelle saisie invalide la requête en vol.
    c._pfCorrTestSeq += 1;
    c.pfCorrTest = null;
    resolveReq({ ticker: "MC.PA", delta: 0.04, tickers: [], row: [] });
    await run;
    expect(c.pfCorrTest).toBeNull(); // la réponse tardive n'a pas écrasé l'état
  });

  it("pickCorrTestSuggestion choisit le ticker, ferme la liste et lance le test", async () => {
    const c = comp({
      pfCorrTestSuggestions: [{ symbol: "MC.PA", name: "LVMH" }],
      runCorrTest: vi.fn().mockResolvedValue(),
    });
    await c.pickCorrTestSuggestion({ symbol: "MC.PA", name: "LVMH" });
    expect(c.pfCorrTestTicker).toBe("MC.PA");
    expect(c.pfCorrTestSuggestions).toEqual([]);
    expect(c.runCorrTest).toHaveBeenCalledTimes(1);
  });

  it("runCorrTest ferme aussi la liste de suggestions", async () => {
    vi.spyOn(api, "portfolioCorrelationTest").mockResolvedValue({
      ticker: "MC.PA", tickers: [], row: [], obs: 0, delta: 0,
    });
    const c = comp({
      pfCorrTestTicker: "MC.PA",
      pfCorrTestSuggestions: [{ symbol: "MC.PA" }],
      $nextTick: (fn) => fn(),
      drawCorrTestRow: vi.fn(),
    });
    await c.runCorrTest();
    expect(c.pfCorrTestSuggestions).toEqual([]);
  });

  it("submitCorrTest privilégie le ticker exact tapé parmi les suggestions", async () => {
    const picked = [];
    const c = comp({
      pfCorrTestTicker: "mc.pa",
      pfCorrTestSuggestions: [{ symbol: "MC.PA" }, { symbol: "MCX.PA" }],
      pickCorrTestSuggestion: (s) => picked.push(s.symbol),
      runCorrTest: vi.fn(),
    });
    await c.submitCorrTest();
    expect(picked).toEqual(["MC.PA"]);
  });

  it("submitCorrTest teste directement la saisie sans suggestion", async () => {
    const run = vi.fn();
    const c = comp({ pfCorrTestTicker: "mc.pa", pfCorrTestSuggestions: [], runCorrTest: run });
    await c.submitCorrTest();
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("pfCorrTestImpact : baisse = bonne (bleu), hausse = mauvaise (rouge)", () => {
    const fmt = (v) => Number(v).toFixed(2).replace(".", ",");
    const good = comp({ fmt, pfCorrTest: { current_avg: 0.17, new_avg: 0.12, delta: -0.05 } });
    const bad = comp({ fmt, pfCorrTest: { current_avg: 0.17, new_avg: 0.23, delta: 0.06 } });
    expect(good.pfCorrTestImpact().good).toBe(true);
    expect(good.pfCorrTestImpact().text).toContain("0,17 → 0,12");
    expect(good.pfCorrTestImpact().text).toContain("(-0,05)");
    expect(bad.pfCorrTestImpact().good).toBe(false);
    expect(bad.pfCorrTestImpact().text).toContain("(+0,06)");
    expect(comp({ pfCorrTest: null }).pfCorrTestImpact()).toBeNull();
  });

  it("pfCorrTestImpactClass mappe la polarité (bleu = bien)", () => {
    const c = comp({
      fmt: (v) => String(v),
      polarity: (g) => (g === true ? "good" : g === false ? "bad" : "neutral"),
      pfCorrTest: { delta: -0.05, current_avg: 0.1, new_avg: 0.05 },
    });
    expect(c.pfCorrTestImpactClass()).toBe("good");
  });

  it("drawCorrTestRow trace une ligne alignée (échelle séquentielle, sans barre)", () => {
    const captured = {};
    const el = document.createElement("div");
    el.id = "corr-row";
    document.body.appendChild(el);
    globalThis.Plotly = { react: (_el, traces, layout) => { captured.trace = traces[0]; captured.layout = layout; } };
    try {
      comp({
        pfCorrTest: { ticker: "MC.PA", tickers: ["A", "B", "C"], row: [0.2, null, 0.7] },
      }).drawCorrTestRow("corr-row");
    } finally {
      delete globalThis.Plotly;
      el.remove();
    }
    expect(captured.trace.colorscale).toBe(C.corrScale);
    expect(captured.trace.zmin).toBe(0);
    expect(captured.trace.zmax).toBe(1);
    expect(captured.trace.showscale).toBe(false);
    // Une seule bande (1×N), colonnes = tickers de la matrice.
    expect(captured.trace.z).toHaveLength(1);
    expect(captured.trace.x).toEqual([0, 1, 2]);
    expect(captured.layout.xaxis.ticktext).toEqual(["A", "B", "C"]);
  });
});

describe("risque — chargement", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("loadPortfolioRisk délègue à api.portfolioRisk avec la portée complète", async () => {
    const spy = vi.spyOn(api, "portfolioRisk").mockResolvedValue({
      dates: ["2024-01-01"], correlation: { tickers: [], matrix: [], excluded: [] },
    });
    const c = comp({
      _pfMetaReady: true,
      portfolioAccountId: 3,
      portfolioTag: "Div",
      pfBenchmark: "CW8.PA",
      pfPeriod: "max",
      $nextTick: (fn) => fn(),
      drawPortfolioRisk: vi.fn(),
    });
    await c.loadPortfolioRisk();
    expect(spy).toHaveBeenCalledWith(3, "CW8.PA", "max", "Div");
    expect(c.pfRiskError).toBe("");
  });

  it("loadPortfolioRisk capture l'erreur réseau sans crash", async () => {
    vi.spyOn(api, "portfolioRisk").mockRejectedValue(new Error("Boom"));
    const c = comp({
      _pfMetaReady: true,
      pfBenchmark: "CW8.PA",
      pfPeriod: "1a",
      $nextTick: (fn) => fn(),
    });
    await c.loadPortfolioRisk();
    expect(c.pfRisk).toBeNull();
    expect(c.pfRiskError).toMatch(/Risque indisponible/);
  });
});
