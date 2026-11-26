import { describe, expect, it, vi } from "vitest";
import {
  loadApp,
  metaFromConfig,
  readConfigSource,
  readValorisationSource,
} from "./helpers/load-app.js";

// #34 — graphe « Prix et valorisation » à couches. Ce fichier verrouille les
// HELPERS PURS extraits de `valorisation.js` (séries bornées, statut, éventail,
// échelle et pastilles « ↑ », dé-collision, barres de dividende, CAGR du pied)
// puis le modèle de la carte (statut, pied, notes, bascules sans réseau).
const app = loadApp();
app.applyMeta(metaFromConfig(readConfigSource()));
const {
  valuationStatus,
  valuationSeries,
  valuationFan,
  valuationScale,
  valuationCorridor,
  spreadPills,
  valuationPillItems,
  dividendBars,
  valuationCagrRows,
  valuationNotes,
} = app;

const DATES = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"];

describe("Valorisation — statut de l'en-tête", () => {
  it("sous-évalué (bleu) / sur-évalué (rouge) en pourcentage", () => {
    const under = valuationStatus({
      price: 90, valoNow: 100, latestOk: true, isEnterprise: false,
      label: "Bénéfices/Actions", gapRatioLimit: 100,
    });
    expect(under.gapPct).toBeCloseTo(-10, 6);
    expect(under.good).toBe(true);
    expect(under.big).toBe(false);

    const over = valuationStatus({
      price: 150, valoNow: 100, latestOk: true, isEnterprise: false,
      label: "Bénéfices/Actions", gapRatioLimit: 100,
    });
    expect(over.gapPct).toBeCloseTo(50, 6);
    expect(over.good).toBe(false);
  });

  it("au-delà de gap_ratio_limit, le statut s'écrit en multiple", () => {
    const st = valuationStatus({
      price: 300, valoNow: 20, latestOk: true, isEnterprise: false,
      label: "Bénéfices/Actions", gapRatioLimit: 100,
    });
    expect(st.big).toBe(true);
    expect(st.ratio).toBeCloseTo(15, 6);
  });

  it("métrique courante ≤ 0 : non calculable ; multiple d'entreprise : aucun statut", () => {
    const negative = valuationStatus({
      price: 90, valoNow: null, latestOk: false, isEnterprise: false,
      label: "Bénéfices/Actions", gapRatioLimit: 100,
    });
    expect(negative.reason).toBe("negative");
    expect(negative.gapPct).toBeNull();

    const enterprise = valuationStatus({
      price: 90, valoNow: null, latestOk: true, isEnterprise: true,
      label: "EBITDA", gapRatioLimit: 100,
    });
    expect(enterprise.reason).toBe("enterprise");
    expect(enterprise.gapPct).toBeNull();
  });
});

describe("Valorisation — série bornée et escalier", () => {
  it("ne garde que les exercices positifs et ferme le dernier palier", () => {
    const s = valuationSeries(DATES, [1, 1, 2, 2], 10, true);
    expect(s).toEqual({
      x: ["2020-01-01", "2022-01-01", "2023-01-01"],
      y: [10, 20, 20],
    });
  });

  it("métrique courante négative : la courbe s'arrête au dernier exercice positif", () => {
    const s = valuationSeries(DATES, [1, 1, 2, -1], 10, false);
    expect(s.x).toEqual(["2020-01-01", "2022-01-01", "2023-01-01"]);
    expect(s.y).toEqual([10, 20, 20]);
  });

  it("multiple absent ou ≤ 0, ou série vide : aucune valorisation", () => {
    expect(valuationSeries(DATES, [1, 2, 3, 4], null, true)).toEqual({ x: [], y: [] });
    expect(valuationSeries(DATES, [1, 2, 3, 4], 0, true)).toEqual({ x: [], y: [] });
    expect(valuationSeries(DATES, [null, null, null, null], 10, true)).toEqual({ x: [], y: [] });
  });
});

