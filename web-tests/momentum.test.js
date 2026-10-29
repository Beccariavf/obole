import { beforeAll, describe, expect, it, vi } from "vitest";
import { api } from "../src/obole/web/api.js";
import { applyMeta } from "../src/obole/web/thresholds.js";
import { momentumMixin } from "../src/obole/web/momentum.js";

// #30 : la table « monde de Markovitz » mesure le COURS (σ autour de la droite,
// z, pente), pas le score de satisfaction — deux séries distinctes du payload.

beforeAll(() => {
  // Bornes calibrées, comme le payload /api/meta : sans elles, tout score
  // tomberait au-dessus de 0 et le test ne dirait rien.
  applyMeta({
    reg_years_default: 20,
    reg_years_financial: 30,
    momentum: {
      window: 250,
      low: 0.35,
      high: 0.6,
      table_windows: [1, 5, 10, 20, 0],
      fee_pct: 0.1,
    },
  });
});

const DAY = 864e5;

function datesFor(n) {
  const out = [];
  const start = new Date("2020-01-01");
  for (let i = 0; i < n; i++) {
    out.push(new Date(start.getTime() + i * DAY).toISOString().slice(0, 10));
  }
  return out;
}

function component(prices, { window = 0, series = "raw", adjPrices = null } = {}) {
  const dates = datesFor(prices.length);
  return {
    ...momentumMixin,
    momWindow: window,
    momSeries: series,
    fmt: (v) => (v == null ? "—" : Number(v).toFixed(2)),
    data: {
      chart: {
        dates,
        price_raw: prices,
        price_adj: adjPrices || prices,
        momentum: {
          n_used: prices.length,
          raw: prices.map(() => 0.5),
          adj: prices.map(() => 0.5),
        },
        ma_short_raw: prices.map(() => 110),
        ma_long_raw: prices.map(() => 105),
      },
    },
  };
}

