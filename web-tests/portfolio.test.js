import { describe, expect, it, vi, beforeEach } from "vitest";

import {
  PORTFOLIO_DEFAULT_SECTION,
  PORTFOLIO_SECTIONS,
  formatDecimalInput,
  parseDecimal,
  portfolioSectionPlanned,
  portfolioMixin,
} from "../src/obole/web/portfolio.js";
import { portfolioDividendsMixin } from "../src/obole/web/portfolio-dividends.js";
import { api } from "../src/obole/web/api.js";

// Espace Portefeuille (#17.0) : onglets, sélection de compte, validation de
// formulaires, saisie décimale à la française. On vérifie que le mixin délègue
// bien à `api.js` (jamais de fetch direct) et que la logique reste testable
// sans DOM.

function comp(overrides = {}) {
  // Le composant réel assemble les DEUX mixins (cf. app.js) : on reproduit cet
  // assemblage pour que les appels croisés (onglet Dividende -> son chargeur)
  // soient exercés comme en production.
  return { ...portfolioMixin, ...portfolioDividendsMixin, ...overrides };
}

describe("parseDecimal — saisie décimale à la française", () => {
  it("accepte la virgule décimale", () => {
    expect(parseDecimal("60,50")).toBe(60.5);
    expect(parseDecimal("1,5")).toBe(1.5);
    expect(parseDecimal("0,99")).toBe(0.99);
  });

  it("accepte les séparateurs de milliers (espace, insécable)", () => {
    expect(parseDecimal("1 234,56")).toBe(1234.56);
    expect(parseDecimal("1\u00a0234,56")).toBe(1234.56);
  });

  it("accepte le point décimal (saisie clavier anglaise)", () => {
    expect(parseDecimal("60.50")).toBe(60.5);
  });

  it("gère les nombres négatifs (rejetés ensuite par la validation métier)", () => {
    expect(parseDecimal("-5")).toBe(-5);
  });

  it("renvoie null sur saisie vide ou invalide", () => {
    for (const bad of ["", "   ", "abc", ",,", "1,2,3", "12,34,56"]) {
      expect(parseDecimal(bad), `« ${bad} » doit être invalide`).toBeNull();
    }
    expect(parseDecimal(null)).toBeNull();
  });

  it("formatDecimalInput produit une chaîne à virgule pour l'édition", () => {
    expect(formatDecimalInput(60.5)).toBe("60,5");
    expect(formatDecimalInput(0)).toBe("0");
    expect(formatDecimalInput(null)).toBe("");
  });
});

describe("registre des sections du portefeuille", () => {
  it("expose les 5 sections dans l'ordre validé", () => {
    expect(PORTFOLIO_SECTIONS.map((s) => s.id)).toEqual([
      "resume",
      "risque",
      "performance",
      "dividende",
      "positions",
    ]);
  });

  it("chaque section porte un libellé et une icône SVG", () => {
    for (const s of PORTFOLIO_SECTIONS) {
      expect(s.label).toBeTruthy();
      expect(s.svg).toMatch(/^<svg /);
      expect(s.svg).toContain("</svg>");
    }
  });

  it("la section par défaut est « Résumé » (page d'accueil du portefeuille)", () => {
    expect(PORTFOLIO_DEFAULT_SECTION).toBe("resume");
    expect(comp().portfolioSection).toBe("resume");
  });

  it("toutes les sections sont consultables (le jalon 05 est livré)", () => {
    const c = comp();
    expect(c.portfolioSectionUsable("resume")).toBe(true);
    expect(c.portfolioSectionUsable("positions")).toBe(true);
    expect(c.portfolioSectionUsable("risque")).toBe(true);
    expect(c.portfolioSectionUsable("performance")).toBe(true);
    expect(c.portfolioSectionUsable("dividende")).toBe(true);
    expect(portfolioSectionPlanned("dividende")).toBe(false);
    expect(portfolioSectionPlanned("resume")).toBe(false);
    expect(portfolioSectionPlanned("positions")).toBe(false);
    expect(portfolioSectionPlanned("risque")).toBe(false);
    expect(portfolioSectionPlanned("performance")).toBe(false);
  });

  it("le libellé d'infobulle distingue « à venir »", () => {
    const c = comp();
    expect(c.portfolioSectionTitle("dividende")).toBe("Dividende");
    expect(c.portfolioSectionTitle("performance")).toBe("Performance");
    expect(c.portfolioSectionTitle("risque")).toBe("Risque");
    expect(c.portfolioSectionTitle("positions")).toBe("Positions");
    expect(c.portfolioSectionTitle("resume")).toBe("Résumé");
  });

  it("setPortfolioSection ouvre l'onglet Dividende", () => {
    // `$nextTick` et les chargeurs sont fournis par Alpine : on les stubbe pour
    // n'exercer que la bascule d'onglet.
    const calls = [];
    const c = comp({
      $nextTick: (fn) => fn(),
      loadPortfolioDividends: () => calls.push("dividende"),
    });
    c.setPortfolioSection("dividende");
    expect(c.portfolioSection).toBe("dividende");
    expect(calls).toEqual(["dividende"]);
    c.setPortfolioSection("resume");
    expect(c.portfolioSection).toBe("resume");
  });
});

