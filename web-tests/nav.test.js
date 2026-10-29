import { describe, expect, it, vi } from "vitest";

import {
  RAIL_FOOT_SPACES,
  SPACE_OPENERS,
  SPACES,
  navMixin,
} from "../src/obole/web/nav.js";
import { indicesMixin } from "../src/obole/web/indices.js";
import { screenerMixin } from "../src/obole/web/screener.js";
import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { watchlistMixin } from "../src/obole/web/watchlist.js";
import { settingsMixin } from "../src/obole/web/settings.js";
import { searchMixin } from "../src/obole/web/search.js";
import { sectionsMixin } from "../src/obole/web/sections.js";
import { obole } from "../src/obole/web/app.js";

// Coquille de navigation : le rail porte les ESPACES (sortir de la fiche), les
// onglets portent les SECTIONS (changer de section dans la fiche). Deux rangs,
// deux sens — c'est l'invariant que ces tests verrouillent.

// Vrais mixins, indexés par le nom d'espace qu'ils servent. C'est la table que
// `SPACE_OPENERS` désigne par des CHAÎNES : la tester contre les objets réels est
// le seul moyen qu'un renommage casse un test au lieu de casser le rail en silence.
const REAL_MIXINS = {
  indices: indicesMixin,
  screener: screenerMixin,
  portfolio: portfolioMixin,
  watchlist: watchlistMixin,
  settings: settingsMixin,
};

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
    // jsdom n'implémente pas `window.scrollTo` : on l'isole. Le geste réel
    // (ouvrir une vue repart du haut) est mesuré en e2e.
    scrollToTop: vi.fn(),
    resizeViewPlots: vi.fn(),
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

  it("chaque espace ouvrable existe, avec son ouverture ET sa fermeture dans le VRAI mixin", () => {
    const declared = [...SPACES, ...RAIL_FOOT_SPACES].map((s) => s.id);
    for (const [id, entry] of Object.entries(SPACE_OPENERS)) {
      expect(declared, `${id} : espace non déclaré`).toContain(id);
      const mixin = REAL_MIXINS[id];
      expect(mixin, `${id} : mixin réel introuvable`).toBeTruthy();
      for (const name of [entry.open, entry.close]) {
        expect(mixin[name], `${id} : ${name}() absent du mixin réel`).toBeTypeOf("function");
      }
    }
  });

  it("chaque drapeau d'ouverture est un état du composant assemblé", () => {
    // Les drapeaux (`portfolioOpen`…) vivent dans les mixins OU dans `app.js`
    // selon l'espace : on les vérifie sur le composant RÉEL (`obole()`), seule
    // surface qui compte pour `openSpace()`.
    const real = obole();
    for (const [id, entry] of Object.entries(SPACE_OPENERS)) {
      expect(entry.flag in real, `${id} : drapeau ${entry.flag} absent du composant`).toBe(true);
    }
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

describe("openSpaceEntry — le déclencheur a déménagé, pas la vue", () => {
  it("un espace appelle son ouverture existante", () => {
    const c = comp();
    c.openSpaceEntry("indices");
    expect(c.openIndices).toHaveBeenCalledOnce();
    c.openSpaceEntry("watchlist");
    expect(c.openWatchlist).toHaveBeenCalledOnce();
  });

  it("« Analyse » referme l'espace ouvert sans rien charger", () => {
    const c = comp({ portfolioOpen: true });
    c.openSpaceEntry("analyse");
    expect(c.closePortfolio).toHaveBeenCalledOnce();
    expect(c.openPortfolio).not.toHaveBeenCalled();
  });

  it("« Analyse » sans espace ouvert ne fait rien", () => {
    const c = comp();
    c.openSpaceEntry("analyse");
    for (const fn of [c.closeIndices, c.closeScreener, c.closePortfolio, c.closeWatchlist, c.closeSettings]) {
      expect(fn).not.toHaveBeenCalled();
    }
  });
});

describe("closeAnySpace — Échap referme l'espace ouvert", () => {
  it("referme celui qui est ouvert et renvoie true", () => {
    const c = comp({ screenerOpen: true });
    expect(c.closeAnySpace()).toBe(true);
    expect(c.closeScreener).toHaveBeenCalledOnce();
  });

  it("sans espace ouvert, ne fait rien et renvoie false", () => {
    const c = comp();
    expect(c.closeAnySpace()).toBe(false);
    for (const fn of [c.closeIndices, c.closeScreener, c.closePortfolio, c.closeWatchlist, c.closeSettings]) {
      expect(fn).not.toHaveBeenCalled();
    }
  });

  it("laisse la priorité à une couche posée par-dessus l'espace", () => {
    // Échap ferme la modale du DESSUS : un zoom de graphe par-dessus le
    // portefeuille ne doit pas emporter le portefeuille avec lui.
    const c = comp({ portfolioOpen: true, pfChartFull: true });
    expect(c.closeAnySpace()).toBe(false);
    expect(c.closePortfolio).not.toHaveBeenCalled();
  });

  it("referme l'espace dès que la couche du dessus est fermée", () => {
    const c = comp({ portfolioOpen: true, pfChartFull: false });
    expect(c.closeAnySpace()).toBe(true);
    expect(c.closePortfolio).toHaveBeenCalledOnce();
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

  it("vide le champ de recherche : « Analyser » ne rouvre pas l'ancien ticker", () => {
    const c = comp();
    c.goHome();
    expect(c.query).toBe("");
  });

  it("oublie la fiche précédente : le même ticker repart sur « Résumé »", () => {
    // `_lastRef` distingue un RAFRAÎCHISSEMENT d'un changement de fiche. Le
    // laisser en place ferait rouvrir l'ancienne section après un retour accueil.
    const c = comp({ ...sectionsMixin, _lastRef: "RI.PA" });
    c.goHome();
    expect(c._lastRef).toBeNull();
  });

  it("invalide un chargement en vol : la fiche ne se rouvre pas toute seule", async () => {
    // `load()` capture la génération courante et abandonne son résultat si elle a
    // changé — c'est ce que fait `goHome()` en l'incrémentant.
    const c = comp({ _loadGeneration: 7 });
    c.goHome();
    expect(c._loadGeneration).toBe(8);
    expect(c.loading).toBe(false);
  });

  it("n'appelle que les fermetures des modales réellement ouvertes", () => {
    const c = comp({ watchlistOpen: true });
    c.goHome();
    expect(c.closeWatchlist).toHaveBeenCalledOnce();
    expect(c.closePortfolio).not.toHaveBeenCalled();
    expect(c.closeScreener).not.toHaveBeenCalled();
  });
});