describe("table monde de Markovitz", () => {
  it("une droite log-parfaite donne une confiance nulle et un z nul", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const stats = component(prices).momStats();
    expect(stats.confidence).toBeLessThan(0.01);
    expect(Math.abs(stats.z)).toBeLessThan(0.5);
  });

  it("la fenêtre change la pente : un an contre le maximum", () => {
    // 550 jours plats puis une pente raide : la fenêtre d'un an ne voit que la
    // pente, la fenêtre MAX voit les deux régimes.
    const prices = Array.from({ length: 1100 }, (_, i) =>
      i < 550 ? 100 : 100 * Math.exp(0.002 * (i - 550)),
    );
    const oneYear = component(prices, { window: 1 }).momStats();
    const max = component(prices, { window: 0 }).momStats();
    expect(oneYear.slope).toBeGreaterThan(max.slope * 1.5);
  });

  it("les moyennes mobiles viennent du payload, jamais recalculées", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const stats = component(prices).momStats();
    expect(stats.maShort).toBe(110);
    expect(stats.maLong).toBe(105);
  });

  it("changer de fiche remet la plage à zéro", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const comp = component(prices, { window: 10 });
    comp._hashRef = () => "RI.PA";
    comp.momSyncRef(); // première synchronisation : rien à conserver
    comp.momStart = 100;
    comp.momEnd = 299;
    comp.momSyncRef(); // même fiche : la plage reste
    expect(comp.momStart).toBe(100);
    comp._hashRef = () => "AI.PA";
    comp.momSyncRef(); // autre fiche : la plage est un index, elle ne vaut plus rien
    expect(comp.momStart).toBeNull();
    expect(comp.momEnd).toBeNull();
  });

  it("la fenêtre par défaut est la référence persistée", () => {
    const prices = Array.from({ length: 1100 }, (_, i) => 100 + i);
    const comp = component(prices, { window: null });
    comp.data.watch = { ref: { start: comp.data.chart.dates[500] } };
    const [start, end] = comp.momRange();
    expect(start).toBe(500);
    expect(end).toBe(1099);
  });

  it("le preset Réf. place la plage sur la date persistée", () => {
    const prices = Array.from({ length: 1100 }, (_, i) => 100 + i);
    const comp = component(prices, { window: null });
    comp.data.watch = { ref: { start: comp.data.chart.dates[500] } };
    comp.drawMomentumHistory = () => {}; // tracé isolé : on ne teste que la plage
    comp.momPreset("ref");
    expect(comp.momStart).toBe(500);
    expect(comp.momEnd).toBe(1099);
    // Même référence que la table : les deux repères ne peuvent pas diverger.
    expect(comp.momStart).toBe(comp.momRange()[0]);
  });

  it("sans référence persistée, le preset Réf. applique 20 ans", () => {
    const prices = Array.from({ length: 12000 }, (_, i) => 100 + i);
    const comp = component(prices, { window: 1 });
    comp.drawMomentumHistory = () => {};
    const end = prices.length - 1;
    comp.momPreset("ref");
    const cutoff = new Date(comp.data.chart.dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - 20);
    expect(new Date(comp.data.chart.dates[comp.momStart]) >= cutoff).toBe(true);
    expect(new Date(comp.data.chart.dates[comp.momStart - 1]) < cutoff).toBe(true);
  });

  it("sans référence persistée, une financière applique 30 ans", () => {
    const prices = Array.from({ length: 15000 }, (_, i) => 100 + i);
    const comp = component(prices, { window: 1 });
    comp.data.identity = { kind: "financial" };
    comp.drawMomentumHistory = () => {};
    const end = prices.length - 1;
    comp.momPreset("ref");
    const cutoff = new Date(comp.data.chart.dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - 30);
    expect(new Date(comp.data.chart.dates[comp.momStart]) >= cutoff).toBe(true);
    expect(new Date(comp.data.chart.dates[comp.momStart - 1]) < cutoff).toBe(true);
  });

  it("l'historique s'ouvre toujours sur 10 ans", () => {
    const prices = Array.from({ length: 8000 }, (_, i) => 100 + i);
    const comp = component(prices);
    comp.drawMomentumYear = () => {};
    comp.drawMomentumHistory = () => {};
    comp.drawMomentum();
    const end = prices.length - 1;
    expect(comp.momStart).toBe(comp._momStartBefore(end, 10));
  });

  it("la fenêtre MAX couvre toute la grille", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const [start, end] = component(prices, { window: 0 }).momRange();
    expect(start).toBe(0);
    expect(end).toBe(299);
  });

  it("les lignes portent les six mesures, formatées", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const rows = component(prices).momRows();
    expect(rows.map((r) => r.key)).toEqual([
      "sigma",
      "z",
      "slope",
      "ma_short",
      "ma_long",
      "confidence",
    ]);
    for (const row of rows) expect(typeof row.value).toBe("string");
  });

  it("l'aiguille est à gauche pour une foule satisfaite", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const comp = component(prices);
    comp.data.chart.momentum.score_raw = 1.0;
    expect(comp.momGaugePos()).toBe(0);
    comp.data.chart.momentum.score_raw = 0.0;
    expect(comp.momGaugePos()).toBe(100);
    comp.data.chart.momentum.score_raw = null;
    expect(comp.momGaugePos()).toBe(50);
  });

  it("les intervalles fusionnent les états contigus", () => {
    const prices = Array.from({ length: 8 }, (_, i) => 100 + i);
    const comp = component(prices);
    // bas, bas, bas, neutre, neutre, haut, haut, bas
    comp.data.chart.momentum.raw = [0.1, 0.1, 0.1, 0.5, 0.5, 0.8, 0.8, 0.1];
    const runs = comp.momRuns();
    expect(runs.map((r) => r.state)).toEqual(["bas", "neutre", "haut", "bas"]);
    expect(runs[0]).toMatchObject({ start: 0, end: 2 });
    expect(runs[3]).toMatchObject({ start: 7, end: 7 });
  });

  it("une série entièrement neutre donne un seul intervalle", () => {
    const prices = Array.from({ length: 8 }, (_, i) => 100 + i);
    const comp = component(prices);
    comp.data.chart.momentum.raw = new Array(8).fill(0.5);
    expect(comp.momRuns()).toHaveLength(1);
  });

  it("la bascule ajusté lit la série de cours ajustée", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const adjPrices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0009 * i));
    const raw = component(prices, { series: "raw" }).momStats();
    const adj = component(prices, { series: "adj", adjPrices }).momStats();
    expect(adj.slope).toBeGreaterThan(raw.slope * 2);
  });
});

