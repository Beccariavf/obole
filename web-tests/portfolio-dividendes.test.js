// Obole — onglet Dividende du PORTEFEUILLE (#17.5).
//
// Vérifie que le mixin ne DÉCIDE rien : la taxonomie des tuiles vient de
// /api/meta (config.PORTFOLIO_DIVIDEND_GROUPS), la polarité de
// PORTFOLIO_DIVIDEND_POLARITY, les unités de PORTFOLIO_DIVIDEND_UNITS. On
// verrouille aussi les règles d'affichage : « — » jamais 0, mois vide = None,
// proposition hachurée et hors agrégats, tri par défaut sur le poids de revenu.
import { beforeEach, describe, expect, it } from "vitest";

import { portfolioDividendsMixin } from "../src/obole/web/portfolio-dividends.js";
import { applyMeta } from "../src/obole/web/thresholds.js";

const META = {
  portfolio_dividend_groups: [
    {
      id: "rendement",
      metrics: [
        { key: "yield_pct", label: "Yield portefeuille" },
        { key: "yield_on_cost_pct", label: "Yield on cost" },
        {
          key: "payout_pct",
          label: "Payout agrégé",
          sub: "dividendes / bénéfices",
          coverage_of: "payout_coverage_pct",
        },
        {
          key: "shareholder_yield_pct",
          label: "Shareholder yield",
          coverage_of: "shareholder_coverage_pct",
        },
      ],
    },
    {
      id: "revenu",
      metrics: [
        { key: "ttm_income", label: "Revenu TTM", sub_of: "total_income" },
        { key: "cagr_pct", label: "Croissance 5 ans", signed: true },
        { key: "dividend_contribution_pct", label: "Part dans la perf", signed: true },
        { key: "yield_coverage_pct", label: "Couverture données" },
      ],
    },
  ],
  portfolio_dividend_polarity: {
    payout_pct: ["le", 80.0],
    cagr_pct: ["ge", 0.0],
    dividend_contribution_pct: ["ge", 0.0],
  },
  portfolio_dividend_units: {
    yield_pct: "pct",
    payment_pct: "pct",
    payout_pct: "pct",
    payout_coverage_pct: "pct",
    shareholder_yield_pct: "pct",
    shareholder_coverage_pct: "pct",
    cagr_pct: "pct",
    yield_coverage_pct: "pct",
    dividend_contribution_pct: "pt",
    twr_with_dividends_pct: "pct",
    twr_without_dividends_pct: "pct",
    ttm_income: "money",
    total_income: "money",
  },
  chart_heights: { mini: 200, portfolio_dividends: 300, portfolio_div_conc: 300 },
  portfolio_dividend_gap_scale_pp: 20,
};

const PAYLOAD = {
  income: {
    years: [2024, 2025],
    rows: [
      {
        year: 2024,
        months: { "6": 35.0, "9": null },
        by_ticker: {
          "RI.PA": { months: { "6": 35.0, "9": null }, proposed: { "6": null, "9": null } },
        },
        total_confirmed: 35.0,
        total_proposed: 0.0,
        count: 1,
      },
      {
        year: 2025,
        months: { "6": 40.0 },
        by_ticker: {
          "RI.PA": {
            months: { "6": 40.0 },
            proposed: { "6": null, "9": 99.0 },
          },
        },
        total_confirmed: 40.0,
        total_proposed: 99.0,
        count: 2,
      },
    ],
    by_company: [
      { ticker: "RI.PA", amount: 75.0, share_pct: 75.0 },
      { ticker: "AI.PA", amount: 25.0, share_pct: 25.0 },
    ],
    total_confirmed: 75.0,
    total_proposed: 99.0,
    last_year: 2025,
  },
  stats: {
    yield_pct: { value: 3.2, good: null },
    yield_coverage_pct: { value: 88.0, good: null },
    yield_on_cost_pct: { value: 4.1, good: null },
    payout_pct: { value: 95.0, good: false },
    payout_coverage_pct: { value: 71.0, good: null },
    shareholder_yield_pct: { value: 5.0, good: null },
    shareholder_coverage_pct: { value: 64.0, good: null },
    ttm_income: { value: 1200.0, good: null },
    total_income: { value: 75.0, good: null },
    cagr_pct: { value: -1.5, good: false },
    twr_with_dividends_pct: { value: 12.4, good: null },
    twr_without_dividends_pct: { value: 8.7, good: null },
    dividend_contribution_pct: { value: 3.7, good: true },
  },
  concentration: {
    n_eff: 1.6,
    top_n_pct: 75.0,
    top_n: 5,
    first_pct: 75.0,
    first_ticker: "RI.PA",
    payers: 2,
  },
  lines: [
    {
      ticker: "AI.PA",
      dps_ttm: 2.0,
      div_yield_pct: 1.3,
      div_to_cost_pct: 1.4,
      income_share_pct: 25.0,
      capital_share_pct: 50.0,
      gap_pp: -25.0,
      cagr_pct: 2.0,
      payout_pct: 40.0,
      flags: [],
    },
    {
      ticker: "RI.PA",
      dps_ttm: 3.5,
      div_yield_pct: 3.5,
      div_to_cost_pct: 3.5,
      income_share_pct: 75.0,
      capital_share_pct: 50.0,
      gap_pp: 25.0,
      cagr_pct: 3.5,
      payout_pct: 45.0,
      flags: [],
    },
  ],
  warnings: ["Payout indisponible sur 1 ligne(s) (ETF, pertes)"],
  months: 12,
};

