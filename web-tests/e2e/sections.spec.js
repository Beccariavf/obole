import { expect, test } from "@playwright/test";

// Refonte #16 : la fiche n'affiche qu'une section à la fois, pilotée par le
// ruban d’onglets horizontaux (libellés lisibles) et par le deep-link `#TICKER/section`.

test("fiche RI.PA : les onglets pilotent la section affichée", async ({ page }) => {
  await page.goto("/");

  const search = page.locator(".searchbar .search-wrap input.search-input");
  await search.fill("RI.PA");
  await search.press("Enter");
  await expect(page.locator(".header")).toBeVisible();

  // Le ruban expose les 7 sections dans l’ordre validé (identifiants stables,
  // indépendants du libellé d'infobulle qui peut être enrichi).
  const rail = page.locator(".section-tabs .section-tab");
  await expect(rail).toHaveCount(7);
  expect(await rail.evaluateAll((els) => els.map((e) => e.dataset.section))).toEqual([
    "resume",
    "quantitatif",
    "dividende",
    "finance",
    "these",
    "valorisation",
    "momentum",
  ]);

  // À l'ouverture, c'est « Résumé » qui est actif : le graphe héro est là.
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "resume");
  await expect(page.locator(".hero")).toBeVisible();
  await expect(page.locator("#chart svg").first()).toBeVisible();
  await expect(page.locator(".kpi").first()).toBeVisible();

  // Le deep-link reflète la section courante.
  await expect(page).toHaveURL(/#RI\.PA\/resume$/);

  // Bascule sur « Quantitatif » : le héro disparaît, les blocs de comptes apparaissent.
  await page.locator(".section-tab[data-section='quantitatif']").click();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "quantitatif");
  await expect(page).toHaveURL(/#RI\.PA\/quantitatif$/);
  await expect(page.locator(".hero")).toBeHidden();
  await expect(page.locator(".section h2", { hasText: "Croissance & flux" })).toBeVisible();
  await expect(page.locator(".section h2", { hasText: "Structure financière" })).toBeVisible();

  // Bascule sur « Dividende ».
  await page.locator(".section-tab[data-section='dividende']").click();
  await expect(page).toHaveURL(/#RI\.PA\/dividende$/);
  await expect(page.locator(".section h2", { hasText: "Dividende" })).toBeVisible();

  // Bouton « retour » du navigateur : revient sur Quantitatif, sans recharger.
  await page.goBack();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "quantitatif");
  await expect(page.locator(".hero")).toBeHidden();
});

test("fiche RI.PA : le deep-link ouvre directement la bonne section", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");

  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "valorisation");
  // La section Résumé (graphe héro) n'est pas affichée.
  await expect(page.locator(".hero")).toBeHidden();
  await expect(page.locator(".section h2", { hasText: "Valorisation" })).toBeVisible();

  // Les mini-charts de la section demandée sont RÉELLEMENT tracés (pas seulement
  // les titres) : un redraw synchrone laisserait des divs vides.
  await expect
    .poll(async () => page.locator(".mini-chart .scatterlayer .trace").count(), {
      timeout: 30_000,
    })
    .toBeGreaterThan(0);
});

test("fiche RI.PA : le rafraîchissement ne quitte pas la section courante", async ({ page }) => {
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "quantitatif");

  // Bouton ↻ : les données sont rechargées, mais la section consultée est gardée.
  await page.locator(".searchbar .btn.ghost[title='Rafraîchir les données']").click();
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "quantitatif");
  await expect(page).toHaveURL(/#RI\.PA\/quantitatif$/);
});

test("fiche RI.PA : les onglets sont un ruban horizontal de libellés lisibles", async ({ page }) => {
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();

  const tabs = await page.locator(".section-tabs").boundingBox();
  const first = await page.locator(".section-tab").first().boundingBox();
  const last = await page.locator(".section-tab").last().boundingBox();

  // Ruban HORIZONTAL : tous les onglets partagent la même ligne, et le ruban est
  // plus large que haut. C'est le renversement du rail vertical.
  expect(tabs.width).toBeGreaterThan(tabs.height * 4);
  expect(last.y).toBeCloseTo(first.y, 0);
  expect(last.x).toBeGreaterThan(first.x);
  // Le premier onglet est dans le ruban (padding + bordure incluses).
  expect(first.y).toBeGreaterThanOrEqual(tabs.y - 1);
  expect(first.y + first.height).toBeLessThanOrEqual(tabs.y + tabs.height + 1);

  // Les libellés sont VISIBLES, sans survol : c'est l'exigence de la refonte.
  const labels = await page
    .locator(".section-tab-label")
    .evaluateAll((els) =>
      els.map((e) => ({ text: e.textContent.trim(), w: e.getBoundingClientRect().width })),
    );
  expect(labels).toHaveLength(7);
  for (const l of labels) {
    expect(l.text, "libellé vide").not.toBe("");
    expect(l.w, `libellé « ${l.text} » non rendu`).toBeGreaterThan(0);
  }
});

