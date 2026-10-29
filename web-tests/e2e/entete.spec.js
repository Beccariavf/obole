import { expect, test } from "@playwright/test";

// En-tête de l'espace Analyse (recherche collante + onglets collés dessous) et
// grille de cartes sans colonne orpheline.
//
// Ce fichier ne teste pas des sélecteurs mais des MESURES : ce sont elles qui
// avaient révélé les deux défauts (rang de recherche flottant avec ~400 px de
// vide à sa droite ; jusqu'à 887 px de colonne morte dans les cartes).

// Vide résiduel à droite d'une grille, mesuré PAR RANGÉE.
//
// Somme brute sur toutes les cartes = assertion vacue : sur 7 cartes en 3
// rangées, la somme vaut ~3 × la largeur de grille et le « vide » calculé est
// toujours négatif, donc toujours sous le seuil, quelle que soit la mise en
// page. On regroupe donc par `y` (une rangée = même ordonnée, à l'arrondi
// sous-pixel près) avant de sommer. Positif = trou à droite de la rangée.
export const mesurerVide = (page) =>
  page.evaluate(() => {
    const out = [];
    for (const s of document.querySelectorAll(".section")) {
      const g = s.querySelector(".charts-grid");
      if (!g || s.getBoundingClientRect().height < 1) continue;
      const cs = [...g.querySelectorAll(".card.mini")].filter(
        (c) => c.getBoundingClientRect().width > 1,
      );
      if (!cs.length) continue;
      const gap = parseFloat(getComputedStyle(g).columnGap) || 0;
      const gridW = g.getBoundingClientRect().width;

      const rangees = new Map();
      for (const c of cs) {
        const r = c.getBoundingClientRect();
        const cle = Math.round(r.y);
        if (!rangees.has(cle)) rangees.set(cle, []);
        rangees.get(cle).push(r);
      }

      const rows = [...rangees.entries()]
        .sort((a, b) => a[0] - b[0])
        .map(([y, cartes]) => {
          const used = cartes.reduce((a, r) => a + r.width, 0) + (cartes.length - 1) * gap;
          return { y, n: cartes.length, vide: Math.round(gridW - used) };
        });

      out.push({
        grp: s.querySelector("h2")?.textContent?.trim(),
        gridW: Math.round(gridW),
        colonnes: getComputedStyle(g).gridTemplateColumns.split(" ").length,
        cards: cs.length,
        // Le pire trou de la grille : c'est lui qui décide.
        vide: Math.max(...rows.map((r) => r.vide)),
        rows,
      });
    }
    return out;
  });

test("en-tête : la recherche et les onglets collent, l'identité défile", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();

  // Le rang est collant par nature (et non par chance de position).
  expect(
    await page.locator(".searchbar").evaluate((e) => getComputedStyle(e).position),
  ).toBe("sticky");
  expect(
    await page.locator(".section-tabs").evaluate((e) => getComputedStyle(e).position),
  ).toBe("sticky");

  // On défile assez pour que l'identité du titre ET les onglets aient quitté le
  // haut de page si rien ne collait.
  await page.mouse.wheel(0, 900);
  await page.waitForTimeout(250);
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(300);

  const pos = await page.evaluate(() => {
    const b = (s) => document.querySelector(s).getBoundingClientRect();
    return {
      search: b(".searchbar"),
      tabs: b(".section-tabs"),
      header: b(".header"),
      rail: b(".app-rail"),
    };
  });

  // Rang 1 visible et aligné sur le rail (mêmes 16 px de haut).
  expect(pos.search.top).toBeGreaterThanOrEqual(15);
  expect(pos.search.top).toBeLessThanOrEqual(18);
  expect(Math.abs(pos.search.top - pos.rail.top)).toBeLessThanOrEqual(1);

  // Rang 2 collé SOUS le rang 1, sans recouvrement.
  expect(pos.tabs.top).toBeGreaterThanOrEqual(pos.search.bottom - 1);
  expect(pos.tabs.top - pos.search.bottom).toBeLessThanOrEqual(12);
  expect(pos.tabs.top).toBeLessThanOrEqual(90);

  // L'identité du titre, elle, a bien défilé : seuls l'en-tête et le contenu
  // restent visibles.
  expect(pos.header.top).toBeLessThan(pos.search.top);

  // Les deux rangs sont opaques : le contenu qui passe dessous ne les traverse
  // pas (un fond transparent laisserait voir le texte des cartes).
  for (const sel of [".searchbar", ".section-tabs"]) {
    const bg = await page
      .locator(sel)
      .evaluate((e) => getComputedStyle(e).backgroundColor);
    expect(bg, `${sel} doit être opaque`).not.toMatch(/rgba\(0, 0, 0, 0\)|transparent/);
  }
});

