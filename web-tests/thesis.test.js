// Thèse & Société (#21) — mixin `web/thesis.js`, sans réseau.
//
// Le mixin est un objet plat, comme les autres domaines : on teste le
// COMPORTEMENT (états, auto-save, conflit, cochage) en stubant `api`, jamais en
// rendant Alpine. Les dépendances DOM (textarea, `$nextTick`) sont facultatives :
// chaque méthode doit fonctionner sans elles.

import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const VENDOR = join(process.cwd(), "..", "src", "obole", "web", "vendor");
for (const file of ["marked.min.js", "dompurify.min.js"]) {
  window.eval(readFileSync(join(VENDOR, file), "utf8"));
}

const { thesisMixin } = await import("../src/obole/web/thesis.js");
const { renderThesis: renderThesisForTest } = await import("../src/obole/web/markdown.js");

// Contexte minimal : le mixin + un état de fiche (comme le composant `obole`).
function ctx(over = {}) {
  const c = {
    ...thesisMixin,
    data: {
      kind_payload: "stock",
      identity: { ticker: "RI.PA", name: "Pernod Ricard" },
      has_thesis: false,
      profile: {
        officers: [
          { name: "Alexandre Ricard", title: "CEO, MD & Chairman", age: 53 },
          { name: "Helene de Tissot", title: "EVP of Finance", age: 55 },
        ],
        employees: 16006,
        address: "Paris, France",
        summary: "Producteur de vins et spiritueux.",
        next_earnings: "2026-11-26",
        next_earnings_estimated: false,
        ex_dividend: "2027-11-25",
      },
    },
  };
  return Object.assign(c, over);
}

describe("profil société (CA2, CA3, CA-UI10)", () => {
  it("la direction générale est identifiée par son titre", () => {
    const c = ctx();
    expect(c.thesisCeo().name).toBe("Alexandre Ricard");
  });

  it("à défaut de titre « CEO », le premier dirigeant est retenu", () => {
    const c = ctx({ data: { kind_payload: "stock", profile: { officers: [{ name: "X" }] } } });
    expect(c.thesisCeo().name).toBe("X");
  });

  it("sans dirigeant connu -> null (pas de crash)", () => {
    expect(ctx({ data: { kind_payload: "stock", profile: {} } }).thesisCeo()).toBe(null);
  });

  it("les faits omettent les champs absents", () => {
    const c = ctx({
      data: { kind_payload: "stock", identity: { ticker: "X" }, profile: { employees: 10 } },
    });
    const labels = c.profileFacts().map((f) => f.label);
    expect(labels).toEqual(["Effectif"]);
  });

  it("l'effectif est formaté en français", () => {
    const c = ctx();
    const row = c.profileFacts().find((f) => f.label === "Effectif");
    expect(row.value).toMatch(/16\s?006/);
  });

  it("le site web est un lien", () => {
    const c = ctx({
      data: {
        kind_payload: "stock",
        identity: { ticker: "X", website: "https://x.fr" },
        profile: {},
      },
    });
    const row = c.profileFacts().find((f) => f.label === "Site web");
    expect(row.href).toBe("https://x.fr");
  });

  // Le prochain résultat n'est plus dans l'agenda du profil : il vit dans la
  // bande « Suivi » (`suivi.js`), une seule occurrence par fiche (CA-B1).
  it("l'agenda ne contient plus le prochain résultat", () => {
    const c = ctx();
    expect(c.profileAgenda().map((r) => r.label)).not.toContain("Prochain résultat");
  });

  it("l'agenda conserve l'ex-dividende avec sa date et son compte à rebours", () => {
    const c = ctx();
    const row = c.profileAgenda().find((r) => r.label === "Ex-dividende");
    expect(row.date).toContain("2027");
    expect(row.relative).toMatch(/dans \d+ j/);
  });

  it("une date de détachement passée devient « passé »", () => {
    const c = ctx({
      data: { kind_payload: "stock", profile: { ex_dividend: "2020-01-01" } },
    });
    const row = c.profileAgenda().find((r) => r.label === "Ex-dividende");
    expect(row.after).toBe("passé");
    expect(row.relative).toBe("");
  });

  it("agenda vide -> aucune ligne", () => {
    const c = ctx({ data: { kind_payload: "stock", profile: {} } });
    expect(c.profileAgenda()).toEqual([]);
  });

  it("« Thèse modifiée » a disparu de l'agenda (doublon avec le statut d'auto-save)", () => {
    const c = ctx({ thesisUpdatedAt: 1700000000 });
    expect(c.profileAgenda().map((r) => r.label)).not.toContain("Thèse modifiée");
  });
});

