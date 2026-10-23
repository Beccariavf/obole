import { describe, expect, it } from "vitest";
import {
  loadApp,
  metaFromConfig,
  parsePyValuationGroups,
  parsePyValuationMetrics,
  readConfigSource,
  readValorisationSource,
} from "./helpers/load-app.js";

// Chantier #20 — section Valorisation. Ce fichier verrouille :
//  1. la PARITÉ des formules entre `engine/valuation_calc.py` (référence) et le
//     miroir JS de `web/valorisation.js` (recalcul live) ;
//  2. la SOURCE UNIQUE de la taxonomie/couleurs (config.py via /api/meta) ;
//  3. les invariants du modèle (matrice Baggr reconstituée au 0,01 pt).
const app = loadApp();
app.applyMeta(metaFromConfig(readConfigSource()));
const {
  obole, fairPrice, safetyMargin, estimatedReturn, targetEntryPrice, matrixGrid, colorBucket,
} = app;

// Fiche de test : comptes sur 4 ans + payload de calculatrice.
function fiche(overrides = {}) {
  const comp = obole();
  comp.$nextTick = (fn) => fn();
  comp.data = {
    kind_payload: "stock",
    identity: { last_price: 100, currency: "EUR" },
    chart: {
      dates: ["2020-01-01", "2021-01-01", "2022-01-01"],
      price_raw: [90, 100, 110],
      eps_ps: [5, 5, 5],
      per: [18, 20, 22],
    },
    fundamentals: {
      kind: "industrial",
      years: [2023, 2022, 2021, 2020],
      metrics: {},
      growth: { cagr_eps_5y: 6.0 },
      estimates: { eps_growth: 5.51 },
      valuation: null,
      dividend: null,
      valuation_calc: {
        metrics: [
          {
            key: "eps",
            label: "Bénéfices/Actions",
            multiple: "PER",
            unit: "money",
            per_share: { "2020": 4, "2021": 4.5, "2022": 5, "2023": 5.5 },
            latest: 5.5,
            median: { "5": 9.0, "10": 10.29 },
            current_multiple: 8.79,
          },
        ],
        periods: [5, 10, 15, 20],
        period_default: 10,
        horizon: 5,
        target_default: 12,
        matrix: { rows: 15, cols: 15, growth_step: 0.5, multiple_step: 1.0 },
        color_ratios: [0.5, 1.0],
        dividend_yield: 5.0,
        dividend_per_share: { "2020": 2, "2021": 2.2, "2022": 2.4 },
        saved: null,
        ...overrides.calc,
      },
    },
  };
  return comp;
}

describe("Valorisation — formules (miroir de engine/valuation_calc.py)", () => {
  it("prix juste = métrique × multiple, None sur base invalide", () => {
    expect(fairPrice(5.5, 10.29)).toBeCloseTo(56.595, 6);
    expect(fairPrice(null, 10)).toBeNull();
    expect(fairPrice(-1, 10)).toBeNull();
    expect(fairPrice(5, 0)).toBeNull();
  });

  it("marge de sécurité = (prix juste − cours) / prix juste", () => {
    expect(safetyMargin(56.595, 50)).toBeCloseTo(11.653, 2);
    expect(safetyMargin(100, 150)).toBeCloseTo(-50, 6);
    expect(safetyMargin(null, 50)).toBeNull();
    expect(safetyMargin(0, 50)).toBeNull();
  });

  it("reproduit la matrice Baggr au 0,01 pt (m0=11,359 / D=8,2)", () => {
    // Cellule (croissance 5,5 % / multiple 8,8) affichée 8,45 % par Baggr.
    const r = estimatedReturn(1, 1, 5.5, 8.8 / 11.359, 5, 8.2);
    expect(r).toBeCloseTo(8.45, 1);
    // Cellule (2,0 % / 1,8) affichée −21,26 %.
    const r2 = estimatedReturn(1, 1, 2.0, 1.8 / 11.359, 5, 8.2);
    expect(r2).toBeCloseTo(-21.26, 1);
  });

  it("le dividende s'ajoute linéairement et vaut 0 si décoché", () => {
    const base = estimatedReturn(5, 100, 5, 20, 5, 0);
    const withDiv = estimatedReturn(5, 100, 5, 20, 5, 8);
    expect(withDiv - base).toBeCloseTo(8, 6);
  });

  it("cas limites : horizon/cours/métrique nuls -> None", () => {
    expect(estimatedReturn(5, 100, 5, 20, 0)).toBeNull();
    expect(estimatedReturn(5, 0, 5, 20, 5)).toBeNull();
    expect(estimatedReturn(0, 100, 5, 20, 5)).toBeNull();
    expect(estimatedReturn(5, 100, 5, -1, 5)).toBeNull();
  });

  it("grille centrée et buckets de couleur ancrés sur la cible", () => {
    const grid = matrixGrid(5, 10, 15, 15, 0.5, 1);
    expect(grid.growths).toHaveLength(15);
    expect(grid.multiples).toHaveLength(15);
    expect(grid.growths[7]).toBe(5); // centre = index n//2
    expect(grid.multiples[7]).toBe(10);
    // Buckets : rouge < 0, brun < 0,5·cible, jaune < cible, vert >= cible.
    expect(colorBucket(-1, 12, [0.5, 1])).toBe(0);
    expect(colorBucket(3, 12, [0.5, 1])).toBe(1);
    expect(colorBucket(9, 12, [0.5, 1])).toBe(2);
    expect(colorBucket(13, 12, [0.5, 1])).toBe(3);
  });
});

