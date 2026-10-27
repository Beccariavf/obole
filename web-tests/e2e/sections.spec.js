import { expect, test } from "@playwright/test";

// Refonte #16 : la fiche n'affiche qu'une section à la fois, pilotée par le
// ruban d’onglets horizontaux (libellés lisibles) et par le deep-link `#TICKER/section`.

test("fiche RI.PA : les onglets pilotent la section affichée", async ({ page }) => {
  await page.goto("/");

  const search = page.locator(".searchbar .search-wrap input.search-input");
  await search.fill("RI.PA");
  await search.press("Enter");
  await expect(page.locator(".header")).toBeVisible();

  // Le ruban expose les 6 sections dans l’ordre validé (identifiants stables,
  // indépendants du libellé d'infobulle qui peut être enrichi).
  const rail = page.locator(".section-tabs .section-tab");
  await expect(rail).toHaveCount(6);
  expect(await rail.evaluateAll((els) => els.map((e) => e.dataset.section))).toEqual([
    "resume",
    "quantitatif",
    "dividende",
    "finance",
    "these",
    "valorisation",
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
  expect(labels).toHaveLength(6);
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
  for (const id of ["quantitatif", "dividende", "finance", "these", "valorisation"]) {
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
