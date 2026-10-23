import { describe, expect, it, beforeEach, vi } from "vitest";

import {
  DEFAULT_SECTION,
  SECTIONS,
  isSectionId,
  sectionPlanned,
  sectionsMixin,
} from "../src/obole/web/sections.js";
// Fiche entreprise : une seule section affichée à la fois, rail vertical à
// gauche, deep-link `#<ticker>/<section>`.

function comp(overrides = {}) {
  const c = {
    ...sectionsMixin,
    data: null,
    $nextTick: (fn) => fn(),
    // `sectionGroups` vit dans charts.js : on fournit un défaut vide pour que
    // `expectedMiniIds()` reste fonctionnel sur un composant partiel.
    sectionGroups: () => [],
    // `sectionAvailable` vit aussi dans charts.js. Par défaut tout est
    // disponible : les tests de navigation ne portent pas sur la disponibilité.
    sectionAvailable: () => true,
    drawChart() {},
    drawMinis() {},
    load() {},
    ...overrides,
  };
  return c;
}

beforeEach(() => {
  window.location.hash = "";
});

describe("registre des sections", () => {
  it("expose les 6 sections dans l'ordre validé", () => {
    expect(SECTIONS.map((s) => s.id)).toEqual([
      "resume",
      "quantitatif",
      "dividende",
      "finance",
      "these",
      "valorisation",
    ]);
  });

  it("chaque section porte un libellé et une icône SVG", () => {
    for (const s of SECTIONS) {
      expect(s.label, `${s.id} : libellé manquant`).toBeTruthy();
      expect(s.svg, `${s.id} : icône manquante`).toMatch(/^<svg /);
      expect(s.svg).toContain("</svg>");
    }
  });

  it("isSectionId reconnaît les identifiants connus seulement", () => {
    expect(isSectionId("quantitatif")).toBe(true);
    expect(isSectionId("valorisation")).toBe(true);
    expect(isSectionId("RI.PA")).toBe(false);
    expect(isSectionId("")).toBe(false);
  });

  it("la section par défaut est « Résumé »", () => {
    expect(DEFAULT_SECTION).toBe("resume");
    expect(comp().activeSection).toBe("resume");
  });
});

describe("parseHash — deep-link #<ticker>/<section>", () => {
  it("ticker + section", () => {
    window.location.hash = "#RI.PA/quantitatif";
    expect(comp().parseHash()).toEqual({ ticker: "RI.PA", section: "quantitatif" });
  });

  it("ticker seul : section par défaut", () => {
    window.location.hash = "#RI.PA";
    expect(comp().parseHash()).toEqual({ ticker: "RI.PA", section: "resume" });
  });

  it("section seule (ratio / indice, sans ticker)", () => {
    window.location.hash = "#dividende";
    expect(comp().parseHash()).toEqual({ ticker: null, section: "dividende" });
  });

  it("section inconnue : repli sur « Résumé », ticker conservé", () => {
    window.location.hash = "#RI.PA/inconnu";
    expect(comp().parseHash()).toEqual({ ticker: "RI.PA", section: "resume" });
  });

  it("hash vide ou absent : null", () => {
    window.location.hash = "";
    expect(comp().parseHash()).toBeNull();
  });

  it("ticker normalisé en majuscules", () => {
    window.location.hash = "#ri.pa/these";
    expect(comp().parseHash()).toEqual({ ticker: "RI.PA", section: "these" });
  });
});

describe("écriture du hash", () => {
  it("une action écrit ticker + section", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.activeSection = "quantitatif";
    expect(c._buildHash()).toBe("#RI.PA/quantitatif");
  });

  it("un ratio / un indice écrit la section seule", () => {
    const c = comp({ data: { kind_payload: "ratio", identity: { ticker: "A / B" } } });
    c.activeSection = "dividende";
    expect(c._buildHash()).toBe("#dividende");
  });

  it("writeHash ne touche pas l'URL si le hash est déjà bon", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.activeSection = "quantitatif";
    window.location.hash = "#RI.PA/quantitatif";
    c.writeHash();
    expect(window.location.hash).toBe("#RI.PA/quantitatif");
  });
});

describe("setSection — navigation par le rail", () => {
  it("change la section, écrit le hash et redessine", () => {
    let redrawn = 0;
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.redrawActiveSection = () => { redrawn += 1; };
    c.setSection("valorisation");
    expect(c.activeSection).toBe("valorisation");
    expect(window.location.hash).toBe("#RI.PA/valorisation");
    expect(redrawn).toBe(1);
  });

  it("section inconnue ou déjà active : aucun effet", () => {
    let redrawn = 0;
    const c = comp();
    c.redrawActiveSection = () => { redrawn += 1; };
    c.setSection("inconnu");
    c.setSection("resume");
    expect(c.activeSection).toBe("resume");
    expect(redrawn).toBe(0);
  });
});