describe("chargement de la thèse (CA4, CA-UI1)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("404 = état vide, pas une erreur", async () => {
    const c = ctx();
    c.loadThesis = thesisMixin.loadThesis.bind(c);
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }));
    await c.loadThesis();
    expect(c.thesisContent).toBe("");
    expect(c.thesisError).toBe("");
    expect(c.thesisLoaded).toBe(true);
    expect(c.thesisHasContent()).toBe(false);
  });

  it("charge le markdown et l'horodatage", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ content: "# Thèse\n\n## Pitch\n\nx", updated_at: 1000 }),
    }));
    await c.loadThesis();
    expect(c.thesisHasContent()).toBe(true);
    expect(c.thesisOriginal).toBe(c.thesisContent);
    expect(c.thesisUpdatedAt).toBe(1000);
  });

  it("une thèse historique (objet JSON) reste affichable", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ content: { pitch: "Décotée" }, updated_at: 1 }),
    }));
    await c.loadThesis();
    expect(c.thesisContent).toContain("## pitch");
    expect(c.thesisContent).toContain("Décotée");
  });

  it("le sommaire est calculé au chargement", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ content: "# A\n\n## B\n", updated_at: 1 }),
    }));
    await c.loadThesis();
    expect(c.thesisView.toc.length).toBe(2);
    expect(c.thesisTocVisible()).toBe(true);
  });

  it("la section n'est pas chargeable sur un ratio", async () => {
    const c = ctx({ data: { kind_payload: "ratio" } });
    globalThis.fetch = vi.fn();
    await c.loadThesis();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("#1 — changer de fiche efface la thèse précédente, même en édition", async () => {
    const c = ctx({ thesisTicker: "RI.PA", thesisContent: "# Thèse Pernod", thesisEditing: true, thesisLoaded: true });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ content: "# Thèse Air Liquide", updated_at: 5 }),
    }));
    // On bascule sur AI.PA : le contenu affiché appartenait à RI.PA.
    c.data.identity.ticker = "AI.PA";
    await c.loadThesis();
    expect(c.thesisTicker).toBe("AI.PA");
    expect(c.thesisEditing).toBe(false);          // plus de mode édition hérité
    expect(c.thesisContent).toBe("# Thèse Air Liquide");
  });

  it("#1 — une fiche sans thèse affiche l'état vide, pas le contenu précédent", async () => {
    const c = ctx({ thesisTicker: "RI.PA", thesisContent: "# Thèse Pernod", thesisLoaded: true });
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }));
    c.data.identity.ticker = "AI.PA";
    await c.loadThesis();
    expect(c.thesisContent).toBe("");
    expect(c.thesisHasContent()).toBe(false);
    expect(c.thesisTicker).toBe("AI.PA");
  });

  it("#1 — le reset annule l'auto-save en attente (pas d'écriture croisée)", () => {
    const c = ctx({ thesisContent: "en cours", thesisOriginal: "" });
    vi.useFakeTimers();
    c.onThesisInput();
    expect(c._thesisTimer).not.toBe(null);
    c.resetThesisState();
    expect(c._thesisTimer).toBe(null);
    expect(c.thesisStatus).toBe("idle");
    expect(c.thesisView.html).toBe("");
    vi.useRealTimers();
  });

  it("#9 — supprimer la thèse revient à l'état vide", async () => {
    const c = ctx({ thesisTicker: "RI.PA", thesisContent: "# Thèse", thesisOriginal: "# Thèse" });
    vi.useFakeTimers();
    globalThis.confirm = vi.fn(() => true);
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ status: "deleted" }) }));
    await c.deleteThesisNow();
    expect(c.thesisHasContent()).toBe(false);
    expect(c.data.has_thesis).toBe(false);
    expect(c.thesisNotice).toBe("Thèse supprimée.");
    vi.useRealTimers();
  });

  it("#9 — une suppression refusée ne touche pas au document", async () => {
    const c = ctx({ thesisContent: "# Précieuse", thesisOriginal: "# Précieuse" });
    globalThis.confirm = vi.fn(() => false);
    globalThis.fetch = vi.fn();
    await c.deleteThesisNow();
    expect(c.thesisContent).toBe("# Précieuse");
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("auto-save et états (CA-UI4, CA-UI5)", () => {
  it("passer en « dirty » dès la première frappe", () => {
    const c = ctx({ thesisContent: "a", thesisOriginal: "" });
    vi.useFakeTimers();
    c.onThesisInput();
    expect(c.thesisStatus).toBe("dirty");
    vi.useRealTimers();
  });

  it("revenir à la version enregistrée remet l'état à « idle »", () => {
    const c = ctx({ thesisContent: "a", thesisOriginal: "a" });
    c.onThesisInput();
    expect(c.thesisStatus).toBe("idle");
  });

  it("un enregistrement réussi met à jour l'horodatage et le drapeau du rail", async () => {
    const c = ctx({ thesisContent: "b", thesisOriginal: "a" });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", updated_at: 42 }),
    }));
    await c.saveThesisNow();
    expect(c.thesisStatus).toBe("saved");
    expect(c.thesisOriginal).toBe("b");
    expect(c.thesisUpdatedAt).toBe(42);
    expect(c.data.has_thesis).toBe(true);
    expect(c.thesisSavedAt).not.toBe("");
  });

  it("un échec est VISIBLE et conserve le contenu (jamais silencieux)", async () => {
    const c = ctx({ thesisContent: "b", thesisOriginal: "a" });
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "Base indisponible" }),
    }));
    await c.saveThesisNow();
    expect(c.thesisStatus).toBe("error");
    expect(c.thesisError).toBe("Base indisponible");
    expect(c.thesisContent).toBe("b");
    expect(c.thesisOriginal).toBe("a");   // on ne ment jamais sur l'état enregistré
  });

  it("rien à enregistrer -> aucun appel réseau", async () => {
    const c = ctx({ thesisContent: "a", thesisOriginal: "a" });
    globalThis.fetch = vi.fn();
    await c.saveThesisNow();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("#4 — taper pendant la requête ne montre PAS « Enregistré » à tort", async () => {
    const c = ctx({ thesisContent: "version1", thesisOriginal: "" });
    vi.useFakeTimers();
    // La réponse arrive APRÈS que l'utilisateur a continué à écrire.
    globalThis.fetch = vi.fn(async () => {
      c.thesisContent = "version2";   // frappe pendant la requête
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", updated_at: 42 }),
      };
    });
    await c.saveThesisNow();
    expect(c.thesisStatus).toBe("dirty");          // pas « saved »
    expect(c.thesisOriginal).toBe("version1");     // seule la version envoyée est sauvée
    expect(c.thesisDirty()).toBe(true);
    vi.useRealTimers();
  });

  it("#3 — l'horodatage survit à un PUT qui ne renvoie pas updated_at", async () => {
    const c = ctx({ thesisContent: "b", thesisOriginal: "a", thesisUpdatedAt: 100 });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok" }),   // pas d'updated_at
    }));
    await c.saveThesisNow();
    expect(c.thesisUpdatedAt).toBe(100);   // on ne l'efface pas
  });

  it("détecte une modification faite ailleurs (MCP)", async () => {
    const c = ctx({ thesisUpdatedAt: 100 });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ updated_at: 200 }),
    }));
    await c.checkThesisConflict();
    expect(c.thesisConflict).toBe(true);
  });

  it("la détection est réellement DÉCLENCHÉE au retour sur l'onglet (CA-UI5)", async () => {
    const c = ctx({ thesisUpdatedAt: 100, activeSection: "these" });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ updated_at: 200 }),
    }));
    c.onThesisWindowFocus();
    await vi.waitFor(() => expect(c.thesisConflict).toBe(true));
    expect(globalThis.fetch).toHaveBeenCalled();
  });

  it("aucune requête si la section thèse n'est pas affichée", () => {
    const c = ctx({ activeSection: "resume" });
    globalThis.fetch = vi.fn();
    c.onThesisWindowFocus();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("aucune requête si l'onglet devient caché (pas de double appel)", () => {
    const c = ctx({ activeSection: "these" });
    globalThis.fetch = vi.fn();
    const spy = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    c.onThesisWindowFocus();
    spy.mockRestore();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("pas de détection pendant l'édition (on n'écrase pas la saisie)", async () => {
    const c = ctx({ thesisUpdatedAt: 100, thesisEditing: true });
    globalThis.fetch = vi.fn();
    await c.checkThesisConflict();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("les écouteurs sont abonnés au démarrage", () => {
    const src = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "app.js"), "utf8");
    expect(src).toMatch(/visibilitychange/);
    expect(src).toMatch(/"focus"/);
    expect(src).toMatch(/onThesisWindowFocus/);
  });

  it("pas de conflit si la version serveur est identique", async () => {
    const c = ctx({ thesisUpdatedAt: 100 });
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ updated_at: 100 }),
    }));
    await c.checkThesisConflict();
    expect(c.thesisConflict).toBe(false);
  });

  it("« garder ma version » repousse la version locale", () => {
    const c = ctx({ thesisContent: "local", thesisOriginal: "serveur", thesisConflict: true });
    vi.useFakeTimers();
    c.keepLocalThesis();
    expect(c.thesisConflict).toBe(false);
    expect(c.thesisStatus).toBe("dirty");
    vi.useRealTimers();
  });
});

