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

// #31 puis #32 : la carte « Fiabilité de l'indicateur » montre le MARCHÉ pendant
// les séances in et out, plus le rendement réel de la stratégie en pied. Le
// backtest est calculé côté serveur (la grille du graphe est décimée) ; le front
// ne fait que charger, formater et colorer.
function backtestBlock(overrides = {}) {
  return {
    cagr_pct: 6.8,
    volatility_pct: 18.2,
    sharpe: 0.37,
    sortino: null,
    max_drawdown_pct: -38.4,
    calmar: 0.18,
    sessions_pct: 100,
    ...overrides,
  };
}

function backtestPayload({
  cagr = 6.8,
  inCagr = 9.1,
  outCagr = -2.4,
  trades = 27,
  strategyCagr = 4.2,
} = {}) {
  return {
    buy_hold: backtestBlock({ cagr_pct: cagr }),
    in: backtestBlock({ cagr_pct: inCagr, sessions_pct: 64 }),
    out: backtestBlock({ cagr_pct: outCagr, sessions_pct: 36, sharpe: -0.11 }),
    window: { start: "2015-01-02", end: "2024-12-31", sessions: 2561 },
    trades,
    strategy_cagr_pct: strategyCagr,
  };
}

function loadedComponent(prices) {
  const comp = component(prices);
  comp.data.kind_payload = "stock";
  comp.data.identity = { ticker: "RI.PA" };
  return comp;
}

