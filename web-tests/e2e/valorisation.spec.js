import { expect, test } from "@playwright/test";

// Section Valorisation (#20) : calculatrice de prix juste pleine largeur.
// On vérifie le rendu RÉEL — KPI, bascule Graphique/Matrice, heatmap, paramètres,
// puis les courbes continues de la partie 2 (jamais de barres).

test("section Valorisation : KPI, graphique et bascule Matrice", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // En-tête : titre + segmented control.
  await expect(page.locator(".val-head h2")).toHaveText("Calculatrice de prix juste");
  await expect(page.locator(".seg-btn", { hasText: "Graphique" })).toBeVisible();
  await expect(page.locator(".seg-btn", { hasText: "Matrice" })).toBeVisible();

  // Trois KPI : prix juste (devise), rendement estimé (%/an), marge de sécurité (%).
  const kpis = page.locator(".val-kpi");
  await expect(kpis).toHaveCount(3);
  await expect(kpis.nth(0)).toContainText("Prix juste");
  await expect(kpis.nth(0)).toContainText("EUR");
  await expect(kpis.nth(1)).toContainText("Rendement estimé");
  await expect(kpis.nth(1)).toContainText("%/an");
  await expect(kpis.nth(2)).toContainText("Marge de sécurité");

  // Graphique : courbe Plotly tracée (cours + valorisation + dividende + projection).
  await expect
    .poll(async () => page.locator("#val-chart .scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(2);

  // Badges prix juste et projeté (annotations sur le graphe).
  await expect
    .poll(async () => page.locator("#val-chart .annotation").count(), { timeout: 20_000 })
    .toBeGreaterThanOrEqual(2);

  // Légende CAGR sous le graphe (croissance annualisée des séries).
  const cagr = page.locator(".val-cagr-legend");
  await expect(cagr).toBeVisible();
  await expect(cagr).toContainText("CAGR");

  // Bascule en Matrice : la heatmap apparaît avec 15 lignes et une cellule active.
  await page.locator(".seg-btn", { hasText: "Matrice" }).click();
  const matrix = page.locator(".val-matrix");
  await expect(matrix).toBeVisible();
  await expect(matrix.locator("tbody tr")).toHaveCount(15);
  await expect(matrix.locator("thead th")).toHaveCount(16); // coin + 15 multiples
  await expect(matrix.locator(".val-active-cell")).toHaveCount(1);
  // Les cellules portent un bucket de couleur (ancré sur la cible).
  await expect(matrix.locator("td.vb-3").first()).toBeVisible();
  // La matrice tient en pleine largeur : AUCUN scroll horizontal (15 colonnes
  // visibles d'un coup, libellés et valeurs à 1 décimale).
  const scroll = page.locator(".val-matrix-scroll");
  const dims = await scroll.evaluate((el) => ({ scrollW: el.scrollWidth, clientW: el.clientWidth }));
  expect(dims.scrollW).toBeLessThanOrEqual(dims.clientW + 1);
  // Valeurs de cellule à 1 décimale maximum (ex. « 12,3% », pas « 12,34% »).
  const cellText = await matrix.locator("td").nth(20).innerText();
  expect(cellText).toMatch(/^-?\d+(,\d)?%$/);
});

test("section Valorisation : la barre Paramètres recalcule les KPI en direct", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // Barre Paramètres compacte (Option A) : champs courts, sans titre « Paramètres ».
  const bar = page.locator(".val-params");
  await expect(bar).toContainText("Données");
  await expect(bar).toContainText("Période");
  await expect(bar).toContainText("Multiple final");
  await expect(bar).toContainText("Rendement cible");
  await expect(bar).toContainText("Dividendes");
  // « Communauté » n'existe pas (mono-poste) : la ligne a été retirée.
  await expect(bar).not.toContainText("Communauté");

  // Augmenter la croissance fait monter le rendement estimé (recalcul live).
  const retKpi = page.locator(".val-kpi").nth(1);
  const before = await retKpi.innerText();
  await page.locator(".val-params input[type=number]").first().fill("20");
  await page.locator(".val-params input[type=number]").first().dispatchEvent("input");
  await expect(retKpi).not.toHaveText(before);
});

