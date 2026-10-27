import { describe, expect, it, vi } from "vitest";

import { RAIL_FOOT_SPACES, SPACES, isSpaceId, navMixin } from "../src/obole/web/nav.js";

// Coquille de navigation : le rail porte les ESPACES (sortir de la fiche), les
// onglets portent les SECTIONS (changer de section dans la fiche). Deux rangs,
// deux sens — c'est l'invariant que ces tests verrouillent.

function comp(overrides = {}) {
  return {
    indicesOpen: false,
    screenerOpen: false,
    portfolioOpen: false,
    watchlistOpen: false,
    settingsOpen: false,
    data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
    error: "",
    loading: false,
    backTo: null,
    suggestions: [{ symbol: "RI.PA" }],
    openIndices: vi.fn(),
    closeIndices: vi.fn(function () { this.indicesOpen = false; }),
    openScreener: vi.fn(),
    closeScreener: vi.fn(function () { this.screenerOpen = false; }),
    openPortfolio: vi.fn(),
    closePortfolio: vi.fn(function () { this.portfolioOpen = false; }),
    openWatchlist: vi.fn(),
    closeWatchlist: vi.fn(function () { this.watchlistOpen = false; }),
    openSettings: vi.fn(),
    closeSettings: vi.fn(function () { this.settingsOpen = false; }),
    ...navMixin,
    ...overrides,
  };
}

describe("registre des espaces", () => {
  it("expose les 5 espaces de consultation dans l'ordre validé", () => {
    expect(SPACES.map((s) => s.id)).toEqual([
      "analyse",
      "indices",
      "screener",
      "portfolio",
      "watchlist",
    ]);
  });

  it("Paramètres vit à part, en pied de rail", () => {
    expect(RAIL_FOOT_SPACES.map((s) => s.id)).toEqual(["settings"]);
    expect(SPACES.map((s) => s.id)).not.toContain("settings");
  });

  it("chaque entrée porte un libellé, une icône SVG et une infobulle", () => {
    for (const s of [...SPACES, ...RAIL_FOOT_SPACES]) {
      expect(s.label, `${s.id} : libellé manquant`).toBeTruthy();
      expect(s.hint, `${s.id} : infobulle manquante`).toBeTruthy();
      expect(s.svg, `${s.id} : icône manquante`).toMatch(/^<svg /);
      expect(s.svg).toContain("</svg>");
    }
  });

  it("isSpaceId reconnaît les espaces connus seulement", () => {
    expect(isSpaceId("portfolio")).toBe(true);
    expect(isSpaceId("settings")).toBe(true);
    expect(isSpaceId("resume")).toBe(false);
    expect(isSpaceId("")).toBe(false);
  });
});

describe("entrée active du rail", () => {
  it("sans modale ouverte, l'état de repos est « Analyse »", () => {
    const c = comp();
    expect(c.openSpace()).toBeNull();
    expect(c.activeSpace()).toBe("analyse");
  });

  it("la modale ouverte désigne l'espace actif, une seule à la fois", () => {
    const c = comp({ portfolioOpen: true });
    expect(c.activeSpace()).toBe("portfolio");
  });

  it("fermer la modale rend la main à « Analyse »", () => {
    const c = comp({ screenerOpen: true });
    expect(c.activeSpace()).toBe("screener");
    c.closeScreener();
    expect(c.activeSpace()).toBe("analyse");
  });

  it("ouvertures et fermetures mutuelles sont vues comme des espaces distincts", () => {
    const c = comp();
    c.settingsOpen = true;
    expect(c.activeSpace()).toBe("settings");
    c.settingsOpen = false;
    c.watchlistOpen = true;
    expect(c.activeSpace()).toBe("watchlist");
  });
});

describe("openSpaceEntry — le déclencheur a déménagé, pas la modale", () => {
  it("un espace appelle son ouverture existante", () => {
    const c = comp();
    c.openSpaceEntry("indices");
    expect(c.openIndices).toHaveBeenCalledOnce();
    c.openSpaceEntry("watchlist");
    expect(c.openWatchlist).toHaveBeenCalledOnce();
  });

  it("« Analyse » referme la modale ouverte sans rien charger", () => {
    const c = comp({ portfolioOpen: true });
    c.openSpaceEntry("analyse");
    expect(c.closePortfolio).toHaveBeenCalledOnce();
    expect(c.openPortfolio).not.toHaveBeenCalled();
  });

  it("« Analyse » sans modale ouverte ne fait rien", () => {
    const c = comp();
    c.openSpaceEntry("analyse");
    for (const fn of [c.closeIndices, c.closeScreener, c.closePortfolio, c.closeWatchlist, c.closeSettings]) {
      expect(fn).not.toHaveBeenCalled();
    }
  });
});

describe("goHome — la marque ramène à l'accueil", () => {
  it("referme tout espace ouvert et vide la fiche", () => {
    window.location.hash = "#RI.PA/quantitatif";
    const c = comp({ settingsOpen: true });
    c.goHome();
    expect(c.closeSettings).toHaveBeenCalledOnce();
    expect(c.data).toBeNull();
    expect(c.backTo).toBeNull();
    expect(c.suggestions).toEqual([]);
    expect(window.location.hash).toBe("");
    expect(window.location.pathname + window.location.search).toBe("/");
  });

  it("n'appelle que les fermetures des modales réellement ouvertes", () => {
    const c = comp({ watchlistOpen: true });
    c.goHome();
    expect(c.closeWatchlist).toHaveBeenCalledOnce();
    expect(c.closePortfolio).not.toHaveBeenCalled();
    expect(c.closeScreener).not.toHaveBeenCalled();
  });
});
