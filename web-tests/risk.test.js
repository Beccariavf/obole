import { beforeEach, describe, expect, it } from "vitest";

import { riskMixin } from "../src/obole/web/risk.js";
import { applyMeta } from "../src/obole/web/thresholds.js";

// #33 — section « Risque & dynamique » : les seuils viennent de /api/meta,
// le rouge ne marque que la volatilité AU-DESSUS du seuil, et l'historique
// court se dit sans verdict.

function isoDates(n) {
  const out = [];
  const d = new Date(Date.UTC(2010, 0, 4));
  while (out.length < n) {
    const day = d.getUTCDay();
    if (day !== 0 && day !== 6) out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

const DATES = isoDates(3000);

function makeApp(nowOverrides = {}) {
  const n = DATES.length;
  return {
    ...riskMixin,
    data: {
      kind_payload: "stock",
      identity: { ticker: "RI.PA" },
      chart: {
        dates: DATES,
        risk: {
          drawdown_pct: DATES.map((_, i) => -((i % 100) / 10)),
          vol_pct: DATES.map((_, i) => 15 + (i % 50) / 10),
          vol_threshold_pct: 20,
          now: {
            drawdown_pct: -12.5,
            peak_date: DATES[n - 30],
            vol_pct: 34,
            vol_percentile: 92,
            bench_vol_pct: 15,
            mom_12_1_pct: -18,
            bench_mom_12_1_pct: 4,
            ...nowOverrides,
          },
        },
      },
    },
  };
}

const META = {
  risk: {
    vol_window: 40,
    vol_anomaly_pctile: 80,
    vol_min_points: 504,
    mom_lookback: 252,
    mom_skip: 21,
    benchmark: "^FCHI",
    default_years: 10,
  },
  chart_heights: { risk: 420 },
};

beforeEach(() => {
  applyMeta(META);
});

describe("seuils lus depuis /api/meta", () => {
  it("fenêtre, centile d'anomalie et plage par défaut viennent du payload", () => {
    const app = makeApp();
    expect(app.riskVolWindow()).toBe(40);
    expect(app.riskAnomalyPctile()).toBe(80);
    expect(app.riskDefaultYears()).toBe(10);
  });

  it("le percentile n'est une anomalie qu'au seuil ou au-dessus", () => {
    const app = makeApp({ vol_percentile: 80 });
    expect(app.riskPercentileAnomaly()).toBe(true);
    app.data.chart.risk.now.vol_percentile = 79.9;
    expect(app.riskPercentileAnomaly()).toBe(false);
    app.data.chart.risk.now.vol_percentile = null;
    expect(app.riskPercentileAnomaly()).toBe(false);
  });
});

describe("rouge réservé aux passages au-dessus du seuil", () => {
  it("rend null partout sauf strictement au-dessus du seuil", () => {
    const app = makeApp();
    expect(app.riskAbove([19, 20, 20.1, null, 34])).toEqual([null, null, 20.1, null, 34]);
  });

  it("sans seuil calculable, aucune valeur n'est marquée", () => {
    const app = makeApp();
    app.data.chart.risk.vol_threshold_pct = null;
    expect(app.riskAbove([10, 20, 30])).toEqual([null, null, null]);
  });
});

describe("historique court", () => {
  it("12-1 absent : « — » et son infobulle", () => {
    const app = makeApp({ mom_12_1_pct: null });
    const [mom] = app.riskMomentumParts();
    expect(mom.text).toContain("12-1 (hors dividendes) : —");
    expect(mom.title).toMatch(/Historique trop court/);
  });

  it("percentile absent : mention « historique trop court pour situer »", () => {
    const app = makeApp({ vol_percentile: null });
    const short = app.riskVolParts().find((p) => p.key === "short");
    expect(short.text).toBe("historique trop court pour situer");
    expect(short.bad).toBe(false);
  });

  it("volatilité absente : « — » expliqué, mention d'historique court", () => {
    const app = makeApp({ vol_pct: null, vol_percentile: null });
    const parts = app.riskVolParts();
    const vol = parts.find((p) => p.key === "vol");
    expect(vol.text).toContain("Volatilité 40 j : —");
    expect(vol.title).toMatch(/moins de 40 séances/);
    expect(parts.find((p) => p.key === "short").text).toBe("historique trop court pour situer");
  });

  it("le percentile affiché garde sa décimale, comme la décision de rougeur", () => {
    applyMeta({ ...META, risk: { ...META.risk, vol_anomaly_pctile: 90 } });
    const app = makeApp({ vol_percentile: 89.6 });
    const pctile = app.riskVolParts().find((p) => p.key === "pctile");
    expect(pctile.text).toContain("89,6 %");
    expect(app.riskPercentileAnomaly()).toBe(false);
  });
});

describe("lignes factuelles", () => {
  it("chute, volatilité et 12-1 sans verdict", () => {
    const app = makeApp();
    expect(app.riskDrawdownText()).toContain("Chute depuis le plus haut : -12,5 %");
    expect(app.riskDrawdownText()).toContain("plus haut le");
    const vol = app.riskVolParts();
    expect(vol[0].text).toContain("Volatilité 40 j : 34 %");
    expect(vol.find((p) => p.key === "pctile").bad).toBe(true);
    expect(vol.find((p) => p.key === "bench").text).toBe("CAC 40 : 15 %");
    const mom = app.riskMomentumParts();
    expect(mom[0].text).toBe("12-1 (hors dividendes) : -18 %");
    expect(mom[1].text).toBe("CAC 40 : +4 %");
  });
});

describe("puces de période", () => {
  it("10 ans par défaut, puis Max sur toute l'histoire", () => {
    const app = makeApp();
    expect(app.riskChipActive(10)).toBe(true);
    expect(app.riskChipActive(1)).toBe(false);

    const [start, end] = app.riskVisible();
    const cutoff = new Date(DATES[DATES.length - 1]);
    cutoff.setFullYear(cutoff.getFullYear() - 10);
    const expected = DATES.findIndex((d) => new Date(d) >= cutoff);
    expect(start).toBe(expected);
    expect(end).toBe(DATES.length - 1);

    app.riskPreset("max");
    expect(app.riskChipActive("max")).toBe(true);
    expect(app.riskVisible()).toEqual([0, DATES.length - 1]);
  });

  it("1A borne la plage à un an de séances", () => {
    const app = makeApp();
    app.riskPreset(1);
    const [start, end] = app.riskVisible();
    const cutoff = new Date(DATES[end]);
    cutoff.setFullYear(cutoff.getFullYear() - 1);
    expect(start).toBe(DATES.findIndex((d) => new Date(d) >= cutoff));
    expect(end).toBe(DATES.length - 1);
  });
});