describe("Valorisation — calculatrice (état + rendus)", () => {
  it("initValuation applique les défauts (croissance consensus, multiple médian)", () => {
    const comp = fiche();
    comp.initValuation();
    expect(comp.valMetric).toBe("eps");
    expect(comp.valPeriod).toBe(10);
    expect(comp.valGrowth).toBe(5.51);          // consensus analystes
    expect(comp.valMultiple).toBe(10.29);       // médiane 10 ans
    expect(comp.valTarget).toBe(12);
    expect(comp.valIncludeDividends).toBe(true);
  });

  it("initValuation privilégie les paramètres enregistrés", () => {
    const comp = fiche({ calc: { saved: {
      metric: "eps", period: 5, growth: 7, multiple: 12, target_yield: 15,
      include_dividends: false, fair_price: 66,
    } } });
    comp.initValuation();
    expect(comp.valPeriod).toBe(5);
    expect(comp.valGrowth).toBe(7);
    expect(comp.valMultiple).toBe(12);
    expect(comp.valTarget).toBe(15);
    expect(comp.valIncludeDividends).toBe(false);
  });

  it("les KPI se recalculent en direct", () => {
    const comp = fiche();
    comp.initValuation();
    comp.valMultiple = 10.29;
    comp.valGrowth = 5.51;
    // Le prix juste est le prix d'entrée atteignant la cible (dérive du multiple
    // de SORTIE et de la croissance), pas la valeur médiane.
    const expected = targetEntryPrice(
      5.5, 5.51, 10.29, 5, Number(comp.valTarget), comp.valDividendYield(), null,
    );
    expect(comp.valFairPrice()).toBeCloseTo(expected, 6);
    // La valeur médiane reste métrique × multiple médian.
    expect(comp.valMedianValue()).toBeCloseTo(5.5 * 10.29, 6);
    // Dividendes inclus (5 %) -> le rendement dépasse le cas sans dividende.
    const withDiv = comp.valEstimatedReturn();
    comp.valIncludeDividends = false;
    const withoutDiv = comp.valEstimatedReturn();
    expect(withDiv - withoutDiv).toBeCloseTo(5.0, 6);
  });

  it("le prix juste est le prix d'entrée qui atteint la cible (aller-retour)", () => {
    const comp = fiche();
    comp.initValuation();
    comp.valTarget = 12;
    comp.valGrowth = 6;
    comp.valMultiple = 11;
    const entry = comp.valFairPrice();
    expect(entry).not.toBeNull();
    // Recalculer le rendement AU prix juste redonne exactement la cible.
    const back = estimatedReturn(
      5.5, entry, 6, 11, 5, comp.valDividendYield(), null,
    );
    expect(back).toBeCloseTo(12, 6);
  });

  it("le KPI rendement se compare à la cible (benchmark)", () => {
    const comp = fiche();
    comp.initValuation();
    comp.valTarget = 12;
    comp.valGrowth = 20;
    comp.valMultiple = 20;
    expect(comp.valBeatsTarget()).toBe(true);
    comp.valTarget = 200;
    expect(comp.valBeatsTarget()).toBe(false);
  });

  it("la matrice est cohérente avec le KPI et marque la cellule active", () => {
    const comp = fiche();
    comp.initValuation();
    const m = comp.valMatrix();
    expect(m.rows).toHaveLength(15);
    expect(m.multiples).toHaveLength(15);
    // La cellule active correspond aux paramètres courants.
    const activeRow = m.rows.find((r) => r.growth === m.activeGrowth);
    const activeCell = activeRow.cells.find((c) => c.multiple === m.activeMultiple);
    expect(activeCell.value).toBeCloseTo(comp.valEstimatedReturn(), 6);
  });

  it("le pas des colonnes suit la base (pas global en repli)", () => {
    const comp = fiche();
    // Base sans multiple_step -> repli sur le pas global (1).
    comp.initValuation();
    let m = comp.valMatrix();
    expect(m.multiples[8] - m.multiples[7]).toBeCloseTo(1.0, 6);
    // On force un pas fin (0,2) sur la base courante -> les colonnes s'espacent
    // de 0,2 (comme P/B). Vérifie que le pas de la base prime sur le global.
    comp.data.fundamentals.valuation_calc.metrics[0].multiple_step = 0.2;
    m = comp.valMatrix();
    expect(m.multiples[8] - m.multiples[7]).toBeCloseTo(0.2, 6);
    expect(m.multiples[7] - m.multiples[6]).toBeCloseTo(0.2, 6);
  });

  it("detailCagr : CAGR de la fenêtre visible, réservé aux courbes « par action »", () => {
    // Une carte « par action » (groupe Croissance, pills = cagr) expose le CAGR
    // de la plage VISIBLE, borné à la disponibilité réelle de la série.
    const comp = fiche();
    comp.data.chart.dates = ["2020-01-01", "2021-01-01", "2022-01-01", "2023-01-01"];
    comp.data.chart.eps_ps = [10, 11, 12, 13];
    comp.visibleRange = () => [0, 3];
    comp.detailCard = { series: "eps_ps", pills: "cagr" };
    // 13/10 sur 3 ans -> (1,3)^(1/3) − 1 ≈ 9,14 %/an.
    expect(comp.detailCagr()).toBeCloseTo(9.14, 1);
    // Fenêtre réduite (2 points seulement) -> CAGR plus court.
    comp.visibleRange = () => [2, 3];
    expect(comp.detailCagr()).toBeCloseTo(((13 / 12) - 1) * 100, 1);
    // Une carte de MULTIPLE (pas de pills cagr) n'expose aucun CAGR.
    comp.detailCard = { series: "per", pills: "stats" };
    expect(comp.detailCagr()).toBeNull();
    // Carte nulle -> null.
    comp.detailCard = null;
    expect(comp.detailCagr()).toBeNull();
  });

  it("la valeur enregistrée pilote le prix juste du Résumé (payload)", () => {
    const comp = fiche();
    comp.initValuation();
    const payload = comp.valPayload();
    expect(payload.metric).toBe("eps");
    expect(payload.period).toBe(10);
    expect(payload.fair_price).toBeCloseTo(comp.valFairPrice(), 6);
    expect(payload.include_dividends).toBe(true);
  });

  it("valuationAvailable dépend de la présence des métriques", () => {
    const comp = fiche();
    expect(comp.valuationAvailable()).toBe(true);
    comp.data.fundamentals.valuation_calc.metrics = [];
    expect(comp.valuationAvailable()).toBe(false);
  });

  it("les cartes de courbes viennent de la taxonomie config.py", () => {
    const comp = fiche();
    comp.data.chart.eps_ps = [5, 5, 5];
    comp.data.chart.per = [18, 20, 22];
    const groups = comp.valuationGroups();
    expect(groups.length).toBeGreaterThan(0);
    for (const g of groups) {
      for (const c of g.cards) {
        expect(c.type).toBe("vline");
        expect(comp.data.chart[c.series]).toBeDefined();
      }
    }
  });

  it("chaque carte de courbe porte une info-bulle non vide (ⓘ fonctionnel)", () => {
    const comp = fiche();
    comp.data.chart.eps_ps = [5, 5, 5];
    comp.data.chart.per = [18, 20, 22];
    const cards = comp.valuationGroups().flatMap((g) => g.cards);
    expect(cards.length).toBeGreaterThan(0);
    for (const c of cards) {
      expect(comp.infoText(c.id), `infoText manquant pour ${c.id}`).toBeTruthy();
    }
  });

  it("la matrice est mémoïsée sur ses entrées (pas de recalcul par cellule)", () => {
    const comp = fiche();
    comp.initValuation();
    const a = comp.valMatrix();
    const b = comp.valMatrix();
    expect(b).toBe(a);              // même référence tant que les entrées ne bougent pas
    comp.valGrowth = 12;            // une entrée change -> nouveau calcul
    const c = comp.valMatrix();
    expect(c).not.toBe(a);
  });

  it("le bouton Enregistrer est désactivé si le prix juste est incalculable", () => {
    const comp = fiche();
    comp.initValuation();
    expect(comp.canSaveValuation()).toBe(true);
    comp.valMetric = "eps";
    // Métrique sans médiane ni valeur récente -> prix juste nul.
    comp.data.fundamentals.valuation_calc.metrics[0].median = {};
    comp.data.fundamentals.valuation_calc.metrics[0].latest = 0;
    expect(comp.valFairPrice()).toBeNull();
    expect(comp.canSaveValuation()).toBe(false);
  });

  it("valuationGroups marque le groupe Croissance en pastille cagr", () => {
    const comp = fiche();
    for (const s of ["eps_ps", "fcf_ps", "sales_ps", "book_ps", "per"]) comp.data.chart[s] = [1, 1, 1];
    const groups = comp.valuationGroups();
    const growth = groups.find((g) => g.title === "Croissance");
    const valorisation = groups.find((g) => g.title === "Valorisation");
    expect(growth.cards).toHaveLength(4);
    expect(growth.cards.every((c) => c.pills === "cagr")).toBe(true);
    expect(valorisation.cards.every((c) => c.pills === "stats")).toBe(true);
  });

  it("la pastille du groupe Croissance est le CAGR de la fenêtre (bleu si ≥ 0)", () => {
    const comp = fiche();
    comp._valStatsCache["bnpa-par-action"] = { cagr: 7.5, median: 5, high: 6, low: 4 };
    const pills = comp.valuationPills({ id: "bnpa-par-action", pills: "cagr", unit: "money" });
    expect(pills).toHaveLength(1);
    expect(pills[0].label).toBe("Croissance");
    expect(pills[0].display).toContain("7,5");
    expect(pills[0].display).toContain("%/an");
    expect(pills[0].good).toBe(true);
    // CAGR négatif -> rouge (mal) ; absent -> aucune pastille.
    comp._valStatsCache["neg"] = { cagr: -3 };
    expect(comp.valuationPills({ id: "neg", pills: "cagr" })[0].good).toBe(false);
    comp._valStatsCache["none"] = { cagr: null };
    expect(comp.valuationPills({ id: "none", pills: "cagr" })).toEqual([]);
  });

  it("les cartes de multiples gardent High / Médiane / Low", () => {
    const comp = fiche();
    comp._valStatsCache["p-e"] = { cagr: 1, median: 20, high: 25, low: 15 };
    const pills = comp.valuationPills({ id: "p-e", pills: "stats", unit: "mult" });
    expect(pills.map((p) => p.label)).toEqual(["High", "Médiane", "Low"]);
  });

  it("_seriesAvailableRange borne la plage à la disponibilité réelle", () => {
    const comp = fiche();
    expect(comp._seriesAvailableRange([null, null, 1, 2, 3, null])).toEqual([2, 4]);
    expect(comp._seriesAvailableRange([1, 2, 3])).toEqual([0, 2]);
    expect(comp._seriesAvailableRange([null, null])).toEqual([0, 1]);
  });

  it("valOnBase ré-amorce le multiple sur la médiane de la base/période", () => {
    const comp = fiche();
    comp.initValuation();
    comp.valPeriod = 5;
    comp.valMultiple = 999; // valeur « ancienne » qui ne doit pas survivre
    comp.valOnBase();
    expect(comp.valMultiple).toBe(9.0); // médiane 5 ans
  });

  it("les Prévisions ne s'affichent que pour la base Bénéfices/Actions", () => {
    const comp = fiche();
    comp.valMetric = "eps";
    expect(comp.valForecast()).toBe(5.51);
    comp.data.fundamentals.valuation_calc.metrics.push({ key: "sales", label: "CA/Action" });
    comp.valMetric = "sales";
    expect(comp.valForecast()).toBeNull();
  });

  it("downloadValuation utilise le CSV du projet (séparateur virgule, décimales point)", () => {
    const comp = fiche();
    comp.initValuation();
    comp._csvCell = (v) => (v == null ? "" : typeof v === "number" ? String(v) : String(v));
    let captured = null;
    comp._downloadCsv = (content) => { captured = content; };
    comp.downloadValuation();
    expect(captured).toContain("# Obole — Calculatrice de prix juste");
    expect(captured).toContain("prix_juste,");
    expect(captured).not.toContain(";");
  });

  it("valNum1 formate la matrice à une décimale (fr-FR)", () => {
    const comp = fiche();
    expect(comp.valNum1(12.34)).toBe("12,3");
    expect(comp.valNum1(17.0)).toBe("17");
    expect(comp.valNum1(-9.87)).toBe("-9,9");
    expect(comp.valNum1(null)).toBe("—");
  });

  it("_stepCorners réduit une série en escalier à ses coins (spline)", () => {
    const comp = fiche();
    const xs = ["2020", "2021", "2022", "2023", "2024"];
    const ys = [5, 5, 5, 8, 8];
    expect(comp._stepCorners(xs, ys)).toEqual({ x: ["2020", "2023", "2024"], y: [5, 8, 8] });
    expect(comp._stepCorners(xs, [null, null])).toBeNull();
  });

  it("la hauteur du graphe prix juste vient de config (560)", () => {
    expect(app.CHART_HEIGHTS.valuation_hero).toBe(560);
  });
});

