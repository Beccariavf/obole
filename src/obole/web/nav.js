// Obole — coquille de navigation : le rail des espaces et l'entrée active.
//
// Deux rangs de navigation, deux sens distincts :
//   - le RAIL (ce module) sort de la fiche : indices, screener, portefeuille,
//     watchlist, paramètres. Ce sont des espaces, pas des sections ;
//   - les ONGLETS (`sections.js`) changent de section DANS la fiche.
//
// Le registre ci-dessous est la source unique : il pilote le rail et l'entrée
// active. Les modales restent des modales ; ce module ne fait que déplacer leur
// déclencheur.
import { icon } from "./util.js";

export const SPACES = [
  {
    id: "analyse",
    label: "Analyse",
    hint: "La fiche du titre recherché : graphe, indicateurs, sections",
    svg: icon('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>'),
  },
  {
    id: "indices",
    label: "Mes indices",
    hint: "Indices personnalisés : paniers d'actions suivis comme un ETF",
    svg: icon('<path d="M3 21h18M6.5 21v-7.5M12 21V4.5M17.5 21v-11"/>'),
  },
  {
    id: "screener",
    label: "Screener",
    hint: "Sélectionne des actions selon la droite de régression, la rentabilité, la valorisation",
    svg: icon('<path d="M3 5h18l-7 8v6l-4 2v-8z"/>'),
  },
  {
    id: "portfolio",
    label: "Portefeuille",
    hint: "Achats, ventes, dividendes : positions et performance",
    svg: icon(
      '<rect x="2.5" y="7" width="19" height="13" rx="2"/>' +
        '<path d="M8.5 7V5.5A1.5 1.5 0 0 1 10 4h4a1.5 1.5 0 0 1 1.5 1.5V7"/>',
    ),
  },
  {
    id: "watchlist",
    label: "Watchlist",
    hint: "Valeurs suivies : tiers de conviction et marges de sécurité",
    svg: icon('<path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8-5.2-2.7-5.2 2.7 1-5.8-4.3-4.1 5.9-.9z"/>'),
  },
];

export const RAIL_FOOT_SPACES = [
  {
    id: "settings",
    label: "Paramètres",
    hint: "Réglage des moyennes mobiles, des seuils de conviction et sauvegarde des données",
    svg: icon(
      '<circle cx="12" cy="12" r="3"/>' +
        '<path d="M19.4 15a7.9 7.9 0 0 0 .1-1 7.9 7.9 0 0 0-.1-1l2-1.6-2-3.4-2.4 1a8 8 0 0 0-1.7-1L15 4.5h-4l-.3 2.5a8 8 0 0 0-1.7 1l-2.4-1-2 3.4L6.6 13a7.9 7.9 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a8 8 0 0 0 1.7 1l.3 2.5h4l.3-2.5a8 8 0 0 0 1.7-1l2.4 1 2-3.4z"/>',
    ),
  },
];

// Espaces qui ouvrent une modale plein écran, et le drapeau d'état qui la porte.
// L'ordre n'a pas d'importance : c'est une table de correspondance, pas un menu.
// Ces noms sont VÉRIFIÉS contre les vrais mixins par `nav.test.js` : sans ça, un
// renommage dans portfolio.js/watchlist.js/… casserait le rail en silence.
export const SPACE_OPENERS = {
  indices: { flag: "indicesOpen", open: "openIndices", close: "closeIndices" },
  screener: { flag: "screenerOpen", open: "openScreener", close: "closeScreener" },
  portfolio: { flag: "portfolioOpen", open: "openPortfolio", close: "closePortfolio" },
  watchlist: { flag: "watchlistOpen", open: "openWatchlist", close: "closeWatchlist" },
  settings: { flag: "settingsOpen", open: "openSettings", close: "closeSettings" },
};

