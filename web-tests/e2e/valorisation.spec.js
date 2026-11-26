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

  // En-tête de la carte à couches : titre + ligne de statut.
  await expect(page.locator(".val-hero-title")).toContainText("Prix et valorisation");
  const status = page.locator(".val-hero-status");
  await expect(status).toContainText("Cours");
  await expect(status).toContainText("valorisation");

  // Graphique : courbe Plotly tracée (cours + valorisation + scénario + prix juste).
  await expect
    .poll(async () => page.locator("#val-chart .scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(2);

  // Pastilles-interrupteurs HTML (pas de légende Plotly) : cours et valorisation
  // sont fixes, les trois couches sont des boutons `aria-pressed`.
  const toggles = page.locator(".val-layer.val-toggle");
  await expect(toggles).toHaveCount(3);
  for (const button of await toggles.all()) {
    await expect(button).toHaveAttribute("aria-pressed", /true|false/);
  }
  // Défaut : couloir et dividende allumés, scénarios éteints.
  await expect(page.locator(".val-toggle", { hasText: "Sous / sur-évalué" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect(page.locator(".val-toggle", { hasText: "Scénarios" }))
    .toHaveAttribute("aria-pressed", "false");
  await expect(page.locator(".val-toggle", { hasText: "Dividende" }))
    .toHaveAttribute("aria-pressed", "true");

  // Badges prix juste, scénario central et repères de dates (annotations).
  await expect
    .poll(async () => page.locator("#val-chart .annotation").count(), { timeout: 20_000 })
    .toBeGreaterThanOrEqual(2);

  // Bâton de l'année en cours : creux (fond blanc) exactement quand le survol
  // l'annonce — jamais l'inverse.
  const bar = await page.evaluate(() => {
    const trace = document.querySelector("#val-chart").data.find((t) => t.type === "bar");
    if (!trace) return null;
    return {
      white: trace.marker.color.filter((c) => c === "#FFFFFF").length,
      hollow: trace.customdata.filter(Boolean).length,
    };
  });
  if (bar) expect(bar.white).toBe(bar.hollow);

  // Pied de carte : CAGR du cours, de la métrique et du dividende.
  const foot = page.locator(".val-foot");
  await expect(foot).toBeVisible();
  await expect(foot).toContainText("%/an");
  await expect(page.locator(".val-cagr-legend")).toHaveCount(0);

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
  // Ligne de valorisation du graphe prix juste : ambre (C.valo), en ESCALIER
  // (`hv`), sans remplissage ni lissage.
  const hero = page.locator("#val-chart");
  const valo = await hero.evaluate((el) => {
    const t = el.data.find((tr) => tr.name === "Valorisation");
    return t ? { shape: t.line.shape, color: t.line.color, fill: t.fill ?? null } : null;
  });
  expect(valo).toEqual({ shape: "hv", color: "#D97706", fill: null });
  // Le scénario central est ambre pointillé ; il relie le cours à l'horizon.
  const proj = await hero.evaluate((el) => {
    const t = el.data.find((tr) => tr.name === "Central");
    return t ? { color: t.line.color, dash: t.line.dash } : null;
  });
  expect(proj).toEqual({ color: "#D97706", dash: "dot" });
  // Le prix juste est un rond creux POSÉ SUR aujourd'hui, pas une ligne dans le passé.
  const fair = await hero.evaluate((el) => {
    const t = el.data.find((tr) => tr.name === "Prix juste");
    const last = el.data.find((tr) => tr.name === "Cours").x.slice(-1)[0];
    return t ? { mode: t.mode, lastX: t.x[t.x.length - 1], last } : null;
  });
  expect(fair.mode).toBe("markers");
  expect(fair.lastX).toBe(fair.last);
});

test("section Valorisation : les trois bascules redessinent sans requête", async ({ page }) => {
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();
  await expect
    .poll(async () => page.locator("#val-chart .scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(2);

  // Aucune requête réseau ne doit partir d'un clic sur une pastille.
  const apiCalls = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/")) apiCalls.push(req.url());
  });
  const traces = () => page.evaluate(() => document.querySelector("#val-chart").data.length);
  const barTraces = () => page.evaluate(
    () => document.querySelector("#val-chart").data.filter((t) => t.type === "bar").length,
  );

  const base = await traces();
  // Scénarios : éteints par défaut ; allumés, ils ajoutent les deux bornes de
  // l'éventail (l'aire est portée par la borne optimiste).
  const scenarios = page.locator(".val-toggle", { hasText: "Scénarios" });
  await scenarios.click();
  await expect(scenarios).toHaveAttribute("aria-pressed", "true");
  await expect.poll(traces).toBe(base + 2);
  await scenarios.click();
  await expect(scenarios).toHaveAttribute("aria-pressed", "false");
  await expect.poll(traces).toBe(base);

  // Couloir : quatre traces de remplissage (deux baselines + deux aires).
  const couloir = page.locator(".val-toggle", { hasText: "Sous / sur-évalué" });
  await couloir.click();
  await expect(couloir).toHaveAttribute("aria-pressed", "false");
  await expect.poll(traces).toBe(base - 4);

  // Dividende : l'étage et son bâton disparaissent.
  const dividend = page.locator(".val-toggle", { hasText: "Dividende" });
  await expect.poll(barTraces).toBeGreaterThan(0);
  await dividend.click();
  await expect.poll(barTraces).toBe(0);

  expect(apiCalls).toEqual([]);
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

  // Étalement : la section Valorisation occupe TOUTE la largeur de contenu
  // disponible (1560 px plafonnés), sans provoquer de scroll horizontal. Le
  // « breakout » qui la faisait déborder a disparu : le contenu est désormais
  // déjà étalé, donc une marge de débordement aurait valu 0 partout.
  const dims = await page.evaluate(() => {
    const sec = document.querySelector(".section-breakout") ||
      [...document.querySelectorAll(".section")].find((s) => s.getBoundingClientRect().width > 0);
    const main = document.querySelector(".fiche-main");
    return {
      secW: Math.round(sec.getBoundingClientRect().width),
      mainW: Math.round(main.getBoundingClientRect().width),
      scrollW: document.documentElement.scrollWidth,
      winW: window.innerWidth,
      breakout: !!document.querySelector(".section-breakout"),
    };
  });
  expect(dims.breakout, "le breakout mort ne doit pas subsister").toBe(false);
  expect(dims.secW).toBe(dims.mainW);
  // À 1280 px (viewport par défaut de Playwright), le contenu plein écran fait
  // toute la largeur restante : la coquille ne perd pas de place utile.
  expect(dims.mainW).toBeGreaterThan(1000);
  expect(dims.scrollW).toBeLessThanOrEqual(dims.winW);

  // Le tracé Plotly occupe TOUTE la largeur du conteneur (sinon il retombe sur sa
  // largeur par défaut ~700px et laisse un grand vide à droite — régression vue
  // quand la section était tracée pendant son masquage `x-show`). On attend que
  // `_fullLayout` existe : une course en CI WebKit mesurait avant le premier layout.
  await expect
    .poll(
      async () => page.evaluate(() => {
        const gd = document.querySelector("#val-chart");
        return gd._fullLayout?.width == null ? null : Math.round(gd.getBoundingClientRect().width);
      }),
      { timeout: 20_000 },
    )
    .not.toBeNull();
  const fit = await page.evaluate(() => {
    const gd = document.querySelector("#val-chart");
    return { divW: Math.round(gd.getBoundingClientRect().width), layoutW: gd._fullLayout?.width };
  });
  expect(Math.abs(fit.layoutW - fit.divW)).toBeLessThanOrEqual(2);

  // Les AUTRES sections gardent la largeur de leur colonne (garde-fou anti-régression).
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();
  const other = await page.evaluate(() => {
    // Section RÉELLEMENT affichée (x-show masque les autres) : on ignore les
    // sections cachées, sinon on lirait une largeur de 0.
    const sec = [...document.querySelectorAll(".section")]
      .find((s) => s.getBoundingClientRect().width > 0);
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

test("section Valorisation : la table « monde de Markovitz » est en bas de section (#33)", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#RI.PA/valorisation");
  await expect(page.locator(".header")).toBeVisible();

  // Six mesures, six en-têtes — la table a quitté l'onglet Momentum (#33).
  const card = page.locator(".mkw-card");
  await expect(card).toBeVisible();
  await expect(card.locator(".mkw-table thead th")).toHaveCount(6);
  await expect(card.locator(".mkw-table tbody td")).toHaveCount(6);
  await expect(card.locator(".mkw-table thead th").first()).toHaveText("σ (bande)");

  // La table suit la fenêtre choisie, sans requête réseau.
  const sigma = () => card.locator(".mkw-table tbody td").first().textContent();
  const before = await sigma();
  await card.locator(".period-chip", { hasText: "1A" }).click();
  await expect.poll(sigma).not.toBe(before);

  // La bascule brut/ajusté reste disponible pour une action.
  await expect(card.locator('input[name="mkw-series"][value="adj"]')).toBeEnabled();

  expect(errors).toEqual([]);
});