test("section Valorisation : enregistrer fixe le prix juste du Résumé", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  const fairKpi = page.locator(".val-kpi").nth(0);
  const fairText = (await fairKpi.innerText()).split("\n").pop().trim();

  await page.locator(".val-bar-actions .btn-icon[aria-label='Enregistrer']").click();
  await page.waitForTimeout(2500);

  // Le Résumé affiche désormais CE prix juste (valeur enregistrée prioritaire).
  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();
  const row = page.locator(".summary-row", { hasText: "Prix juste" }).first();
  await expect(row.locator(".s-value")).toContainText(fairText.split(" ")[0]);

  // Réinitialiser efface la valeur (retour à la droite de régression) — avec
  // confirmation (geste destructeur, cohérent avec le reste de l'app).
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await page.locator(".val-bar-actions .btn-icon[aria-label='Réinitialiser']").click();
  await page.waitForTimeout(2500);
  const cleared = await (await page.request.get("/api/valuation/RI.PA")).json();
  expect(cleared.saved).toBeNull();
});

test("section Valorisation : courbes continues (jamais de barres)", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // Partie 2 : croissance par action (4 cartes) + multiples, en courbes (scatterlayer).
  for (const title of ["BNPA par action", "FCF par action", "CA par action", "Actif net par action", "P/E", "P/FCF"]) {
    const card = page.locator(".card.mini:visible", { hasText: title }).first();
    await expect(card).toBeVisible();
    await expect
      .poll(async () => card.locator(".scatterlayer .trace").count(), { timeout: 20_000 })
      .toBeGreaterThan(0);
    // Aucun barlayer : ce sont des courbes continues.
    await expect(card.locator(".barlayer .trace")).toHaveCount(0);
  }

  // Courbes de CROISSANCE lissées (spline) : coins arrondis, bleu inchangé.
  const bnpa = page.locator("#mc-BNPA-par-action");
  const bnpaStyle = await bnpa.evaluate((el) => ({ shape: el.data[0].line.shape, color: el.data[0].line.color }));
  expect(bnpaStyle.shape).toBe("spline");
  expect(bnpaStyle.color).toBe("#2563EB");
  // Points annuels discrets (cercles blancs bordés bleu) sur les courbes de croissance.
  const bnpaMarker = await bnpa.evaluate((el) => el.data[0].marker);
  expect(bnpaMarker.color).toBe("#fff");
  expect(bnpaMarker.line.color).toBe("#2563EB");
  // Les multiples (série quotidienne) restent nets, SANS marqueurs.
  const pe = page.locator("#mc-P-E");
  const peStyle = await pe.evaluate((el) => el.data[0].line.shape);
  expect(peStyle).toBeUndefined();
  const peMarker = await pe.evaluate((el) => el.data[0].marker || null);
  expect(peMarker).toBeNull();
  // Ligne de valorisation du graphique prix juste : OR, lissée, avec fond doré pâle.
  const hero = page.locator("#val-chart");
  const valo = await hero.evaluate((el) => {
    const t = el.data.find((tr) => (tr.name || "").startsWith("Valorisation"));
    return t ? { shape: t.line.shape, color: t.line.color, fill: t.fill, fillcolor: t.fillcolor } : null;
  });
  expect(valo.shape).toBe("spline");
  expect(valo.color).toBe("#F59E0B");
  expect(valo.fill).toBe("tozeroy");
  expect(valo.fillcolor).toBe("rgba(245,158,11,.08)");
  // La projection est dorée pointillée (Baggr) et porte aussi le fond doré.
  const proj = await hero.evaluate((el) => {
    const t = el.data.find((tr) => tr.name === "Projection");
    return t ? { color: t.line.color, dash: t.line.dash, fill: t.fill } : null;
  });
  expect(proj).toEqual({ color: "#F59E0B", dash: "dot", fill: "tozeroy" });
});

