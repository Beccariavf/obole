// Obole — sections de la fiche entreprise : registre + navigation.
//
// La fiche n'affiche qu'UNE section à la fois (onglets horizontaux au-dessus du
// contenu). L'ordre ci-dessous est la source unique : il pilote les onglets, le
// filtrage des cartes (charts.js::sectionGroups) et le deep-link
// `#<ticker>/<section>`.
//
// Les icônes sont des SVG inline (constantes du module, aucun contenu tiers ni
// donnée utilisateur) : le front reste sans build et sans CDN.
import { NON_CHART_TYPES } from "./charts.js";
import { icon } from "./util.js";

export const SECTIONS = [
  {
    id: "resume",
    label: "Résumé",
    svg: icon('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>'),
  },
  {
    id: "quantitatif",
    label: "Quantitatif",
    svg: icon('<path d="M3 21h18M6.5 21v-7.5M12 21V4.5M17.5 21v-11"/>'),
  },
  {
    id: "dividende",
    label: "Dividende",
    svg: icon('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.2"/>'),
  },
  {
    id: "finance",
    label: "Finance",
    svg: icon(
      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>' +
        '<path d="M14 3v5h5"/>',
    ),
  },
  {
    id: "these",
    label: "Thèse & Société",
    svg: icon(
      '<path d="M4 21V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v16"/>' +
        '<path d="M16 8h2a2 2 0 0 1 2 2v11"/><path d="M2 21h20"/>',
    ),
  },
  {
    id: "valorisation",
    label: "Valorisation",
    svg: icon('<path d="M12 2.5 21.5 12 12 21.5 2.5 12z"/>'),
  },
  {
    id: "momentum",
    label: "Momentum",
    // Jauge : le régime de foule, entre le monde de Markovitz et celui de
    // Mandelbrot (Clara Vallis, #30).
    svg: icon('<path d="M4 17a8 8 0 0 1 16 0"/><path d="M12 17l4.5-4.5"/><circle cx="12" cy="17" r="1.4"/>'),
  },
];

export const DEFAULT_SECTION = "resume";

// Sections dont le contenu reste à construire (étapes 2→7 du chantier #16). Elles
// apparaissent en onglets comme repères de navigation, mais sont marquées
// « à venir » — à distinguer d'une section vide faute de données pour le titre.
// (#21 a livré « these » : elle n'est donc plus « à venir ».)
export const PLANNED_SECTIONS = new Set();

export function sectionPlanned(id) {
  return PLANNED_SECTIONS.has(id);
}

export function isSectionId(id) {
  return SECTIONS.some((s) => s.id === id);
}

