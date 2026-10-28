import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { parsePyDividendGroups, readConfigSource } from "./helpers/load-app.js";

// En-tête de l'espace Analyse et grille de cartes.
//
// Deux défauts mesurés en session ont motivé ce fichier :
//   - le rang de recherche flottait (il disparaissait au défilement) et laissait
//     ~400 px de vide à sa droite : les actions collaient au champ au lieu
//     d'occuper le rang ;
//   - `@media (min-width: 1450px)` forçait 3 colonnes dans `.charts-grid`, ce qui
//     laissait une colonne orpheline (443 px de vide) dès qu'un groupe n'avait
//     pas un multiple de 3 cartes — et 887 px pour une carte seule.
//
// Les assertions portent sur les RÈGLES (CSS/HTML) parce que vitest ne calcule
// pas de mise en page : la mesure réelle du vide est vérifiée en e2e.
const RACINE_WEB = join(process.cwd(), "..", "src", "obole", "web");
const css = readFileSync(join(RACINE_WEB, "style.css"), "utf8");
const html = readFileSync(join(RACINE_WEB, "index.html"), "utf8");
const dividendJs = readFileSync(join(RACINE_WEB, "dividend.js"), "utf8");

// Extrait le premier bloc de règles d'un sélecteur (sans les media queries).
function bloc(selecteur) {
  const echappe = selecteur.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const m = css.match(new RegExp(`\\n${echappe}\\s*\\{([^}]*)\\}`));
  return m ? m[1] : null;
}

