import { describe, expect, it } from "vitest";
import { loadApp, metaFromConfig, readConfigSource } from "./helpers/load-app.js";

// Chantier Quantitatif : la section quantitative est pilotée par la taxonomie
// `config.QUANT_GROUPS` (source unique via /api/meta). Ce fichier verrouille
// les invariants de lisibilité : une métrique par graphe, un axe honnête (puce
// « N ans »), et le comparateur multi-métriques en base 100.
const app = loadApp();
app.applyMeta(metaFromConfig(readConfigSource()));
const { obole } = app;

// Fiche de test : comptes sur 4 ans (2023-2026), dont une série COURTE (Agilité
// renseignée sur 2 ans seulement) — le cas Pernod qui étirait l'axe.
function fiche({ years = [2023, 2024, 2025, 2026], metrics } = {}) {
  const comp = obole();
  comp.$nextTick = (fn) => fn();
  const n = years.length;
  const full = (vals) => vals.concat(Array(Math.max(0, n - vals.length)).fill(null)).slice(0, n);
  comp.data = {
    kind_payload: "stock",
    identity: { last_price: 100, currency: "EUR" },
    fundamentals: {
      kind: "industrial",
      years,
      metrics: metrics || {
        "Chiffre d'affaires": full([100, 110, 120, 130]),
        "Bénéfice net": full([10, 11, 12, 13]),
        "Marge brute": full([40, 40, 41, 41]),
        "Marge opérationnelle": full([20, 20, 21, 21]),
        "Marge nette": full([10, 10, 10, 10]),
        "ROE": full([10, 11, 12, 13]),
        "ROIC": full([12, 13, 14, 15]),
        "Gearing": full([60, 58, 55, 52]),
        "Agilité": [null, null, 120, 150],
        "Actions en circulation": full([1000, 990, 980, 970]),
      },
      growth: { cagr_revenue_3y: 5, cagr_eps_3y: 4, cagr_fcf_3y: 3 },
      valuation: null,
      dividend: null,
    },
  };
  return comp;
}

describe("Quantitatif — une métrique par graphe (sauf familles de ratios)", () => {
  it("aucune carte combo : les flux sont séparés, les ratios groupés par famille", () => {
    const comp = fiche();
    for (const g of comp.fundamentalGroups()) {
      for (const c of g.cards) {
        expect(["line", "bars", "shares", "cagr"]).toContain(c.type);
      }
    }
  });

  it("les marges et les rentabilités (dont ROIC) partagent un graphe multi-lignes", () => {
    const comp = fiche();
    const cards = comp.fundamentalGroups().flatMap((g) => g.cards);
    const marges = cards.find((c) => c.title === "Marges");
    expect(marges.metrics).toEqual(["Marge brute", "Marge opérationnelle", "Marge nette"]);
    const rent = cards.find((c) => c.title === "Rentabilités (ROE · ROA · ROCE · ROIC)");
    expect(rent.metrics).toContain("ROIC");
  });

  it("le Free Cash Flow est tracé dans « Génération de cash », jamais dupliqué", () => {
    const comp = fiche({
      metrics: { "Free Cash Flow": [12, 10, 9, 11], "Cash-flow d'exploitation": [15, 13, 11, 12] },
    });
    const cards = comp.fundamentalGroups().flatMap((g) => g.cards);
    const titles = cards.map((c) => c.title);
    // Pas de carte FCF dédiée : il vit dans « Génération de cash » (OCF vs FCF).
    expect(titles).not.toContain("Free Cash Flow");
    const cash = cards.find((c) => c.title === "Génération de cash");
    expect(cash.metrics).toEqual(["Cash-flow d'exploitation", "Free Cash Flow"]);
  });

  it("chaque carte du Quantitatif a une info-bulle non vide", () => {
    const comp = fiche();
    for (const g of comp.fundamentalGroups()) {
      for (const c of g.cards) {
        // Le bouton ⓘ est rendu sur CHAQUE carte : une clé manquante ouvre un
        // panneau vide (régression #2). On verrouille la couverture.
        expect(comp.infoText(c.id), `infoText(${c.id}) est vide`).not.toBe("");
      }
    }
  });

  it("les cartes proviennent de la taxonomie config.py (source unique)", () => {
    const comp = fiche();
    const groups = comp.fundamentalGroups();
    const titles = groups.map((g) => g.title);
    expect(titles).toContain("Croissance & flux");
    expect(titles).toContain("Rentabilité & marges");
    expect(titles).toContain("Structure financière");
    const cardTitles = groups.flatMap((g) => g.cards.map((c) => c.title));
    expect(cardTitles).toContain("Chiffre d'affaires");
    expect(cardTitles).toContain("Marges");
    expect(cardTitles).toContain("Actions en circulation");
  });

  it("une carte dont la métrique est absente n'est pas créée", () => {
    const comp = fiche({ metrics: { "Chiffre d'affaires": [100, 110, 120, 130] } });
    const titles = comp.fundamentalGroups().flatMap((g) => g.cards.map((c) => c.title));
    expect(titles).toContain("Chiffre d'affaires");
    expect(titles).not.toContain("Marges");
    expect(titles).not.toContain("Actions en circulation");
  });

  it("la carte CAGR n'existe que si les comptes portent des croissances", () => {
    const withGrowth = fiche();
    expect(withGrowth.fundamentalGroups().flatMap((g) => g.cards.map((c) => c.title)))
      .toContain("Croissance annualisée (CAGR)");
    const noGrowth = fiche({ metrics: { "Chiffre d'affaires": [1, 2, 3, 4] } });
    noGrowth.data.fundamentals.growth = null;
    expect(noGrowth.fundamentalGroups().flatMap((g) => g.cards.map((c) => c.title)))
      .not.toContain("Croissance annualisée (CAGR)");
  });
});