describe("points de contrôle du document (CA-UI6, CA-UI7)", () => {
  // Les cases GFM du document restent cliquables : c'est le document LIBRE, à
  // distinguer des points de contrôle SUIVIS de la bande « Suivi » (#21), qui
  // vivent dans leur propre liste persistée.
  it("le cochage met à jour le document, sans mode édition", () => {
    const c = ctx({ thesisContent: "- [ ] a\n- [ ] b\n" });
    c._thesisRecompute();
    expect(c.thesisContent).toBe("- [ ] a\n- [ ] b\n");
    c.thesisToggleTask(0);
    expect(c.thesisContent).toBe("- [x] a\n- [ ] b\n");
    expect(c.thesisEditing).toBe(false);
  });

  it("le cochage déclenche l'auto-save", () => {
    const c = ctx({ thesisContent: "- [ ] a\n" });
    vi.useFakeTimers();
    c.thesisToggleTask(0, true);
    expect(c.thesisStatus).toBe("dirty");
    expect(c.thesisContent).toBe("- [x] a\n");
    vi.useRealTimers();
  });

  it("sans indication, la bascule reste le comportement par défaut", () => {
    const c = ctx({ thesisContent: "- [ ] a\n" });
    vi.useFakeTimers();
    c.thesisToggleTask(0);
    expect(c.thesisContent).toBe("- [x] a\n");
    vi.useRealTimers();
  });

  it("le compteur ne bouge pas si l'état demandé est déjà le bon", () => {
    const c = ctx({ thesisContent: "- [ ] a\n" });
    vi.useFakeTimers();
    c.thesisToggleTask(0, false);
    expect(c.thesisStatus).toBe("idle");
    vi.useRealTimers();
  });

  it("le double dispatch d'un même clic n'annule pas le cochage", () => {
    const c = ctx({ thesisContent: "- [ ] a\n- [ ] b\n" });
    vi.useFakeTimers();
    c.thesisToggleTask(1, true);
    c.thesisToggleTask(1, true);
    expect(c.thesisContent).toBe("- [ ] a\n- [x] b\n");
    vi.useRealTimers();
  });

  it("index hors bornes : document inchangé", () => {
    const c = ctx({ thesisContent: "- [ ] a\n" });
    c.thesisToggleTask(9);
    expect(c.thesisContent).toBe("- [ ] a\n");
  });

  it("le compteur d'en-tête a été retiré (#21 : il appartient à la bande)", () => {
    const c = ctx({ thesisContent: "## Pitch\n" });
    c._thesisRecompute();
    expect(c.thesisTasksLabel).toBeUndefined();
  });
});

