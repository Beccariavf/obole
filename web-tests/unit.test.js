import { describe, expect, it } from "vitest";
import { loadApp, metaFromConfig, readConfigSource } from "./helpers/load-app.js";

const app = loadApp();
// #06 : les seuils arrivent de /api/meta (source unique config.py). On simule le
// chargement au démarrage avant les tests qui en dépendent.
app.applyMeta(metaFromConfig(readConfigSource()));
const { olsLog, classify, scored, ratioGood, obole, LABELS, RATIO_THRESHOLDS } = app;

describe("olsLog — régression OLS de ln(P) sur le temps", () => {
  it("cas nominal : retrouve une droite exacte", () => {
    const times = [0, 1, 2, 3];
    const prices = times.map((t) => 100 * Math.exp(0.05 * t));
    const { a, b, sigma } = olsLog(times, prices);
    expect(a).toBeCloseTo(Math.log(100), 10);
    expect(b).toBeCloseTo(0.05, 10);
    expect(sigma).toBeCloseTo(0, 10);
  });

  it("série constante : pente et sigma nuls", () => {
    const { b, sigma } = olsLog([0, 1, 2, 3, 4], [50, 50, 50, 50, 50]);
    expect(b).toBeCloseTo(0, 12);
    expect(sigma).toBeCloseTo(0, 12);
  });

  it("pente négative (marché baissier)", () => {
    const { b } = olsLog([0, 1, 2], [100, 90, 81]);
    expect(b).toBeLessThan(0);
  });

  it("entrée vide : ne lève pas (renvoie des valeurs non finies)", () => {
    expect(() => olsLog([], [])).not.toThrow();
    expect(Number.isFinite(olsLog([], []).a)).toBe(false);
  });
});

describe("classify — seuils de labels", () => {
  it("renvoie le premier label dont la borne est dépassée", () => {
    expect(classify(-3, LABELS.distance)).toBe("Décotée");
    expect(classify(-1.5, LABELS.distance)).toBe("Sous-cotée");
    expect(classify(2, LABELS.distance)).toBe("Surcotée");
  });

  it("borne exacte : bascule au label suivant (comparaison stricte)", () => {
    expect(classify(4, LABELS.perf)).toBe("Moyen");
    expect(classify(3.99, LABELS.perf)).toBe("Médiocre");
  });

  it("le dernier label capte l'infini (borne null)", () => {
    expect(classify(1e9, LABELS.perf)).toBe("Bien");
  });
});

describe("scored — indicateur + label + couleur", () => {
  it("valeur absente ou NaN : indicateur neutre", () => {
    expect(scored(null, "distance")).toEqual({ value: null, label: null, good: null });
    expect(scored(NaN, "perf")).toEqual({ value: null, label: null, good: null });
    expect(scored(undefined, "ecart")).toEqual({ value: null, label: null, good: null });
  });

  it("distance (z) : décoté = bleu (good true)", () => {
    expect(scored(-3.81, "distance", 2)).toEqual({
      value: -3.81,
      label: "Décotée",
      good: true,
    });
    expect(scored(1, "distance", 2).good).toBe(false);
  });

  it("écart-type : bleu sous 35 %, rouge au-delà (borne 35 exclue)", () => {
    expect(scored(34.9, "ecart").good).toBe(true);
    expect(scored(35, "ecart").good).toBe(false);
    expect(scored(50, "ecart").label).toBe("Plutôt élevée");
  });

  it("perf et potentiel : bleu à partir de leur seuil", () => {
    expect(scored(4, "perf").good).toBe(true);
    expect(scored(3.9, "perf").good).toBe(false);
    expect(scored(5, "potential").good).toBe(true);
    expect(scored(4.9, "potential").good).toBe(false);
  });

  it("bêta : toujours neutre, négatif = « Inversés »", () => {
    expect(scored(1.5, "beta", 2)).toEqual({
      value: 1.5,
      label: "Offensif",
      good: null,
    });
    expect(scored(-0.5, "beta", 2).label).toBe("Inversés");
  });

  it("corrélation : classe sur |ρ| et suffixe si inverse", () => {
    expect(scored(0.3, "corr", 2).label).toBe("Peu corrélés");
    expect(scored(-0.3, "corr", 2).label).toBe("Peu corrélés (inverse)");
    expect(scored(0.3, "corr", 2).good).toBeNull();
  });

  it("arrondi configurable (0 = entier, défaut = 1 décimale)", () => {
    expect(scored(12.345, "perf", 0).value).toBe(12);
    expect(scored(12.345, "perf").value).toBe(12.3);
  });
});

