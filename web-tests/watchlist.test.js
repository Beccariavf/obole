// Watchlist (#25) — helpers purs, état de la modale et fenêtre de confiance.
//
// Aucun réseau : on teste les fonctions pures (tri, libellés, couverture) et
// les méthodes de calcul de la fenêtre de référence du mixin. Les appels HTTP
// (étoile, modale, référence) sont couverts par l'e2e, routes interceptées.
import { describe, expect, it } from "vitest";
import {
  loadApp,
  metaFromConfig,
  readConfigSource,
  readWatchlistSource,
} from "./helpers/load-app.js";

const meta = metaFromConfig(readConfigSource());
const app = loadApp();
app.applyMeta(meta);

function component(overrides = {}) {
  return {
    ...app.watchlistMixin,
    fmt: (v) => (v == null ? "—" : String(v)),
    ...overrides,
  };
}

describe("source unique des seuils watchlist (/api/meta)", () => {
  it("les tiers, le minimum de points et le plafond viennent de config.py", () => {
    expect(app.WATCH_TIERS).toEqual(meta.watch.tiers);
    expect(app.WATCH_TIERS).toHaveLength(3);
    expect(app.WATCH_MIN_REF_POINTS).toBe(meta.watch.min_ref_points);
    expect(app.WATCH_MAX_ITEMS).toBe(meta.watch.max_items);
  });

  it("watchlist.js ne code aucun de ces nombres en dur", () => {
    const src = readWatchlistSource();
    expect(src).toContain("WATCH_MIN_REF_POINTS");
    expect(src).not.toMatch(/const\s+\w*(MIN|MAX)\w*\s*=\s*\d+/);
    // La fenêtre par défaut est décidée serveur (`ref_is_default`), pas ici.
    expect(src).not.toMatch(/REG_YEARS/);
  });
});

describe("libellés et badges", () => {
  it("tierLabel lit la liste reçue de /api/meta", () => {
    expect(app.tierLabel(1)).toBe("Tier 1");
    expect(app.tierLabel(3)).toBe("Tier 3");
    expect(app.tierLabel(9)).toBe("—");
    expect(app.tierLabel(null)).toBe("—");
  });

  it("la source du prix juste est lisible sans seuil", () => {
    expect(app.fairPriceSourceLabel({ fair_price: 100, fair_price_source: "saved" })).toBe("calc");
    expect(app.fairPriceSourceLabel({ fair_price: 100, fair_price_source: "regression" })).toBe(
      "droite",
    );
    expect(app.fairPriceSourceLabel({ fair_price: null, fair_price_source: null })).toBe("—");
  });

  it("watchCoverage compte les prix justes réellement définis", () => {
    expect(
      app.watchCoverage([
        { fair_price_source: "saved" },
        { fair_price_source: "regression" },
        { fair_price_source: null },
      ]),
    ).toEqual({ defined: 1, total: 3 });
    expect(app.watchCoverage([])).toEqual({ defined: 0, total: 0 });
  });
});

describe("tri du classement", () => {
  const rows = [
    { ticker: "A", tier: 2, safety_margin_pct: 10 },
    { ticker: "B", tier: 1, safety_margin_pct: null },
    { ticker: "C", tier: 1, safety_margin_pct: 20 },
  ];

  it("marge décroissante, valeurs absentes en dernier", () => {
    expect(app.sortWatchRows(rows, "safety_margin_pct", "desc").map((r) => r.ticker)).toEqual([
      "C",
      "A",
      "B",
    ]);
  });

  it("les absentes restent en dernier même en ascendant", () => {
    expect(app.sortWatchRows(rows, "safety_margin_pct", "asc").map((r) => r.ticker)).toEqual([
      "A",
      "C",
      "B",
    ]);
  });

  it("à égalité, tier puis ticker départagent", () => {
    const equal = [
      { ticker: "Z", tier: 2, z: -1 },
      { ticker: "Y", tier: 1, z: -1 },
      { ticker: "X", tier: 1, z: -1 },
    ];
    expect(app.sortWatchRows(equal, "z", "desc").map((r) => r.ticker)).toEqual(["X", "Y", "Z"]);
  });
});