test("la barre de recherche ne porte plus aucun espace", async ({ page }) => {
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  // Les espaces ont déménagé dans le rail : la barre ne garde que la recherche
  // et ses actions de fiche (Analyser, ↻, retour éventuel).
  for (const label of ["Mes indices", "Screener", "Portefeuille", "Watchlist", "Paramètres"]) {
    await expect(page.locator(".searchbar button", { hasText: label })).toHaveCount(0);
  }
  await expect(page.locator(".searchbar button", { hasText: "Analyser" })).toHaveCount(1);

  // Le rail, lui, porte les six entrées (5 espaces + Paramètres en pied).
  await expect(page.locator(".app-rail-btn")).toHaveCount(6);
});

test("un ratio désactive les sections sans comptes", async ({ page }) => {
  await page.goto("/");
  const search = page.locator(".searchbar .search-wrap input.search-input");
  await search.fill("CW8.PA / SPY");
  await search.press("Enter");
  await expect(page.locator(".header")).toBeVisible();

  // Un ratio n'a ni comptes ni dividendes : seul « Résumé » reste disponible.
  await expect(page.locator(".section-tab[data-section='resume']")).toBeEnabled();
  for (const id of ["quantitatif", "dividende", "finance", "these", "valorisation", "momentum"]) {
    await expect(page.locator(`.section-tab[data-section='${id}']`)).toBeDisabled();
  }
});

test("la section « Thèse & Société » est accessible pour une action (#21)", async ({ page }) => {
  // Elle a été livrée au chantier #21 : plus « à venir », plus de repli sur Résumé.
  await page.goto("/#RI.PA/these");
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "these");
  await expect(page).toHaveURL(/#RI\.PA\/these$/);

  const these = page.locator(".section-tab[data-section='these']");
  await expect(these).toBeEnabled();
  await expect(these).toHaveAttribute("title", "Thèse & Société");

  // La section affiche les deux zones attendues : profil société et thèse.
  await expect(page.locator("#these-section h2", { hasText: "Profil société" })).toBeVisible();
  await expect(page.locator("#these-section .thesis-card .thesis-card-title")).toHaveText("Thèse");
});

test("la bande « Suivi » porte l'échéance et les points de contrôle (#21, #21.4)", async ({
  page,
  request,
}) => {
  // Le parcours exige des points de contrôle SUIVIS pour vérifier la ligne de
  // tête — la CI part d'un checkout neuf où il n'y en a aucun. On en sème deux
  // (pour que la barre existe aussi) et on les retire en sortie.
  const crees = [];
  for (const label of ["E2E point A", "E2E point B"]) {
    const r = await request.post("/api/checkpoints/RI.PA", { data: { label } });
    if (r.ok()) crees.push((await r.json()).id);
  }

  try {
    await page.goto("/#RI.PA/these");
    await expect(page.locator(".header")).toBeVisible();

    const suivi = page.locator(".suivi-card");
    await expect(suivi).toBeVisible();
    await expect(suivi.locator(".suivi-title")).toHaveText("Suivi");

    // L'échéance vit ICI et nulle part ailleurs sur la fiche (pas de doublon avec
    // l'agenda du profil société).
    await expect(suivi.locator(".suivi-label", { hasText: "Prochain résultat" })).toBeVisible();
    await expect(page.locator(".profile-card", { hasText: "Prochain résultat" })).toHaveCount(0);

    // #21.4 : une SEULE ligne de tête. Le compteur est sur la même ligne que
    // l'échéance, aligné à droite, et le libellé « Points de contrôle » a disparu
    // (le compteur seul suffit ; son intitulé accessible le dit au lecteur d'écran).
    await expect(suivi).not.toContainText("Points de contrôle");
    await expect(suivi.locator(".suivi-cp-head")).toHaveCount(0);
    const top = suivi.locator(".suivi-topline");
    await expect(top).toBeVisible();
    const count = suivi.locator(".suivi-count");
    await expect(count).toHaveText(/\d+\/\d+/);
    // L'intitulé doit être RÉELLEMENT exposé à l'arbre d'accessibilité — pas
    // seulement présent comme attribut (un `aria-label` sur un `<span>` sans rôle
    // est ignoré). On interroge donc le nœud `.sr-only` par son contenu.
    await expect(count.locator(".sr-only")).toHaveText(/\d+ point? validé?s? sur \d+ point?s? de contrôle/);
    await expect(count.locator('[aria-hidden="true"]')).toHaveText(/\d+\/\d+/);
    const yCount = (await count.boundingBox()).y;

    // Même ligne que le libellé d'échéance : les deux boîtes se chevauchent.
    const yLib = (await suivi.locator(".suivi-label", { hasText: "Prochain résultat" }).boundingBox()).y;
    expect(Math.abs(yCount - yLib)).toBeLessThan(12);
    // Poussé tout à droite de la carte (et pas collé au libellé).
    const cardBox = await suivi.boundingBox();
    const countBox = await count.boundingBox();
    expect(countBox.x + countBox.width).toBeGreaterThan(cardBox.x + cardBox.width * 0.8);

    await expect(suivi.locator(".suivi-add input")).toBeVisible();
    // Avec 2 points suivis, la barre de progression existe (#21.4 : jamais à 1).
    if (crees.length >= 2) {
      await expect(suivi.locator(".suivi-bar")).toBeVisible();
    }

    // Le compteur n'est PLUS dans l'en-tête de la carte thèse (il appartient à la
    // bande) : aucun « n/N » à côté du titre du document.
    const head = page.locator(".thesis-card .thesis-card-head");
    await expect(head.locator(".thesis-counter")).toHaveCount(0);
    await expect(head).not.toContainText("points de contrôle");
  } finally {
    // Restauration : on retire uniquement ce que ce test a créé (les points
    // préexistants de l'utilisateur ne sont pas touchés).
    for (const id of crees) await request.delete(`/api/checkpoints/${id}`);
  }
});