test("section Valorisation : boutons icônes (sans emoji) et graphe étalé (breakout)", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // Actions = 3 boutons icônes SVG, aucun emoji.
  const actions = page.locator(".val-bar-actions");
  await expect(actions.locator(".btn-icon")).toHaveCount(3);
  await expect(actions.locator(".btn-icon .ico")).toHaveCount(3);
  expect((await actions.innerText()).trim()).toBe("");
  // Accessibles par aria-label.
  await expect(actions.locator("[aria-label='Enregistrer']")).toBeVisible();
  await expect(actions.locator("[aria-label='Télécharger']")).toBeVisible();
  await expect(actions.locator("[aria-label='Réinitialiser']")).toBeVisible();

  // Breakout : la section Valorisation est plus large que sa colonne (.fiche-main),
  // sans provoquer de scroll horizontal.
  const dims = await page.evaluate(() => {
    const sec = document.querySelector(".section-breakout");
    const main = document.querySelector(".fiche-main");
    return {
      secW: Math.round(sec.getBoundingClientRect().width),
      mainW: Math.round(main.getBoundingClientRect().width),
      scrollW: document.documentElement.scrollWidth,
      winW: window.innerWidth,
    };
  });
  expect(dims.secW).toBeGreaterThan(dims.mainW);
  expect(dims.scrollW).toBeLessThanOrEqual(dims.winW);

  // Le tracé Plotly occupe TOUTE la largeur du conteneur (sinon il retombe sur sa
  // largeur par défaut ~700px et laisse un grand vide à droite — régression vue
  // quand la section était tracée pendant son masquage `x-show`).
  const fit = await page.evaluate(() => {
    const gd = document.querySelector("#val-chart");
    return { divW: Math.round(gd.getBoundingClientRect().width), layoutW: gd._fullLayout?.width };
  });
  expect(Math.abs(fit.layoutW - fit.divW)).toBeLessThanOrEqual(2);

  // Les AUTRES sections gardent la largeur de leur colonne (garde-fou anti-régression).
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();
  const other = await page.evaluate(() => {
    // Section RÉELLEMENT affichée (x-show masque les autres) : on exclut le
    // breakout et les sections cachées, sinon on lirait une largeur de 0.
    const sec = [...document.querySelectorAll(".section")]
      .find((s) => !s.classList.contains("section-breakout") && s.getBoundingClientRect().width > 0);
    const main = document.querySelector(".fiche-main");
    return {
      secW: Math.round(sec.getBoundingClientRect().width),
      mainW: Math.round(main.getBoundingClientRect().width),
    };
  });
  expect(other.secW).toBeGreaterThan(0);
  expect(other.secW).toBeLessThanOrEqual(other.mainW);
});

test("section Valorisation : zoom plein écran d'une courbe continue (sans requête)", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // Chaque carte de la partie 2 est extensible (patron Dividend Yield).
  const card = page.locator(".card.mini:visible", { hasText: "P/E" }).first();
  await card.locator(".expand-btn").click();

  const modal = page.locator(".modal-detail", { hasText: "P/E" });
  await expect(modal).toBeVisible();
  await expect
    .poll(async () => modal.locator("#chart-detail-plot .scatterlayer .trace").count(), {
      timeout: 20_000,
    })
    .toBeGreaterThan(0);

  // Presets de période + curseur à deux poignées SOUS le graphe.
  await expect(modal.locator(".period-chip", { hasText: "5A" })).toBeVisible();
  const chartBox = await modal.locator("#chart-detail-plot").boundingBox();
  const sliderBox = await modal.locator(".dual-slider").boundingBox();
  expect(sliderBox.y).toBeGreaterThan(chartBox.y + chartBox.height - 1);

  // Déplacer une poignée change la plage partagée (curseur fonctionnel).
  await modal.locator(".period-chip", { hasText: "MAX" }).click();
  const before = (await modal.locator(".detail-range").innerText()).trim();
  await modal.locator(".dual-slider .ds-min").evaluate((el) => {
    el.value = String(Math.floor(Number(el.max) * 0.5));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(modal.locator(".detail-range")).not.toHaveText(before);

  await page.keyboard.press("Escape");
  await expect(modal).not.toBeVisible();
});
