import { describe, expect, it, vi, beforeEach } from "vitest";

import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { api } from "../src/obole/web/api.js";

// #24 : jetons anti-course des sections Résumé et Risque, sur le modèle de
// `_pfPerfSeq` (Performance). Un changement rapide de compte / étiquette / période
// lance plusieurs requêtes concurrentes ; sans jeton, une réponse PÉRIMÉE arrivant
// en retard écrase l'écran avec les données d'un périmètre qui n'est plus choisi.

function comp(overrides = {}) {
  return {
    ...portfolioMixin,
    _pfMetaReady: true,
    pfBenchmark: "CW8.PA",
    pfPeriod: "max",
    portfolioAccountId: null,
    portfolioTag: "",
    $nextTick: (fn) => fn && fn(),
    drawPortfolioSummary: vi.fn(),
    drawPortfolioRisk: vi.fn(),
    loadPortfolioNames: vi.fn(),
    runCorrTest: vi.fn(),
    pfCorrTestTicker: "",
    ...overrides,
  };
}

// Résout/rejette `promise` quand on tire le déclencheur : contrôle l'ORDRE.
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((r, j) => {
    resolve = r;
    reject = j;
  });
  return { promise, resolve, reject };
}

describe("jetons anti-course (#24)", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("Résumé — une réponse périmée n'écrase pas l'écran", async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, "portfolioSummary")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const c = comp();
    const p1 = c.loadPortfolioSummary(); // requête 1 (périmée)
    const p2 = c.loadPortfolioSummary(); // requête 2 (courante)
    // La requête 1 répond APRÈS la 2 : c'est le scénario du bug.
    second.resolve({ kpis: { total_value: 2 } });
    first.resolve({ kpis: { total_value: 1 } });
    await Promise.all([p1, p2]);

    expect(c.pfSummary.kpis.total_value).toBe(2);
    expect(c.pfSummaryLoading).toBe(false);
  });

  it("Risque — une réponse périmée n'écrase pas l'écran", async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, "portfolioRisk")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const c = comp();
    const p1 = c.loadPortfolioRisk();
    const p2 = c.loadPortfolioRisk();
    second.resolve({ metrics: { volatility_pct: 2 } });
    first.resolve({ metrics: { volatility_pct: 1 } });
    await Promise.all([p1, p2]);

    expect(c.pfRisk.metrics.volatility_pct).toBe(2);
    expect(c.pfRiskLoading).toBe(false);
  });

  it("Résumé — l'état de chargement suit la dernière demande", async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, "portfolioSummary")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const c = comp();
    const p1 = c.loadPortfolioSummary();
    const p2 = c.loadPortfolioSummary();
    first.resolve({ kpis: {} }); // la périmée rend la main la première
    await p1;
    expect(c.pfSummaryLoading).toBe(true); // la courante est encore en vol
    second.resolve({ kpis: {} });
    await p2;
    expect(c.pfSummaryLoading).toBe(false);
  });

  it("Risque — une erreur périmée ne pose pas l'erreur à l'écran", async () => {
    const first = deferred();
    const second = deferred();
    vi.spyOn(api, "portfolioRisk")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);

    const c = comp();
    const p1 = c.loadPortfolioRisk();
    const p2 = c.loadPortfolioRisk();
    second.resolve({ metrics: {} });
    first.reject(new Error("boom périmé"));
    await Promise.all([p1, p2]);

    expect(c.pfRiskError).toBe("");
    expect(c.pfRisk).toEqual({ metrics: {} });
  });
});