function comp(payload = PAYLOAD) {
  return {
    ...portfolioDividendsMixin,
    pfDiv: payload,
    pfDivYear: "ttm",
    pfDivSortKey: "income_share_pct",
    pfDivSortDir: -1,
    fmt: (v) => String(v),
    pfMoney: (v) => String(v),
    $nextTick: (fn) => fn && fn(),
  };
}

beforeEach(() => {
  applyMeta(META);
});

describe("tuiles KPI pilotées par la taxonomie serveur", () => {
  it("rend les tuiles dans l'ordre de la taxonomie, sans libellé en dur", () => {
    const c = comp();
    const kpis = c.pfDivKpis();
    expect(kpis.map((k) => k.key)).toEqual([
      "yield_pct",
      "yield_on_cost_pct",
      "payout_pct",
      "shareholder_yield_pct",
      "ttm_income",
      "cagr_pct",
      "dividend_contribution_pct",
      "yield_coverage_pct",
    ]);
    expect(kpis[0].label).toBe("Yield portefeuille");
  });

  it("affiche le taux de couverture du PAYOUT en sous-texte, jamais en tuile", () => {
    const c = comp();
    const kpi = c.pfDivKpis().find((k) => k.key === "payout_pct");
    expect(kpi.sub).toContain("dividendes / bénéfices");
    expect(kpi.sub).toContain("couverture 71 %");
  });

  it("affiche la couverture du shareholder yield", () => {
    const c = comp();
    const kpi = c.pfDivKpis().find((k) => k.key === "shareholder_yield_pct");
    expect(kpi.sub).toContain("couverture 64 %");
  });

  it("affiche le cumul en sous-texte de la tuile Revenu TTM", () => {
    const c = comp();
    const kpi = c.pfDivKpis().find((k) => k.key === "ttm_income");
    expect(kpi.sub).toContain("cumul 75");
  });

  it("tire la polarité de meta (payout 95 % au-dessus du seuil 80 -> rouge)", () => {
    const c = comp();
    const kpi = c.pfDivKpis().find((k) => k.key === "payout_pct");
    expect(kpi.good).toBe(false);
  });

  it("n'ajoute le « + » qu'aux VARIATIONS (jamais à un niveau)", () => {
    const c = comp();
    const kpis = c.pfDivKpis();
    // Yield : un NIVEAU, jamais signé.
    expect(kpis.find((k) => k.key === "yield_pct").value).toBe("3.2 %");
    // CAGR : une VARIATION négative, signée (le « − » vient du nombre).
    expect(kpis.find((k) => k.key === "cagr_pct").value).toBe("-1.5 %");
    // Contribution positive : signée.
    expect(kpis.find((k) => k.key === "dividend_contribution_pct").value).toBe("+3.7 pt");
  });

  it("rend la contribution auditable (les deux taux en sous-texte)", () => {
    const c = comp();
    const kpi = c.pfDivKpis().find((k) => k.key === "dividend_contribution_pct");
    expect(kpi.sub).toContain("12.4 % avec");
    expect(kpi.sub).toContain("8.7 % sans");
  });

  it("affiche « — » pour une valeur absente, jamais 0", () => {
    const c = comp({ ...PAYLOAD, stats: { ...PAYLOAD.stats, yield_pct: { value: null, good: null } } });
    const kpi = c.pfDivKpis().find((k) => k.key === "yield_pct");
    expect(kpi.value).toBe("—");
  });
});