test("en-tête : le rang se remplit à droite et « Retour » ne décale personne", async ({ page }) => {
  for (const w of [1280, 1440, 1600, 1920]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.goto("/#RI.PA/resume");
    await expect(page.locator(".header")).toBeVisible();

    const m = await page.evaluate(() => {
      const bar = document.querySelector(".searchbar").getBoundingClientRect();
      const main = document.querySelector(".app-main").getBoundingClientRect();
      const acts = document.querySelector(".search-actions").getBoundingClientRect();
      const ana = [...document.querySelectorAll(".search-actions .btn")].find(
        (b) => b.textContent.trim() === "Analyser",
      );
      return {
        main: main.width,
        barW: bar.width,
        trou: Math.round(bar.right - acts.right),
        anaRight: ana.getBoundingClientRect().right,
        barRight: bar.right,
      };
    });
    expect(m.barW, `${w} px : le rang occupe la colonne`).toBeGreaterThanOrEqual(m.main - 1);
    // Anti-vide : le dernier bouton du rang s'aligne sur le bord droit.
    expect(m.trou, `${w} px : ${m.trou} px de vide à droite`).toBeLessThanOrEqual(20);
  }
});

test("en-tête : « Retour à … » grandit vers la gauche, sans reflow des voisins", async ({
  page,
}) => {
  // Parcours réel : ouvrir une valeur DEPUIS la watchlist arme le bouton de
  // retour. Les routes sont interceptées (aucun test n'écrit dans la base).
  await page.route("**/api/watchlist/run", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        generated_at: 1700000000,
        count: 1,
        rows: [
          {
            ticker: "RI.PA",
            tier: 1,
            name: "Pernod Ricard",
            sector: "Consumer Defensive",
            currency: "EUR",
            price: 100,
            fair_price: 120,
            fair_price_source: "saved",
            target_yield: 12,
            safety_margin_pct: 16.67,
            margin_good: true,
            ref_start: "2005-01-03",
            ref_is_default: false,
            ref_line: 110,
            trend_gap_pct: 9.09,
            z: -1.2,
            ecart_type_pct: 25,
            pente_pct: 5,
            pot_5y_pct: 8,
            pot_10y_pct: 6,
            pot_5y_source: "valuation",
            pot_10y_source: "regression",
            trend_bullish: true,
            warnings: [],
            error: null,
          },
        ],
      }),
    }),
  );

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();
  // `x-show` laisse le bouton dans le DOM (masqué) : c'est sa visibilité qui
  // compte, pas sa présence.
  await expect(page.locator(".search-back")).toBeHidden();

  const positionAnalyser = () =>
    page.evaluate(() => {
      const ana = [...document.querySelectorAll(".search-actions .btn")].find(
        (b) => b.textContent.trim() === "Analyser",
      );
      const r = ana.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y) };
    });

  const avant = await positionAnalyser();

  // Ouvrir la watchlist puis une valeur : le bouton de retour apparaît.
  await page.locator(".app-rail-btn[data-space='watchlist']").click();
  await expect(page.locator(".app-view.view-watchlist")).toBeVisible();
  // La modale s'ouvre sur la vue cadrans : la ligne cliquable vit dans le
  // tableau, d'où la bascule explicite.
  await page.locator(".wl-view-toggle .btn", { hasText: "Tableau" }).click();
  await page.locator(".wl-table tbody tr").first().click();
  await expect(page.locator(".search-back")).toBeVisible();
  await expect(page.locator(".search-back")).toContainText("Retour à « Watchlist »");
  // Le rechargement passe par un état sans données (`data = null`), pendant
  // lequel « ↻ » est masqué. Mesurer à cet instant comparerait deux rangées
  // différentes : on attend que la fiche soit complètement revenue.
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".search-actions .btn.ghost[title='Rafraîchir les données']")).toBeVisible();

  const apres = await positionAnalyser();

  // L'invariant : « Analyser » ne bouge PAS. Il est suivi du même voisin (↻), et
  // le retour, placé en tête du groupe calé à droite, n'a fait grandir le groupe
  // que vers la gauche.
  expect(apres.x).toBe(avant.x);
  expect(apres.y).toBe(avant.y);
});