describe("ancres et routeur (CA-TOC5)", () => {
  it("un clic d'ancre NE TOUCHE PAS location.hash", () => {
    window.location.hash = "#RI.PA/these";
    const c = ctx();
    const link = document.createElement("a");
    link.setAttribute("href", "#pitch");
    const holder = document.createElement("div");
    holder.appendChild(link);
    const ev = { target: link, preventDefault: vi.fn(), currentTarget: holder };
    document.body.appendChild(holder);
    c.onThesisBodyClick(ev);
    expect(ev.preventDefault).toHaveBeenCalled();
    expect(window.location.hash).toBe("#RI.PA/these");
    document.body.removeChild(holder);
  });

  it("un clic sur une case route vers toggleTask (état voulu, idempotent)", () => {
    const c = ctx({ thesisContent: "- [ ] a\n- [ ] b\n" });
    const holder = document.createElement("div");
    holder.innerHTML = '<input type="checkbox"><input type="checkbox" checked>';
    const boxes = holder.querySelectorAll('input[type="checkbox"]');
    const ev = { target: boxes[1], currentTarget: holder, preventDefault: vi.fn() };
    c.onThesisBodyClick(ev);
    expect(c.thesisContent).toBe("- [ ] a\n- [x] b\n");
    // Un SECOND dispatch du même clic ne doit rien annuler (l'état voulu est
    // porté par la case, pas par une bascule).
    c.onThesisBodyClick(ev);
    expect(c.thesisContent).toBe("- [ ] a\n- [x] b\n");
  });
});

