import { beforeAll, describe, expect, it } from "vitest";
import { applyMeta } from "../src/obole/web/thresholds.js";
import { valorisationMixin } from "../src/obole/web/valorisation.js";

// #33 : la table « monde de Markovitz » mesure le COURS (σ autour de la droite,
// z, pente), pas un score de foule. Elle vit désormais dans la section
// Valorisation et recalcule ses mesures côté client sur la fenêtre choisie.

beforeAll(() => {
  // Fenêtres servies par /api/meta (source unique config.py). Sans elles, le
  // sélecteur serait vide et les tests ne diraient rien.
  applyMeta({
    reg_years_default: 20,
    reg_years_financial: 30,
    markowitz: { table_windows: [1, 5, 10, 20, 0] },
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
    ...valorisationMixin,
    mkwWindow: window,
    mkwSeries: series,
    fmt: (v) => (v == null ? "—" : Number(v).toFixed(2)),
    data: {
      kind_payload: "stock",
      chart: {
        dates,
        price_raw: prices,
        price_adj: adjPrices || prices,
        ma_short_raw: prices.map(() => 110),
        ma_long_raw: prices.map(() => 105),
      },
    },
  };
}

describe("table monde de Markovitz", () => {
  it("une droite log-parfaite donne une confiance nulle et un z nul", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const stats = component(prices).mkwStats();
    expect(stats.confidence).toBeLessThan(0.01);
    expect(Math.abs(stats.z)).toBeLessThan(0.5);
  });

  it("la fenêtre change la pente : un an contre le maximum", () => {
    // 550 jours plats puis une pente raide : la fenêtre d'un an ne voit que la
    // pente, la fenêtre MAX voit les deux régimes.
    const prices = Array.from({ length: 1100 }, (_, i) =>
      i < 550 ? 100 : 100 * Math.exp(0.002 * (i - 550)),
    );
    const oneYear = component(prices, { window: 1 }).mkwStats();
    const max = component(prices, { window: 0 }).mkwStats();
    expect(oneYear.slope).toBeGreaterThan(max.slope * 1.5);
  });

  it("les moyennes mobiles viennent du payload, jamais recalculées", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const stats = component(prices).mkwStats();
    expect(stats.maShort).toBe(110);
    expect(stats.maLong).toBe(105);
  });

  it("la fenêtre par défaut est la référence persistée", () => {
    const prices = Array.from({ length: 1100 }, (_, i) => 100 + i);
    const comp = component(prices, { window: null });
    comp.data.watch = { ref: { start: comp.data.chart.dates[500] } };
    const [start, end] = comp.mkwRange();
    expect(start).toBe(500);
    expect(end).toBe(1099);
  });

  it("sans référence persistée, la fenêtre par défaut couvre 20 ans", () => {
    const prices = Array.from({ length: 12000 }, (_, i) => 100 + i);
    const comp = component(prices, { window: null });
    const end = prices.length - 1;
    const [start] = comp.mkwRange();
    const cutoff = new Date(comp.data.chart.dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - 20);
    expect(new Date(comp.data.chart.dates[start]) >= cutoff).toBe(true);
    expect(new Date(comp.data.chart.dates[start - 1]) < cutoff).toBe(true);
  });

  it("sans référence persistée, une financière couvre 30 ans", () => {
    const prices = Array.from({ length: 15000 }, (_, i) => 100 + i);
    const comp = component(prices, { window: null });
    comp.data.identity = { kind: "financial" };
    const end = prices.length - 1;
    const [start] = comp.mkwRange();
    const cutoff = new Date(comp.data.chart.dates[end]);
    cutoff.setFullYear(cutoff.getFullYear() - 30);
    expect(new Date(comp.data.chart.dates[start]) >= cutoff).toBe(true);
    expect(new Date(comp.data.chart.dates[start - 1]) < cutoff).toBe(true);
  });

  it("la fenêtre MAX couvre toute la grille", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const [start, end] = component(prices, { window: 0 }).mkwRange();
    expect(start).toBe(0);
    expect(end).toBe(299);
  });

  it("les lignes portent les six mesures, formatées", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const rows = component(prices).mkwRows();
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

  it("la bascule ajusté lit la série de cours ajustée", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0003 * i));
    const adjPrices = Array.from({ length: 300 }, (_, i) => 100 * Math.exp(0.0009 * i));
    const raw = component(prices, { series: "raw" }).mkwStats();
    const adj = component(prices, { series: "adj", adjPrices }).mkwStats();
    expect(adj.slope).toBeGreaterThan(raw.slope * 2);
  });

  it("un indice n'a pas de série ajustée : la bascule est désactivée", () => {
    const prices = Array.from({ length: 300 }, (_, i) => 100 + i);
    const comp = component(prices);
    comp.data.kind_payload = "basket";
    expect(comp.mkwHasAdj()).toBe(false);
  });
});