describe("fiabilité de l'indicateur", () => {
  it("sept mesures, trois colonnes, formatées", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    const rows = comp.momBacktestRows();
    expect(rows).toHaveLength(7);
    expect(rows.map((r) => r.key)).toEqual([
      "cagr",
      "volatility",
      "sharpe",
      "sortino",
      "max_drawdown",
      "calmar",
      "sessions",
    ]);
    for (const row of rows) {
      expect(row.cells).toHaveLength(3); // Buy & hold, in, out
      for (const cell of row.cells) expect(typeof cell.value).toBe("string");
    }
    expect(rows[0].label).toBe("CAGR");
    expect(rows[0].cells.map((c) => c.value)).toEqual(["6,80 %", "9,10 %", "-2,40 %"]);
    expect(rows[2].cells[0].value).toBe("0,37");
    expect(rows[6].label).toBe("Part des séances");
    expect(rows[6].cells.map((c) => c.value)).toEqual(["100,00 %", "64,00 %", "36,00 %"]);
  });

  it("la polarité est standard en in et INVERSÉE en out", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    // Même CAGR positif dans les deux paniers : bleu dedans, rouge dehors.
    comp.momBacktest = backtestPayload({ inCagr: 2.4, outCagr: 2.4 });
    const cagr = comp.momBacktestRows().find((r) => r.key === "cagr");
    expect(cagr.cells[0].good).toBe(true); // buy & hold, polarité standard
    expect(cagr.cells[1].good).toBe(true); // in, positif = bon signe
    expect(cagr.cells[2].good).toBe(false); // out, positif = mauvais signe
    expect(comp.momCellClass(cagr.cells[1])).toBe("good");
    expect(comp.momCellClass(cagr.cells[2])).toBe("bad");
    // Un out négatif redevient bleu : le signal a bien évité les baisses.
    comp.momBacktest.out.cagr_pct = -2.4;
    const reverse = comp.momBacktestRows().find((r) => r.key === "cagr");
    expect(reverse.cells[2].good).toBe(true);
    expect(comp.momCellClass(reverse.cells[2])).toBe("good");
  });

  it("une valeur qui s'affiche 0,00 % reste neutre", () => {
    // La couleur suit la valeur LUE : 0,0004 % s'affiche « 0,00 % », donc ni
    // bleu ni rouge — sinon la table prêterait un signe invisible à l'écran.
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload({ inCagr: 0.0004, outCagr: 0.0004 });
    const cagr = comp.momBacktestRows().find((r) => r.key === "cagr");
    expect(cagr.cells[1].value).toBe("0,00 %");
    expect(cagr.cells[1].good).toBeNull();
    expect(cagr.cells[2].good).toBeNull();
    expect(comp.momCellClass(cagr.cells[2])).toBe("");
    // Un négatif négligeable s'affiche « -0,00 % » : neutre aussi.
    comp.momBacktest.in.cagr_pct = -0.0004;
    expect(comp.momBacktestRows()[0].cells[1].value).toBe("-0,00 %");
    expect(comp.momBacktestRows()[0].cells[1].good).toBeNull();
    // Juste au-dessus, l'arrondi affiche un signe : la couleur revient.
    comp.momBacktest.in.cagr_pct = 0.006;
    expect(comp.momBacktestRows()[0].cells[1].value).toBe("0,01 %");
    expect(comp.momBacktestRows()[0].cells[1].good).toBe(true);
    // La frontière exacte : −0,005 s'affiche « -0,01 % », donc se colore
    // (arrondi demi vers l'extérieur, comme Intl — pas vers zéro).
    comp.momBacktest.in.cagr_pct = -0.005;
    expect(comp.momBacktestRows()[0].cells[1].value).toBe("-0,01 %");
    expect(comp.momBacktestRows()[0].cells[1].good).toBe(false);
  });

  it("les mesures non signées restent neutres, dans toutes les colonnes", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    for (const key of ["volatility", "max_drawdown", "sessions"]) {
      const row = comp.momBacktestRows().find((r) => r.key === key);
      for (const cell of row.cells) {
        expect(cell.good).toBeNull();
        expect(comp.momCellClass(cell)).toBe("");
      }
    }
  });

  it("une mesure absente affiche un tiret, jamais NaN", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    const sortino = comp.momBacktestRows().find((r) => r.key === "sortino");
    for (const cell of sortino.cells) expect(cell.value).toBe("—");
    expect(sortino.hint).toContain("Aucune baisse");
    comp.momBacktest.buy_hold.sharpe = Infinity;
    expect(comp.momBacktestRows()[2].cells[0].value).toBe("—");
  });

  it("un panier vide donne un tiret par mesure et 0 % de part", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    // Fenêtre entièrement investie : out n'a aucune séance.
    Object.assign(comp.momBacktest.out, {
      cagr_pct: null,
      volatility_pct: null,
      sharpe: null,
      sortino: null,
      max_drawdown_pct: null,
      calmar: null,
      sessions_pct: 0,
    });
    const rows = comp.momBacktestRows();
    for (const row of rows.slice(0, 6)) expect(row.cells[2].value).toBe("—");
    expect(rows[6].cells[2].value).toBe("0,00 %");
    expect(rows[6].cells[2].good).toBeNull();
    // La table reste construite : aucune ligne perdue, aucun crash.
    expect(rows).toHaveLength(7);
  });

  it("le pied affiche les trades et le CAGR de la stratégie", () => {
    const comp = loadedComponent(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.momBacktest = backtestPayload();
    expect(comp.momBacktestTrades()).toBe("27");
    expect(comp.momBacktestFoot()).toBe("27 trades · stratégie 4,20 %/an");
    expect(comp.momBacktestNote()).toContain("conditionnel");
    expect(comp.momBacktestNote()).toContain("séances in et out");
    // Un trade au singulier, et l'absence de trades reste lisible.
    comp.momBacktest.trades = 1;
    expect(comp.momBacktestFoot()).toContain("1 trade ·");
    comp.momBacktest.trades = null;
    expect(comp.momBacktestTrades()).toBe("—");
    expect(comp.momBacktestFoot()).toContain("— ·");
    comp.momBacktest.strategy_cagr_pct = null;
    expect(comp.momBacktestFoot()).toContain("stratégie —/an");
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
    expect(comp.momBacktestRows()).toHaveLength(7);
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
    expect(comp.momBacktestLoading).toBe(false);
    expect(comp.momBacktestRows()).toEqual([]);
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

// Phase 1 de la lecture du score : le rang du score dans l'histoire du titre.
// Il arrive déjà calculé dans le payload (historique complet, pas la plage
// affichée) ; le front ne fait que choisir la série et formater le libellé.
describe("lecture du score : percentile", () => {
  it("le rang suit la bascule brut / ajusté", () => {
    const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.data.chart.momentum.percentile_raw = 30;
    comp.data.chart.momentum.percentile_adj = 80;
    comp.data.chart.momentum.history_start = "1998-05-04";
    expect(comp.momPercentile()).toBe(30);
    expect(comp.momPercentileLabel()).toBe(
      "30e percentile de l'historique du titre, depuis 1998",
    );
    comp.momSeries = "adj";
    expect(comp.momPercentile()).toBe(80);
  });

  it("le premier rang s'écrit « 1er »", () => {
    const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.data.chart.momentum.percentile_raw = 1;
    expect(comp.momPercentileLabel()).toBe("1er percentile de l'historique du titre");
  });

  it("sans rang, la ligne est vide — jamais un tiret", () => {
    const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    expect(comp.momPercentile()).toBeNull();
    expect(comp.momPercentileLabel()).toBe("");
    // Un rang illisible ne s'affiche pas non plus.
    comp.data.chart.momentum.percentile_raw = "abc";
    expect(comp.momPercentile()).toBeNull();
    comp.data.chart.momentum.percentile_raw = Number.POSITIVE_INFINITY;
    expect(comp.momPercentile()).toBeNull();
  });

  it("un indice sans série ajustée lit le rang brut, même bascule sur ajusté", () => {
    const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    comp.data.chart.momentum.adj = null;
    comp.data.chart.momentum.percentile_raw = 42;
    comp.data.chart.momentum.percentile_adj = null;
    comp.momSeries = "adj"; // radio désactivé, mais la valeur peut rester
    expect(comp.momUsesAdj()).toBe(false);
    expect(comp.momPercentile()).toBe(42);
  });
});

// Phase 2 de la lecture du score : le rendement qui a suivi chaque zone. Le
// calcul vit côté serveur (historique complet) ; le front range les quatre
// lignes, marque la zone courante et formate.
function conditionalBlock(overrides = {}) {
  return {
    median_pct: 8.24,
    p10_pct: -4.2,
    p90_pct: 19.82,
    episodes: 7,
    thin: false,
    ...overrides,
  };
}

function conditionalPayload(overrides = {}) {
  return {
    zones: {
      bas: conditionalBlock({ median_pct: -2.4, p10_pct: -18.2, p90_pct: 9.6, episodes: 9 }),
      neutre: conditionalBlock(),
      haut: conditionalBlock({ median_pct: 14.1, p10_pct: 2.4, p90_pct: 28.6, episodes: 4 }),
    },
    baseline: conditionalBlock(),
    horizon: 252,
    ...overrides,
  };
}

function readingComponent({ series = "raw", block = conditionalPayload() } = {}) {
  const comp = component(Array.from({ length: 300 }, (_, i) => 100 + i), { series });
  // Le `fmt` réel vient de l'application (deux décimales, virgule française) :
  // les libellés de zone portent le seuil formaté comme à l'écran.
  comp.fmt = (v) => Number(v).toFixed(2).replace(".", ",");
  comp.data.chart.momentum.conditional_raw = block;
  comp.data.chart.momentum.conditional_adj = block;
  comp.data.chart.momentum.score_raw = 0.8; // score courant : zone haute
  return comp;
}

describe("lecture du score : rendement conditionnel", () => {
  it("quatre lignes : trois zones puis le repère global", () => {
    const rows = readingComponent().momConditionalRows();
    expect(rows.map((r) => r.key)).toEqual(["bas", "neutre", "haut", "baseline"]);
    expect(rows[0].label).toBe("Score bas (< 0,35)");
    expect(rows[2].label).toBe("Score haut (> 0,60)");
    expect(rows[3].label).toBe("Tout l'historique");
    // Les pourcentages se lisent au dixième, l'intervalle en « 10e / 90e »,
    // les épisodes en entier.
    expect(rows[1].median).toBe("8,2 %");
    expect(rows[1].range).toBe("-4,2 % / 19,8 %");
    expect(rows[1].episodes).toBe("7");
  });

  it("la zone du score courant est distinguée", () => {
    const comp = readingComponent();
    expect(comp.momConditionalRows().map((r) => r.current)).toEqual([
      false,
      false,
      true,
      false,
    ]);
    // Changer de score courant change la ligne distinguée.
    comp.data.chart.momentum.score_raw = 0.1;
    expect(comp.momConditionalRows().map((r) => r.current)).toEqual([
      true,
      false,
      false,
      false,
    ]);
    // Le repère global n'est jamais « courant ».
    comp.data.chart.momentum.score_raw = 0.5;
    const neutral = comp.momConditionalRows();
    expect(neutral[1].current).toBe(true);
    expect(neutral[3].current).toBe(false);
  });

  it("une zone sans fenêtre garde sa ligne, en tirets", () => {
    const comp = readingComponent({
      block: conditionalPayload({
        zones: {
          bas: null,
          neutre: conditionalBlock(),
          haut: conditionalBlock(),
        },
      }),
    });
    const rows = comp.momConditionalRows();
    expect(rows).toHaveLength(4);
    expect(rows[0]).toMatchObject({ median: "—", range: "—", episodes: "—" });
  });

  it("la zone courante sans fenêtre n'est pas marquée", () => {
    const comp = readingComponent({
      block: conditionalPayload({
        zones: { bas: null, neutre: conditionalBlock(), haut: conditionalBlock() },
      }),
    });
    comp.data.chart.momentum.score_raw = 0.1; // zone basse, absente du payload
    expect(comp.momConditionalRows().every((r) => r.current)).toBe(false);
  });

  it("aucune zone complète : pas de carte", () => {
    const comp = readingComponent({
      block: conditionalPayload({
        zones: { bas: null, neutre: null, haut: null },
      }),
    });
    expect(comp.momConditionalRows()).toEqual([]);
    // Un payload sans bloc conditionnel (cache ancien) ne casse rien non plus.
    const legacy = component(Array.from({ length: 300 }, (_, i) => 100 + i));
    expect(legacy.momConditional()).toBeNull();
    expect(legacy.momConditionalRows()).toEqual([]);
  });

  it("la note dit l'horizon, le chevauchement et les épisodes", () => {
    const comp = readingComponent();
    const note = comp.momConditionalNote();
    expect(note).toContain("252 séances");
    expect(note).toContain("chevauchent");
    expect(note).toContain("pas des observations indépendantes");
    expect(note).toContain("épisodes");
    expect(note).not.toContain("presque rien"); // aucune zone `thin` ici
    // L'horizon vient du payload : pas de « 12 mois » recopié côté JS.
    comp.data.chart.momentum.conditional_raw = conditionalPayload({ horizon: 126 });
    expect(comp.momConditionalNote()).toContain("126 séances");
    delete comp.data.chart.momentum.conditional_raw.horizon;
    expect(comp.momConditionalNote()).toContain("Le rendement qui a suivi chaque date.");
  });

  it("une zone `thin` porte la mention de prudence", () => {
    const block = conditionalPayload({
      zones: {
        bas: conditionalBlock({ thin: true, episodes: 2 }),
        neutre: conditionalBlock(),
        haut: conditionalBlock(),
      },
    });
    const comp = readingComponent({ block });
    const rows = comp.momConditionalRows();
    expect(rows[0].thin).toBe(true);
    expect(rows[0].hint).toContain("Trop peu d'épisodes");
    expect(rows[1].hint).toBeUndefined();
    expect(comp.momConditionalNote()).toContain("trop peu d'épisodes");
  });

  it("le conditionnel suit la bascule ajusté", () => {
    const comp = readingComponent();
    comp.data.chart.momentum.conditional_raw = conditionalPayload({
      zones: { bas: conditionalBlock({ median_pct: 1.0 }), neutre: null, haut: null },
    });
    comp.data.chart.momentum.conditional_adj = conditionalPayload({
      zones: { bas: null, neutre: null, haut: conditionalBlock({ median_pct: 12.0 }) },
    });
    expect(comp.momConditionalRows()[0].median).toBe("1,0 %");
    comp.momSeries = "adj";
    expect(comp.momConditionalRows()[2].median).toBe("12,0 %");
    // Un indice sans série ajustée retombe sur le brut, jamais sur du vide.
    comp.data.chart.momentum.adj = null;
    comp.data.chart.momentum.conditional_adj = null;
    expect(comp.momConditionalRows()[0].median).toBe("1,0 %");
  });

  it("une valeur illisible devient un tiret, jamais NaN", () => {
    const comp = readingComponent({
      block: conditionalPayload({
        baseline: conditionalBlock({ median_pct: Number.NaN, episodes: null }),
      }),
    });
    const baseline = comp.momConditionalRows()[3];
    expect(baseline.median).toBe("—");
    expect(baseline.episodes).toBe("—");
  });
});
