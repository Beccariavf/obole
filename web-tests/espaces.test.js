import { describe, expect, it } from "vitest";

import { navMixin, SPACE_OPENERS, SPACES, RAIL_FOOT_SPACES } from "../src/obole/web/nav.js";
import { readIndexSource, readStyleSource } from "./helpers/load-app.js";

// Espaces en PAGES (et non en modales plein écran).
//
// Avant ce chantier, chaque espace était une couche `.modal-overlay` de 98vw
// posée sur la fiche : elle recouvrait le rail, donc on ne pouvait passer d'un
// espace à l'autre qu'en refermant, et le rail était invisible la plupart du
// temps. Les cinq espaces sont désormais des vues SŒURS dans `.app-main`, sur
// lesquelles `x-show` bascule.
//
// vitest ne calcule pas de mise en page : les assertions portent ici sur les
// RÈGLES (structure HTML, CSS, contrat des drapeaux). Les mesures réelles
// (rail visible, vue à droite du rail, défilement du document) sont en e2e
// (`sections.spec.js` §« espaces »).
const html = readIndexSource();
const css = readStyleSource();

function bloc(selecteur) {
  const echappe = selecteur.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = css.match(new RegExp(`\\n${echappe}\\s*\\{([^}]*)\\}`));
  return m ? m[1] : null;
}

const VUES = ["analyse", "indices", "screener", "portfolio", "watchlist", "settings"];

describe("espaces — structure en vues", () => {
  it("chaque espace est une vue de la coquille, pas une modale", () => {
    for (const id of VUES) {
      expect(html, `vue ${id} absente`).toContain(`class="app-view view-${id}"`);
    }
    // Une vue par espace, jamais deux marqueurs pour la même chose.
    for (const id of VUES) {
      const occurrences = html.split(`class="app-view view-${id}"`).length - 1;
      expect(occurrences, `${id} : une seule vue`).toBe(1);
    }
  });

  it("aucune vue ne porte plus la classe `.modal`", () => {
    // Le vocabulaire suit la structure : une vue n'est pas une modale. Un alias
    // `modal-*` conservé « pour les tests » aurait fait diverger les deux
    // vocabulaires à la première correction.
    for (const id of ["indices", "screener", "portfolio", "watchlist", "settings"]) {
      expect(html).not.toContain(`class="modal modal-${id === "screener" ? "screen" : id}"`);
    }
    expect(css).not.toMatch(/\.modal-indices/);
    expect(css).not.toMatch(/\.modal-screen/);
    expect(css).not.toMatch(/\.modal-watchlist/);
    expect(css).not.toMatch(/\.modal-portfolio/);
    expect(css).not.toMatch(/\.modal-settings/);
  });

  it("les couches secondaires restent des modales", () => {
    // Un zoom de graphe, l'export, les événements, l'import CSV, le jeu de
    // conviction et les détails du portefeuille sont des gestes ponctuels : ils
    // doivent recouvrir la vue et lui rendre la main en se fermant.
    for (const drapeau of [
      "detailCard",
      "exportOpen",
      "eventsOpen",
      "convictionOpen",
      "pfChartFull",
      "pfDetailOpen",
      "showImportModal",
    ]) {
      const motif = new RegExp(`class="modal-overlay" x-show="${drapeau}"`);
      expect(html, `${drapeau} doit rester un overlay`).toMatch(motif);
    }
  });

  it("l'analyse est elle aussi une vue, pilotée par l'espace actif", () => {
    // Sans ce conteneur, la recherche et la fiche resteraient visibles SOUS
    // chaque espace (elles ne sont pas masquées par une couche).
    expect(html).toMatch(
      /class="app-view view-analyse"\s+x-show="activeSpace\(\) === 'analyse'"/,
    );
  });

  it("les vues espaces sont pilotées par leur drapeau existant", () => {
    for (const [id, entry] of Object.entries(SPACE_OPENERS)) {
      const motif = new RegExp(
        `class="app-view view-${id}"\\s+x-show="${entry.flag}"`,
      );
      expect(html, `${id} : la vue doit suivre ${entry.flag}`).toMatch(motif);
    }
  });

  it("aucune vue ne porte de croix de fermeture dans son en-tête", () => {
    // On ne ferme pas une page : on en change (rail), ou on revient à Analyse.
    // Les ✕ qui subsistent DANS le corps sont d'autres gestes (retirer un
    // membre d'un indice, effacer les filtres, supprimer un compte) : on ne
    // cible donc que l'en-tête, là où vivait la croix de fermeture.
    for (const tete of html.matchAll(/<div class="view-head">([\s\S]*?)\n      <\/div>/g)) {
      expect(tete[1], "en-tête de vue sans croix").not.toMatch(/✕/);
    }
    // Et aucun gestionnaire de fermeture n'est câblé dans ces en-têtes.
    for (const fermeture of [
      "closeIndices()",
      "closeScreener()",
      "closeWatchlist()",
      "closeSettings()",
      "closePortfolio()",
    ]) {
      const motif = new RegExp(`class="view-head"[\\s\\S]{0,600}${fermeture.replace(/[()]/g, "")}`);
      expect(html, `${fermeture} ne doit plus être un bouton de vue`).not.toMatch(motif);
    }
  });
});

