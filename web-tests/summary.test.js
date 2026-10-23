import { describe, expect, it, beforeEach } from "vitest";

import { summaryMixin } from "../src/obole/web/summary.js";
import { applySummaryMeta, summaryGood, zoneLabel, marketCapLabel } from "../src/obole/web/thresholds.js";

// Synthèse fondamentale (section Résumé) : grille de valeurs non interactive.
// Les seuils viennent de config.py (via /api/summary-meta) — on les injecte ici
// comme le ferait `applySummaryMeta` au démarrage.

const META = {
  market_cap_labels: [
    [10000000000, "Large Cap"],
    [2000000000, "Mid Cap"],
    [0, "Small Cap"],
  ],
  altman_zones: [
    [2.99, "Sain"],
    [1.81, "Zone grise"],
    [null, "Détresse"],
  ],
  piotroski_zones: [
    [7, "Solide"],
    [4, "Correct"],
    [0, "Fragile"],
  ],
  summary_colors: {
    net_debt_ebitda: ["le", 2.0],
    per: ["le_pos", 12.0],
    roe_5y: ["ge", 10.0],
    shares_change_3y: ["le", 0.0],
  },
};

function comp(overrides = {}) {
  return {
    ...summaryMixin,
    _summaryMeta: META,
    fmt(v) { return v == null ? "—" : Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 2 }); },
    polarity(good) { return good === true ? "good" : good === false ? "bad" : "neutral"; },
    data: { identity: { currency: "EUR", market_cap: 5000000000 } },
    ...overrides,
  };
}

beforeEach(() => {
  applySummaryMeta(META);
});

describe("seuils de la synthèse (source unique config.py)", () => {
  it("summaryGood applique la polarité (ge / le / le_pos)", () => {
    expect(summaryGood("roe_5y", 12)).toBe(true);
    expect(summaryGood("roe_5y", 8)).toBe(false);
    expect(summaryGood("net_debt_ebitda", 1.5)).toBe(true);
    expect(summaryGood("net_debt_ebitda", 3)).toBe(false);
    // le_pos : un multiple négatif n'est jamais « bon ».
    expect(summaryGood("per", 10)).toBe(true);
    expect(summaryGood("per", -5)).toBe(false);
    expect(summaryGood("per", null)).toBe(null);
  });

  it("zoneLabel classe les scores (bornes inférieures)", () => {
    expect(zoneLabel(3.5, META.altman_zones)).toBe("Sain");
    expect(zoneLabel(2.0, META.altman_zones)).toBe("Zone grise");
    expect(zoneLabel(0.5, META.altman_zones)).toBe("Détresse");
    expect(zoneLabel(9, META.piotroski_zones)).toBe("Solide");
    expect(zoneLabel(5, META.piotroski_zones)).toBe("Correct");
    expect(zoneLabel(2, META.piotroski_zones)).toBe("Fragile");
  });

  it("marketCapLabel catégorise la capitalisation", () => {
    expect(marketCapLabel(15e9)).toBe("Large Cap");
    expect(marketCapLabel(5e9)).toBe("Mid Cap");
    expect(marketCapLabel(1e9)).toBe("Small Cap");
    expect(marketCapLabel(null)).toBe(null);
  });
});

describe("rendu de la grille", () => {
  it("formate une valeur absente en --", () => {
    const c = comp();
    expect(c.summaryValue({ key: "per", value: null, unit: "num" })).toBe("--");
  });

  it("formate pourcentage, montant (devise) et note sur 20", () => {
    const c = comp();
    expect(c.summaryValue({ value: 4.71, unit: "pct" })).toBe("4,71 %");
    expect(c.summaryValue({ value: -2.5, unit: "pct" })).toBe("-2,5 %");
    expect(c.summaryValue({ value: 13, unit: "money" })).toBe("13 EUR");
    expect(c.summaryValue({ value: 194043428864, unit: "money" })).toBe("194,04 Md EUR");
    expect(c.summaryValue({ value: 13.5, unit: "score" })).toBe("13,5/20");
  });

  it("abrège les volumes et localise le range 52S", () => {
    const c = comp();
    expect(c.summaryValue({ key: "volume", value: 175885, unit: "num" })).toBe("175,9 k");
    expect(c.summaryValue({ key: "avg_volume", value: 509771, unit: "num" })).toBe("509,8 k");
    expect(c.summaryValue({ key: "week52", text: "392.25 – 654.70", unit: "text" })).toBe(
      "392,25 – 654,7",
    );
  });

  it("rend le texte brut (pays, secteur, site)", () => {
    const c = comp();
    expect(c.summaryValue({ text: "France", value: null, unit: "text" })).toBe("France");
  });

  it("applique la classe de couleur depuis les seuils reçus", () => {
    const c = comp();
    expect(c.summaryClass({ key: "roe_5y", value: 12 })).toBe("good");
    expect(c.summaryClass({ key: "roe_5y", value: 4 })).toBe("bad");
    expect(c.summaryClass({ key: "unknown", value: 4 })).toBe("neutral");
  });

  it("affiche la zone d'un score de santé", () => {
    const c = comp();
    expect(c.summaryZone({ key: "piotroski", value: 8 })).toBe("Solide");
    expect(c.summaryZone({ key: "altman_z", value: 0.7 })).toBe("Détresse");
    expect(c.summaryZone({ key: "per", value: 12 })).toBe(null);
  });

  it("expose la note explicative d'une ligne (mixin)", () => {
    const c = comp();
    // Le mixin laisse passer la note du payload (affichée par le template).
    expect(
      c.summaryNote({ key: "altman_z", note: "Non applicable aux financières" }),
    ).toBe("Non applicable aux financières");
    // Aucune note -> null (la ligne reste propre).
    expect(c.summaryNote({ key: "piotroski", note: null })).toBe(null);
    expect(c.summaryNote({ key: "per" })).toBe(null);
  });

  it("replie la catégorie de capi sur la valeur serveur, sinon calcule", () => {
    const c = comp();
    expect(c.summaryCapLabel({ key: "cap_category", text: "Mid Cap" })).toBe("Mid Cap");
    expect(c.summaryCapLabel({ key: "cap_category", text: null })).toBe("Mid Cap");
  });

  it("expose les cartes de la fiche courante", () => {
    const cards = [{ id: "profil", title: "Profil", rows: [] }];
    const c = comp({ data: { identity: {}, summary: cards } });
    expect(c.summaryCards()).toEqual(cards);
    expect(comp({ data: null }).summaryCards()).toEqual([]);
  });
});

describe("carte matrice Croissance (CA + EPS fusionnés)", () => {
  it("expose les colonnes et formate chaque cellule selon l'unité", () => {
    const c = comp();
    const card = { id: "croissance", columns: ["1A", "5A", "10A", "Futur"], rows: [] };
    expect(c.summaryColumns(card)).toEqual(["1A", "5A", "10A", "Futur"]);
    const row = { key: "ca", unit: "pct" };
    expect(c.summaryCell(row, 4.4)).toBe("4,4 %");
    expect(c.summaryCell(row, -0.66)).toBe("-0,66 %");
    expect(c.summaryCell(row, null)).toBe("--");
  });

  it("applique la polarité par cellule (précalculée serveur)", () => {
    const c = comp();
    const row = { key: "ca", unit: "pct", cell_good: [true, null, false, true] };
    expect(c.summaryCellClass(row, 0)).toBe("good");
    expect(c.summaryCellClass(row, 1)).toBe("neutral");
    expect(c.summaryCellClass(row, 2)).toBe("bad");
  });
});