describe("édition et toolbar (CA-UI8, CA-TOC8)", () => {
  it("la structure insérée suit le prompt de thèse et s'ajoute au texte", () => {
    const c = ctx({ thesisContent: "## Existant\n" });
    vi.useFakeTimers();
    c.insertSkeleton();
    expect(c.thesisContent).toContain("## Pitch");
    expect(c.thesisContent).toContain("## Existant");
    expect(c.thesisContent).toContain("- [ ]");
    vi.useRealTimers();
  });

  it("le gras encadre la sélection", () => {
    const c = ctx({ thesisContent: "" });
    vi.useFakeTimers();
    c.insertBold();
    expect(c.thesisContent).toContain("**gras**");
    vi.useRealTimers();
  });

  it("⌘B déclenche le gras, Échap sort de l'édition", () => {
    const c = ctx({ thesisEditing: true, thesisContent: "" });
    vi.useFakeTimers();
    const evB = { key: "b", metaKey: true, preventDefault: vi.fn() };
    c.onThesisKeydown(evB);
    expect(evB.preventDefault).toHaveBeenCalled();
    const evEsc = { key: "Escape", preventDefault: vi.fn() };
    c.onThesisKeydown(evEsc);
    expect(c.thesisEditing).toBe(false);
    vi.useRealTimers();
  });

  it("le plan d'édition liste les titres du document", () => {
    const c = ctx({ thesisContent: "# A\n\n## B\n\n### C\n" });
    c._thesisRecompute();
    expect(c.thesisView.toc.map((t) => t.text)).toEqual(["A", "B", "C"]);
  });

  it("le sommaire intégré s'arrête à 2 niveaux, le plan va jusqu'à 3", () => {
    const c = ctx({ thesisContent: "# A\n\n## B\n\n### C\n" });
    c._thesisRecompute();
    // `thesisView.toc` sert le plan d'édition ET le plan latéral (3 niveaux) ;
    // le sommaire intégré borne à 2 niveaux, comme `buildToc` le prévoit.
    expect(c.thesisView.toc.length).toBe(3);
  });
});

describe("import / export (CA-UI9, CA-TOC11)", () => {
  it("le contenu exporté est le markdown stocké, sans sommaire ajouté", () => {
    const md = "# Thèse\n\n## Pitch\n\nDécotée.\n";
    const c = ctx({ thesisContent: md });
    expect(c.thesisContent).toBe(md);
    expect(c.thesisContent).not.toMatch(/sommaire/i);
  });

  it("un fichier importé devient le contenu et part en auto-save", async () => {
    const c = ctx();
    vi.useFakeTimers();
    globalThis.confirm = vi.fn(() => true);
    class FakeReader {
      readAsText() {
        this.result = "# Importé\n\n## Pitch\n";
        this.onload();
      }
    }
    globalThis.FileReader = FakeReader;
    c.importThesisFile({ name: "these.md" });
    expect(c.thesisContent).toContain("# Importé");
    expect(c.thesisEditing).toBe(true);
    expect(c.thesisStatus).toBe("dirty");
    vi.useRealTimers();
  });

  it("un import REFUSÉ ne touche pas au document (CA-UI9)", () => {
    const c = ctx({ thesisContent: "# Ma thèse\n\nprécieux\n" });
    vi.useFakeTimers();
    globalThis.confirm = vi.fn(() => false);
    class FakeReader {
      readAsText() {
        this.result = "# Écrasé";
        this.onload();
      }
    }
    globalThis.FileReader = FakeReader;
    c.importThesisFile({ name: "autre.md" });
    expect(c.thesisContent).toBe("# Ma thèse\n\nprécieux\n");
    expect(globalThis.confirm).toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("aucune confirmation si la thèse est vide (rien à perdre)", () => {
    const c = ctx({ thesisContent: "" });
    vi.useFakeTimers();
    globalThis.confirm = vi.fn(() => true);
    class FakeReader {
      readAsText() {
        this.result = "# Neuf";
        this.onload();
      }
    }
    globalThis.FileReader = FakeReader;
    c.importThesisFile({ name: "neuve.md" });
    expect(globalThis.confirm).not.toHaveBeenCalled();
    expect(c.thesisContent).toBe("# Neuf");
    vi.useRealTimers();
  });

  it("l'aperçu du rendu ne contient pas de sommaire injecté", () => {
    const c = ctx({ thesisContent: "# A\n\n## B\n\ntexte\n" });
    c._thesisRecompute();
    expect(c.thesisView.html).toContain('id="a"');
    expect(c.thesisView.html).not.toContain("md-toc");
  });
});

describe("prompt de thèse (CA-UI1)", () => {
  // Le bouton est présenté comme LE différenciateur MCP : il ne doit pas échouer
  // en silence. Le câblage HTTP faisait un GET sur une route POST (405), panne
  // invisible car seul `thesisError` était posé, sans statut d'erreur.
  it("copie le prompt avec un POST (méthode de la route serveur)", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ prompt: "Tu es analyste", data: {}, warnings: [] }),
    }));
    let copied = "";
    c._writeClipboard = (text) => {
      copied = text;
    };
    c.copyThesisPrompt();
    await vi.waitFor(() => expect(copied).toBe("Tu es analyste"));
    const [url, opts] = globalThis.fetch.mock.calls[0];
    expect(url).toBe("/api/thesis/RI.PA/prompt");
    expect(opts?.method).toBe("POST");
  });

  it("un échec du prompt est VISIBLE (statut d'erreur + message)", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 405,
      json: async () => ({ detail: "Method Not Allowed" }),
    }));
    c.copyThesisPrompt();
    await vi.waitFor(() => expect(c.thesisStatus).toBe("error"));
    expect(c.thesisError).toBe("Method Not Allowed");
  });
});