test("accueil : la recherche et l'invite partagent un seul axe de centrage", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await expect(page.locator(".empty")).toBeVisible();

  // À l'accueil, rien à coller : le rang est statique (un héros collé n'en est
  // plus un).
  expect(
    await page.locator(".searchbar").evaluate((e) => getComputedStyle(e).position),
  ).toBe("static");

  const c = await page.evaluate(() => {
    const centre = (el) => {
      const r = el.getBoundingClientRect();
      return r.x + r.width / 2;
    };
    const main = document.querySelector(".app-main").getBoundingClientRect();
    return {
      champ: centre(document.querySelector(".search-input")),
      invite: centre(document.querySelector(".empty")),
      colonne: main.x + main.width / 2,
      largeurChamp: document.querySelector(".search-input").getBoundingClientRect().width,
    };
  });

  // Un seul axe : le champ était collé à gauche pendant que l'invite était
  // centrée (~380 px d'écart entre les deux centres).
  expect(Math.abs(c.champ - c.colonne)).toBeLessThanOrEqual(2);
  expect(Math.abs(c.invite - c.colonne)).toBeLessThanOrEqual(2);
  expect(Math.abs(c.champ - c.invite)).toBeLessThanOrEqual(2);
  // Le champ garde sa largeur de saisie (au-delà, le regard perd le curseur).
  expect(c.largeurChamp).toBeLessThanOrEqual(422);

  // L'action principale est sous le champ, sur le même axe.
  const sousChamp = await page.evaluate(() => {
    const i = document.querySelector(".search-input").getBoundingClientRect();
    const a = [...document.querySelectorAll(".search-actions .btn")].find(
      (b) => b.textContent.trim() === "Analyser",
    );
    const r = a.getBoundingClientRect();
    return { dessous: r.top >= i.bottom, centre: Math.abs(r.x + r.width / 2 - (i.x + i.width / 2)) };
  });
  expect(sousChamp.dessous).toBe(true);
  expect(sousChamp.centre).toBeLessThanOrEqual(2);
});

test("grille : aucune colonne orpheline dans le Dividende ni le Quantitatif", async ({ page }) => {
  for (const w of [1440, 1600, 1920]) {
    await page.setViewportSize({ width: w, height: 1200 });
    for (const section of ["dividende", "quantitatif"]) {
      await page.goto(`/#RI.PA/${section}`);
      await expect(page.locator(".header")).toBeVisible();
      await page.waitForTimeout(400);

      const groupes = await mesurerVide(page);
      expect(groupes.length, `${w} px / ${section} : aucun groupe mesuré`).toBeGreaterThan(0);
      for (const g of groupes) {
        // Avant correctif, mesuré : 443 px sur « Dividende par action » et
        // « Payout », 887 px sur « Retour à l'actionnaire » et 807-887 px sur
        // les trois groupes du Quantitatif (7 cartes en 3+3+1, 4 en 3+1).
        // La tolérance couvre l'arrondi sous-pixel.
        expect(
          g.vide,
          `${w} px / ${section} / « ${g.grp} » : ${g.vide} px de colonne morte`,
        ).toBeLessThanOrEqual(30);
      }
    }
  }
});

test("grille : le bandeau de métriques tient sur un seul rang en pleine largeur", async ({
  page,
}) => {
  for (const w of [1600, 1920]) {
    await page.setViewportSize({ width: w, height: 1200 });
    await page.goto("/#RI.PA/dividende");
    await expect(page.locator(".header")).toBeVisible();

    const m = await page.evaluate(() => {
      const card = [...document.querySelectorAll(".card.mini")].find(
        (c) => c.querySelector("h3 span")?.textContent === "Métriques clés",
      );
      const grid = card.closest(".charts-grid");
      const items = [...card.querySelectorAll(".cagr-item")].map((i) => ({
        y: Math.round(i.getBoundingClientRect().y),
        w: Math.round(i.getBoundingClientRect().width),
        label: i.querySelector(".cagr-label")?.textContent,
      }));
      return {
        cardW: Math.round(card.getBoundingClientRect().width),
        gridW: Math.round(grid.getBoundingClientRect().width),
        cardH: Math.round(card.getBoundingClientRect().height),
        rangs: new Set(items.map((i) => i.y)).size,
        items,
      };
    });

    // Pleine largeur : la carte occupe toute la grille.
    expect(Math.abs(m.cardW - m.gridW), `${w} px : carte non pleine largeur`).toBeLessThanOrEqual(2);
    // Un seul rang de chiffres (contre trois en colonne simple).
    expect(m.rangs, `${w} px : ${m.rangs} rangs de chiffres`).toBe(1);
    // Boîte compacte : 146 px mesurés, contre 283 px en tuile étroite.
    expect(m.cardH).toBeLessThanOrEqual(170);
    // Et le contenu attendu est bien là (aucune valeur perdue au passage).
    const labels = m.items.map((i) => i.label);
    expect(labels).toContain("Yield (TTM)");
    expect(labels).not.toContain("Prochain paiement");
  }
});