describe("applySectionsAfterLoad — section à l'ouverture d'une fiche", () => {
  it("sans demande explicite : retombe sur « Résumé »", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.activeSection = "dividende";
    c.applySectionsAfterLoad();
    expect(c.activeSection).toBe("resume");
    expect(window.location.hash).toBe("#RI.PA/resume");
  });

  it("avec une section en attente (deep-link) : la conserve", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c._pendingSection = "quantitatif";
    c.applySectionsAfterLoad();
    expect(c.activeSection).toBe("quantitatif");
    expect(c._pendingSection).toBeNull();
    expect(window.location.hash).toBe("#RI.PA/quantitatif");
  });

  it("un deep-link vers une section sans contenu retombe sur « Résumé »", () => {
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      sectionAvailable: (id) => id !== "these",   // section sans données pour ce titre
    });
    c._pendingSection = "these";
    c.applySectionsAfterLoad();
    expect(c.activeSection).toBe("resume");
    expect(window.location.hash).toBe("#RI.PA/resume");
  });

  it("rafraîchir la MÊME fiche conserve la section consultée", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.activeSection = "quantitatif";
    c._lastRef = "RI.PA";           // fiche déjà affichée une première fois
    c.applySectionsAfterLoad();      // rechargement (bouton ↻)
    expect(c.activeSection).toBe("quantitatif");
    expect(window.location.hash).toBe("#RI.PA/quantitatif");
  });

  it("changer de fiche repart bien sur « Résumé »", () => {
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "MC.PA" } } });
    c.activeSection = "quantitatif";
    c._lastRef = "RI.PA";           // fiche précédente différente
    c.applySectionsAfterLoad();
    expect(c.activeSection).toBe("resume");
    expect(c._lastRef).toBe("MC.PA");
  });

  it("le redraw attend que les conteneurs de la section existent (DOM flushé)", () => {
    vi.useFakeTimers();
    const origRaf = globalThis.requestAnimationFrame;
    // jsdom fournit rAF : on force le repli setTimeout pour piloter le timing.
    delete globalThis.requestAnimationFrame;
    let redrawn = 0;
    let probes = 0;
    const c = comp({ sectionGroups: () => [{ cards: [{ id: "x", type: "mono" }] }] });
    c.redrawActiveSection = () => { redrawn += 1; };
    const spy = vi.spyOn(document, "getElementById").mockImplementation(() => {
      probes += 1;
      return probes >= 2 ? document.createElement("div") : null;
    });
    try {
      c.scheduleRedraw();
      expect(redrawn, "conteneur absent : on ne trace pas sur l'ancien DOM").toBe(0);
      vi.runAllTimers();
      expect(redrawn, "conteneur apparu : le tracé a lieu").toBe(1);
    } finally {
      spy.mockRestore();
      vi.useRealTimers();
      globalThis.requestAnimationFrame = origRaf;
    }
  });
});

describe("sections planifiées (« à venir ») — toutes livrées", () => {
  it("aucune section n'est « à venir » : la thèse est livrée (#21)", () => {
    for (const id of ["resume", "quantitatif", "dividende", "finance", "these", "valorisation"]) {
      expect(sectionPlanned(id), `${id} ne doit pas être « à venir »`).toBe(false);
    }
  });

  it("le libellé d'infobulle distingue « à venir » de « aucune donnée »", () => {
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      sectionAvailable: (id) => id !== "dividende",
    });
    expect(c.sectionTitle("dividende")).toBe("Dividende — aucune donnée pour ce titre");
    expect(c.sectionTitle("resume")).toBe("Résumé");
    expect(c.sectionTitle("these")).toBe("Thèse & Société");
  });
});

describe("alignement de la thèse au changement de fiche (#1)", () => {
  it("changer de fiche réinitialise la thèse, MÊME hors section « these »", () => {
    // Le scénario du bug : on quitte la section en changeant de titre, donc le
    // reset ne peut pas dépendre de l'affichage de la section.
    let reset = 0;
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "AI.PA" } },
      activeSection: "resume",
      thesisTicker: "RI.PA",
      thesisLoaded: true,
      resetThesisState() {
        reset += 1;
        this.thesisTicker = null;
        this.thesisLoaded = false;
      },
    });
    c.applySectionsAfterLoad();
    expect(reset).toBe(1);
    expect(c.thesisTicker).toBe(null);
  });

  it("un simple rafraîchissement de la même fiche ne réinitialise rien", () => {
    let reset = 0;
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      activeSection: "resume",
      thesisTicker: "RI.PA",
      thesisLoaded: true,
      resetThesisState() {
        reset += 1;
      },
    });
    c.applySectionsAfterLoad();
    expect(reset).toBe(0);
  });

  it("aucun reset avant tout chargement (état initial)", () => {
    let reset = 0;
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      activeSection: "resume",
      resetThesisState() {
        reset += 1;
      },
    });
    c.applySectionsAfterLoad();
    expect(reset).toBe(0);
  });
});

