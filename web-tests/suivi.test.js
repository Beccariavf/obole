// Bande « Suivi » (#21) — mixin `web/suivi.js`, sans réseau.
//
// Le mixin est un objet plat, comme les autres domaines : on teste le
// COMPORTEMENT (échéance, compteur, mutations) en stubant `fetch`, jamais en
// rendant Alpine. `thesisEditing` est fourni par `thesis.js` (dépendance
// inter-mixins assumée : ils sont fusionnés dans le même composant).

import { beforeEach, describe, expect, it, vi } from "vitest";

const { checkpointsMixin } = await import("../src/obole/web/suivi.js");

// Réponse JSON minimale, comme `api.js` la consomme.
const reply = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

function ctx(over = {}) {
  const c = {
    ...checkpointsMixin,
    kind_payload: "stock",
    thesisEditing: false,
    data: {
      kind_payload: "stock",
      identity: { ticker: "RI.PA", name: "Pernod Ricard" },
      profile: {
        next_earnings: "2026-11-26",
        next_earnings_estimated: false,
        ex_dividend: "2027-11-25",
      },
    },
  };
  return Object.assign(c, over);
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("échéance (CA-B1, CA-B2)", () => {
  it("donne la date absolue et le compte à rebours", () => {
    const c = ctx();
    const e = c.cpEarnings();
    expect(e.date).toContain("2026");
    expect(e.relative).toMatch(/dans \d+ j/);
    expect(e.estimated).toBe(false);
    expect(e.after).toBe("");
  });

  it("une date passée devient « publié » sans compte à rebours", () => {
    const c = ctx({
      data: {
        kind_payload: "stock",
        identity: { ticker: "RI.PA" },
        profile: { next_earnings: "2020-01-01" },
      },
    });
    const e = c.cpEarnings();
    expect(e.after).toBe("publié");
    expect(e.relative).toBe("");
  });

  it("le caractère estimé est exposé", () => {
    const c = ctx({
      data: {
        kind_payload: "stock",
        identity: { ticker: "RI.PA" },
        profile: { next_earnings: "2099-01-01", next_earnings_estimated: true },
      },
    });
    expect(c.cpEarnings().estimated).toBe(true);
  });

  it("sans date connue, aucune ligne (pas de crash)", () => {
    const c = ctx({
      data: { kind_payload: "stock", identity: { ticker: "X" }, profile: {} },
    });
    expect(c.cpEarnings()).toBeNull();
  });
});

describe("visibilité de la bande (CA-B4, CA-B5)", () => {
  it("visible pour une action, même sans thèse", () => {
    expect(ctx().cpVisible()).toBe(true);
  });

  it("invisible pour un ratio ou un indice", () => {
    expect(ctx({ data: { kind_payload: "ratio" } }).cpVisible()).toBe(false);
    expect(ctx({ data: { kind_payload: "basket" } }).cpVisible()).toBe(false);
  });

  it("aucune donnée chargée -> fiche vide, pas une erreur", () => {
    expect(ctx({ data: null }).cpVisible()).toBeFalsy();
  });
});

describe("compteur (CA-B3, CA-D5, CA-D6, CA-D7)", () => {
  it("dérive le label du nombre de points cochés", () => {
    const c = ctx({ cpItems: [{ id: 1, done: true }, { id: 2, done: false }] });
    expect(c.cpLabel()).toBe("1/2");
    expect(c.cpProgress()).toBe(50);
  });

  it("aucun point -> label vide (pas « 0/0 »)", () => {
    const c = ctx({ cpItems: [] });
    expect(c.cpLabel()).toBe("");
    expect(c.cpProgress()).toBe(0);
  });

  // #21.4 : à 1 point, la barre vide n'exprime RIEN — elle se lit comme un filet
  // de séparation. Elle n'apparaît qu'à partir de 2 points.
  it("la barre n'apparaît qu'à partir de 2 points (CA-D5)", () => {
    expect(ctx({ cpItems: [] }).cpBarVisible()).toBe(false);
    expect(ctx({ cpItems: [{ id: 1, done: false }] }).cpBarVisible()).toBe(false);
    expect(ctx({ cpItems: [{ id: 1, done: true }, { id: 2, done: false }] }).cpBarVisible()).toBe(true);
  });

  // #21.4 : le compteur est le SEUL reste de la ligne « points de contrôle » —
  // il doit encore dire ce qu'il compte (le libellé visible a disparu).
  it("le compteur porte un intitulé accessible (CA-D7)", () => {
    const zero = ctx({ cpItems: [{ id: 1, done: false }, { id: 2, done: false }] });
    expect(zero.cpLabelTitle()).toBe("0 point validé sur 2 points de contrôle");
    const un = ctx({ cpItems: [{ id: 1, done: true }, { id: 2, done: false }] });
    expect(un.cpLabelTitle()).toBe("1 point validé sur 2 points de contrôle");
    const deux = ctx({ cpItems: [{ id: 1, done: true }, { id: 2, done: true }] });
    expect(deux.cpLabelTitle()).toBe("2 points validés sur 2 points de contrôle");
    // Sans point suivi : rien à annoncer.
    expect(ctx({ cpItems: [] }).cpLabelTitle()).toBe("");
  });

  // Défaut réel (revue) : les deux accords étaient liés à la même variable, d'où
  // « 1 point validé sur 1 points de contrôle ».
  it("l'intitulé accorde séparément « validé » et « point de contrôle » (CA-D7)", () => {
    const un = ctx({ cpItems: [{ id: 1, done: true }] });
    expect(un.cpLabelTitle()).toBe("1 point validé sur 1 point de contrôle");
    const zeroSurUn = ctx({ cpItems: [{ id: 1, done: false }] });
    expect(zeroSurUn.cpLabelTitle()).toBe("0 point validé sur 1 point de contrôle");
  });

  it("le compteur est neutre à 0 coché, en accent dès le premier (CA-D6)", () => {
    expect(ctx({ cpItems: [{ id: 1, done: false }] }).cpHasDone()).toBe(false);
    expect(ctx({ cpItems: [{ id: 1, done: true }] }).cpHasDone()).toBe(true);
    expect(ctx({ cpItems: [] }).cpHasDone()).toBe(false);
  });

  it("la liste est masquée en mode édition (une seule surface d'écriture)", () => {
    const loaded = { cpLoaded: true, thesisEditing: false };
    expect(ctx(loaded).cpListVisible()).toBe(true);
    expect(ctx({ ...loaded, thesisEditing: true }).cpListVisible()).toBe(false);
    expect(ctx({ cpLoaded: false }).cpListVisible()).toBe(false);
  });
});

describe("chargement (CA-CK5, CA-CK6)", () => {
  it("charge la liste du ticker courant", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () =>
      reply(200, [{ id: 7, label: "Marge", done: false }]),
    );
    await c.loadCheckpoints();
    expect(c.cpItems).toEqual([{ id: 7, label: "Marge", done: false }]);
    expect(c.cpTicker).toBe("RI.PA");
    expect(c.cpLoaded).toBe(true);
    expect(c.cpError).toBe("");
  });

  it("une erreur réseau est visible, jamais avalée", async () => {
    const c = ctx();
    globalThis.fetch = vi.fn(async () => reply(500, { detail: "Boom" }));
    await c.loadCheckpoints();
    expect(c.cpError).toBe("Boom");
    expect(c.cpItems).toEqual([]);
  });

  it("ne charge rien hors d'une action", async () => {
    const c = ctx({ data: { kind_payload: "ratio" } });
    globalThis.fetch = vi.fn();
    await c.loadCheckpoints();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("le reset remet l'état à zéro (fuite inter-fiches)", () => {
    const c = ctx({ cpItems: [{ id: 1, done: true }], cpTicker: "RI.PA", cpLoaded: true });
    c.resetCheckpoints();
    expect(c.cpItems).toEqual([]);
    expect(c.cpTicker).toBe(null);
    expect(c.cpLoaded).toBe(false);
  });

  it("changer de ticker repart d'une liste vide", async () => {
    const c = ctx({ cpItems: [{ id: 1, done: true }], cpTicker: "RI.PA", cpLoaded: true });
    c.data.identity.ticker = "AI.PA";
    globalThis.fetch = vi.fn(async () => reply(200, []));
    await c.loadCheckpoints();
    expect(c.cpItems).toEqual([]);
    expect(c.cpTicker).toBe("AI.PA");
  });
});

describe("mutations (CA-CK1, CA-CK2, CA-CK4)", () => {
  it("ajoute un point puis recharge la liste", async () => {
    const c = ctx({ cpDraft: "  Marge > 28%  " });
    const calls = [];
    globalThis.fetch = vi.fn(async (url, opts) => {
      calls.push({ url, method: opts?.method, body: opts?.body });
      if (opts?.method === "POST") return reply(200, { status: "ok", id: 1 });
      return reply(200, [{ id: 1, label: "Marge > 28%", done: false }]);
    });
    await c.cpAdd();
    expect(c.cpDraft).toBe("");
    expect(c.cpItems).toEqual([{ id: 1, label: "Marge > 28%", done: false }]);
    // Le libellé est trimé AVANT l'envoi.
    expect(JSON.parse(calls[0].body)).toEqual({ label: "Marge > 28%" });
  });

  it("n'envoie rien pour un libellé vide ou blanc", async () => {
    for (const draft of ["", "   "]) {
      const c = ctx({ cpDraft: draft });
      globalThis.fetch = vi.fn();
      await c.cpAdd();
      expect(globalThis.fetch).not.toHaveBeenCalled();
    }
  });

  it("un ajout refusé n'est pas silencieux", async () => {
    const c = ctx({ cpDraft: "x" });
    globalThis.fetch = vi.fn(async () => reply(422, { detail: "Libellé trop long" }));
    await c.cpAdd();
    expect(c.cpError).toBe("Libellé trop long");
    expect(c.cpDraft).toBe("x");
  });

  it("le cochage est optimiste puis confirmé", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(200, { status: "ok", id: 1 }));
    await c.cpToggle(item, true);
    expect(item.done).toBe(true);
    expect(c.cpError).toBe("");
  });

  it("un cochage refusé revient à l'état précédent et le dit", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(500, { detail: "Échec serveur" }));
    await c.cpToggle(item, true);
    expect(item.done).toBe(false);
    expect(c.cpError).toBe("Échec serveur");
  });

  it("sans indication, la bascule inverse l'état courant", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(200, { status: "ok", id: 1 }));
    await c.cpToggle(item);
    expect(item.done).toBe(true);
  });

  it("un état déjà voulu ne déclenche aucune requête", async () => {
    const item = { id: 1, label: "A", done: true };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn();
    await c.cpToggle(item, true);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("les mutations sont sérialisées (pas de PUT concurrents)", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item], cpBusy: true });
    globalThis.fetch = vi.fn();
    await c.cpToggle(item, true);
    expect(globalThis.fetch).not.toHaveBeenCalled();
    expect(item.done).toBe(false);
  });

  it("supprime un point de la liste", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(200, { status: "deleted", id: 1 }));
    await c.cpRemove(item);
    expect(c.cpItems).toEqual([]);
  });

  it("un 404 à la suppression retire quand même la ligne (déjà absente)", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(404, { detail: "inconnu" }));
    await c.cpRemove(item);
    expect(c.cpItems).toEqual([]);
    expect(c.cpError).toBe("");
  });

  it("une suppression refusée conserve la ligne et l'annonce", async () => {
    const item = { id: 1, label: "A", done: false };
    const c = ctx({ cpItems: [item] });
    globalThis.fetch = vi.fn(async () => reply(500, { detail: "Boom" }));
    await c.cpRemove(item);
    expect(c.cpItems).toEqual([item]);
    expect(c.cpError).toBe("Boom");
  });

  it("la soumission du formulaire n'ajoute qu'une fois", async () => {
    const c = ctx({ cpDraft: "A" });
    let posts = 0;
    globalThis.fetch = vi.fn(async (url, opts) => {
      if (opts?.method === "POST") posts += 1;
      return opts?.method === "POST" ? reply(200, { id: 1 }) : reply(200, []);
    });
    const ev = { preventDefault: vi.fn() };
    c.cpSubmit(ev);
    await vi.waitFor(() => expect(posts).toBe(1));
    expect(ev.preventDefault).toHaveBeenCalled();
  });
});