test("la thèse : sommaire dérivé, points de contrôle et éditeur (#21)", async ({ page }) => {
  // Parcours NON destructif : on ne modifie pas le contenu persisté (le test
  // e2e tourne contre la vraie base de l'utilisateur).
  await page.goto("/#RI.PA/these");
  await expect(page.locator(".header")).toBeVisible();

  // Le profil société est alimenté par /api/stock (aucun appel supplémentaire).
  const profil = page.locator(".profile-card");
  await expect(profil).toBeVisible();
  await expect(profil.locator(".profile-label", { hasText: "Direction générale" })).toBeVisible();

  // #21.4 : la grille du profil est fluide (plus de colonne fixe à moitié vide).
  // On lit les colonnes réellement calculées et l'alignement des valeurs.
  const grille = await page.evaluate(() => {
    const g = document.querySelector(".profile-grid");
    const cols = getComputedStyle(g).gridTemplateColumns.split(" ").filter(Boolean).length;
    const labels = [...document.querySelectorAll(".profile-card .profile-label")]
      .map((el) => el.getBoundingClientRect().x);
    const uniques = new Set(labels.map((x) => Math.round(x)));
    return {
      cols,
      largeur: g.getBoundingClientRect().width,
      card: document.querySelector(".profile-card").getBoundingClientRect().width,
      alignements: uniques.size,
      nbLignes: labels.length,
    };
  });
  expect(grille.cols).toBeGreaterThanOrEqual(2);
  // Largeur exploitée : la grille remplit la carte (moins le rembourrage).
  expect(grille.largeur).toBeGreaterThan(grille.card * 0.8);
  if (grille.nbLignes > 0) {
    // Toutes les valeurs démarrent au même x, dans chaque colonne.
    expect(grille.alignements).toBeLessThanOrEqual(grille.cols);
  }

  // #21.4 : sur TOUTE la plage étroite, la grille ne doit jamais déborder sa
  // carte ni tronquer une valeur. Un `minmax(420px, 1fr)` nu débordait de 360 à
  // 580 px (le track ne descend jamais sous son minimum) : le contrôle initial
  // n'avait été fait qu'à 700 px, où le contenu tenait encore.
  for (const w of [720, 620, 580, 500, 480, 414, 390, 360, 320]) {
    await page.setViewportSize({ width: w, height: 900 });
    await page.waitForTimeout(60);
    const debord = await page.evaluate(() => {
      const card = document.querySelector(".profile-card").getBoundingClientRect();
      const rows = [...document.querySelectorAll(".profile-card .profile-row")];
      const pire = Math.max(...rows.map((r) => r.getBoundingClientRect().right));
      const g = document.querySelector(".profile-grid");
      return {
        horsCarte: Math.round(pire - card.right),
        cols: getComputedStyle(g).gridTemplateColumns.split(" ").filter(Boolean).length,
        docDeborde: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });
    expect(debord.horsCarte, `@${w}px`).toBeLessThanOrEqual(1);
    if (w <= 620) expect(debord.cols, `@${w}px`).toBe(1);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // De la thèse, on ne présume pas du contenu : soit l'état vide (avec les trois
  // chemins + le rappel MCP), soit le document rendu avec son sommaire dérivé.
  const vide = page.locator(".thesis-empty");
  const corps = page.locator("#thesis-body");
  if (await vide.isVisible()) {
    // 3 boutons + le label d'import (stylé `.btn`, donc compté à part).
    await expect(page.locator(".thesis-empty-actions button.btn")).toHaveCount(3);
    await expect(page.locator(".thesis-empty-actions .thesis-file")).toHaveCount(1);
    await expect(page.locator(".thesis-mcp")).toContainText("MCP");
  } else {
    await expect(corps).toBeVisible();
    // Le sommaire n'existe que s'il y a au moins 2 titres, et chaque entrée du
    // sommaire pointe une ancre réellement présente (parité CA-TOC2).
    const entrees = await page.locator(".md-toc-item").count();
    if (entrees > 0) {
      expect(entrees).toBeGreaterThan(1);
      const cible = page.locator(".md-toc-item").first().locator("span").last();
      const slug = await page.locator("#thesis-body h1, #thesis-body h2").first().getAttribute("id");
      expect(slug).toBeTruthy();
      await page.locator(".md-toc-item").first().click();
      // Clic d'ancre : le routeur de hash n'est PAS touché.
      await expect(page).toHaveURL(/#RI\.PA\/these$/);
      await expect(cible).toBeVisible();
    }
  }

  // L'éditeur s'ouvre avec sa toolbar complète (aucun enregistrement à ce stade :
  // ouvrir puis fermer sans saisie ne déclenche pas d'écriture). L'action vit
  // dans l'en-tête de la CARTE thèse (#21).
  await page.locator(".thesis-card-head .btn", { hasText: /Écrire|Éditer/ }).click();
  await expect(page.locator("#thesis-editor")).toBeVisible();
  for (const titre of ["Titre de niveau 1", "Gras (⌘B)", "Liste de tâches", "Lien"]) {
    await expect(page.locator(`.md-toolbar button[title="${titre}"]`)).toBeVisible();
  }
  await expect(page.locator('.md-toolbar input[accept*="image"]')).toHaveCount(1);
  await page.locator(".thesis-card-head .btn", { hasText: "Terminé" }).click();
  await expect(page.locator(".thesis-card-head .btn", { hasText: /Écrire|Éditer/ })).toBeVisible();
});

test("le plan de la thèse se replie et se souvient de son état (#21.2)", async ({
  page,
  request,
}) => {
  // Le parcours exige une thèse AVEC sommaire (≥ 2 titres dans `tocMain`) et
  // assez longue pour défiler : on sème donc la fixture nous-mêmes — la CI part
  // d'un checkout neuf (`cache.sqlite` est gitignoré) où AUCUNE thèse n'existe.
  // On restaure l'état initial en sortie : la suite tourne contre la vraie base.
  const remplissage = "Paragraphe de remplissage pour rendre le document long. ";
  const MEMO =
    "# Thèse\n\n## Pitch\n\n" + remplissage.repeat(40) +
    "\n\n## Bull case\n\n" + remplissage.repeat(40) +
    "\n\n## Bear case\n\n" + remplissage.repeat(40) + "\n";
  const avant = await request.get("/api/thesis/RI.PA");
  const existait = avant.ok();
  const precedent = existait ? (await avant.json()).content : null;

  await request.put("/api/thesis/RI.PA", { data: { content: MEMO } });

  try {
    // Préférence locale au navigateur : on la remet à zéro pour un parcours
    // déterministe (le test ne doit pas dépendre de l'état du poste).
    await page.goto("/#RI.PA/these");
    await expect(page.locator(".header")).toBeVisible();
    await page.evaluate(() => window.localStorage.removeItem("obole.thesis.planOpen"));
    await page.reload();
    await expect(page.locator(".header")).toBeVisible();

    const handle = page.locator(".thesis-edge");
    const pin = page.locator(".thesis-pin");
    await expect(handle).toBeVisible();
    await expect(pin).toHaveAttribute("aria-expanded", "false");

    // Défaut : plan FERMÉ — la fiche est recentrée, l'onglet est masqué au repos.
    await expect(page.locator("#thesis-plan")).toBeHidden();
    await expect(page.locator(".thesis-flow")).toHaveClass(/plan-closed/);
    await expect(pin).not.toHaveClass(/open/);
    await expect(pin).toHaveCSS("opacity", "0");

    // La largeur de la fiche ne dépend PAS du plan (#21.3, CA-PL19) : la bande de
    // bord est absolue, donc contribution NULLE au layout. Preuve directe : sa
    // propre largeur vaut exactement le rembourrage de la carte, et retirer la
    // bande du flux ne change rien à la largeur mesurée.
    const mesure = await page.evaluate(() => {
      const card = document.querySelector("#thesis-card");
      const edge = document.querySelector(".thesis-edge");
      const cs = getComputedStyle(card);
      const base = card.clientWidth;
      edge.style.width = "300px";        // une bande large ne doit RIEN déplacer
      const apres = card.clientWidth;
      edge.style.width = "";
      return {
        base, apres,
        padRight: parseFloat(cs.paddingRight),
        bande: document.querySelector(".thesis-edge").getBoundingClientRect().width,
        card: document.querySelector(".thesis-card").getBoundingClientRect().width,
        main: document.querySelector(".thesis-main").getBoundingClientRect().width,
        plan: document.querySelector("#thesis-plan").getBoundingClientRect().width,
      };
    });
    expect(mesure.apres).toBe(mesure.base);
    expect(mesure.bande).toBe(mesure.padRight);
    const largeurFermee = mesure.base;
    const largeurMain = mesure.main;
    // La bande ne recouvre AUCUN pixel du corps de lecture (elle commence après).
    expect(mesure.main + mesure.padRight).toBeLessThanOrEqual(mesure.card);

    // …on OUVRE (survol du bord droit -> l'onglet apparaît -> clic)…
    await expect(pin).toHaveAttribute("title", "Afficher le plan");
    await handle.hover();
    await expect(pin).toHaveCSS("opacity", "1");
    await pin.click();
    await expect(pin).toHaveAttribute("aria-expanded", "true");
    await expect(pin).toHaveClass(/open/);
    await expect(page.locator("#thesis-plan")).toBeVisible();
    await expect(page.locator(".thesis-flow")).not.toHaveClass(/plan-closed/);
    // Plan affiché, curseur ÉLOIGNÉ de la bande : l'onglet reste faiblement
    // visible (on ne perd pas le seul moyen de refermer).
    await page.mouse.move(10, 10);
    await expect(pin).toHaveCSS("opacity", "0.45");
    // …et le survol rétablit la pleine opacité (défaut réel corrigé : le
    // sélecteur de survol « ouvert » était mort, la poignée restait à 45 %).
    await handle.hover();
    await expect(pin).toHaveCSS("opacity", "1");

    // …et on REFERME depuis le bord, plan affiché.
    await handle.hover();
    await pin.click();
    await expect(page.locator("#thesis-plan")).toBeHidden();
    await expect(pin).not.toHaveClass(/open/);
    const largeurFermee2 = await page.locator("#thesis-card").evaluate((el) => el.clientWidth);
    expect(largeurFermee2).toBe(largeurFermee);
    expect(largeurFermee).toBeGreaterThan(0);
    expect(largeurMain).toBeGreaterThan(0);
    // Plan masqué : la colonne n'occupe aucune largeur (elle n'existe pas).
    const planFerme = await page.evaluate(() => {
      const el = document.querySelector("#thesis-plan");
      return el.getBoundingClientRect().width;
    });
    expect(planFerme).toBe(0);

    // Préférence MÉMORISÉE : un rechargement la restitue.
    await handle.hover();
    await pin.click();
    await page.reload();
    await expect(page.locator(".header")).toBeVisible();
    await expect(pin).toHaveClass(/open/);
    await expect(page.locator("#thesis-plan")).toBeVisible();
    await page.evaluate(() => window.localStorage.removeItem("obole.thesis.planOpen"));
    await page.reload();
    await expect(page.locator(".header")).toBeVisible();

    // Défaut d'origine (#21.3) : on DESCEND au milieu du document — l'onglet est
    // épinglé, donc toujours atteignable, et referme bien le plan. C'est le
    // scénario exact rapporté (impossible d'ouvrir/fermer une fois descendu).
    await page.locator("#thesis-card").scrollIntoViewIfNeeded();
    await page.locator(".thesis-pin").click();
    await expect(page.locator("#thesis-plan")).toBeVisible();
    const hauteurDoc = await page.locator(".thesis-main").evaluate((el) => el.scrollHeight);
    expect(hauteurDoc).toBeGreaterThan(1000);      // il y a bien de quoi défiler
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(200);
    const scrolled = await page.evaluate(() => window.scrollY);
    expect(scrolled).toBeGreaterThan(0);
    // L'onglet est toujours épinglé au bord droit, à hauteur de fenêtre.
    const box = await pin.boundingBox();
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeLessThan(200);               // proche du haut de la fenêtre
    expect(box.width).toBe(mesure.padRight);       // 22 px : la bande de bord
    await handle.hover();
    await expect(pin).toBeVisible();
    await pin.click();
    await expect(page.locator("#thesis-plan")).toBeHidden();

    // En édition, le plan ET sa poignée disparaissent (une seule surface de travail).
    await page.locator(".thesis-card-head .btn", { hasText: /Écrire|Éditer/ }).click();
    await expect(page.locator("#thesis-editor")).toBeVisible();
    await expect(page.locator("#thesis-plan")).toBeHidden();
    await expect(handle).toBeHidden();
    await page.locator(".thesis-card-head .btn", { hasText: "Terminé" }).click();
  } finally {
    // Remise à l'état par défaut de la préférence + restauration de la base.
    await page.evaluate(() => window.localStorage.removeItem("obole.thesis.planOpen"));
    if (existait) await request.put("/api/thesis/RI.PA", { data: { content: precedent } });
    else await request.delete("/api/thesis/RI.PA");
  }
});

test("une fiche sans comptes explique l'indisponibilité par le manque de données", async ({
  page,
}) => {
  await page.goto("/");
  const search = page.locator(".searchbar .search-wrap input.search-input");
  await search.fill("CW8.PA / SPY");
  await search.press("Enter");
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab[data-section='quantitatif']")).toHaveAttribute(
    "title",
    "Quantitatif — aucune donnée pour ce titre",
  );
});

test("coquille : le rail est sticky, actif par espace, et Paramètres est en pied", async ({ page }) => {
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  // Sticky : une fois le rail collé (défilement engagé), il ne bouge plus à
  // l'écran, même quand la page continue de descendre. Mesurer avant le premier
  // défilement comparerait la position de flux à la position collée — deux états
  // différents, et un écart de `top` attendu.
  await page.mouse.wheel(0, 600);
  await page.waitForTimeout(200);
  const colle = await page.locator(".app-rail").boundingBox();
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  expect(colle.y).toBeGreaterThanOrEqual(0);
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(200);
  const colle2 = await page.locator(".app-rail").boundingBox();
  expect(Math.abs(colle2.y - colle.y)).toBeLessThanOrEqual(1);
  expect(colle2.y).toBeGreaterThanOrEqual(0);

  // Au repos, c'est « Analyse » qui est actif — la fiche est l'état par défaut.
  await expect(page.locator(".app-rail-btn[data-space='analyse']")).toHaveAttribute(
    "aria-current",
    "page",
  );

  // Paramètres vit en pied de rail : après Watchlist, et séparé par un filet.
  const boxes = await page.evaluate(() => {
    const b = (s) => document.querySelector(s).getBoundingClientRect();
    return {
      watch: b(".app-rail-btn[data-space='watchlist']").bottom,
      settings: b(".app-rail-btn[data-space='settings']").top,
      border: getComputedStyle(document.querySelector(".app-rail-foot")).borderTopWidth,
    };
  });
  expect(boxes.settings).toBeGreaterThan(boxes.watch);
  expect(boxes.border).not.toBe("0px");

  // Cliquer la marque ramène à l'accueil : plus de fiche, plus de hash.
  await page.locator(".app-brand").click();
  await expect(page.locator(".header")).toHaveCount(0);
  await expect(page).toHaveURL(/\/$/);
});

test("coquille : repli responsive du rail et largeur du contenu", async ({ page }) => {
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  const mesure = () =>
    page.evaluate(() => {
      const rail = document.querySelector(".app-rail");
      const main = document.querySelector(".app-main");
      const labels = [...document.querySelectorAll(".app-rail-label")];
      return {
        rail: Math.round(rail.getBoundingClientRect().width),
        railH: Math.round(rail.getBoundingClientRect().height),
        railDir: getComputedStyle(rail.parentElement).display,
        main: Math.round(main.getBoundingClientRect().width),
        labelsVisibles: labels.filter((l) => l.getBoundingClientRect().width > 1).length,
        deborde:
          document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });

  // Le redimensionnement déclenche le redraw Plotly (`responsive: true`) : un
  // scroll horizontal transitoire apparaît le temps d'une frame. On interroge
  // donc `expect.poll` — la propriété vérifiée est « finit par tenir », pas
  // « tient dans la milliseconde qui suit le resize ».
  const attendreStable = async (prop, attendu, nom) => {
    await expect
      .poll(async () => (await mesure())[prop], { timeout: 5000, message: nom })
      .toBe(attendu);
  };
  const attendreDebordementNul = (nom) =>
    expect
      .poll(async () => (await mesure()).deborde, { timeout: 5000, message: nom })
      .toBe(false);

  // ≥ 1280 px : rail étiqueté, tous les libellés rendus.
  for (const w of [1600, 1440, 1280]) {
    await page.setViewportSize({ width: w, height: 900 });
    await attendreStable("rail", 176, `@${w}px`);
    expect((await mesure()).labelsVisibles, `@${w}px : libellés visibles`).toBe(6);
    await attendreDebordementNul(`@${w}px : débordement`);
  }

  // 1279–900 px : icônes seules (libellés retirés du flux visuel), contenu préservé.
  for (const w of [1279, 1100, 900]) {
    await page.setViewportSize({ width: w, height: 900 });
    await attendreStable("rail", 68, `@${w}px`);
    expect((await mesure()).labelsVisibles, `@${w}px : libellés masqués`).toBe(0);
    await attendreDebordementNul(`@${w}px : débordement`);
  }

  // < 900 px : bandeau horizontal, aucun débordement.
  for (const w of [899, 720, 390]) {
    await page.setViewportSize({ width: w, height: 900 });
    await attendreDebordementNul(`@${w}px : débordement`);
    const m = await mesure();
    expect(m.railH, `@${w}px : bandeau horizontal`).toBeLessThan(90);
    expect(m.rail, `@${w}px : bandeau pleine largeur`).toBeGreaterThan(250);
  }

  // Le contenu exploite la largeur : ≥ 1300 px à 1600 px de fenêtre.
  await page.setViewportSize({ width: 1600, height: 900 });
  await attendreStable("rail", 176, "@1600px");
  expect((await mesure()).main).toBeGreaterThanOrEqual(1300);
});

// --- Espaces en pages (coquille) -------------------------------------------
//
// Les cinq espaces ne sont plus des modales plein écran posées SUR la fiche :
// ce sont des vues sœurs dans `.app-main`, sur lesquelles `x-show` bascule. Le
// rail reste donc visible ET cliquable — c'est tout l'objet du chantier, et ce
// que ces mesures verrouillent : une modale 98vw recouvrirait le rail, une vue
// non.

const ESPACES = [
  ["indices", ".app-view.view-indices"],
  ["screener", ".app-view.view-screener"],
  ["portfolio", ".app-view.view-portfolio"],
  ["watchlist", ".app-view.view-watchlist"],
  ["settings", ".app-view.view-settings"],
];

test("espaces : chaque espace est une vue, sans overlay, avec le rail cliquable", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page.locator(".app-rail")).toBeVisible();

  for (const [id, selecteur] of ESPACES) {
    await page.locator(`.app-rail-btn[data-space='${id}']`).click();
    const vue = page.locator(selecteur);
    await expect(vue, `${id} : vue visible`).toBeVisible();

    // 1. Aucune couche plein écran pour un espace : le fond n'est pas assombri
    //    et la fiche a bien cédé la place. `x-show` laisse les autres blocs dans
    //    le DOM en `display: none` : on ne compte que les VISIBLES.
    const overlaysVisibles = await page.evaluate(
      () =>
        [...document.querySelectorAll(".modal-overlay")].filter(
          (el) => el.getBoundingClientRect().height > 0,
        ).length,
    );
    expect(overlaysVisibles, `${id} : aucune modale ouverte`).toBe(0);

    // 2. Le rail reste à sa place et à portée de clic.
    const rail = await page.locator(".app-rail").boundingBox();
    expect(rail, `${id} : rail mesurable`).not.toBeNull();
    await expect(page.locator(".app-rail-btn[data-space='analyse']")).toBeVisible();

    // 3. La vue commence à DROITE du rail : elle ne le recouvre pas.
    const box = await vue.boundingBox();
    expect(box.x, `${id} : vue à droite du rail`).toBeGreaterThanOrEqual(
      rail.x + rail.width - 1,
    );

    // 4. Aucune croix de fermeture dans l'en-tête de la vue.
    await expect(
      vue.locator(".view-head button", { hasText: "✕" }),
      `${id} : pas de croix (on sort par le rail)`,
    ).toHaveCount(0);
  }

  // « Analyse » ramène la fiche, et l'analyse redevient visible.
  await page.locator(".app-rail-btn[data-space='analyse']").click();
  await expect(page.locator(".app-view.view-analyse")).toBeVisible();
  await expect(page.locator(".app-view.view-settings")).toBeHidden();
});

test("espaces : un clic de rail bascule directement d'une vue à l'autre", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='screener']").click();
  await expect(page.locator(".app-view.view-screener")).toBeVisible();

  // Changement direct : la vue précédente cède la place sans fermeture préalable.
  await page.locator(".app-rail-btn[data-space='watchlist']").click();
  await expect(page.locator(".app-view.view-watchlist")).toBeVisible();
  await expect(page.locator(".app-view.view-screener")).toBeHidden();

  // Et l'entrée active du rail suit l'espace affiché.
  await expect(page.locator(".app-rail-btn[data-space='watchlist']")).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.locator(".app-rail-btn[data-space='screener']")).toHaveAttribute(
    "aria-current",
    "false",
  );
});