describe("validation des formulaires (miroir serveur)", () => {
  it("transaction : compte, ticker, date, quantité > 0, prix ≥ 0 requis", () => {
    const base = {
      account_id: 1,
      ticker: "RI.PA",
      trade_date: "2024-01-02",
      quantity: "10",
      price: "100",
      fees: "",
    };
    const c = comp({ txForm: { ...base } });
    expect(c._txFormValid()).toBe(true);
    for (const bad of [
      { account_id: "" },
      { ticker: "  " },
      { trade_date: "02/01/2024" },
      { quantity: "0" },
      { quantity: "-1" },
      { quantity: "abc" },
      { price: "" },
      { price: "-1" },
      { fees: "abc" },
    ]) {
      c.txForm = { ...base, ...bad };
      expect(c._txFormValid(), JSON.stringify(bad)).toBe(false);
    }
  });

  it("transaction : accepte les décimales à la virgule", () => {
    const c = comp({
      txForm: {
        account_id: 1,
        ticker: "RI.PA",
        trade_date: "2024-01-02",
        quantity: "1,5",
        price: "60,50",
        fees: "0,99",
      },
    });
    expect(c._txFormValid()).toBe(true);
  });

  it("dividende : compte, ticker, date, montant ≥ 0 requis", () => {
    const base = { account_id: 1, ticker: "RI.PA", pay_date: "2024-06-15", amount: "42" };
    const c = comp({ divForm: { ...base } });
    expect(c._divFormValid()).toBe(true);
    for (const bad of [
      { account_id: "" },
      { ticker: "" },
      { pay_date: "15/06/2024" },
      { amount: "-1" },
      { amount: "" },
      { amount: "abc" },
    ]) {
      c.divForm = { ...base, ...bad };
      expect(c._divFormValid(), JSON.stringify(bad)).toBe(false);
    }
  });
});

describe("bascule Transaction / Dividende", () => {
  it("le mode par défaut est « tx »", () => {
    expect(comp().portfolioFormMode).toBe("tx");
  });

  it("setPortfolioFormMode bascule et annule l'édition du formulaire quitté", () => {
    const c = comp({ portfolioFormMode: "tx" });
    c.txForm = { id: 7, account_id: 1, ticker: "RI.PA" };
    c.setPortfolioFormMode("div");
    expect(c.portfolioFormMode).toBe("div");
    expect(c.txForm.id).toBeNull();  // édition abandonnée
    c.setPortfolioFormMode("inconnu");
    expect(c.portfolioFormMode).toBe("div");  // mode invalide ignoré
  });
});

describe("délégation à api.js", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("reloadPortfolioData interroge les endpoints avec le compte courant", async () => {
    const c = comp({
      portfolioAccountId: 3,
      apiTx: vi.spyOn(api, "portfolioTransactions").mockResolvedValue([]),
      apiDiv: vi.spyOn(api, "portfolioDividends").mockResolvedValue([]),
      apiPos: vi.spyOn(api, "portfolioPositions").mockResolvedValue([]),
      apiTags: vi.spyOn(api, "portfolioTags").mockResolvedValue({ tags: [] }),
    });
    await c.reloadPortfolioData();
    expect(c.apiTx).toHaveBeenCalledWith(3, null);
    expect(c.apiDiv).toHaveBeenCalledWith(3);
    expect(c.apiPos).toHaveBeenCalledWith(3, null);
  });

  it("setPortfolioAccount change le compte et recharge", async () => {
    const c = comp({ portfolioAccountId: null, reloadPortfolioData: vi.fn().mockResolvedValue() });
    await c.setPortfolioAccount(5);
    expect(c.portfolioAccountId).toBe(5);
    expect(c.reloadPortfolioData).toHaveBeenCalledTimes(1);
  });

  it("saveTransaction n'appelle l'API que si le formulaire est valide", async () => {
    const spy = vi.spyOn(api, "createPortfolioTransaction").mockResolvedValue({ ok: true, data: {} });
    const c = comp({ txForm: { id: null, account_id: "", ticker: "", trade_date: "", quantity: null, price: null } });
    await c.saveTransaction();
    expect(spy).not.toHaveBeenCalled();
    expect(c.portfolioError).toMatch(/requis/);
  });
});

describe("formatage", () => {
  it("portfolioMoney renvoie « — » sur valeur absente", () => {
    const c = comp();
    expect(c.portfolioMoney(null)).toBe("—");
    expect(c.portfolioMoney(1234.5)).toContain("1");
  });
});