describe("Quantitatif — axe honnête (couverture réelle)", () => {
  it("cardSpan compte les années réellement renseignées", () => {
    const comp = fiche();
    const cards = comp.fundamentalGroups().flatMap((g) => g.cards);
    const agilite = cards.find((c) => c.title === "Agilité (FCF / CAPEX)");
    // Agilité n'a que 2 valeurs (2025, 2026) sur 4 années de colonnes.
    expect(comp.cardSpan(agilite)).toBe(2);
    const ca = cards.find((c) => c.title === "Chiffre d'affaires");
    expect(comp.cardSpan(ca)).toBe(4);
  });

  it("pastilles : dernière valeur + couleur par polarité", () => {
    const comp = fiche();
    const pill = comp.metricPill("Marge nette"); // 10 % -> >= 5 (seuil) = bon
    expect(pill.display).toBe("10 %");
    expect(pill.good).toBe(true);
    // Multiple : suffixe « × » (jamais « % »), coloré par son seuil.
    expect(comp.metricPill("Gearing").display).toBe("52 %");
    // Montant : pastille neutre (pas de couleur), abrégée.
    const ca = comp.metricPill("Chiffre d'affaires");
    expect(ca.good).toBeNull();
    // Métrique absente -> pas de pastille.
    expect(comp.metricPill("Inexistante")).toBeNull();
  });

  it("metricUnit distingue pourcentage, multiple et montant", () => {
    const comp = fiche();
    expect(comp.metricUnit("Marge nette")).toBe("pct");
    expect(comp.metricUnit("Liquidité")).toBe("mult");
    expect(comp.metricUnit("PER")).toBe("mult");
    expect(comp.metricUnit("Couverture des intérêts")).toBe("mult");
    expect(comp.metricUnit("Chiffre d'affaires")).toBe("money");
  });

  it("pastille « Couverture des intérêts » : multiple « × » coloré", () => {
    const comp = fiche();
    comp.data.fundamentals.metrics["Couverture des intérêts"] = [null, null, null, 8.2];
    const pill = comp.metricPill("Couverture des intérêts");
    expect(pill.display).toBe("8,2×");
    expect(pill.good).toBe(true); // 8,2 >= 3 (seuil RATIO_THRESHOLDS)
  });

  it("cardPills liste une pastille par métrique tracée", () => {
    const comp = fiche();
    const marges = comp.fundamentalGroups().flatMap((g) => g.cards).find((c) => c.title === "Marges");
    expect(comp.cardPills(marges).map((p) => p.label))
      .toEqual(["Marge brute", "Marge opérationnelle", "Marge nette"]);
  });

  it("metricSeries ne conserve que les années renseignées (pas de trous)", () => {
    const comp = fiche();
    const { years, values } = comp.metricSeries({}, "Agilité");
    // Une série de 2 ans n'est pas étirée sur 4 années : l'axe est honnête.
    expect(years).toEqual([2025, 2026]);
    expect(values).toEqual([120, 150]);
  });

  it("cardEmpty : état vide explicite si la série a moins de 2 points", () => {
    const comp = fiche();
    // Métrique à un seul point : pas de tracé (message dans le template).
    comp.data.fundamentals.metrics["Un seul point"] = [null, null, null, 42];
    expect(comp.cardPointCount({ metrics: ["Un seul point"] })).toBe(1);
    expect(comp.cardEmpty({ metrics: ["Un seul point"] })).toBe(true);
    // Métrique entièrement vide (ligne présente, valeurs nulles) -> vide aussi.
    comp.data.fundamentals.metrics["Vide"] = [null, null, null, null];
    expect(comp.cardEmpty({ metrics: ["Vide"] })).toBe(true);
    // Série complète : tracé normal.
    expect(comp.cardEmpty({ metrics: ["Chiffre d'affaires"] })).toBe(false);
  });

  it("cardEmpty : les cartes hors `metrics` (dividende, rachats) ne sont jamais vides", () => {
    const comp = fiche();
    // Ces cartes lisent `f.dividend.per_share` / `dividend_series`, pas `metrics` :
    // le garde-fou ne doit PAS les masquer (régression : section Dividende cassée).
    // Types de la taxonomie actuelle `config.DIVIDEND_GROUPS`.
    expect(comp.cardEmpty({ type: "divbars", title: "Dividende / Action" })).toBe(false);
    expect(comp.cardEmpty({ type: "stacked", title: "Shareholder Returns" })).toBe(false);
    expect(comp.cardEmpty({ type: "kpi", title: "Métriques clés" })).toBe(false);
    expect(comp.cardEmpty({ type: "cagr", title: "Croissance annualisée (CAGR)" })).toBe(false);
  });

  it("yearRange = plage réelle de la donnée de la carte (échelle relative)", () => {
    const comp = fiche();
    // CA : 4 ans renseignés -> la carte couvre ~4 ans (bornes ±0,5).
    expect(comp.yearRange({ metrics: ["Chiffre d'affaires"] })).toEqual([2022.5, 2026.5]);
    // Agilité : 2 ans renseignés -> la carte couvre ~2 ans, jamais 4.
    expect(comp.yearRange({ metrics: ["Agilité"] })).toEqual([2024.5, 2026.5]);
    // Métrique absente : pas de plage.
    expect(comp.yearRange({ metrics: ["Inexistante"] })).toBeNull();
  });
});

describe("Quantitatif — comparateur de métriques", () => {
  it("sélectionne au plus 3 métriques", () => {
    const comp = fiche();
    comp.toggleCompare("Chiffre d'affaires");
    comp.toggleCompare("Bénéfice net");
    comp.toggleCompare("Marge nette");
    comp.toggleCompare("Agilité"); // 4e -> ignorée (plafond 3)
    expect(comp.compareKeys).toEqual(["Chiffre d'affaires", "Bénéfice net", "Marge nette"]);
  });

  it("re-cliquer une métrique active la retire", () => {
    const comp = fiche();
    comp.toggleCompare("Chiffre d'affaires");
    comp.toggleCompare("Chiffre d'affaires");
    expect(comp.compareKeys).toEqual([]);
  });

  it("les options du comparateur sont les métriques disponibles", () => {
    const comp = fiche();
    const keys = comp.compareOptions().map((o) => o.key);
    expect(keys).toContain("Chiffre d'affaires");
    expect(keys).toContain("Agilité");
  });
});