describe("Valorisation — éventail et échelle", () => {
  it("l'éventail s'ouvre de ±growthSpan / ±multipleSpan via projectedValue", () => {
    const fan = valuationFan({
      latest: 5, growth: 6, multiple: 10, horizon: 5,
      growthSpan: 3, multipleSpan: 4,
    });
    expect(fan.central).toBeCloseTo(5 * 1.06 ** 5 * 10, 6);
    expect(fan.pessimistic).toBeCloseTo(5 * 1.03 ** 5 * 6, 6);
    expect(fan.optimistic).toBeCloseTo(5 * 1.09 ** 5 * 14, 6);
  });

  it("un multiple pessimiste ≤ 0 supprime l'éventail (pas d'erreur)", () => {
    const fan = valuationFan({
      latest: 5, growth: 6, multiple: 3, horizon: 5,
      growthSpan: 3, multipleSpan: 4,
    });
    expect(fan.central).toBeGreaterThan(0);
    expect(fan.pessimistic).toBeNull();
    expect(fan.optimistic).toBeGreaterThan(0);
  });

  it("échelle : 1,12 × le plus haut repère, plafonnée à yCap × le plus haut cours", () => {
    const plain = valuationScale({ prices: [10, 20], valuationY: [15], fair: 8, central: 12, yCap: 2.2 });
    expect(plain.yMax).toBeCloseTo(22.4, 6);
    expect(plain.highest).toBe(20);
    const capped = valuationScale({ prices: [10, 20], valuationY: [], fair: null, central: 100, yCap: 2.2 });
    expect(capped.yMax).toBeCloseTo(44, 6);
    expect(valuationScale({ prices: [], valuationY: [], fair: 3, central: 4, yCap: 2.2 }).yMax).toBeNull();
  });
});

describe("Valorisation — couloir sous/sur-évalué", () => {
  it("borne les deux aires sur la plage de valorisation", () => {
    const corridor = valuationCorridor({
      dates: DATES,
      price: [5, 20, 30, 40],
      valo: { x: ["2020-01-01", "2022-01-01"], y: [10, 10] },
      latestOk: true,
    });
    expect(corridor.lower).toEqual([5, 10, 10, 10]);
    expect(corridor.upper).toEqual([10, 20, 30, 40]);
  });

  it("métrique courante négative : le couloir s'arrête au dernier exercice positif", () => {
    const corridor = valuationCorridor({
      dates: DATES,
      price: [5, 20, 30, 40],
      valo: { x: ["2020-01-01", "2021-01-01"], y: [10, 10] },
      latestOk: false,
    });
    expect(corridor.x).toEqual(["2020-01-01", "2021-01-01"]);
  });

  it("sans valorisation, aucun couloir", () => {
    expect(valuationCorridor({
      dates: DATES, price: [1, 2, 3, 4], valo: { x: [], y: [] }, latestOk: true,
    })).toBeNull();
  });
});

describe("Valorisation — pastilles et dé-collision", () => {
  it("écarte deux pastilles de 16 px au moins", () => {
    const out = spreadPills([{ y: 10 }, { y: 9.5 }], { yMax: 10, heightPx: 100, minGapPx: 16 });
    // 10 → 100 px, 9,5 → 95 px, repoussée à 84 px (100 − 16).
    expect(out[0].y).toBeCloseTo(10, 6);
    expect(out[1].y).toBeCloseTo(8.4, 6);
  });

  it("espace trois pastilles de la même colonne", () => {
    const out = spreadPills([{ y: 10 }, { y: 9.9 }, { y: 9.8 }], { yMax: 10, heightPx: 100 });
    expect(out[0].y).toBeCloseTo(10, 6);
    expect(out[1].y).toBeCloseTo(8.4, 6);
    expect(out[2].y).toBeCloseTo(6.8, 6);
  });

  it("une valeur hors cadre est collée sous le plafond mais garde sa valeur", () => {
    const items = valuationPillItems({
      central: 30, optimistic: 50, pessimistic: 2, showFan: true, fanFits: true,
      yMax: 10, heightPx: 100,
    });
    const central = items.find((p) => p.key === "central");
    expect(central.value).toBe(30);
    expect(central.y).toBeLessThanOrEqual(10);
    expect(items.map((p) => p.key).sort()).toEqual(["central", "optimistic", "pessimistic"]);
  });

  it("les bornes de l'éventail n'existent que si la couche est allumée et tient", () => {
    const off = valuationPillItems({
      central: 5, optimistic: 9, pessimistic: 2, showFan: false, fanFits: true,
      yMax: 10, heightPx: 100,
    });
    expect(off.map((p) => p.key)).toEqual(["central"]);
    const noFit = valuationPillItems({
      central: 5, optimistic: 9, pessimistic: 2, showFan: true, fanFits: false,
      yMax: 10, heightPx: 100,
    });
    expect(noFit.map((p) => p.key)).toEqual(["central"]);
  });
});