test("espaces : la vue défile avec le document, sans hauteur imposée", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='settings']").click();
  const vue = page.locator(".app-view.view-settings");
  await expect(vue).toBeVisible();

  // Pas de `96vh` hérité de la modale : une page n'impose pas sa hauteur.
  const style = await vue.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { height: cs.height, overflowY: cs.overflowY, maxHeight: cs.maxHeight };
  });
  expect(style.maxHeight, "aucune hauteur maximale imposée").toBe("none");
  expect(style.overflowY, "la vue ne défile pas sur elle-même").not.toBe("auto");

  // Le document défile bien à la place (le rail, lui, reste collé).
  const defilable = await page.evaluate(
    () => document.documentElement.scrollHeight > window.innerHeight + 20,
  );
  if (defilable) {
    // On mesure APRÈS le premier défilement : avant, le rail est encore à sa
    // position de flux (20 px de padding de page), pas encore collé à 16 px.
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
    const colle = await page.locator(".app-rail").boundingBox();
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(200);
    const encore = await page.locator(".app-rail").boundingBox();
    expect(Math.round(encore.y), "rail collé pendant le défilement de la vue").toBe(
      Math.round(colle.y),
    );
    expect(Math.abs(Math.round(colle.y) - 16), "rail à --head-top").toBeLessThanOrEqual(1);
  }
});