export const sectionsMixin = {
  sections: SECTIONS,
  activeSection: DEFAULT_SECTION,
  // Section demandée par un deep-link, appliquée APRÈS le chargement des données
  // (sinon `load()` retomberait sur « Résumé »).
  _pendingSection: null,
  // Référence de la dernière fiche affichée : sert à distinguer un CHANGEMENT de
  // fiche (on repart sur « Résumé ») d'un simple RAFRAÎCHISSEMENT (on garde la
  // section consultée).
  _lastRef: null,

  // Référence d'identité de la fiche courante. Sert à distinguer un CHANGEMENT
  // de fiche (on repart sur « Résumé ») d'un simple RAFRAÎCHISSEMENT (on garde
  // la section consultée). Doit être stable pour les trois types de fiche :
  //   action  -> son ticker            (« RI.PA »)
  //   ratio   -> la paire              (« CW8.PA/SPY »)
  //   indice  -> son identifiant       (« INDEX:7 »)
  // Renvoie null tant que la fiche n'est pas chargée (état initial).
  _hashRef() {
    const d = this.data;
    if (!d) return null;
    if (d.kind_payload === "stock") return d.identity?.ticker || null;
    if (d.kind_payload === "ratio") {
      const a = d.identity?.ticker_a;
      const b = d.identity?.ticker_b;
      return a && b ? `${a}/${b}` : null;
    }
    if (d.kind_payload === "basket") {
      const id = d.identity?.index_id;
      return id != null ? `INDEX:${id}` : null;
    }
    return null;
  },

  // Référence du titre pour le HASH : seul un ticker d'action y a sa place (un
  // ratio / un indice n'a pas de ticker simple -> hash réduit à la section).
  _hashTicker() {
    if (this.data?.kind_payload !== "stock") return null;
    return this.data.identity?.ticker || null;
  },

  // `#RI.PA/quantitatif` | `#RI.PA` | `#quantitatif` -> { ticker, section }.
  // Un segment unique qui n'est pas une section connue est lu comme un ticker.
  parseHash() {
    const raw = (window.location.hash || "").replace(/^#/, "").trim();
    if (!raw) return null;
    const parts = raw.split("/");
    if (parts.length === 1) {
      const only = parts[0].trim();
      if (isSectionId(only.toLowerCase())) return { ticker: null, section: only.toLowerCase() };
      return { ticker: only.toUpperCase() || null, section: DEFAULT_SECTION };
    }
    const ticker = parts[0].trim().toUpperCase() || null;
    const rawSection = (parts[1] || "").trim().toLowerCase();
    return { ticker, section: isSectionId(rawSection) ? rawSection : DEFAULT_SECTION };
  },

  _buildHash() {
    const ref = this._hashTicker();
    return ref ? `#${ref}/${this.activeSection}` : `#${this.activeSection}`;
  },

  writeHash() {
    const h = this._buildHash();
    if (window.location.hash !== h) window.location.hash = h;
  },

  // Identifiants des conteneurs de mini-charts attendus pour la section active
  // (les cartes de type graphe ont un div `mc-<slug>` ; les bandeaux de chiffres
  // — CAGR, KPI dividende — n'en ont pas). Source unique : `NON_CHART_TYPES`
  // est importée de `charts.js` (même règle que `isChartCard`, pas de dérive).
  expectedMiniIds() {
    // La section Valorisation rend ses cartes par un template DÉDIÉ (calculatrice
    // + courbes) : `sectionGroups()` ne les expose pas. On lit donc directement
    // `valuationGroups()` pour que `scheduleRedraw` attende les bons conteneurs.
    const groups =
      this.activeSection === "valorisation" && typeof this.valuationGroups === "function"
        ? this.valuationGroups()
        : typeof this.sectionGroups === "function"
          ? this.sectionGroups()
          : [];
    return groups
      .flatMap((g) => g.cards)
      .filter((c) => !NON_CHART_TYPES.has(c.type))
      .map((c) => "mc-" + c.id);
  },

  // Une section est-elle consultable pour la fiche affichée ? Combine l'identifiant
  // connu, le fait qu'elle soit déjà implémentée (une section « à venir » n'a
  // rien à montrer) et la disponibilité réelle (définie par
  // `charts.js::sectionAvailable`, qui sait quelles cartes existent). Un ratio
  // n'a pas de comptes : tout sauf « Résumé » est vide, donc inaccessible.
  _sectionUsable(id) {
    if (!isSectionId(id) || sectionPlanned(id)) return false;
    if (typeof this.sectionAvailable !== "function") return true;
    return this.sectionAvailable(id);
  },

  // Libellé d'infobulle : explique POURQUOI une entrée est grisée. « à venir »
  // (contenu non encore construit) n'est pas « aucune donnée pour ce titre »
  // (la source ne fournit rien pour cette société).
  sectionTitle(id) {
    const s = SECTIONS.find((x) => x.id === id);
    if (!s) return "";
    if (sectionPlanned(id)) return `${s.label} — à venir`;
    if (!this._sectionUsable(id)) return `${s.label} — aucune donnée pour ce titre`;
    return s.label;
  },

  setSection(id) {
    if (!this._sectionUsable(id) || id === this.activeSection) return;
    this.activeSection = id;
    this.writeHash();
    this.scheduleRedraw();
    // `_loadThesisIfNeeded` porte le chargement de la thèse ET l'armement du
    // scroll-spy (source unique, cf. son commentaire).
    if (typeof this._loadThesisIfNeeded === "function") this._loadThesisIfNeeded();
  },

  // Redessine ce qui est visible : le graphe héro (section Résumé) et les
  // mini-charts de la section active. Indispensable car un graphe masqué par
  // `x-show` a une taille nulle et Plotly ne peut pas le tracer.
  redrawActiveSection() {
    if (this.activeSection === "resume") {
      try {
        this.drawChart();
      } catch (e) {
        console.error("drawChart error:", e);
      }
    }
    try {
      this.drawMinis();
    } catch (e) {
      console.error("drawMinis error:", e);
    }
  },

  // Attend que les conteneurs des mini-charts de la section active existent
  // RÉELLEMENT dans le DOM avant de tracer. Un simple `$nextTick` ne suffit pas :
  // après un changement de section, le re-render Alpine de `sectionGroups()`
  // (qui crée ces divs) peut être flushé APRÈS notre callback — `drawMinis()`
  // itérerait alors l'ancien DOM et laisserait la nouvelle section vide. On
  // réessaie donc sur quelques frames, puis on trace quoi qu'il arrive.
  scheduleRedraw(attempt = 0) {
    const ready = this.expectedMiniIds().every((id) => document.getElementById(id));
    if (!ready && attempt < 12) {
      const raf =
        typeof requestAnimationFrame === "function"
          ? requestAnimationFrame
          : (fn) => setTimeout(fn, 0);
      raf(() => this.scheduleRedraw(attempt + 1));
      return;
    }
    this.redrawActiveSection();
  },

  // Après un chargement de fiche : applique la section demandée (deep-link) ou
  // retombe sur « Résumé » (nouvelle recherche, screener, indice…). Un simple
  // rafraîchissement de la MÊME fiche conserve la section consultée.
  //
  // Une section demandée mais INDISPONIBLE (section sans comptes sur un ratio)
  // est repliée sur « Résumé » : sinon un lien partagé / rechargé atterrirait sur
  // une page blanche sous le header.
  applySectionsAfterLoad() {
    const ref = this._hashRef();
    const isRefresh = ref !== null && ref === this._lastRef;
    if (!isRefresh) {
      const wanted = this._pendingSection;
      this.activeSection = this._sectionUsable(wanted) ? wanted : DEFAULT_SECTION;
    }
    this._lastRef = ref;
    this._pendingSection = null;
    this.writeHash();
    this.scheduleRedraw();
    // La thèse est chargée à la demande, une fois la section connue (#21) : les
    // fiches sans thèse n'entraînent aucun appel réseau supplémentaire.
    this._loadThesisIfNeeded();
  },

  // Chargement paresseux de la thèse : uniquement quand la section est affichée
  // (ou en attente de l'être), jamais pour les autres sections.
  //
  // Le plan latéral (scroll-spy) est branché ICI et non dans `setSection` :
  // c'est le seul point de passage de TOUS les chemins d'affichage (clic,
  // deep-link `#RI.PA/these`, retour navigateur, rechargement de fiche). Sinon
  // un deep-link ouvrait la section sans jamais surligner le plan (CA-TOC6).
  _loadThesisIfNeeded() {
    // ALIGNEMENT DE FICHE — indépendant de la section affichée. Changer de titre
    // quitte la section « these » (on revient à « Résumé ») : si le reset était
    // conditionné à l'affichage, l'état de l'ancienne fiche survivrait, et une
    // saisie en cours partirait sous le ticker de la nouvelle (voir #1).
    const ticker = this.data?.identity?.ticker;
    if (
      typeof this.resetThesisState === "function" &&
      (this.thesisTicker || this.thesisLoaded) &&
      ticker !== this.thesisTicker
    ) {
      this.resetThesisState();
    }
    // Même précaution pour les points de contrôle suivis (#21) : ils sont
    // persistés par ticker, donc une liste validée sur une autre fiche ne doit
    // jamais s'afficher (ni s'écrire) ici.
    if (
      typeof this.resetCheckpoints === "function" &&
      (this.cpTicker || this.cpLoaded) &&
      ticker !== this.cpTicker
    ) {
      this.resetCheckpoints();
    }
    if (this.activeSection !== "these") {
      if (typeof this.stopThesisScrollSpy === "function") this.stopThesisScrollSpy();
      return;
    }
    // Bande « Suivi » : chargée avec la section, indépendamment de la thèse (elle
    // porte aussi l'échéance société, qui existe sans document).
    if (typeof this.loadCheckpoints === "function") {
      this.loadCheckpoints().catch(() => {
        /* l'erreur est portée par l'état du mixin */
      });
    }
    if (typeof this.loadThesis !== "function") return;
    this.loadThesis().then(
      () => {
        // Après le rendu du corps : les titres à observer existent alors.
        this.$nextTick?.(() => {
          if (typeof this.startThesisScrollSpy === "function") this.startThesisScrollSpy();
        });
      },
      () => {
        /* l'erreur est portée par l'état du mixin */
      },
    );
  },

  // Bouton « retour » du navigateur (et hash saisi à la main). Idempotent : un
  // hash identique à l'état courant ne déclenche rien (pas de boucle).
  onHashChange() {
    const h = this.parseHash();
    if (!h) return;
    if (h.ticker && h.ticker !== this._hashTicker()) {
      this._pendingSection = h.section;
      this.query = h.ticker;
      this.load();
      return;
    }
    // Section indisponible : on replie sur « Résumé » (jamais d'écran vide).
    const target = this._sectionUsable(h.section) ? h.section : DEFAULT_SECTION;
    if (target !== this.activeSection) {
      this.activeSection = target;
      this.writeHash();
      this.scheduleRedraw();
    }
  },
};