export const navMixin = {
  spaces: SPACES,
  spacesFoot: RAIL_FOOT_SPACES,

  // Espace dont la modale est ouverte ; `null` quand aucune ne l'est. Sert à
  // marquer l'entrée active du rail ET à retomber sur « Analyse ».
  openSpace() {
    for (const [id, { flag }] of Object.entries(SPACE_OPENERS)) {
      if (this[flag]) return id;
    }
    return null;
  },

  // Entrée active du rail. « Analyse » est l'état de REPOS : c'est la fiche, et
  // elle est là même quand aucune modale n'est ouverte.
  activeSpace() {
    return this.openSpace() || "analyse";
  },

  // Les espaces autres que l'analyse : leur ouverture est asynchrone et peut
  // échouer (réseau, liaison KO). L'erreur est portée par l'état de CHAQUE
  // espace (`screenerError`, `portfolioError`…) ; on ne l'avale pas ici, on
  // empêche seulement une promesse rejetée de fuir sans handler.
  //
  // TROIS GESTES, dans cet ordre, et chacun corrige un défaut du passage de la
  // modale à la page :
  //  1. EXCLUSIVITÉ — les espaces sont des vues SŒURS, donc les drapeaux
  //     pourraient être vrais en même temps (deux vues empilées, deux entrées
  //     actives). On referme tout autre espace AVANT d'ouvrir celui demandé.
  //     En modale le problème ne se voyait pas : la couche du dessus masquait
  //     celle du dessous ; une vue, elle, s'empile visiblement.
  //  2. DÉFILEMENT — c'est le DOCUMENT qui défile. Sans remise à zéro, on
  //     arrivait au MILIEU de la page suivante (mesuré : titre à y = −568), donc
  //     sans titre, sans onglets et sans bandeau de contexte — exactement ce
  //     qu'on attend d'une page. `x-show` ne peut pas le faire : il ne touche
  //     pas au défilement du document.
  //  3. TRACÉS — une vue masquée donne une largeur nulle à Plotly, et un
  //     redimensionnement de fenêtre pendant ce temps ne la corrige pas (le
  //     redessin n'écoute que `window.resize`, qui ne se produit pas ici). On
  //     redessine la vue à son entrée.
  //
  // RELANCE INTERDITE sur l'espace DÉJÀ affiché : `open<s>()` réinitialise et
  // refait les appels réseau (mesuré : 5 lignes de screener → 0, onglet
  // « Risque » → « Résumé »). En modale un re-clic était sans conséquence ; le
  // rail étant devenu la navigation permanente, c'est un clic réflexe qui coûte
  // l'état de travail.
  openSpaceEntry(id) {
    if (this.activeSpace() === id && id !== "analyse") {
      this.scrollToTop();
      return;
    }
    if (id === "analyse") {
      const open = this.openSpace();
      if (open) this[SPACE_OPENERS[open].close]();
      this.scrollToTop();
      // La fiche redevient visible : ses tracés ont pu être dimensionnés pendant
      // qu'elle était masquée. On les retrace, sinon le graphe héro revient à la
      // largeur qu'il avait avant l'ouverture de l'espace.
      if (typeof this.scheduleRedraw === "function") this.scheduleRedraw();
      return;
    }
    const entry = SPACE_OPENERS[id];
    if (!entry || typeof this[entry.open] !== "function") return;
    for (const [other, spec] of Object.entries(SPACE_OPENERS)) {
      if (other !== id && this[spec.flag]) this[spec.close]();
    }
    this.scrollToTop();
    Promise.resolve(this[entry.open]())
      .then(() => this.resizeViewPlots())
      .catch(() => {
        /* l'erreur est déjà exposée par l'état de l'espace */
      });
  },

  // Remet le document en haut : une page qu'on ouvre se lit depuis son titre.
  scrollToTop() {
    if (typeof window === "undefined" || typeof window.scrollTo !== "function") return;
    window.scrollTo(0, 0);
  },

  // Redimensionne les tracés Plotly de la vue VISIBLE. `responsive: true` ne
  // réagit qu'à `window.resize` : une vue montée (ou revenue après un
  // redimensionnement passé pendant qu'elle était masquée) garde sinon la
  // largeur de sa dernière mesure (mesuré : hôte 378 px, SVG 710 px, carte qui
  // déborde). Le donut du portefeuille a son propre ResizeObserver, les autres
  // graphes n'en ont pas.
  resizeViewPlots() {
    if (typeof document === "undefined") return;
    const run = () => {
      const trace = (typeof window !== "undefined" && window.Plotly) || null;
      if (!trace || typeof trace.Plots?.resize !== "function") return;
      const plots = document.querySelectorAll(".app-view .js-plotly-plot");
      for (const plot of plots) {
        if (!plot.getBoundingClientRect().width) continue;
        try {
          trace.Plots.resize(plot);
        } catch {
          /* un graphe non initialisé n'a rien à redimensionner */
        }
      }
    };
    if (typeof requestAnimationFrame === "function") requestAnimationFrame(run);
    else run();
  },

  // Referme l'espace ouvert, quel qu'il soit. Appelé par Échap : les modales
  // plein écran recouvrent le rail (elles font 98vw), donc le clavier est le seul
  // moyen de passer d'un espace à l'autre sans viser la croix.
  //
  // Échap ferme la couche du DESSUS : si une modale imbriquée (détail de graphe,
  // zoom plein écran, export, événements, import…) est ouverte par-dessus
  // l'espace, c'est elle que la touche doit refermer. Sinon Échap ferait
  // disparaître l'espace entier sous la modale que l'utilisateur regarde.
  closeAnySpace() {
    if (this._nestedModalOpen()) return false;
    const open = this.openSpace();
    if (!open) return false;
    this[SPACE_OPENERS[open].close]();
    return true;
  },

  // Une modale est-elle posée AU-DESSUS de l'espace courant ? Liste explicite
  // des couches secondaires : chacune a son propre gestionnaire d'Échap, ce
  // prédicat ne fait que lui laisser la priorité.
  _nestedModalOpen() {
    return !!(
      this.detailCard ||
      this.pfChartFull ||
      this.pfDetailOpen ||
      this.pfBenchFreeOpen ||
      this.exportOpen ||
      this.eventsOpen ||
      this.showImportModal ||
      this.convictionOpen ||
      this.draftsOpen ||
      this.watchPopoverOpen ||
      this.watchRefOpen
    );
  },

  // Marque · Retour à l'accueil : aucune fiche, aucun espace, aucun reste.
  //
  // Trois états survivraient sans ça, et chacun rend le geste faux :
  //   - `query` garderait le ticker précédent, donc « Analyser » le rouvrirait ;
  //   - `_lastRef` (sections.js) ferait passer une RECHERCHE du même ticker pour
  //     un RAFRAÎCHISSEMENT, et rouvrirait l'ancienne section au lieu de Résumé ;
  //   - un `load()` en vol réaffecterait `data` et réécrirait le hash APRÈS le
  //     retour, rouvrant la fiche que l'utilisateur vient de quitter.
  // D'où le jeton de génération : `load()` le capture et abandonne son résultat
  // s'il a changé entre-temps (voir `_loadGeneration` dans search.js).
  goHome() {
    for (const [id, { close }] of Object.entries(SPACE_OPENERS)) {
      if (this[SPACE_OPENERS[id].flag]) this[close]();
    }
    this._loadGeneration = (this._loadGeneration || 0) + 1;
    this.query = "";
    this.data = null;
    this.error = "";
    this.loading = false;
    this.backTo = null;
    this.suggestions = [];
    if ("_lastRef" in this) this._lastRef = null;
    // `location.hash = ""` laisse une `#` orpheline dans l'URL : on la retire par
    // l'API History, qui ne déclenche pas `hashchange` (aucun rechargement).
    if (window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  },
};