describe("api.momentumBacktest", () => {
  it("construit l'URL avec les quatre paramètres encodés", async () => {
    const calls = [];
    const realFetch = global.fetch;
    global.fetch = async (url) => {
      calls.push(url);
      return { ok: true, json: async () => ({}) };
    };
    try {
      await api.momentumBacktest("stock", "RI.PA", "2020-01-01", "2021-01-01", "adj");
      await api.momentumBacktest("basket", 7, "2020-01-01", "2021-01-01", "raw");
    } finally {
      global.fetch = realFetch;
    }
    expect(calls[0]).toBe(
      "/api/stock/RI.PA/momentum-backtest?start=2020-01-01&end=2021-01-01&series=adj",
    );
    expect(calls[1]).toBe(
      "/api/index/7/momentum-backtest?start=2020-01-01&end=2021-01-01&series=raw",
    );
  });
});

// #31 : la carte « Fiabilité de l'indicateur » compare buy & hold et la
// stratégie sur la fenêtre visible. Le backtest est calculé côté serveur (la
// grille du graphe est décimée) ; le front ne fait que charger et formater.
function backtestPayload({ cagr = 6.8, strategyCagr = 9.1 } = {}) {
  const block = (value) => ({
    cagr_pct: value,
    volatility_pct: 18.2,
    sharpe: 0.37,
    sortino: null,
    max_drawdown_pct: -38.4,
    calmar: 0.18,
    invested_pct: 100,
    trades: 1,
  });
  return {
    buy_hold: block(cagr),
    strategy: { ...block(strategyCagr), invested_pct: 64, trades: 7 },
    window: { start: "2015-01-02", end: "2024-12-31", sessions: 2561 },
  };
}

function loadedComponent(prices) {
  const comp = component(prices);
  comp.data.kind_payload = "stock";
  comp.data.identity = { ticker: "RI.PA" };
  return comp;
}