describe("sections indisponibles — repli sur « Résumé »", () => {
  it("un deep-link vers une section sans contenu retombe sur « Résumé »", () => {
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      sectionAvailable: (id) => id !== "these",   // « Thèse & Société » à venir
    });
    c._pendingSection = "these";
    c.applySectionsAfterLoad();
    expect(c.activeSection, "pas d'écran blanc : on replie sur Résumé").toBe("resume");
    expect(window.location.hash).toBe("#RI.PA/resume");
  });

  it("une section disponible est bien conservée", () => {
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      sectionAvailable: (id) => id !== "these",
    });
    c._pendingSection = "quantitatif";
    c.applySectionsAfterLoad();
    expect(c.activeSection).toBe("quantitatif");
  });

  it("setSection refuse une section indisponible", () => {
    const c = comp({
      data: { kind_payload: "stock", identity: { ticker: "RI.PA" } },
      sectionAvailable: (id) => id !== "these",
    });
    c.setSection("these");
    expect(c.activeSection).toBe("resume");
  });

  it("le hash d'une section indisponible retombe sur « Résumé »", () => {
    const c = comp({
      data: { kind_payload: "ratio", identity: { ticker: "A / B" } },
      sectionAvailable: (id) => id === "resume",
    });
    c.activeSection = "resume";
    window.location.hash = "#dividende";
    c.onHashChange();
    expect(c.activeSection).toBe("resume");
  });
});

describe("rafraîchissement d'un ratio / d'un indice", () => {
  it("un ratio garde sa section au rafraîchissement", () => {
    const c = comp({
      data: {
        kind_payload: "ratio",
        identity: { ticker_a: "CW8.PA", ticker_b: "SPY" },
      },
    });
    c.activeSection = "resume";
    c._lastRef = "CW8.PA/SPY";        // même fiche que la fois précédente
    c.applySectionsAfterLoad();
    expect(c._lastRef).toBe("CW8.PA/SPY");
    expect(window.location.hash).toBe("#resume");
  });

  it("un indice garde sa section au rafraîchissement", () => {
    const c = comp({
      data: {
        kind_payload: "basket",
        identity: { index_id: 7, name: "CAC Tech" },
      },
    });
    c.activeSection = "resume";
    c._lastRef = "INDEX:7";
    c.applySectionsAfterLoad();
    expect(c._lastRef).toBe("INDEX:7");
  });

  it("changer d'indice repart bien sur « Résumé »", () => {
    const c = comp({
      data: { kind_payload: "basket", identity: { index_id: 8, name: "Autre" } },
    });
    c.activeSection = "resume";
    c._lastRef = "INDEX:7";
    c.applySectionsAfterLoad();
    expect(c._lastRef).toBe("INDEX:8");
  });

  it("_hashRef distingue action, ratio et indice", () => {
    expect(comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } })._hashRef())
      .toBe("RI.PA");
    expect(
      comp({ data: { kind_payload: "ratio", identity: { ticker_a: "CW8.PA", ticker_b: "SPY" } } })._hashRef(),
    ).toBe("CW8.PA/SPY");
    expect(comp({ data: { kind_payload: "basket", identity: { index_id: 7 } } })._hashRef())
      .toBe("INDEX:7");
    expect(comp({ data: null })._hashRef()).toBeNull();
  });
});

describe("onHashChange — bouton retour du navigateur", () => {
  it("changer de section par le hash met à jour l'état sans recharger", () => {
    let loaded = 0;
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.load = () => { loaded += 1; };
    c.activeSection = "resume";
    window.location.hash = "#RI.PA/valorisation";
    c.onHashChange();
    expect(c.activeSection).toBe("valorisation");
    expect(loaded).toBe(0);
  });

  it("un autre ticker déclenche le chargement avec la section demandée", () => {
    let loaded = 0;
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.load = () => { loaded += 1; };
    window.location.hash = "#MC.PA/dividende";
    c.onHashChange();
    expect(c.query).toBe("MC.PA");
    expect(c._pendingSection).toBe("dividende");
    expect(loaded).toBe(1);
  });

  it("hash identique à l'état courant : aucun effet (idempotent)", () => {
    let loaded = 0;
    const c = comp({ data: { kind_payload: "stock", identity: { ticker: "RI.PA" } } });
    c.load = () => { loaded += 1; };
    c.activeSection = "quantitatif";
    window.location.hash = "#RI.PA/quantitatif";
    c.onHashChange();
    expect(c.activeSection).toBe("quantitatif");
    expect(loaded).toBe(0);
  });
});