describe("ratioGood — couleur d'un ratio fondamental", () => {
  it("sens « ge » : bon au-dessus du seuil, rouge juste en dessous", () => {
    expect(ratioGood("ROE", 10)).toBe(true);
    expect(ratioGood("ROE", 9.9)).toBe(false);
  });

  it("sens « le » : bon sous le seuil", () => {
    expect(ratioGood("PER", 12)).toBe(true);
    expect(ratioGood("PER", 12.1)).toBe(false);
  });

  it("métrique inconnue ou valeur absente : neutre (null)", () => {
    expect(ratioGood("Métrique inconnue", 5)).toBeNull();
    expect(ratioGood("ROE", null)).toBeNull();
    expect(ratioGood("ROE", NaN)).toBeNull();
  });

  it("seuils alignés sur config.RATIO_THRESHOLDS", () => {
    expect(RATIO_THRESHOLDS.ROE).toEqual([10, "ge"]);
  });
});

describe("_buildFilters — body.filters depuis les bornes saisies", () => {
  function withRanges(ranges) {
    const comp = obole();
    for (const key of Object.keys(comp.screenerRanges)) {
      comp.screenerRanges[key] = { min: null, max: null };
    }
    for (const [key, [lo, hi]] of Object.entries(ranges)) {
      comp.screenerRanges[key] = { min: lo, max: hi };
    }
    return comp;
  }

  it("capi min seule : convertie en EUR (×1e9)", () => {
    const comp = withRanges({ market_cap: [5, null] });
    expect(comp._buildFilters()).toEqual({ market_cap: [5e9, null] });
    expect(comp.screenerRangesError).toBe("");
  });

  it("capi max seule : borne haute convertie, borne basse absente", () => {
    const comp = withRanges({ market_cap: [null, 3] });
    expect(comp._buildFilters()).toEqual({ market_cap: [null, 3e9] });
  });

  it("capi min ET max : les deux bornes converties", () => {
    const comp = withRanges({ market_cap: [2, 8] });
    expect(comp._buildFilters()).toEqual({ market_cap: [2e9, 8e9] });
  });

  it("critères non-capi : bornes passées telles quelles", () => {
    const comp = withRanges({ roe_pct: [10, null], z: [-100, 0] });
    expect(comp._buildFilters()).toEqual({ roe_pct: [10, null], z: [-100, 0] });
  });

  it("aucune borne posée : objet vide (aucun filtre envoyé)", () => {
    expect(withRanges({})._buildFilters()).toEqual({});
  });

  it("bornes inversées : filtre omis et message de retour visuel", () => {
    const comp = withRanges({ market_cap: [8, 2], roe_pct: [10, null] });
    expect(comp._buildFilters()).toEqual({ roe_pct: [10, null] });
    expect(comp.screenerRangesError).toContain("Capi");
    expect(comp.screenerRangesError).toContain("inversées");
  });

  it("bornes vides (chaîne) : ignorées, jamais de NaN", () => {
    const comp = withRanges({ market_cap: ["", null] });
    expect(comp._buildFilters()).toEqual({});
  });
});

describe("computeLive — indicateurs recalculés sur la fenêtre visible", () => {
  function liveFor({ a, b, sigma, t0, dates, series, obsIdx }) {
    const comp = obole();
    comp.data = { identity: { last_price: 1 } };
    comp.computeLive(a, b, sigma, t0, dates, series, obsIdx);
    return comp.live;
  }

  const dates = ["2020-01-01", "2021-01-01", "2022-01-01"];
  const t0 = new Date(dates[0]);
  const tNow = (new Date(dates[2]) - t0) / (365.25 * 864e5);
  const b = Math.log(1.05); // +5 %/an en continu
  const sigma = Math.log(1.5); // écart-type -> 50 %
  // Droite passant exactement par le dernier cours (100) : z = 0.
  const a = Math.log(100) - b * tNow;

  it("calcule perf, écart-type et potentiels annualisés", () => {
    const live = liveFor({
      a,
      b,
      sigma,
      t0,
      dates,
      series: [null, null, 100],
      obsIdx: 2,
    });
    expect(live.perf_passee.value).toBeCloseTo(5, 6);
    expect(live.perf_passee.label).toBe("Moyen");
    expect(live.ecart_type.value).toBeCloseTo(50, 6);
    expect(live.ecart_type.label).toBe("Plutôt élevée");
    // Annualisé : les deux horizons convergent vers la même pente.
    expect(live.potential_5y.value).toBeCloseTo(5, 6);
    expect(live.potential_10y.value).toBeCloseTo(5, 6);
    expect(live.distance_sigma.value).toBeCloseTo(0, 6);
  });

  it("un cours sous la droite donne un z négatif (décoté)", () => {
    const live = liveFor({
      a,
      b,
      sigma,
      t0,
      dates,
      series: [null, null, 100 * Math.exp(-3 * sigma)], // résidu = -3 σ
      obsIdx: 2,
    });
    expect(live.distance_sigma.value).toBeCloseTo(-3, 6);
    expect(live.distance_sigma.label).toBe("Décotée");
    expect(live.distance_sigma.good).toBe(true);
  });

  it("retombe sur le dernier cours serveur si la série est absente", () => {
    const comp = obole();
    comp.data = { identity: { last_price: 100 } };
    comp.computeLive(a, b, sigma, t0, dates, [null, null, null], 2);
    expect(comp.live.distance_sigma.value).toBeCloseTo(0, 6);
  });
});