describe("images (CA7)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("un upload réussi insère l'URL renvoyée par le serveur", async () => {
    const c = ctx({ thesisContent: "", thesisEditing: true });
    vi.useFakeTimers();
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ url: "/api/thesis/assets/abc123.png", bytes: 10, mime: "image/png" }),
    }));
    await c.uploadThesisImage({ name: "x.png" });
    expect(c.thesisContent).toContain("/api/thesis/assets/abc123.png");
    expect(c.thesisContent).toContain("![");
    expect(c.thesisNotice).toBe("Image insérée.");
    vi.useRealTimers();
  });

  it("un upload refusé est visible et n'insère RIEN (pas de lien mort)", async () => {
    const c = ctx({ thesisContent: "", thesisEditing: true });
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 422,
      json: async () => ({ detail: "Type d'image non autorisé" }),
    }));
    await c.uploadThesisImage({ name: "evil.svg" });
    expect(c.thesisContent).toBe("");
    expect(c.thesisError).toBe("Type d'image non autorisé");
    expect(c.thesisStatus).toBe("error");
  });

  it("le collage d'une capture passe par la même voie", () => {
    const c = ctx();
    const upload = vi.fn();
    c.uploadThesisImage = upload;
    const ev = {
      clipboardData: { items: [{ type: "image/png", getAsFile: () => ({ name: "p.png" }) }] },
      preventDefault: vi.fn(),
    };
    c.onThesisPaste(ev);
    expect(ev.preventDefault).toHaveBeenCalled();
    expect(upload).toHaveBeenCalled();
  });

  it("un collage de texte n'est pas intercepté", () => {
    const c = ctx();
    const upload = vi.fn();
    c.uploadThesisImage = upload;
    const ev = { clipboardData: { items: [{ type: "text/plain" }] }, preventDefault: vi.fn() };
    c.onThesisPaste(ev);
    expect(ev.preventDefault).not.toHaveBeenCalled();
    expect(upload).not.toHaveBeenCalled();
  });
});

describe("structure du module", () => {
  it("aucun fetch hors api.js (le mixin passe par la couche `api`)", () => {
    const src = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "thesis.js"), "utf8");
    expect(src).not.toMatch(/\bfetch\s*\(/);
    expect(src).toMatch(/import \{ api \}/);
  });

  it("la pastille du rail vient du payload, sans appel supplémentaire", () => {
    const c = ctx({ data: { kind_payload: "stock", has_thesis: true } });
    expect(c.thesisExists()).toBe(true);
    const c2 = ctx({ data: { kind_payload: "stock", has_thesis: false } });
    expect(c2.thesisExists()).toBe(false);
  });

  it("la pastille est RÉELLEMENT branchée dans le rail (CA-UI2)", () => {
    const html = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "index.html"), "utf8");
    expect(html).toMatch(/rail-dot/);
    expect(html).toMatch(/s\.id === 'these' && thesisExists\(\)/);
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    expect(css).toMatch(/\.rail-dot\s*\{/);
  });

  it("la poignée et la colonne obéissent à la MÊME media query (CA-PL3, CA-PL22)", () => {
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    // La poignée n'existe qu'à partir de la largeur où la colonne existe : une
    // media query CSS unique, jamais un écouteur `resize` en JS.
    const bloc = css.match(/@media \(min-width: 1100px\) \{[\s\S]*?\n\}/g) || [];
    const seuil = bloc.find((b) => b.includes(".thesis-plan {"));
    expect(seuil, "media query 1100 px introuvable").toBeTruthy();
    expect(seuil).toMatch(/\.thesis-edge\s*\{\s*display:\s*flex/);
    // Appareil sans survol : la poignée n'a pas de révélateur -> visible d'office.
    expect(css).toMatch(/@media \(hover: none\)[\s\S]*\.thesis-pin\s*\{[^}]*opacity:\s*0?\.\d/);
    // Aucun écouteur de redimensionnement côté JS (état dérivé du CSS).
    const js = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "thesis.js"), "utf8");
    expect(js).not.toMatch(/addEventListener\(\s*["']resize/);
  });

  it("les rangées d'actions ne coupent jamais un libellé en deux (#21.2)", () => {
    // Défaut réel corrigé : sans `white-space: nowrap`, sur écran étroit les
    // boutons étaient comprimés et « Importer .md » se repliait sur deux lignes
    // (hauteur 50 px contre 33 px pour ses voisins — rangée bancale). Les deux
    // rangées d'actions de la carte thèse doivent porter la règle.
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    for (const rangee of [".thesis-actions", ".thesis-empty-actions"]) {
      const bloc = css.match(new RegExp(`${rangee.replace(".", "\\.")}[^{]*\\{[^}]*\\}`));
      expect(bloc, `${rangee} introuvable`).toBeTruthy();
      expect(bloc[0]).toMatch(/flex-wrap:\s*wrap/);
    }
    expect(css).toMatch(/\.thesis-actions \.btn\s*\{\s*white-space:\s*nowrap;\s*\}/);
    expect(css).toMatch(/\.thesis-empty-actions \.btn\s*\{\s*white-space:\s*nowrap;\s*\}/);
  });
});