describe("période affichée (TTM par défaut + sélecteur d'année)", () => {
  it("démarre en TTM : aucune année n'est sélectionnée", () => {
    const c = comp();
    expect(c.pfDivIsTtm()).toBe(true);
    expect(c.pfDivActiveYear()).toBeNull();
  });

  it("sélectionner une année quitte le mode TTM", () => {
    const c = comp();
    c.setPfDivPeriod("2024");
    expect(c.pfDivIsTtm()).toBe(false);
    expect(c.pfDivActiveYear()).toBe(2024);
    c.setPfDivPeriod("ttm");
    expect(c.pfDivIsTtm()).toBe(true);
  });

  it("étiquette l'année en cours « (en cours) »", () => {
    const c = comp();
    const now = new Date().getFullYear();
    expect(c.pfDivYearLabel(now)).toBe(`${now} (en cours)`);
    expect(c.pfDivYearLabel(1999)).toBe("1999");
  });

  it("propose les années en ordre décroissant pour le sélecteur", () => {
    const c = comp();
    expect(c.pfDivYears()).toEqual([2025, 2024]);
  });

  it("ignore une valeur identique (pas de redessin inutile)", () => {
    const c = comp();
    let draws = 0;
    c.$nextTick = (fn) => { draws += 1; fn && fn(); };
    c.setPfDivPeriod("ttm"); // déjà TTM
    expect(draws).toBe(0);
    c.setPfDivPeriod("2024");
    expect(draws).toBe(1);
  });
});

describe("fenêtre TTM", () => {
  it("borne la fenêtre aux 12 derniers mois calendaires", () => {
    const c = comp();
    const window = c.pfDivWindowMonths();
    // Dernier point = juin 2025 → fenêtre depuis juillet 2024 : juin 2024 sort,
    // septembre 2024 (même à null) reste un point de l'axe, comme le veut le
    // contrat « un mois sans versement n'est pas un zéro » : il est tracé vide.
    expect(window.map((k) => `${k.year}-${k.month}`)).toEqual([
      "2024-9", "2025-6",
    ]);
  });

  it("un trou mensuel ne rallonge pas la fenêtre (compteur année×12+mois)", () => {
    const payload = {
      income: {
        years: [2026, 2025],
        rows: [
          { year: 2025, months: { "1": 10.0 }, by_ticker: {}, total_confirmed: 10.0,
            total_proposed: 0, count: 1 },
          { year: 2026, months: { "3": 20.0 }, by_ticker: {}, total_confirmed: 20.0,
            total_proposed: 0, count: 1 },
        ],
        by_company: [], total_confirmed: 30.0, total_proposed: 0, last_year: 2026,
      },
      stats: {},
    };
    const c = comp(payload);
    // Dernier point = mars 2026 → fenêtre depuis avril 2025 : janvier 2025 sort.
    expect(c.pfDivWindowMonths().map((k) => `${k.year}-${k.month}`)).toEqual(["2026-3"]);
  });
});

describe("barres mensuelles", () => {
  it("un mois sans versement reste null (jamais 0)", () => {
    const c = comp();
    c.pfDivYear = "2024";
    const data = c.pfDivMonthlySeries();
    expect(data.labels).toEqual(["Juin", "Sept"]);
    const ri = data.series.find((s) => s.ticker === "RI.PA");
    expect(ri.values[0]).toBe(35.0);
    expect(ri.values[1]).toBeNull();
  });

  it("les propositions sont portées à part (hachurées, hors totaux confirmés)", () => {
    const c = comp();
    c.pfDivYear = "2025";
    const totals = c.pfDivYearTotals();
    expect(totals.confirmed).toBe(40.0);
    expect(totals.proposed).toBe(99.0);
  });
});

describe("concentration", () => {
  it("expose les chiffres de contexte depuis le payload", () => {
    const c = comp();
    const stats = c.pfDivConcentrationStats();
    expect(stats.map((s) => s.label)).toEqual([
      "Payeurs",
      "Payeurs effectifs",
      "Top 5",
      "1er payeur",
    ]);
    expect(stats[1].value).toBe("1.6");
  });

  it("ne rend rien sans revenu exploitable", () => {
    const c = comp({ ...PAYLOAD, concentration: { n_eff: null, payers: 0 } });
    expect(c.pfDivConcentrationStats()).toEqual([]);
  });
});