test("espaces : Échap revient à Analyse, la marque quitte tout", async ({ page }) => {
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='screener']").click();
  await expect(page.locator(".app-view.view-screener")).toBeVisible();

  // Échap referme l'espace : c'est le clavier qui sort d'une vue, comme il
  // sortait d'une modale avant ce chantier.
  await page.keyboard.press("Escape");
  await expect(page.locator(".app-view.view-screener")).toBeHidden();
  await expect(page.locator(".app-view.view-analyse")).toBeVisible();

  // La marque ramène à l'accueil (aucune fiche, aucun espace).
  await page.locator(".app-rail-btn[data-space='watchlist']").click();
  await expect(page.locator(".app-view.view-watchlist")).toBeVisible();
  await page.locator(".app-brand").click();
  await expect(page.locator(".app-view.view-watchlist")).toBeHidden();
  await expect(page.locator(".app-view.view-analyse")).toBeVisible();
});

test("espaces : le graphe héro garde sa largeur au retour d'un espace", async ({ page }) => {
  await page.goto("/#RI.PA/resume");
  await expect(page.locator("#chart svg").first()).toBeVisible();

  const largeur = () =>
    page.evaluate(() => {
      const svg = document.querySelector("#chart svg");
      const hote = document.querySelector("#chart");
      return {
        svg: Math.round(svg.getBoundingClientRect().width),
        hote: Math.round(hote.getBoundingClientRect().width),
      };
    });

  const avant = await largeur();
  expect(avant.svg, "graphe tracé à la largeur de son conteneur").toBeGreaterThan(
    avant.hote - 8,
  );

  // Passer par une vue masque la fiche (`display: none`) : Plotly voit alors une
  // largeur nulle. Sans redessin au retour, le graphe revient à cette mesure.
  await page.locator(".app-rail-btn[data-space='settings']").click();
  await expect(page.locator(".app-view.view-settings")).toBeVisible();
  await page.locator(".app-rail-btn[data-space='analyse']").click();
  await expect(page.locator(".app-view.view-analyse")).toBeVisible();
  await expect(page.locator("#chart svg").first()).toBeVisible();

  await expect
    .poll(async () => (await largeur()).svg, { timeout: 10_000 })
    .toBeGreaterThan(avant.hote - 8);
});