describe("espaces — mise en page d'une vue", () => {
  it("une vue n'impose ni hauteur ni défilement interne", () => {
    // Le `96vh` + `overflow: hidden` des modales n'a plus de sens : c'est le
    // document qui défile, comme pour la fiche. Deux barres se disputeraient la
    // même hauteur et le trackpad changerait de cible selon le curseur.
    const vue = bloc(".app-view");
    expect(vue, "règle .app-view introuvable").toBeTruthy();
    expect(vue).not.toMatch(/height:\s*\d+vh/);
    expect(vue).not.toMatch(/overflow(-y)?:\s*(auto|scroll)/);
    // Et le conteneur principal du portefeuille ne défile plus sur lui-même.
    expect(bloc(".pf-main")).not.toMatch(/overflow-y:\s*auto/);
  });

  it("l'en-tête d'une vue est un titre de page, pas une barre collante", () => {
    // Coller le titre ET le bandeau du portefeuille demanderait une cascade de
    // `top` dont la moindre retouche de hauteur décalerait le second. Un seul
    // élément collant par vue : le bandeau, à la hauteur du rail.
    const tete = bloc(".view-head");
    expect(tete, "règle .view-head introuvable").toBeTruthy();
    expect(tete).not.toMatch(/position:\s*sticky/);
    expect(tete).toMatch(/border-bottom:\s*1px solid/);
  });

  it("le bandeau du portefeuille s'accroche à la hauteur du rail", () => {
    expect(bloc(".pf-context")).toMatch(/position:\s*sticky/);
    expect(bloc(".pf-context")).toMatch(/top:\s*var\(--head-top\)/);
  });

  it("l'en-tête de tableau reste accroché pendant le défilement", () => {
    const regle = css.match(/\.screen-table thead th \{([^}]*)\}/);
    expect(regle, "règle .screen-table thead th introuvable").toBeTruthy();
    expect(regle[1]).toMatch(/position:\s*sticky/);
    expect(regle[1]).toMatch(/top:\s*var\(--head-top\)/);
    // Et le conteneur ne doit PAS créer de défilement : `auto` comme `clip`
    // rattachent le `sticky` à une boîte qui ne défile jamais dans une vue,
    // donc l'en-tête ne collerait à rien (mesuré : il partait à −763 px).
    const wrap = bloc(".screen-table-wrap");
    expect(wrap, "règle .screen-table-wrap introuvable").toBeTruthy();
    // Commentaires retirés : ils citent justement `auto`/`clip` pour expliquer
    // pourquoi ces valeurs sont écartées.
    const declarations = wrap.replace(/\/\*[\s\S]*?\*\//g, "");
    expect(declarations).toMatch(/overflow:\s*visible/);
    expect(declarations).not.toMatch(/overflow(-y)?:\s*(auto|scroll|clip|hidden)/);
  });

  it("plus aucun sélecteur ne scope une règle à une « modale » d'espace", () => {
    expect(css).not.toMatch(/\.modal-(screen|watchlist|indices|portfolio|settings)\b/);
  });
});