describe("Valorisation — source unique (config.py via /api/meta)", () => {
  const source = readConfigSource();

  it("la taxonomie des bases vient de config.py", () => {
    expect(app.VALUATION_METRICS.map((m) => m.key)).toEqual(
      parsePyValuationMetrics(source).map((m) => m.key),
    );
  });

  it("le pas des multiples par base vient de config.py", () => {
    const parsed = Object.fromEntries(
      parsePyValuationMetrics(source).map((m) => [m.key, m.multiple_step]),
    );
    // PER, P/FCF et EV/EBITDA restent au pas de 1 ; P/CA et P/B passent au pas fin.
    expect(parsed).toEqual({ eps: 1.0, fcf: 1.0, ebitda: 1.0, sales: 0.1, book: 0.2 });
  });

  it("les groupes de courbes viennent de config.py", () => {
    const parsed = parsePyValuationGroups(source);
    const jsSeries = app.VALUATION_GROUPS.flatMap((g) => g.cards.map((c) => c.series));
    const pySeries = parsed.flatMap((g) => g.cards.map((c) => c.series));
    expect(jsSeries).toEqual(pySeries);
  });

  it("aucun seuil littéral de valorisation dans le JS", () => {
    const src = readValorisationSource();
    // L'horizon et la cible viennent de /api/meta : pas de valeur en dur.
    expect(src).not.toMatch(/HORIZON\s*=\s*5\b/);
    expect(src).not.toMatch(/TARGET\s*=\s*12\b/);
  });
});