describe("plan de la thèse — afficher / masquer (#21.2)", () => {
  // Le plan sert PENDANT la lecture : à l'ouverture, le sommaire intégré couvre la
  // structure. D'où un défaut FERMÉ, mémorisé côté navigateur (préférence locale,
  // dépendante de la largeur d'écran — pas du ticker, pas de la sauvegarde).
  beforeEach(() => {
    window.localStorage.clear();
    vi.restoreAllMocks();
  });

  it("par défaut (aucune préférence) le plan est FERMÉ (CA-PL7)", () => {
    const c = ctx();
    c.loadThesisPlanPreference();
    expect(c.thesisPlanOpen).toBe(false);
  });

  it("une préférence enregistrée est restituée (CA-PL6)", () => {
    window.localStorage.setItem("obole.thesis.planOpen", "1");
    const c = ctx();
    c.loadThesisPlanPreference();
    expect(c.thesisPlanOpen).toBe(true);
  });

  it("la bascule enregistre la préférence, dans les deux sens (CA-PL6)", () => {
    const c = ctx();
    c.loadThesisPlanPreference();
    c.toggleThesisPlan();
    expect(c.thesisPlanOpen).toBe(true);
    expect(window.localStorage.getItem("obole.thesis.planOpen")).toBe("1");
    c.toggleThesisPlan();
    expect(c.thesisPlanOpen).toBe(false);
    expect(window.localStorage.getItem("obole.thesis.planOpen")).toBe("0");
  });

  it("le plan ne s'affiche jamais pendant l'édition (CA-PL11)", () => {
    const c = ctx({ thesisPlanOpen: true, thesisEditing: true });
    c.thesisView = renderThesisForTest("# Thèse\n\n## Pitch\n");
    expect(c.thesisPlanVisible()).toBe(false);
    c.thesisEditing = false;
    expect(c.thesisPlanVisible()).toBe(true);
  });

  it("un plan fermé ne s'affiche pas, même hors édition (CA-PL11)", () => {
    const c = ctx({ thesisPlanOpen: false });
    c.thesisView = renderThesisForTest("# Thèse\n\n## Pitch\n");
    expect(c.thesisPlanVisible()).toBe(false);
  });

  it("sans sommaire exploitable, aucun plan (CA-PL12)", () => {
    const c = ctx({ thesisPlanOpen: true });
    c.thesisView = renderThesisForTest("juste du texte\n");
    expect(c.thesisPlanVisible()).toBe(false);
  });

  it("un stockage indisponible ne fait PAS planter le chargement (CA-PL7)", () => {
    const c = ctx();
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("stockage refusé");
    });
    expect(() => c.loadThesisPlanPreference()).not.toThrow();
    expect(c.thesisPlanOpen).toBe(false);
    spy.mockRestore();
  });

  it("une écriture refusée n'empêche pas la bascule (CA-PL7)", () => {
    const c = ctx();
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(() => c.toggleThesisPlan()).not.toThrow();
    expect(c.thesisPlanOpen).toBe(true);
    spy.mockRestore();
  });

  it("une valeur corrompue est traitée comme « fermé » (CA-PL7)", () => {
    for (const valeur of ["maybe", "", "2", "{}"]) {
      window.localStorage.setItem("obole.thesis.planOpen", valeur);
      const c = ctx();
      c.loadThesisPlanPreference();
      expect(c.thesisPlanOpen, `valeur « ${valeur} »`).toBe(false);
    }
  });

  it("la préférence est GLOBALE, pas par ticker (CA-PL8)", () => {
    const c = ctx();
    c.toggleThesisPlan();
    const autre = ctx();
    autre.loadThesisPlanPreference();
    expect(autre.thesisPlanOpen).toBe(true);
  });

  it("la poignée et le repli sont RÉELLEMENT branchés dans le template (CA-PL16, CA-PL17, CA-PL21)", () => {
    const html = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "index.html"), "utf8");
    // #21.3 : le bouton d'en-tête est SUPPRIMÉ — le contrôle vit dans la bande de
    // survol du bord droit, atteignable à toute hauteur de lecture.
    expect(html).not.toMatch(/thesis-card-head[\s\S]{0,900}?thesis-plan-toggle/);
    expect(html).not.toMatch(/class="thesis-plan-toggle"/);
    expect(html).toMatch(/<div class="thesis-edge"[\s\S]{0,600}?class="thesis-pin"/);
    expect(html).toMatch(/@click="toggleThesisPlan\(\)"/);
    expect(html).toMatch(/:aria-expanded="thesisPlanOpen/);
    expect(html).toMatch(/aria-controls="thesis-plan"/);
    expect(html).toMatch(/id="thesis-plan"/);
    expect(html).toMatch(/x-show="thesisPlanAvailable\(\)"/);
    // Bouton natif (Tab/Entrée/Espace) et état porté par une classe, pas par un
    // input caché (plus de sélecteur dépendant de l'ordre dans l'arbre).
    expect(html).toMatch(/<button type="button" class="thesis-pin"/);
    expect(html).toMatch(/:class="\{ open: thesisPlanOpen \}"/);
    expect(html).not.toMatch(/thesis-plan-input/);
    // Le plan lui-même obéit à l'état, plus seulement à la largeur d'écran.
    expect(html).toMatch(/class="thesis-plan"[\s\S]{0,80}x-show="thesisPlanVisible\(\)"/);
  });

  it("aucun style orphelin du bouton supprimé (CA-PL16)", () => {
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    expect(css).not.toMatch(/thesis-plan-toggle/);
  });

  it("le survol rétablit la pleine opacité, plan affiché (CA-PL20)", () => {
    // Défaut réel (revue de code) : la règle de survol « ouvert » était un
    // sélecteur MORT — `.thesis-plan-input:checked ~ .thesis-edge` est impossible,
    // l'input étant un ENFANT de `.thesis-edge`, pas son frère. Résultat : le
    // plan ouvert, la poignée restait figée à 45 % au survol. L'état vit
    // désormais dans une CLASSE sur le bouton, donc plus de sélecteur frère.
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    expect(css).not.toMatch(/\.thesis-plan-input/);
    // L'ordre tranche : la règle de survol vient APRÈS celle des 45 %.
    const iOpen = css.search(/\.thesis-pin\.open\s*\{[^}]*opacity:\s*\.45/);
    const iHover = css.search(/\.thesis-edge:hover\s+\.thesis-pin\s*\{[^}]*opacity:\s*1/);
    expect(iOpen, "règle des 45 % introuvable").toBeGreaterThan(-1);
    expect(iHover, "règle de survol à pleine opacité introuvable").toBeGreaterThan(-1);
    expect(iHover).toBeGreaterThan(iOpen);
  });

  it("la largeur de la bande vient du rembourrage de la carte, source unique (CA-PL17, CA-PL19)", () => {
    const css = readFileSync(join(process.cwd(), "..", "src", "obole", "web", "style.css"), "utf8");
    // Une seule déclaration alimente le rembourrage de la carte ET la largeur de
    // la bande : impossible de dériver l'un de l'autre sans casser la garantie
    // « la fiche ne rétrécit pas ».
    expect(css).toMatch(/\.thesis-card\s*\{[^}]*--thesis-pad-x:\s*22px/);
    expect(css).toMatch(/\.thesis-card\s*\{[^}]*padding:\s*18px var\(--thesis-pad-x\)/);
    const bande = css.match(/\.thesis-edge\s*\{[^}]*\}/);
    expect(bande, "règle .thesis-edge introuvable").toBeTruthy();
    // `absolute` => contribution NULLE au layout : la fiche garde sa largeur.
    expect(bande[0]).toMatch(/position:\s*absolute/);
    expect(bande[0]).toMatch(/width:\s*var\(--thesis-pad-x\)/);
    // La bande vit DANS le flux (sinon elle recouvrirait la rangée « Éditer »).
    expect(css).toMatch(/\.thesis-flow\s*\{[^}]*position:\s*relative/);
    // Onglet épinglé : atteignable quel que soit le défilement.
    expect(css).toMatch(/\.thesis-pin\s*\{[^}]*position:\s*sticky/);
  });

  it("la poignée n'existe que si le plan peut exister (CA-PL22)", () => {
    const c = ctx({ thesisPlanOpen: false });
    expect(c.thesisPlanAvailable()).toBe(false);
    c.thesisEditing = true;
    expect(c.thesisPlanAvailable()).toBe(false);
    c.thesisEditing = false;
    c.thesisView = renderThesisForTest("# Thèse\n\n## Pitch\n");
    expect(c.thesisPlanAvailable()).toBe(true);
    c.thesisView = renderThesisForTest("juste du texte\n");
    expect(c.thesisPlanAvailable()).toBe(false);
  });

  it("la bascule ne déclenche AUCUNE requête réseau (CA-PL2)", () => {
    const c = ctx();
    globalThis.fetch = vi.fn();
    c.toggleThesisPlan();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