describe("rang de recherche — collant", () => {
  it("le rang porte `position: sticky` et un `top` aligné sur le rail", () => {
    const regles = bloc(".searchbar");
    expect(regles, "règle .searchbar introuvable").toBeTruthy();
    expect(regles).toMatch(/position:\s*sticky/);
    expect(regles).toMatch(/top:\s*var\(--head-top\)/);
    // Même valeur que le rail : les deux colonnes commencent à la même hauteur.
    expect(bloc(".app-rail")).toMatch(/top:\s*var\(--head-top\)/);
    expect(css).toMatch(/--head-top:\s*16px/);
  });

  it("il est opaque et au-dessus du contenu qui défile dessous", () => {
    const regles = bloc(".searchbar");
    expect(regles).toMatch(/background:\s*var\(--bg\)/);
    expect(regles).toMatch(/z-index:\s*15/);
  });

  it("les onglets collent SOUS le rang, à la hauteur exacte du rang", () => {
    const regles = bloc(".section-tabs");
    expect(regles, "règle .section-tabs introuvable").toBeTruthy();
    expect(regles).toMatch(/position:\s*sticky/);
    // L'offset est calculé : rang (haut + hauteur + joint) — jamais un nombre nu
    // qui dériverait à la première retouche du rang.
    expect(regles).toMatch(
      /top:\s*calc\(var\(--head-top\)\s*\+\s*var\(--search-h\)\s*\+\s*var\(--head-gap\)\)/,
    );
    expect(bloc(".section-tabs")).toMatch(/background:\s*var\(--bg\)/);
  });

  it("le collant du rang s'éteint à l'accueil (un héros collé n'en est plus un)", () => {
    const hero = bloc(".searchbar.is-hero");
    expect(hero, "règle .searchbar.is-hero introuvable").toBeTruthy();
    expect(hero).toMatch(/position:\s*static/);
    // La classe est pilotée par l'état de la fiche, pas par un script. Une
    // seconde classe (`is-stuck`) avait été liée sans aucune règle CSS : elle a
    // été retirée plutôt que laissée en place, et le test qui la verrouillait
    // avec elle.
    expect(html).toMatch(/'is-hero':\s*!data\s*&&\s*!loading/);
    expect(html).not.toMatch(/is-stuck/);
  });

  it("sous 900 px, le rang redevient statique et passe sur deux lignes", () => {
    // Cette règle vit APRÈS les règles de base : à spécificité égale, c'est
    // l'ordre du fichier qui décide (le placement avant `.searchbar` perdait).
    const blocsMobile = css.match(/@media \(max-width: 899px\) \{([\s\S]*?)\n\}/g) || [];
    const regle = blocsMobile.find((b) => b.includes(".searchbar { position: static"));
    expect(regle, "repli mobile du rang introuvable").toBeTruthy();
    expect(regle).toMatch(/\.section-tabs \{ position: static/);
    // Téléphone : champ pleine largeur, actions dessous (pas de débordement).
    expect(regle).toMatch(/\.searchbar \.search-wrap \{ flex: 1 1 100%/);
    expect(regle).toMatch(/\.searchbar \.search-actions \{ margin-left: 0/);
    // Le repli doit venir APRÈS la règle de base (l'ordre du fichier tranche à
    // spécificité égale ; placé avant, il perdait et le rang restait collé sous
    // 900 px — vérifié en e2e).
    const base = css.indexOf("position: sticky; top: var(--head-top)");
    const position = css.indexOf(".searchbar { position: static; flex-wrap: wrap; }");
    expect(base).toBeGreaterThan(-1);
    expect(position).toBeGreaterThan(base);
  });
});

describe("rang de recherche — actions à droite", () => {
  it("les actions sont groupées et poussées à droite du rang", () => {
    const regles = bloc(".search-actions");
    expect(regles, "règle .search-actions introuvable").toBeTruthy();
    expect(regles).toMatch(/margin-left:\s*auto/);
    expect(regles).toMatch(/display:\s*flex/);
    // Le groupe est DANS le rang, après le champ.
    expect(html).toMatch(/<div class="search-actions">/);
    expect(html.indexOf('class="search-actions"')).toBeGreaterThan(
      html.indexOf('class="search-wrap"'),
    );
  });

  it("« Retour à … » est le PREMIER du groupe, qui est calé à droite", () => {
    // L'invariant réalisé ici : dans un groupe calé à droite, la position de
    // « Analyser » ne dépend que des éléments qui le SUIVENT. Placer le retour
    // en tête fait donc grandir le groupe vers la gauche quand il apparaît, sans
    // décaler personne — et sans réserver une largeur morte à droite.
    const regles = bloc(".search-actions");
    expect(regles).toMatch(/margin-left:\s*auto/);
    const debut = html.indexOf('<div class="search-actions">');
    const groupe = html.slice(debut, html.indexOf("</div>", debut));
    expect(groupe.indexOf("search-back")).toBeGreaterThan(-1);
    expect(groupe.indexOf("search-back")).toBeLessThan(groupe.indexOf("Analyser"));
  });

  it("aucun tabindex positif ne réordonne la page", () => {
    // L'ordre de tabulation réel (champ → actions → rail → onglets) se mesure en
    // e2e : c'est un comportement, pas une déclaration. Ici on garantit seulement
    // qu'aucun `tabindex` positif ne subsiste — un indice positif est un
    // anti-pattern WCAG 2.4.3 et sautait par-dessus le rail puis y revenait :
    // mesuré, `↻` n'était atteint qu'APRÈS les six entrées du rail. L'ordre
    // voulu (« la recherche d'abord ») vient du DOM, pas d'un indice.
    const positifs = [...html.matchAll(/tabindex="(\d+)"/g)]
      .map((m) => Number(m[1]))
      .filter((n) => n > 0);
    expect(positifs).toEqual([]);
  });
});

describe("accueil — un seul axe de centrage", () => {
  it("le champ et l'invite partagent la même colonne centrée", () => {
    const hero = bloc(".searchbar.is-hero");
    expect(hero).toMatch(/flex-direction:\s*column/);
    expect(hero).toMatch(/align-items:\s*center/);
    const wrap = css.match(/\.searchbar\.is-hero \.search-wrap\s*\{([^}]*)\}/);
    expect(wrap, "règle .searchbar.is-hero .search-wrap introuvable").toBeTruthy();
    expect(wrap[1]).toMatch(/width:\s*100%/);
    expect(wrap[1]).toMatch(/max-width:\s*420px/);
    // L'invite est déjà centrée : c'est le champ qui devait la rejoindre.
    expect(bloc(".empty")).toMatch(/text-align:\s*center/);
  });
});

describe("grille de cartes — aucune colonne orpheline", () => {
  it("plus de plafond de 3 colonnes imposé à la grille des cartes", () => {
    // Le plafond ne visait QUE `.charts-grid` : les autres `repeat(3)` du
    // fichier (KPI du portefeuille, barres de la valorisation) sont légitimes.
    const plafond = css.match(/@media[^{]*\{\s*\.charts-grid\s*\{[^}]*\}/g) || [];
    expect(plafond).toHaveLength(0);
    for (const m of css.matchAll(/\.charts-grid[^{]*\{([^}]*)\}/g)) {
      expect(m[1]).not.toMatch(/repeat\(3/);
    }
  });

  it("la grille n'est plus une grille : une rangée incomplète doit pouvoir s'étirer", () => {
    // L'assertion porte sur la PROPRIÉTÉ, pas sur l'écriture : une grille CSS ne
    // sait pas étirer une rangée partielle (7 cartes en 3+3+1 laissaient 807 px
    // mesurés), donc `grid-template-columns` ne doit plus exister sur cette
    // classe. La valeur réelle du vide se mesure en e2e — ici on ne vérifie que
    // l'absence du mécanisme qui l'empêchait.
    const colonnes = [...css.matchAll(/\.charts-grid[^{]*\{[^}]*grid-template-columns/g)];
    expect(colonnes).toHaveLength(0);
    expect(bloc(".charts-grid")).toMatch(/display:\s*flex/);
  });

  it("les cartes partagent la rangée et peuvent rétrécir sous le plancher", () => {
    const carte = css.match(/\.charts-grid > \.card\.mini \{([^}]*)\}/);
    expect(carte, "règle des cartes de la grille introuvable").toBeTruthy();
    // Deux propriétés, pas une écriture : le partage de l'espace (donc le nombre
    // de colonnes vient de la largeur, pas d'un chiffre décidé) et la
    // possibilité de rétrécir (sinon débordement à 390 px de fenêtre, mesuré).
    expect(carte[1]).toMatch(/flex:\s*\d+\s+\d+\s*\d+px/);
    expect(carte[1]).toMatch(/min-width:\s*0/);
  });

  it("une carte `wide` ne partage pas sa rangée", () => {
    const large = css.match(/\.charts-grid > \.card\.mini\.wide \{([^}]*)\}/);
    expect(large, "règle des cartes pleine largeur introuvable").toBeTruthy();
    // `flex-basis: 100%` — la propriété qui la met seule sur sa ligne. Le
    // résultat est mesuré en e2e (carte pleine largeur + un seul rang).
    expect(large[1]).toMatch(/flex-basis:\s*100%/);
  });
});

describe("aucun réglage mort", () => {
  // Deux réglages sans effet avaient été livrés : une classe `is-stuck` liée
  // dans le HTML sans aucune règle CSS, et un `top` mobile de `.thesis-pin`
  // placé AVANT sa définition (donc perdant à spécificité égale). Les deux sont
  // désormais verrouillés ici, parce qu'un réglage mort ne se voit pas à l'œil.
  it("chaque classe CONDITIONNELLE du HTML a une règle CSS", () => {
    // Périmètre : les classes liées par `:class="{ … }"` (donc conditionnelles).
    // Une classe statique de `class="…"` peut être un crochet de test sans
    // style (`.search-back` en est un) ; une classe conditionnelle, non : elle
    // n'existe que parce qu'un état doit changer quelque chose. `is-stuck` était
    // exactement ce cas — liée, jamais stylée, jamais lue.
    const liees = new Set();
    for (const m of html.matchAll(/:class="\{([^"]+)\}"/g)) {
      for (const k of m[1].matchAll(/'([a-z0-9-]+)':/g)) liees.add(k[1]);
    }
    expect(liees.size).toBeGreaterThan(0);
    for (const classe of liees) {
      expect(css, `classe « ${classe} » liée mais sans règle CSS`).toMatch(
        new RegExp(`\\.${classe}[\\s,{:]`),
      );
    }
  });

  it("les éléments collés de la fiche utilisent la géométrie d'en-tête partagée", () => {
    // Le comportement (« ne sont-ils pas recouverts ? ») se mesure en e2e ; ici
    // on garantit seulement qu'aucun `top` littéral ne subsiste sur les éléments
    // qui vivent sous l'en-tête — c'est la cause racine des deux régressions
    // livrées (plan de thèse et barre markdown à `top: 0 / 16px`). Une assertion
    // sur l'ORDRE du fichier a été retirée : elle cassait à toute reformulation
    // équivalente et ne vérifiait pas le résultat.
    for (const sel of [".thesis-pin", ".thesis-plan", ".md-toolbar"]) {
      const regles = css.match(new RegExp(`\\n${sel.replace(".", "\\.")}\\s*\\{([^}]*)\\}`));
      expect(regles, `règle ${sel} introuvable`).toBeTruthy();
      // Les commentaires sont retirés : ils CITENT l'ancien `top: 16px` pour
      // expliquer le défaut, et un regex naïf les prendrait pour du code.
      const sansCommentaire = regles[1].replace(/\/\*[\s\S]*?\*\//g, "");
      // `(^|[\s;])top:` — sinon `margin-top: 14px` serait pris pour un décalage.
      expect(sansCommentaire, `${sel} ne doit pas figer son décalage`).not.toMatch(
        /(^|[\s;])top:\s*-?\d+px/,
      );
      expect(sansCommentaire, `${sel} doit suivre la géométrie partagée`).toMatch(
        /top:\s*var\(--head-(h|top)\)/,
      );
    }
    // Et la variable qui les pilote existe et est calculée, pas recopiée.
    expect(css).toMatch(/--head-h:\s*calc\(var\(--head-top\)/);
  });
});

describe("section Dividende — bandeau de métriques", () => {
  it("« Métriques clés » est déclarée pleine largeur par la TAXONOMIE", () => {
    // La source est `config.DIVIDEND_GROUPS` (via /api/meta) : le front ne
    // décide pas quelles cartes sont larges.
    const groupes = parsePyDividendGroups(readConfigSource());
    const cartes = groupes.flatMap((g) => g.cards);
    const kpi = cartes.find((c) => c.title === "Métriques clés");
    expect(kpi, "carte « Métriques clés » absente de la taxonomie").toBeTruthy();
    expect(kpi.wide).toBe(true);
    // Aucun cas particulier de largeur dans le JS.
    expect(dividendJs).not.toMatch(/Métriques clés[^\n]*wide/);
  });

  it("le bandeau ne porte plus de ligne vide (« Prochain paiement — »)", () => {
    // yfinance Europe ne fournit aucun calendrier : la ligne n'apportait qu'un
    // tiret et consommait un emplacement du bandeau.
    expect(dividendJs).not.toMatch(/Prochain paiement/);
  });
});