test("grille : paliers responsives sans débordement horizontal", async ({ page }) => {
  // Ce qui compte n'est pas un nombre de colonnes imposé, mais qu'AUCUNE
  // rangée ne laisse de trou et que rien ne déborde horizontalement. On mesure
  // les DEUX sections (le Quantitatif a 7 et 4 cartes : c'est là que les
  // rangées incomplètes apparaissaient, jamais dans le Dividende à 2 cartes).
  for (const w of [1280, 899, 720, 390]) {
    await page.setViewportSize({ width: w, height: 900 });

    for (const section of ["quantitatif", "dividende"]) {
      await page.goto(`/#RI.PA/${section}`);
      await expect(page.locator(".header")).toBeVisible();
      await page.waitForTimeout(400);

      const groupes = await mesurerVide(page);
      expect(groupes.length, `${w} px / ${section} : aucun groupe mesuré`).toBeGreaterThan(0);
      for (const g of groupes) {
        expect(
          g.vide,
          `${w} px / ${section} / « ${g.grp} » : ${g.vide} px de colonne morte`,
        ).toBeLessThanOrEqual(30);
      }

      const deborde = await page.evaluate(
        () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      );
      expect(deborde, `${w} px / ${section} : débordement horizontal`).toBe(false);
    }

    // Sous 900 px, plus rien ne colle (bandeau + écran court).
    const sticky = await page.locator(".searchbar").evaluate((e) => getComputedStyle(e).position);
    if (w < 900) expect(sticky, `${w} px`).toBe("static");
    else expect(sticky, `${w} px`).toBe("sticky");
  }
});