describe("espaces — exclusivité de l'affichage", () => {
  function comp(overrides = {}) {
    return {
      indicesOpen: false,
      screenerOpen: false,
      portfolioOpen: false,
      watchlistOpen: false,
      settingsOpen: false,
      openIndices() { this.indicesOpen = true; },
      closeIndices() { this.indicesOpen = false; },
      openScreener() { this.screenerOpen = true; },
      closeScreener() { this.screenerOpen = false; },
      openPortfolio() { this.portfolioOpen = true; },
      closePortfolio() { this.portfolioOpen = false; },
      openWatchlist() { this.watchlistOpen = true; },
      closeWatchlist() { this.watchlistOpen = false; },
      openSettings() { this.settingsOpen = true; },
      closeSettings() { this.settingsOpen = false; },
      // jsdom n'implémente pas `window.scrollTo` : on l'isole par défaut.
      scrollToTop() {},
      resizeViewPlots() {},
      ...navMixin,
      ...overrides,
    };
  }

  it("ouvrir un espace referme celui qui était ouvert", () => {
    // Une modale du dessus cachait celle du dessous ; une VUE, elle, s'empile
    // visiblement — deux vues affichées et deux entrées actives sinon.
    const c = comp({ screenerOpen: true });
    c.openSpaceEntry("watchlist");
    expect(c.screenerOpen).toBe(false);
    expect(c.watchlistOpen).toBe(true);
    expect(c.activeSpace()).toBe("watchlist");
  });

  it("« Analyse » referme l'espace ouvert et retrace la fiche", () => {
    // Les tracés d'une fiche masquée (`display: none`) ont pu être dimensionnés
    // à largeur nulle : sans redessin, le graphe héro revient à sa largeur
    // d'avant l'ouverture de l'espace.
    const trace = [];
    const c = comp({ portfolioOpen: true });
    c.scheduleRedraw = () => trace.push("redraw");
    c.openSpaceEntry("analyse");
    expect(c.portfolioOpen).toBe(false);
    expect(trace).toEqual(["redraw"]);
  });

  it("une page ouverte se lit depuis son titre : le défilement repart de zéro", () => {
    // `x-show` ne touche pas au défilement du document. Sans remise à zéro, on
    // arrivait au MILIEU de la page suivante (mesuré : titre à y = −568), donc
    // sans titre, sans onglets et sans bandeau de contexte.
    const c = comp();
    const appels = [];
    c.scrollToTop = () => appels.push("haut");
    c.openSpaceEntry("portfolio");
    expect(appels).toEqual(["haut"]);
    appels.length = 0;
    c.openSpaceEntry("analyse");
    expect(appels).toEqual(["haut"]);
  });

  it("re-cliquer l'entrée DÉJÀ active ne relance ni reset ni appel réseau", () => {
    // En modale, un re-clic était sans conséquence visible ; le rail étant
    // devenu la navigation permanente, c'est un clic réflexe qui coûtait l'état
    // (résultats du screener vidés, onglet du portefeuille retombé sur Résumé).
    let ouvertures = 0;
    const c = comp({
      portfolioOpen: true,
      openPortfolio() {
        ouvertures += 1;
        this.portfolioOpen = true;
      },
    });
    c.scrollToTop = () => {};
    c.openSpaceEntry("portfolio");
    expect(ouvertures, "aucune réouverture").toBe(0);
    expect(c.portfolioOpen).toBe(true);
    // Un vrai changement d'espace ouvre normalement.
    c.openSpaceEntry("watchlist");
    expect(c.watchlistOpen).toBe(true);
    expect(c.portfolioOpen).toBe(false);
  });

  it("une vue montée redimensionne ses tracés Plotly", async () => {
    // `responsive: true` n'écoute que `window.resize` : une vue masquée pendant
    // un redimensionnement garde sinon la largeur de sa dernière mesure
    // (mesuré : hôte 378 px, SVG 710 px, carte qui déborde).
    const c = comp();
    c.scrollToTop = () => {};
    let resize = 0;
    c.resizeViewPlots = () => { resize += 1; };
    c.openSpaceEntry("settings");
    await Promise.resolve();
    expect(resize).toBe(1);
  });
});

describe("espaces — le rail reste la seule sortie", () => {
  it("chaque espace est atteignable depuis le rail, dans l'ordre du registre", () => {
    const ids = [...SPACES, ...RAIL_FOOT_SPACES].map((s) => s.id);
    expect(ids).toEqual([
      "analyse",
      "indices",
      "screener",
      "portfolio",
      "watchlist",
      "settings",
    ]);
    // Chaque entrée du rail écrit `data-space` : c'est le crochet des tests
    // (e2e) et l'attribut qui rend l'entrée identifiable sans son libellé.
    expect(html).toMatch(/:data-space="s\.id"/);
  });
});
