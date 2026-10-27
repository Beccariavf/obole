// Obole — coquille de navigation : le rail des espaces et l'entrée active.
//
// Deux rangs de navigation, deux sens distincts :
//   - le RAIL (ce module) sort de la fiche : indices, screener, portefeuille,
//     watchlist, paramètres. Ce sont des espaces, pas des sections ;
//   - les ONGLETS (`sections.js`) changent de section DANS la fiche.
//
// Le registre ci-dessous est la source unique : il pilote le rail, l'entrée
// active et les infobulles. Les modales restent des modales ; ce module ne fait
// que déplacer leur déclencheur.

const icon = (paths) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ` +
  `stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;

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
const SPACE_OPENERS = {
  indices: { flag: "indicesOpen", open: "openIndices", close: "closeIndices" },
  screener: { flag: "screenerOpen", open: "openScreener", close: "closeScreener" },
  portfolio: { flag: "portfolioOpen", open: "openPortfolio", close: "closePortfolio" },
  watchlist: { flag: "watchlistOpen", open: "openWatchlist", close: "closeWatchlist" },
  settings: { flag: "settingsOpen", open: "openSettings", close: "closeSettings" },
};

export function isSpaceId(id) {
  return SPACES.some((s) => s.id === id) || RAIL_FOOT_SPACES.some((s) => s.id === id);
}

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

  spaceLabel(id) {
    const s = [...SPACES, ...RAIL_FOOT_SPACES].find((x) => x.id === id);
    return s ? s.label : "";
  },

  spaceHint(id) {
    const s = [...SPACES, ...RAIL_FOOT_SPACES].find((x) => x.id === id);
    return s ? s.hint : "";
  },

  // Ouvre un espace. « Analyse » ne fait que refermer la modale courante : la
  // fiche est déjà derrière, on n'a rien à charger.
  openSpaceEntry(id) {
    if (id === "analyse") {
      const open = this.openSpace();
      if (open) this[SPACE_OPENERS[open].close]();
      return;
    }
    const entry = SPACE_OPENERS[id];
    if (entry && typeof this[entry.open] === "function") this[entry.open]();
  },

  // Marque · Retour à la maison : aucune fiche, aucun espace. On remet aussi le
  // champ de recherche à vide, sinon l'état affiché mentirait sur ce qu'on voit.
  goHome() {
    for (const [id, { close }] of Object.entries(SPACE_OPENERS)) {
      if (this[SPACE_OPENERS[id].flag]) this[close]();
    }
    this.data = null;
    this.error = "";
    this.loading = false;
    this.backTo = null;
    this.suggestions = [];
    // `location.hash = ""` laisse une `#` orpheline dans l'URL : on la retire par
    // l'API History, qui ne déclenche pas `hashchange` (aucun rechargement).
    if (window.location.hash) {
      window.history.replaceState(null, "", window.location.pathname + window.location.search);
    }
  },
};