test("espaces : ouvrir une vue repart du haut, re-cliquer ne détruit rien", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/");

  // 1. On ouvre une vue, on descend, puis on change d'espace : la page suivante
  //    se lit DEPUIS SON TITRE. `x-show` ne touche pas au défilement du
  //    document, donc sans `scrollTo(0,0)` on arrivait au milieu (titre hors
  //    écran, mesuré à y = −568).
  await page.locator(".app-rail-btn[data-space='settings']").click();
  await expect(page.locator(".app-view.view-settings")).toBeVisible();
  await page.mouse.wheel(0, 500);
  await page.waitForTimeout(200);
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  await page.locator(".app-rail-btn[data-space='watchlist']").click();
  await expect(page.locator(".app-view.view-watchlist")).toBeVisible();
  expect(await page.evaluate(() => window.scrollY), "vue ouverte en haut de page").toBe(0);
  const titre = await page.locator(".app-view.view-watchlist .view-head h3").boundingBox();
  expect(titre.y, "titre de la vue visible").toBeGreaterThan(0);

  // 2. Re-cliquer l'entrée DÉJÀ active ne relance ni réinitialisation ni appel
  //    réseau : sur le Screener, cela vidait les résultats et revenait à
  //    l'accueil. Le geste est un réflexe (« où suis-je ? »).
  await page.route("**/api/screener/run", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "test",
        count: 3,
        tickers_count: 3,
        rows: ["RI.PA", "AI.PA", "MC.PA"].map((ticker, i) => ({
          ticker,
          name: `Titre ${i}`,
          market_cap: 2e9,
          z: -1,
          pente_pct: 6,
          ecart_type_pct: 22,
          pot_5y_pct: 30,
          pot_10y_pct: 60,
          trend_bullish: 1,
          roe_pct: 12,
          per: 14,
          p_b: 1.4,
          p_fcf: 12,
          fcf_yield_pct: 5,
          quality_score: 60,
          colors: {},
        })),
      }),
    }),
  );
  await page.locator(".app-rail-btn[data-space='screener']").click();
  const vue = page.locator(".app-view.view-screener");
  await expect(vue).toBeVisible();
  await vue.locator(".screen-home").waitFor();
  await vue.locator(".screen-preset").first().click();
  await expect(vue.locator(".screen-table")).toBeVisible({ timeout: 15_000 });
  const lignes = await vue.locator(".screen-table tbody tr").count();
  expect(lignes).toBe(3);

  await page.locator(".app-rail-btn[data-space='screener']").click();
  await page.waitForTimeout(300);
  expect(
    await vue.locator(".screen-table tbody tr").count(),
    "re-clic : les résultats sont conservés",
  ).toBe(lignes);
  await expect(vue.locator(".screen-home"), "re-clic : pas de retour à l'accueil").toBeHidden();
});

