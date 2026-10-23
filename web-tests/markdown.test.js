// Sommaire & plan de la thèse (#21) — module `web/markdown.js`, sans réseau.
//
// `marked` et `DOMPurify` sont vendorisés dans le vrai front : les tests les
// chargent depuis `src/obole/web/vendor/` avant d'importer le module, exactement
// comme `index.html` le fait (scripts globaux + module).

import { beforeAll, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// jsdom réécrit `import.meta.url` en URL http : on résout depuis le cwd (vitest
// tourne dans `web-tests/`), même convention que `vitest.config.js`.
const VENDOR = join(process.cwd(), "..", "src", "obole", "web", "vendor");

beforeAll(() => {
  // Exécute les libs vendorisées dans le contexte jsdom : elles y posent
  // `window.marked` et `window.DOMPurify` (même mécanique qu'au navigateur).
  // jsdom n'exécute pas les scripts ajoutés après coup : on passe par `window.eval`.
  for (const file of ["marked.min.js", "dompurify.min.js"]) {
    const src = readFileSync(join(VENDOR, file), "utf8");
    window.eval(src);
  }
});

const {
  slugify,
  extractHeadings,
  buildToc,
  renderMarkdown,
  renderThesis,
  toggleTask,
  relativeDays,
  daysUntil,
  formatDate,
  agendaRow,
  THESIS_SKELETON,
} = await import("../src/obole/web/markdown.js");

describe("slugify (CA-TOC7)", () => {
  it("déplie les accents et minuscule", () => {
    expect(slugify("Résultats annuels")).toBe("resultats-annuels");
    expect(slugify("Écart-type")).toBe("ecart-type");
  });

  it("réduit la ponctuation à un tiret unique", () => {
    expect(slugify("Bull case : marge > 28 %")).toBe("bull-case-marge-28");
  });

  it("titre vide ou purement ponctuel -> « section »", () => {
    expect(slugify("")).toBe("section");
    expect(slugify("  ???  ")).toBe("section");
  });
});

describe("extractHeadings (CA-TOC1, CA-TOC7)", () => {
  it("extrait les titres dans l'ordre avec leur niveau", () => {
    const heads = extractHeadings("# Thèse\n\n## Pitch\n\ntexte\n\n## Bull case\n");
    expect(heads.map((h) => [h.level, h.text])).toEqual([
      [1, "Thèse"],
      [2, "Pitch"],
      [2, "Bull case"],
    ]);
  });

  it("slugs dupliqués suffixés (jamais deux ancres identiques)", () => {
    const heads = extractHeadings("## Pitch\n\ntexte\n\n## Pitch\n\ntexte\n\n## Pitch\n");
    expect(heads.map((h) => h.slug)).toEqual(["pitch", "pitch-2", "pitch-3"]);
  });

  it("nettote le markdown inline du libellé", () => {
    const heads = extractHeadings("## **Bull** case [détail](https://x)\n");
    expect(heads[0].text).toBe("Bull case détail");
  });

  it("ignore les # dans un bloc de code (CA-TOC4)", () => {
    const md = "# Réel\n\n```\n# pas un titre\n## non plus\n```\n\n## Aussi réel\n";
    const heads = extractHeadings(md);
    expect(heads.map((h) => h.text)).toEqual(["Réel", "Aussi réel"]);
  });

  it("document sans titre -> liste vide", () => {
    expect(extractHeadings("Juste du texte.\n\n- une liste")).toEqual([]);
  });

  it("un titre cité reçoit une ancre mais reste HORS sommaire", () => {
    // Il doit être collecté (alignement des ids) mais pas exposé au sommaire.
    const heads = extractHeadings("# A\n\n> # Citation\n\n## B\n");
    expect(heads.map((h) => [h.text, h.topLevel])).toEqual([
      ["A", true],
      ["Citation", false],
      ["B", true],
    ]);
    expect(buildToc(heads, 3).map((t) => t.text)).toEqual(["A", "B"]);
  });
});

describe("buildToc (CA-TOC1, CA-TOC3)", () => {
  it("numérote et borne la profondeur", () => {
    const heads = extractHeadings("# A\n\n## B\n\n### C\n\n#### D\n");
    const toc = buildToc(heads, 2);
    expect(toc.map((t) => [t.index, t.text, t.level])).toEqual([
      [1, "A", 1],
      [2, "B", 2],
    ]);
  });

  it("aucun titre -> sommaire vide (pas de bruit)", () => {
    expect(buildToc(extractHeadings("texte"))).toEqual([]);
  });
});

describe("renderMarkdown — parité ancres <-> sommaire (CA-TOC2)", () => {
  it("les id rendus sont exactement les slugs du sommaire", () => {
    const md = "# Thèse\n\n## Résultats & marges\n\n## Résultats & marges\n";
    const { html, headings } = (() => {
      const h = extractHeadings(md);
      return { html: renderMarkdown(md, h), headings: h };
    })();
    for (const head of headings) {
      expect(html).toContain(`id="${head.slug}"`);
    }
    expect(html).toContain('id="resultats-marges"');
    expect(html).toContain('id="resultats-marges-2"');
  });

  it("titre accentué et ponctué", () => {
    const md = "## Écart-type : 25 % !";
    const html = renderMarkdown(md, extractHeadings(md));
    expect(html).toContain('id="ecart-type-25"');
  });

  it("titres sans id préexistant du parseur (nous les posons)", () => {
    const md = "# A\n\n## B\n";
    const html = renderMarkdown(md, extractHeadings(md));
    expect((html.match(/id="[^"]*"/g) || []).length).toBe(2);
  });

  it("RÉGRESSION — un titre cité ne décale pas les id suivants", () => {
    // Le rendu produit un `<hN>` pour la citation : si elle n'était pas
    // collectée, tous les id suivants glissaient d'un cran et `## B` se
    // retrouvait sans ancre (le sommaire pointait sur la citation).
    const md = "# A\n\n> # Citation\n\n## B\n";
    const html = renderMarkdown(md, extractHeadings(md));
    const ids = [...html.matchAll(/<h([1-6])[^>]*id="([^"]+)"/g)];
    expect(ids.map((m) => m[2])).toEqual(["a", "citation", "b"]);
    expect(html).toContain('id="b"');
  });

  it("RÉGRESSION — un titre en liste ne décale pas non plus", () => {
    const md = "# A\n\n- item\n\n## B\n";
    const html = renderMarkdown(md, extractHeadings(md));
    const ids = [...html.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);
    expect(ids).toEqual(["a", "b"]);
  });
});

describe("sanitisation (CA-TOC9 / CA6)", () => {
  it("neutralise <script>", () => {
    const html = renderMarkdown("# T\n\n<script>alert(1)</script>\n");
    expect(html).not.toContain("<script");
  });

  it("neutralise onerror", () => {
    const html = renderMarkdown('# T\n\n<img src=x onerror="alert(1)">\n');
    expect(html).not.toContain("onerror");
  });

  it("neutralise javascript:", () => {
    const html = renderMarkdown("# T\n\n[lien](javascript:alert(1))\n");
    expect(html.toLowerCase()).not.toContain("javascript:");
  });

  it("neutralise les images de thèse piégées (data:/externes)", () => {
    const html = renderMarkdown(
      '# T\n\n![a](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)\n' +
        "![b](https://exemple.invalid/x.png)\n",
    );
    expect(html).not.toContain("data:text/html");
    expect(html).not.toContain("exemple.invalid");
  });

  it("conserve une image de thèse locale (/api/thesis/assets)", () => {
    const html = renderMarkdown("# T\n\n![titre](/api/thesis/assets/abc123.png)\n");
    expect(html).toContain("/api/thesis/assets/abc123.png");
  });

  it("conserve le HTML légitime (gras, listes, titres)", () => {
    const html = renderMarkdown("# T\n\n**gras** et *italique*\n\n- item\n", extractHeadings("# T\n"));
    expect(html).toContain("<strong>gras</strong>");
    expect(html).toContain("<em>italique</em>");
    expect(html).toContain("<li>item</li>");
  });
});

describe("cases à cocher du document (CA-UI6)", () => {
  it("coche la n-ième case sans toucher aux autres", () => {
    const md = "- [ ] a\n- [ ] b\n- [ ] c\n";
    expect(toggleTask(md, 1)).toBe("- [ ] a\n- [x] b\n- [ ] c\n");
  });

  it("décoche une case déjà cochée", () => {
    expect(toggleTask("- [x] a\n", 0)).toBe("- [ ] a\n");
  });

  it("index hors bornes -> document inchangé", () => {
    const md = "- [ ] a\n";
    expect(toggleTask(md, 5)).toBe(md);
  });

  it("la bascule est réversible et idempotente sur l'état voulu", () => {
    const md = "- [ ] a\n- [ ] b\n";
    const once = toggleTask(md, 0);
    expect(once).toBe("- [x] a\n- [ ] b\n");
    expect(toggleTask(once, 0)).toBe(md);
  });
});

describe("renderThesis — agrégat et non-persistance (CA-TOC11)", () => {
  it("renvoie html + titres + sommaire, SANS compteur de points de contrôle", () => {
    const md = "# Thèse\n\n## Points de contrôle\n\n- [ ] a\n";
    const out = renderThesis(md);
    // Le compteur du document a été retiré (#21.1) : un seul « n/N » subsiste,
    // celui de la bande « Suivi », alimenté par la liste persistée.
    expect(Object.keys(out).sort()).toEqual(["headings", "html", "toc", "tocMain"]);
    expect(out.toc.length).toBe(2);
    expect(out.tocMain.length).toBe(2);
  });

  it("le sommaire n'est PAS injecté dans le corps rendu", () => {
    const out = renderThesis("# A\n\n## B\n\ntexte\n");
    expect(out.html).not.toMatch(/sommaire/i);
    expect(out.html).not.toContain("md-toc");
  });

  it("sommaire intégré borné à 2 niveaux, plan jusqu'à 3 (CA-TOC3)", () => {
    const out = renderThesis("# A\n\n## B\n\n### C\n");
    expect(out.tocMain.map((t) => t.text)).toEqual(["A", "B"]);
    expect(out.toc.map((t) => t.text)).toEqual(["A", "B", "C"]);
  });

  it("document vide -> aucun crash", () => {
    const out = renderThesis("");
    expect(out.headings).toEqual([]);
    expect(out.html).toBe("");
  });
});

describe("relativeDays (CA-UI10)", () => {
  const now = new Date("2026-10-12T12:00:00");

  it("compte les jours à venir", () => {
    expect(relativeDays("2026-11-26", now)).toBe("dans 45 j");
  });

  it("gère aujourd'hui et demain", () => {
    expect(relativeDays("2026-10-12", now)).toBe("aujourd'hui");
    expect(relativeDays("2026-10-13", now)).toBe("demain");
  });

  it("gère le passé", () => {
    expect(relativeDays("2026-10-01", now)).toBe("il y a 11 j");
  });

  it("date absente ou invalide -> null", () => {
    expect(relativeDays(null, now)).toBe(null);
    expect(relativeDays("pas-une-date", now)).toBe(null);
  });
});

describe("dates d'agenda — source unique (CA-UI10, #21.1)", () => {
  // `agendaRow` est l'UNIQUE mise en forme des dates de la fiche (agenda du
  // profil + bande « Suivi ») : deux copies divergeraient au premier changement.
  const now = new Date("2026-10-12T12:00:00");

  it("formatDate rend la date française longue", () => {
    expect(formatDate("2026-11-26")).toBe("26 novembre 2026");
    expect(formatDate("pas-une-date")).toBe("pas-une-date");
    expect(formatDate(null)).toBe("");
  });

  it("daysUntil donne un entier signé, ou null", () => {
    expect(daysUntil("2026-11-26", now)).toBe(45);
    expect(daysUntil("2026-10-01", now)).toBe(-11);
    expect(daysUntil("2026-10-12", now)).toBe(0);
    expect(daysUntil(null, now)).toBe(null);
  });

  it("une échéance à venir : date + relatif, pas d'état", () => {
    const row = agendaRow("2026-11-26", { now });
    expect(row).toEqual({ date: "26 novembre 2026", relative: "dans 45 j", after: "" });
  });

  it("une échéance passée : date + état, aucun relatif", () => {
    const row = agendaRow("2026-10-01", { pastLabel: "publié", now });
    expect(row).toEqual({ date: "1 octobre 2026", relative: "", after: "publié" });
  });

  it("le vocabulaire du passé est paramétrable (« publié » vs « passé »)", () => {
    expect(agendaRow("2020-01-01", { pastLabel: "passé", now }).after).toBe("passé");
    expect(agendaRow("2020-01-01", { now }).after).toBe("passé");
  });

  it("une date absente ou illisible -> aucune ligne (pas de crash)", () => {
    expect(agendaRow(null, { now })).toBe(null);
    expect(agendaRow("pas-une-date", { now })).toBe(null);
  });
});

describe("squelette de structure (CA-TOC8)", () => {
  it("suit la structure du prompt de thèse", () => {
    for (const section of ["Pitch", "Bull case", "Bear case", "Catalyseurs", "Points de contrôle"]) {
      expect(THESIS_SKELETON).toContain(`## ${section}`);
    }
  });

  it("contient une case à cocher prête à l'emploi", () => {
    expect(THESIS_SKELETON).toContain("- [ ] ");
  });

  it("produit un sommaire exploitable une fois inséré", () => {
    expect(buildToc(extractHeadings(THESIS_SKELETON), 2).length).toBe(6);
  });
});