test("en-tête collant : AUCUN élément sticky de la fiche n'est recouvert", async ({ page }) => {
  // Cette famille de régressions (plan de thèse, barre markdown) est passée
  // parce qu'aucun test ne regardait les AUTRES `sticky` de la fiche. On les
  // sonde tous : un élément collé est « atteignable » si `elementFromPoint` à son
  // centre renvoie lui-même (ou un descendant), et si son `top` calculé est au
  // moins égal à la hauteur de l'en-tête.
  const hauteurEntete = (p) =>
    p.evaluate(() => {
      const cs = getComputedStyle(document.documentElement);
      const px = (n) => parseFloat(cs.getPropertyValue(n));
      return px("--head-top") + px("--search-h") + px("--head-gap") + px("--tabs-h");
    });

  for (const [w, h] of [
    [1440, 700],
    [1440, 900],
    [1100, 600],
    [1280, 560],
  ]) {
    await page.setViewportSize({ width: w, height: h });
    await page.goto("/#RI.PA/these");
    await expect(page.locator(".header")).toBeVisible();

    const attendu = await hauteurEntete(page);
    // `--head-h` doit valoir la somme des tokens : la géométrie reste calculée,
    // jamais recopiée (une valeur figée dans le test dériverait du CSS).
    const declare = await page.evaluate(
      () => getComputedStyle(document.documentElement).getPropertyValue("--head-h").trim(),
    );
    expect(declare, "— --head-h doit être un calc() des tokens").toMatch(/calc\(/);

    // Le plan de thèse est masqué par défaut : on le déplie pour le mesurer.
    const pin = page.locator(".thesis-pin");
    await expect(pin).toHaveCount(1);
    const topPin = await pin.evaluate((e) => parseFloat(getComputedStyle(e).top));
    expect(topPin, `${w}×${h} : poignée sous l'en-tête (${attendu} px)`).toBe(attendu);

    // Le plan de thèse peut être déjà déplié : son état est persisté
    // (localStorage). La poignée BASCULE, donc on ne clique que s'il est masqué
    // — sinon on le refermerait, et WebKit tombait ici sur un plan caché.
    const plan = page.locator("#thesis-plan");
    if (!(await plan.isVisible())) {
      await page.locator(".thesis-edge").hover({ force: true });
      await pin.click({ force: true });
    }
    await expect(plan).toBeVisible();

    // Défilement franc : sans marge, le plan passerait sous les deux rangs.
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(400);

    const sonde = await page.evaluate(() => {
      const plan = document.querySelector("#thesis-plan");
      const top = parseFloat(getComputedStyle(plan).top);
      const items = [...plan.querySelectorAll(".thesis-plan-item")];
      const invisibles = items.filter((a) => {
        const r = a.getBoundingClientRect();
        if (r.width < 1 || r.top < 0) return false;
        const at = document.elementFromPoint(r.x + 6, r.top + r.height / 2);
        return !(at === a || a.contains(at));
      }).length;
      return { top, items: items.length, invisibles };
    });

    // Le plan ne commence pas sous l'en-tête…
    expect(sonde.top, `${w}×${h} : top du plan`).toBeGreaterThanOrEqual(attendu - 1);
    // …et toutes ses entrées sauf celles sorties par le haut sont cliquables.
    expect(sonde.invisibles, `${w}×${h} : ${sonde.invisibles} entrée(s) recouverte(s)`).toBe(0);
    expect(sonde.items, `${w}×${h} : le plan est vide, la mesure ne prouve rien`).toBeGreaterThan(
      2,
    );
  }
});

test("ancres de la thèse : le titre visé atterrit SOUS l'en-tête", async ({ page }) => {
  // `scrollIntoView({block:'start'})` plaquait le titre à 0 : recouvert par les
  // deux rangs (mesuré : 36 px sur « Synthèse », −107 px sur « Fondement »). Le
  // `scroll-margin-top` doit égaler la hauteur de l'en-tête.
  await page.setViewportSize({ width: 1440, height: 700 });
  await page.goto("/#RI.PA/these");
  await expect(page.locator(".header")).toBeVisible();

  const entete = await page.evaluate(() => {
    const cs = getComputedStyle(document.documentElement);
    const px = (n) => parseFloat(cs.getPropertyValue(n));
    return px("--head-top") + px("--search-h") + px("--head-gap") + px("--tabs-h");
  });

  const titres = page.locator(".md-body h1, .md-body h2");
  const n = await titres.count();
  expect(n, "aucun titre dans le corps de thèse").toBeGreaterThan(1);

  const margin = await titres.first().evaluate((e) => parseFloat(getComputedStyle(e).scrollMarginTop));
  expect(margin, "scroll-margin-top absent").toBe(entete);

  // Clic sur une ancre réelle du sommaire, puis mesure de l'atterrissage.
  const lien = page.locator(".md-toc-item").nth(1);
  if (await lien.count()) {
    await lien.click();
    await page.waitForTimeout(900);
    const tops = await page.evaluate(() =>
      [...document.querySelectorAll(".md-body h1, .md-body h2")].map((h) =>
        Math.round(h.getBoundingClientRect().top),
      ),
    );
    // Aucun titre visible ne doit être coincé SOUS l'en-tête (0 < top < entete).
    const coinces = tops.filter((t) => t > 0 && t < entete - 1);
    expect(coinces, `titre(s) coincé(s) sous l'en-tête : ${coinces}`).toEqual([]);
  }
});

test("le champ de recherche ne descend pas sous sa largeur de saisie", async ({ page }) => {
  // Un libellé de retour long écrasait le champ jusqu'à 203 px (mesuré) : sous
  // ce seuil le placeholder ne tient plus. Plancher `min-width` sur `.search-wrap`.
  await page.setViewportSize({ width: 960, height: 800 });
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  const largeur = await page
    .locator(".searchbar .search-wrap")
    .evaluate((e) => Math.round(e.getBoundingClientRect().width));
  expect(largeur, "champ écrasé").toBeGreaterThanOrEqual(260);
});

test("chargement d'un autre ticker : « Analyser » ne bouge pas", async ({ page }) => {
  // « ↻ » apparaît/disparaît selon `data`. Placé APRÈS l'action principale, il
  // la décalait de 57 px à chaque chargement (mesuré). Les deux actions
  // conditionnelles sont désormais en tête du groupe calé à droite.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  const xAnalyser = () =>
    page.evaluate(() => {
      const ana = [...document.querySelectorAll(".search-actions .btn")].find(
        (b) => b.textContent.trim() === "Analyser",
      );
      return Math.round(ana.getBoundingClientRect().x);
    });

  const charge = await xAnalyser();

  // On relance un chargement et on mesure PENDANT l'état sans données.
  await page.locator(".search-actions .btn", { hasText: /^Analyser$/ }).click();
  const pendant = await page.evaluate(() => {
    const ana = [...document.querySelectorAll(".search-actions .btn")].find(
      (b) => b.textContent.trim() === "Analyser",
    );
    return Math.round(ana.getBoundingClientRect().x);
  });

  expect(pendant, "« Analyser » se décale pendant le chargement").toBe(charge);
  await expect(page.locator(".header")).toBeVisible();
  expect(await xAnalyser()).toBe(charge);
});