test("espaces : les graphes d'une vue se remettent à l'échelle à l'entrée", async ({ page }) => {
  // Correctif de test pré-existant : la base e2e n'a aucun portefeuille seedé,
  // donc `#pf-summary-plot` n'avait rien à tracer et le test échouait sur la
  // base comme sur les branches. On mocke un résumé minimal NON VIDE pour que
  // le graphe existe — l'intention testée reste le redimensionnement à l'entrée.
  const summary = {
    dates: ["2025-01-02", "2025-02-03", "2025-03-03", "2025-04-01"],
    period: "1a",
    period_start: null,
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    portfolio: [100, 101, 103, 104],
    benchmark_curve: [100, 100.5, 101.5, 102],
    kpis: {},
    accounts: [],
    holdings: [],
    account: null,
    top: [],
    flop: [],
    warnings: [],
  };
  await page.route("**/api/portfolio/summary**", (route) => route.fulfill({ json: summary }));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  const trace = page.locator("#pf-summary-plot");
  await expect(trace.locator("svg").first()).toBeVisible({ timeout: 30_000 });

  const mesure = () =>
    page.evaluate(() => {
      const hote = document.querySelector("#pf-summary-plot");
      const svg = hote?.querySelector("svg");
      return {
        hote: Math.round(hote?.getBoundingClientRect().width || 0),
        svg: Math.round(svg?.getBoundingClientRect().width || 0),
      };
    });
  const large = await mesure();
  expect(large.svg, "tracé à la largeur de l'hôte").toBeGreaterThan(large.hote - 8);

  // La fenêtre rétrécit PENDANT que la vue est masquée : `responsive: true`
  // n'écoute que `window.resize`, donc rien ne corrige la largeur du SVG. Sans
  // redimensionnement à l'entrée, le tracé reste à 710 px dans un hôte de
  // 378 px et la carte déborde.
  await page.locator(".app-rail-btn[data-space='analyse']").click();
  await expect(page.locator(".app-view.view-analyse")).toBeVisible();
  await page.setViewportSize({ width: 1000, height: 900 });
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await expect(page.locator(".app-view.view-portfolio")).toBeVisible();

  await expect
    .poll(async () => {
      const m = await mesure();
      return m.svg > 0 && Math.abs(m.svg - m.hote) < 8;
    }, { timeout: 10_000 })
    .toBe(true);
});