describe("état de la modale", () => {
  it("compteurs par tier calculés sur l'appartenance", () => {
    const c = component({ watchItems: [{ tier: 1 }, { tier: 1 }, { tier: 3 }] });
    expect(c.watchCounts()).toEqual({ all: 3, 1: 2, 2: 0, 3: 1 });
  });

  it("filtre par tier et masquage des replis", () => {
    const c = component({
      watchRows: [
        { ticker: "A", tier: 1, fair_price_source: "saved" },
        { ticker: "B", tier: 1, fair_price_source: "regression" },
        { ticker: "C", tier: 2, fair_price_source: "saved" },
      ],
    });
    expect(c.watchVisibleRows().map((r) => r.ticker)).toEqual(["A", "B", "C"]);
    c.watchTierFilter = 1;
    expect(c.watchVisibleRows().map((r) => r.ticker)).toEqual(["A", "B"]);
    c.watchHideFallback = true;
    expect(c.watchVisibleRows().map((r) => r.ticker)).toEqual(["A"]);
    c.watchTierFilter = 3;
    expect(c.watchVisibleRows()).toEqual([]);
  });

  it("le tri au clic cycle desc → asc → ordre serveur", () => {
    const c = component();
    c.toggleWatchSort("safety_margin_pct");
    expect(c.watchSort).toEqual({ key: "safety_margin_pct", dir: "desc" });
    c.toggleWatchSort("safety_margin_pct");
    expect(c.watchSort).toEqual({ key: "safety_margin_pct", dir: "asc" });
    c.toggleWatchSort("safety_margin_pct");
    expect(c.watchSort).toBeNull();
    c.toggleWatchSort("z");
    expect(c.watchSort).toEqual({ key: "z", dir: "desc" });
  });

  it("l'ordre serveur est conservé tant qu'aucun tri n'est demandé", () => {
    const c = component({
      watchRows: [{ ticker: "B", tier: 1, safety_margin_pct: 1 }, { ticker: "A", tier: 1, safety_margin_pct: 9 }],
    });
    expect(c.watchRowsSorted().map((r) => r.ticker)).toEqual(["B", "A"]);
  });

  it("le libellé du calcul reste lisible", () => {
    const c = component({ watchGeneratedAt: 1700000000 });
    expect(c.watchGeneratedLabel()).toContain("Calculé à");
  });
});

describe("fenêtre de confiance", () => {
  it("le libellé dit la référence ou le défaut", () => {
    const none = component({ data: { watch: { ref: null } } });
    expect(none.watchRefLabel()).toBe("Réf. droite");
    const set = component({ data: { watch: { ref: { start: "2012-01-04" } } } });
    expect(set.watchRefLabel()).toBe("Réf. 2012");
  });

  it("le tier de la fiche se lit dans le payload", () => {
    expect(component({ data: { watch: { tier: 2 } } }).watchTier()).toBe(2);
    expect(component({ data: { watch: { tier: null } } }).watchTier()).toBeNull();
    expect(component({ data: {} }).watchTier()).toBeNull();
  });

  it("« Définir » exige le dernier cours et le minimum de points", () => {
    const base = {
      data: { kind_payload: "stock" },
      isRatio: () => false,
      isBasket: () => false,
      watchMinRefPoints: () => 30,
      maxIdx: () => 100,
    };
    expect(component({ ...base, visibleRange: () => [70, 100] }).canDefineWatchRef()).toBe(true);
    // Poignée droite pas sur le dernier cours : on refuse (la référence irait
    // jusqu'à aujourd'hui, pas jusqu'à la fin visible).
    expect(component({ ...base, visibleRange: () => [70, 90] }).canDefineWatchRef()).toBe(false);
    // Fenêtre trop courte (< 30 points).
    expect(component({ ...base, visibleRange: () => [95, 100] }).canDefineWatchRef()).toBe(false);
    // Ratio / indice : pas de référence.
    expect(
      component({ ...base, isRatio: () => true, visibleRange: () => [70, 100] }).canDefineWatchRef(),
    ).toBe(false);
    // Métadonnées pas encore chargées.
    expect(
      component({ ...base, watchMinRefPoints: () => 0, visibleRange: () => [70, 100] }).canDefineWatchRef(),
    ).toBe(false);
  });

  it("la date de début est celle de la poignée gauche", () => {
    const c = component({
      data: { chart: { dates: ["2000-01-03", "2001-01-02", "2002-01-02"] } },
      visibleRange: () => [1, 2],
    });
    expect(c.watchRefStartDate()).toBe("2001-01-02");
  });

  it("watchPct formate ou rend un tiret", () => {
    const c = component();
    expect(c.watchPct(12.5)).toBe("12.5 %");
    expect(c.watchPct(null)).toBe("—");
  });
});