describe("tableau par ligne", () => {
  it("trie par poids de revenu décroissant par défaut", () => {
    const c = comp();
    expect(c.pfDivLines().map((r) => r.ticker)).toEqual(["RI.PA", "AI.PA"]);
  });

  it("inverse le tri au second clic sur la même colonne", () => {
    const c = comp();
    c.setPfDivSort("income_share_pct");
    expect(c.pfDivSortDir).toBe(1);
    expect(c.pfDivLines().map((r) => r.ticker)).toEqual(["AI.PA", "RI.PA"]);
  });

  it("formate l'écart en points signés et le reste en %", () => {
    const c = comp();
    expect(c.pfDivCell("gap_pp", 25)).toBe("+25 pt");
    expect(c.pfDivCell("div_yield_pct", 3.5)).toBe("3.5 %");
    expect(c.pfDivCell("div_yield_pct", null)).toBe("—");
  });

  it("borne la micro-barre divergente selon l'échelle venue de config", () => {
    const c = comp();
    // Échelle lue de /api/meta (20 pt) : 25 pt sature à 1, −5 pt vaut un quart.
    expect(c.pfDivGapWidth(25)).toBe(1);
    expect(c.pfDivGapWidth(-5)).toBeCloseTo(0.25);
    expect(c.pfDivGapSide(1)).toBe("pos");
    expect(c.pfDivGapSide(-1)).toBe("neg");
  });

  it("expose les DEUX taux annualisés de la double TWR", () => {
    const c = comp();
    const kpis = c.pfDivKpis();
    const withDiv = PAYLOAD.stats.twr_with_dividends_pct.value;
    const withoutDiv = PAYLOAD.stats.twr_without_dividends_pct.value;
    expect(withDiv - withoutDiv).toBeCloseTo(3.7, 1);
    // La tuile de contribution reste la seule de la taxonomie : les deux taux
    // servent de sous-texte / d'audit, pas de tuiles supplémentaires.
    expect(kpis.some((k) => k.key === "twr_with_dividends_pct")).toBe(false);
  });

  it("trie la colonne TEXTE alphabétiquement, dans les deux sens", () => {
    const c = comp();
    c.setPfDivSort("ticker"); // nouveau tri -> décroissant
    expect(c.pfDivLines().map((r) => r.ticker)).toEqual(["RI.PA", "AI.PA"]);
    c.setPfDivSort("ticker"); // second clic -> croissant
    expect(c.pfDivLines().map((r) => r.ticker)).toEqual(["AI.PA", "RI.PA"]);
  });

  it("expose aria-sort pour l'accessibilité des en-têtes", () => {
    const c = comp();
    expect(c.pfDivAriaSort("income_share_pct")).toBe("descending");
    expect(c.pfDivAriaSort("ticker")).toBe("none");
    c.setPfDivSort("ticker");
    expect(c.pfDivAriaSort("ticker")).toBe("descending");
    expect(c.pfDivAriaSort("income_share_pct")).toBe("none");
  });

  it("places les valeurs absentes en dernier", () => {
    const c = comp({
      ...PAYLOAD,
      lines: [
        { ...PAYLOAD.lines[0], income_share_pct: null },
        PAYLOAD.lines[1],
      ],
    });
    expect(c.pfDivLines()[0].ticker).toBe("RI.PA");
  });
});

describe("badges de fiabilité", () => {
  it("rend les avertissements du serveur tels quels", () => {
    const c = comp();
    expect(c.pfDivWarnings()).toHaveLength(1);
  });
});

describe("états vides", () => {
  it("« aucun versement saisi » ne masque pas des KPI calculables", () => {
    // Portefeuille avec positions mais aucun dividende saisi : les tuiles
    // (rendement courant, TTM, couverture) restent exploitables.
    const c = comp({ ...PAYLOAD, income: { years: [], rows: [], by_company: [] } });
    expect(c.pfDivEmpty()).toBe(true);      // graphe/tableau vides
    expect(c.pfDivAllEmpty()).toBe(false);  // mais la page s'affiche
    expect(c.pfDivKpis().length).toBeGreaterThan(0);
  });

  it("masque toute la page quand rien n'est calculable", () => {
    const c = comp({ income: { years: [], rows: [], by_company: [] }, stats: {} });
    expect(c.pfDivEmpty()).toBe(true);
    expect(c.pfDivAllEmpty()).toBe(true);
    expect(c.pfDivKpis()).toEqual([]);
  });
});
