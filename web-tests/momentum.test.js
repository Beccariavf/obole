import { beforeAll, describe, expect, it } from "vitest";
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
    momentum: { window: 250, low: 0.35, high: 0.6, table_windows: [1, 5, 10, 20, 0] },
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