describe("Valorisation — barres de dividende", () => {
  it("une barre par année de la fenêtre, année en cours creuse", () => {
    const bars = dividendBars(
      { "2015": 1, "2018": 2, "2020": 3, "2026": 1.5, "2027": 9 },
      { years: 10, currentYear: 2026 },
    );
    expect(bars.has).toBe(true);
    expect(bars.x).toEqual(["2018-07-01", "2020-07-01", "2026-07-01"]);
    expect(bars.y).toEqual([2, 3, 1.5]);
    // 2026 = année civile en cours (bâton creux) ; 2027 (futur) est ignorée.
    expect(bars.current).toEqual([false, false, true]);
  });

  it("sans versement positif sur la fenêtre : étage absent", () => {
    expect(dividendBars({ "2010": 1 }, { years: 10, currentYear: 2026 }).has).toBe(false);
    expect(dividendBars({ "2025": 0 }, { years: 10, currentYear: 2026 }).has).toBe(false);
    expect(dividendBars(null, { years: 10, currentYear: 2026 }).has).toBe(false);
  });
});

describe("Valorisation — CAGR du pied", () => {
  it("cours sur la fenêtre, métrique depuis son premier exercice, dividende complet", () => {
    const rows = valuationCagrRows({
      dates: DATES,
      priceSeries: [100, 110, 120, 121],
      metricSeries: [5, 5.5, 6, 6.05],
      dividendPerShare: { "2019": 1, "2020": 1.1, "2021": 1.21, "2022": 1.331, "2023": 1.4641 },
      fromIndex: 0,
      windowYears: 10,
      currentYear: 2023,
      isEnterprise: false,
      metricLabel: "Bénéfices/Actions",
    });
    expect(rows.map((r) => r.key)).toEqual(["price", "metric", "dividend"]);
    expect(rows[0].span).toBe("sur 10 ans");
    expect(rows[1].span).toBe("depuis 2020");
    // L'année en cours (2023) est exclue : 2019 → 2022, soit +10 %/an.
    expect(rows[2].cagr).toBeCloseTo(10, 6);
    expect(rows[2].span).toBe("sur 3 ans");
  });

  it("multiple d'entreprise : pas de ligne métrique ; dividende non calculable -> null", () => {
    const rows = valuationCagrRows({
      dates: DATES,
      priceSeries: [100, 110, 120, 121],
      metricSeries: [8, 9, 10, 11],
      dividendPerShare: { "2022": 2 },
      fromIndex: 0,
      windowYears: 10,
      currentYear: 2023,
      isEnterprise: true,
      metricLabel: "EBITDA",
    });
    expect(rows.map((r) => r.key)).toEqual(["price", "dividend"]);
    expect(rows[1].cagr).toBeNull();
  });
});

describe("Valorisation — notes sous le graphe", () => {
  it("métrique négative, multiple d'entreprise, hors cadre, dividende absent", () => {
    expect(valuationNotes({
      isEnterprise: false, latestOk: false, hasValo: true, central: 1,
      yMax: 10, hasDividends: true, years: 10,
    })).toEqual([{ key: "negative" }]);
    expect(valuationNotes({
      isEnterprise: true, latestOk: true, hasValo: false, central: 1,
      yMax: 10, hasDividends: true, years: 10,
    })).toEqual([{ key: "enterprise" }]);
    expect(valuationNotes({
      isEnterprise: false, latestOk: true, hasValo: false, central: 100,
      yMax: 10, hasDividends: false, years: 10,
    })).toEqual([
      { key: "empty" },
      { key: "out-of-frame", value: 100 },
      { key: "no-dividend", years: 10 },
    ]);
  });
});

// Fiche de test : 10 ans de cours, une métrique stable, un dividende dont
// l'année en cours est partielle.
function fiche(overrides = {}) {
  const dates = [];
  for (let year = 2017; year <= 2026; year++) dates.push(`${year}-01-01`);
  const comp = app.obole();
  comp.$nextTick = (fn) => fn();
  comp.data = {
    kind_payload: "stock",
    identity: { ticker: "TEST.PA", name: "Test SA", last_price: 95, currency: "EUR" },
    chart: {
      dates,
      price_raw: dates.map((_, i) => 50 + i * 5),
      eps_ps: dates.map(() => 5),
      ev_ebitda: dates.map(() => 8),
    },
    fundamentals: {
      kind: "industrial",
      growth: { cagr_eps_5y: 6 },
      estimates: { eps_growth: 5 },
      valuation_calc: {
        metrics: [
          {
            key: "eps",
            label: "Bénéfices/Actions",
            multiple: "PER",
            unit: "money",
            per_share: {},
            latest: 5,
            median: { "10": 10 },
            current_multiple: 10,
          },
          {
            key: "ebitda",
            label: "EBITDA",
            multiple: "EV / EBITDA",
            unit: "money",
            per_share: {},
            latest: 8,
            median: { "10": 8 },
            current_multiple: 8,
            enterprise: true,
            net_debt_per_share: 10,
          },
        ],
        periods: [5, 10, 15, 20],
        period_default: 10,
        horizon: 5,
        target_default: 12,
        dividend_yield: 3,
        dividend_per_share: {
          "2019": 2, "2020": 2.2, "2021": 2.4, "2022": 2.6, "2023": 2.8,
          "2024": 3, "2025": 3.2, "2026": 1.5,
        },
        saved: null,
        ...overrides.calc,
      },
    },
  };
  comp.valMetric = overrides.metric || "eps";
  comp.valPeriod = 10;
  comp.valGrowth = 5;
  comp.valMultiple = 10;
  comp.valTarget = 12;
  comp.valIncludeDividends = true;
  return comp;
}