describe("fiabilité de l'indicateur", () => {
  it("huit mesures, deux colonnes, formatées", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    const rows = comp.momBacktestRows();
    expect(rows).toHaveLength(8);
    expect(rows.map((r) => r.key)).toEqual([
      "cagr",
      "volatility",
      "sharpe",
      "sortino",
      "max_drawdown",
      "calmar",
      "invested",
      "trades",
    ]);
    for (const row of rows) {
      expect(typeof row.buy_hold).toBe("string");
      expect(typeof row.strategy).toBe("string");
    }
    expect(rows[0].buy_hold).toBe("6,80 %");
    expect(rows[0].strategy).toBe("9,10 %");
    expect(rows[2].buy_hold).toBe("0,37");
    expect(rows[7].strategy).toBe("7");
  });

  it("une mesure absente affiche un tiret, jamais NaN", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    const sortino = comp.momBacktestRows().find((r) => r.key === "sortino");
    expect(sortino.buy_hold).toBe("—");
    expect(sortino.hint).toContain("Aucune baisse");
    comp.momBacktest.buy_hold.sharpe = Infinity;
    expect(comp.momBacktestRows()[2].buy_hold).toBe("—");
  });

  it("un échec réseau est traduit en message lisible", async () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    const spy = vi
      .spyOn(api, "momentumBacktest")
      .mockRejectedValue(new TypeError("Failed to fetch"));
    await comp.loadMomentumBacktest();
    expect(comp.momBacktestError).toContain("le serveur ne répond pas");
    spy.mockRestore();
  });

  it("la légende annonce la série et la durée", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    expect(comp.momBacktestSpan()).toBe("10 ans");
    expect(comp.momBacktestLegend()).toContain("brute, dividendes non comptés");
    expect(comp.momBacktestLegend()).toContain("10 ans");
    expect(comp.momBacktestLegend()).toContain("0,10 % par ordre");
    comp.momSeries = "adj";
    expect(comp.momBacktestLegend()).toContain("ajustée, dividendes réinvestis");
  });

  it("la légende d'un indice dit total-return, jamais « brut »", () => {
    const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.data.kind_payload = "basket";
    comp.data.identity = { index_id: 7 };
    comp.momBacktest = backtestPayload();
    expect(comp.momSeries).toBe("raw"); // le radio ajusté est désactivé
    const legend = comp.momBacktestLegend();
    expect(legend).toContain("indice total-return, dividendes réinvestis");
    expect(legend).not.toContain("non comptés");
  });

  it("le chargement est visible tant que la requête court", async () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    let resolve;
    const pending = new Promise((r) => {
      resolve = r;
    });
    const spy = vi.spyOn(api, "momentumBacktest").mockReturnValueOnce(pending);
    const p = comp.loadMomentumBacktest();
    expect(comp.momBacktestLoading).toBe(true);
    expect(comp.momBacktestRows()).toEqual([]);
    resolve(backtestPayload());
    await p;
    expect(comp.momBacktestLoading).toBe(false);
    expect(comp.momBacktestRows()).toHaveLength(8);
    spy.mockRestore();
  });

  it("changer de fiche vide les chiffres du ticker précédent", async () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    let resolve;
    const pending = new Promise((r) => {
      resolve = r;
    });
    const spy = vi
      .spyOn(api, "momentumBacktest")
      .mockResolvedValueOnce(backtestPayload())
      .mockReturnValueOnce(pending);
    await comp.loadMomentumBacktest(); // RI.PA
    expect(comp.momBacktest).not.toBeNull();
    comp.data.identity = { ticker: "AI.PA" }; // autre référence
    const p = comp.loadMomentumBacktest();
    expect(comp.momBacktest).toBeNull(); // pas de chiffres d'un autre ticker
    expect(comp.momBacktestLoading).toBe(true);
    resolve(backtestPayload());
    await p;
    expect(comp.momBacktest).not.toBeNull();
    spy.mockRestore();
  });

  it("une erreur est visible et laisse le tableau vide", async () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    const spy = vi.spyOn(api, "momentumBacktest").mockRejectedValue(new Error("panne réseau"));
    await comp.loadMomentumBacktest();
    expect(comp.momBacktestError).toBe("panne réseau");
    expect(comp.momBacktest).toBeNull();
    expect(comp.momBacktestLoading).toBe(false);    expect(comp.momBacktestRows()).toEqual([]);
    spy.mockRestore();
  });

  it("une réponse tardive ne remplace pas une réponse plus récente", async () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    let resolveOld;
    let resolveRecent;
    const old = new Promise((r) => {
      resolveOld = r;
    });
    const recent = new Promise((r) => {
      resolveRecent = r;
    });
    const spy = vi
      .spyOn(api, "momentumBacktest")
      .mockReturnValueOnce(old)
      .mockReturnValueOnce(recent);
    const p1 = comp.loadMomentumBacktest();
    comp.momSeries = "adj"; // nouvelle fenêtre logique : la clé change
    const p2 = comp.loadMomentumBacktest();
    const recentPayload = backtestPayload({ cagr: 2 });
    resolveRecent(recentPayload);
    await p2;
    resolveOld(backtestPayload({ cagr: 99 }));
    await p1;
    expect(comp.momBacktest).toBe(recentPayload);
    expect(comp.momBacktestLoading).toBe(false);
    spy.mockRestore();
  });

  it("le premier dessin déclenche le calcul, le preset et la poignée aussi", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    const load = vi.spyOn(comp, "loadMomentumBacktest").mockImplementation(() => {});
    comp.drawMomentumYear = () => {};
    comp.drawMomentumHistory = () => {};
    comp.drawMomentum();
    expect(load).toHaveBeenCalledTimes(1);
    comp.momPreset(1);
    expect(load).toHaveBeenCalledTimes(2);
    comp.momRangeChanged();
    expect(load).toHaveBeenCalledTimes(3);
  });
});