describe("Valorisation — carte à couches (modèle du composant)", () => {
  it("les couches par défaut : couloir et dividende allumés, scénarios éteints", () => {
    const comp = fiche();
    expect(comp.valLayers).toEqual({ couloir: true, scenarios: false, dividendes: true });
  });

  it("l'en-tête écrit le statut et colore le verdict", () => {
    const comp = fiche();
    const status = comp.valChartStatus();
    expect(status.lead).toBe("Cours 95 EUR · valorisation 50");
    // 95 pour une valorisation de 50 : +90 %, donc sur-évalué (rouge).
    expect(status.text).toBe(" · sur-évalué de 90 %");
    expect(status.kind).toBe("bad");
  });

  it("au-delà de 100 % d'écart, l'en-tête écrit le multiple du cours", () => {
    const comp = fiche();
    comp.data.identity.last_price = 300;
    expect(comp.valChartStatus().text).toBe(" · sur-évalué (cours ×6)");
  });

  it("métrique négative : « valorisation non calculable »", () => {
    const comp = fiche();
    comp.data.fundamentals.valuation_calc.metrics[0].latest = -1;
    comp.data.chart.eps_ps = comp.data.chart.dates.map(() => -1);
    const status = comp.valChartStatus();
    expect(status.text).toBe(" · valorisation non calculable (Bénéfices/Actions négatif)");
    expect(status.kind).toBe("");
  });

  it("multiple d'entreprise : ni valorisation, ni statut, note dédiée", () => {
    const comp = fiche({ metric: "ebitda" });
    expect(comp.valChartStatus().text).toBe("");
    expect(comp.valChartLegend().valo).toBe("");
    expect(comp.valChartLegend().scenarios).toBe(true);
    expect(comp.valChartNotes()).toContain(
      "EV/EBITDA est un multiple d'entreprise : pas de courbe de valorisation ni de couloir.",
    );
  });

  it("le pied affiche trois CAGR, « — » si non calculable", () => {
    const comp = fiche();
    const footer = comp.valChartFooter();
    expect(footer.map((r) => r.key)).toEqual(["price", "metric", "dividend"]);
    // Dividende complet 2019 → 2025 : ≈ +8,15 %/an, donc bleu.
    expect(footer[2].cagr).toBeGreaterThan(8);
    expect(footer[2].cagr).toBeLessThan(8.5);
    expect(footer[2].text).toMatch(/^\+8,\d+ %\/an$/);
    expect(footer[2].kind).toBe("good");
  });

  it("une bascule redessine sans requête réseau", () => {
    const comp = fiche();
    comp.drawValuationChart = vi.fn();
    comp.valToggleLayer("scenarios");
    expect(comp.valLayers.scenarios).toBe(true);
    expect(comp.drawValuationChart).toHaveBeenCalledTimes(1);
    comp.valToggleLayer("scenarios");
    expect(comp.valLayers.scenarios).toBe(false);
    expect(comp.drawValuationChart).toHaveBeenCalledTimes(2);
  });

  it("le modèle est mémoïsé sur ses entrées (un changement de couche ne le refait pas)", () => {
    const comp = fiche();
    const a = comp.valChartModel();
    const b = comp.valChartModel();
    expect(b).toBe(a);
    comp.valGrowth = 7;
    expect(comp.valChartModel()).not.toBe(a);
  });

  it("aucune constante du graphe n'est écrite en dur dans valorisation.js", () => {
    const src = readValorisationSource();
    // Les cinq valeurs de 4.15 viennent de /api/meta (thresholds.VALUATION_CHART).
    expect(src).not.toMatch(/VALUATION_CHART_YEARS\s*=\s*10\b/);
    expect(src).not.toMatch(/FAN_GROWTH_SPAN\s*=\s*3\b/);
    expect(src).not.toMatch(/FAN_MULTIPLE_SPAN\s*=\s*4\b/);
    expect(src).not.toMatch(/CHART_Y_CAP\s*=\s*2\.2\b/);
    expect(src).not.toMatch(/GAP_RATIO_LIMIT\s*=\s*100\b/);
  });
});
