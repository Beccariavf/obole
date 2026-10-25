import { expect, test } from "@playwright/test";

// Watchlist (#25) : bouton entre Portefeuille et Paramètres, modale de classement,
// étoile de la fiche et fenêtre de confiance. Toutes les routes watchlist sont
// interceptées : aucun test n'écrit dans la base réelle.

const TIERS = [
  { id: 1, label: "Tier 1", hint: "Conviction la plus forte — à acheter en priorité" },
  { id: 2, label: "Tier 2", hint: "À suivre de près" },
  { id: 3, label: "Tier 3", hint: "Veille — opportunité à confirmer" },
];

const RUN = {
  generated_at: 1700000000,
  count: 2,
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
    {
      ticker: "AI.PA",
      tier: 2,
      name: "Air Liquide",
      sector: "Basic Materials",
      currency: "EUR",
      price: 100,
      fair_price: 80,
      fair_price_source: "regression",
      target_yield: 12,
      safety_margin_pct: -25,
      margin_good: false,
      ref_start: "2006-10-24",
      ref_is_default: true,
      ref_line: 80,
      trend_gap_pct: -25,
      z: 0.8,
      ecart_type_pct: 20,
      pente_pct: 4,
      pot_5y_pct: 5,
      pot_10y_pct: 4,
      pot_5y_source: "regression",
      pot_10y_source: "regression",
      trend_bullish: true,
      warnings: [],
      error: null,
    },
  ],
};

const RUN_GAME = {
  generated_at: 1700000000,
  count: 4,
  rows: [
    RUN.rows[0],
    RUN.rows[1],
    {
      ...RUN.rows[0],
      ticker: "MC.PA",
      name: "LVMH",
      tier: 1,
      safety_margin_pct: -10,
      z: 0.3,
      pot_5y_pct: 6,
      pot_5y_source: "regression",
    },
    {
      ...RUN.rows[1],
      ticker: "OR.PA",
      name: "L'Oréal",
      tier: 3,
      safety_margin_pct: -30,
      z: 1.4,
      pot_5y_pct: 3,
      pot_5y_source: "regression",
    },
  ],
};

async function routeWatchlist(page, { run = RUN, items = null } = {}) {
  const state = {
    tiers: TIERS,
    items:
      items ??
      [
        { ticker: "RI.PA", tier: 1, added_at: 1 },
        { ticker: "AI.PA", tier: 2, added_at: 2 },
      ],
    refs: {},
  };
  await page.route(/\/api\/watchlist\/run$/, (route) => route.fulfill({ json: run }));
  await page.route(/\/api\/watchlist$/, (route) => route.fulfill({ json: state }));
}

test("watchlist : bouton, modale, compteurs et classement", async ({ page }) => {
  await routeWatchlist(page);
  await page.goto("/");

  // Position demandée : entre Portefeuille et Paramètres.
  const labels = await page.locator(".searchbar .btn.ghost").allInnerTexts();
  const iPortfolio = labels.findIndex((l) => l.includes("Portefeuille"));
  const iWatch = labels.findIndex((l) => l.includes("Watchlist"));
  const iSettings = labels.findIndex((l) => l.includes("Paramètres"));
  expect(iPortfolio).toBeGreaterThan(-1);
  expect(iWatch).toBeGreaterThan(iPortfolio);
  expect(iSettings).toBeGreaterThan(iWatch);

  await page.locator(".searchbar .btn.ghost", { hasText: "Watchlist" }).click();
  await expect(page.locator(".modal.modal-watchlist h3")).toHaveText("Watchlist");
  // La vue cadrans est le défaut ; ce test vérifie le tableau dense.
  await page.locator(".wl-view-toggle button", { hasText: "Tableau" }).click();

  // Compteurs : tous + par tier (source = appartenance).
  await expect(page.locator(".wl-tier-btn", { hasText: "Tous" })).toContainText("2");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 1" })).toContainText("1");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 2" })).toContainText("1");
  await expect(page.locator(".wl-coverage")).toContainText("Prix justes enregistrés : 1/2");

  // Deux lignes, badges de source distincts, marges colorées.
  const rows = page.locator(".wl-table tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("RI.PA");
  await expect(rows.nth(0)).toContainText("calc");
  await expect(rows.nth(0)).toContainText("16,67 %");
  await expect(rows.nth(1)).toContainText("AI.PA");
  await expect(rows.nth(1)).toContainText("droite");

  // Le select doit afficher le tier réel de la ligne (et non la 1re option).
  const aiSelect = rows.nth(1).locator("select");
  await expect(aiSelect).toHaveValue("2");
  await expect(aiSelect.locator("option:checked")).toHaveText("Tier 2");
  await page.route(/\/api\/watchlist\/items\/AI\.PA$/, (route) =>
    route.fulfill({ json: { item: { ticker: "AI.PA", tier: 3 } } }),
  );
  await aiSelect.selectOption("3");
  await expect(aiSelect).toHaveValue("3");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 2" })).toContainText("0");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 3" })).toContainText("1");

  // Source du Pot. 5A : valorisation enregistrée vs droite total-return.
  await expect(rows.nth(0).locator("td").nth(7)).toContainText("valo");
  await expect(rows.nth(1).locator("td").nth(7)).toContainText("droite");
  await expect(rows.nth(1)).toContainText("objectif 12 %/an");
  await expect(rows.nth(1)).toContainText("-25 %");
  // Le label de position σ est rendu par `scored` (exposé à Alpine) : sans lui,
  // l'expression échouait et la cellule restait muette.
  await expect(rows.nth(0).locator(".wl-z-label")).toContainText("Sous-cotée");

  // Tri : 1er clic = décroissant (ordre serveur), 2e = ascendant (la plus faible).
  const marginTh = page.locator(".wl-table thead th", { hasText: "Marge sécurité" });
  await marginTh.click();
  await expect(marginTh).toHaveClass(/sort-desc/);
  await marginTh.click();
  await expect(marginTh).toHaveClass(/sort-asc/);
  await expect(page.locator(".wl-table tbody tr").nth(0)).toContainText("AI.PA");

  // Filtre par tier : Tier 1 ne garde que RI.PA.
  await page.locator(".wl-tier-btn", { hasText: "Tier 1" }).click();
  await expect(page.locator(".wl-table tbody tr")).toHaveCount(1);
  await expect(page.locator(".wl-table tbody tr").nth(0)).toContainText("RI.PA");

  // Ligne cliquable : ouvre la fiche, la modale se ferme, le retour la rouvre.
  await page.locator(".wl-table tbody tr").nth(0).click();
  await expect(page.locator(".modal.modal-watchlist")).toBeHidden();
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".searchbar .btn.ghost", { hasText: "Retour à « Watchlist »" })).toBeVisible();
  await page.locator(".searchbar .btn.ghost", { hasText: "Retour à « Watchlist »" }).click();
  await expect(page.locator(".modal.modal-watchlist")).toBeVisible();
});

test("watchlist : vue cadrans par tier et bascule tableau", async ({ page }) => {
  await routeWatchlist(page);
  await page.goto("/");
  await page.locator(".searchbar .btn.ghost", { hasText: "Watchlist" }).click();

  await expect(page.locator(".wl-board")).toBeVisible();
  await expect(page.locator(".wl-tier-col")).toHaveCount(3);
  await expect(page.locator(".wl-tier-col").nth(0)).toContainText("RI.PA");
  await expect(page.locator(".wl-tier-col").nth(1)).toContainText("AI.PA");
  await expect(page.locator(".wl-tier-col").nth(2)).toContainText("Aucune valeur");
  // Le cadran du tier 1 (une valeur, marge 16,67 %) et le select de la carte AI.
  await expect(page.locator(".wl-tier-col").nth(0).locator(".wl-dial-text").first()).toContainText(
    "16,67 %",
  );
  await expect(page.locator(".wl-tier-col").nth(1).locator(".wl-card select")).toHaveValue("2");

  // Carte compacte : hauteur, sémantique de tier et nom accessible du ✕.
  const firstCard = page.locator(".wl-card").first();
  expect(await firstCard.evaluate((el) => el.getBoundingClientRect().height)).toBeLessThanOrEqual(130);
  expect(
    await page.locator(".wl-tier-head").first().evaluate((el) => el.getBoundingClientRect().height),
  ).toBeLessThanOrEqual(50);
  await expect(page.locator(".wl-tier-col").first().locator("h4")).toHaveText("Tier 1");
  await expect(firstCard.locator(".wl-card-x")).toHaveAttribute("aria-label", /Retirer RI\.PA/);

  // Voir ouvre la fiche ; le retour rouvre la watchlist.
  await firstCard.locator(".wl-card-foot .btn", { hasText: "Voir" }).click();
  await expect(page.locator(".header")).toBeVisible();
  await page.locator(".searchbar .btn.ghost", { hasText: "Retour à « Watchlist »" }).click();
  await expect(page.locator(".modal.modal-watchlist")).toBeVisible();

  // ✕ retire la carte (dialog accepté, DELETE intercepté).
  page.once("dialog", (dialog) => dialog.accept());
  await page.route(/\/api\/watchlist\/items\/RI\.PA$/, (route) =>
    route.fulfill({ json: { status: "removed" } }),
  );
  await page.locator(".wl-card").first().locator(".wl-card-x").click();
  await expect(page.locator(".wl-card")).toHaveCount(1);

  await page.locator(".wl-view-toggle button", { hasText: "Tableau" }).click();
  await expect(page.locator(".wl-table")).toBeVisible();
  await expect(page.locator(".wl-board")).toBeHidden();
  await page.locator(".wl-view-toggle button", { hasText: "Cadrans" }).click();
  await expect(page.locator(".wl-board")).toBeVisible();

  // En dessous de 900 px, le tableau de bord passe à une colonne.
  await page.setViewportSize({ width: 390, height: 800 });
  const columns = await page.locator(".wl-board").evaluate(
    (el) => getComputedStyle(el).gridTemplateColumns.split(" ").filter(Boolean).length,
  );
  expect(columns).toBe(1);
  const tableButton = page.locator(".wl-view-toggle button", { hasText: "Tableau" });
  await expect(tableButton).toBeVisible();
  const tableBox = await tableButton.boundingBox();
  expect(tableBox.x + tableBox.width).toBeLessThanOrEqual(390);
  expect(
    await page.locator(".wl-card").first().evaluate((el) => el.getBoundingClientRect().height),
  ).toBeLessThanOrEqual(150);
});

test("watchlist : état vide", async ({ page }) => {
  await routeWatchlist(page, { run: { generated_at: 1700000000, count: 0, rows: [] }, items: [] });
  await page.goto("/");
  await page.locator(".searchbar .btn.ghost", { hasText: "Watchlist" }).click();
  await expect(page.locator(".modal.modal-watchlist")).toContainText("Ta watchlist est vide");
});

test("étoile : ajout puis retrait, sans recharger la fiche", async ({ page }) => {
  const putBodies = [];
  await page.route(/\/api\/watchlist\/items\/RI\.PA$/, async (route) => {
    if (route.request().method() === "PUT") {
      putBodies.push(route.request().postDataJSON());
      return route.fulfill({ json: { item: { ticker: "RI.PA", tier: 2, added_at: 1 } } });
    }
    return route.fulfill({ json: { removed: true } });
  });

  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();

  // Non suivie au chargement (base e2e vide) : l'étoile invite à choisir.
  const star = page.locator(".watch-star");
  await expect(star).toContainText("Watchlist");
  await star.click();
  await expect(page.locator(".watch-pop")).toBeVisible();

  await page.locator(".watch-pop-item", { hasText: "Tier 2" }).click();
  await expect(star).toContainText("Tier 2");
  expect(putBodies).toEqual([{ tier: 2 }]);

  // Retrait (confirmation native) : l'état revient à « non suivie ».
  page.once("dialog", (d) => d.accept());
  await star.click();
  await page.locator(".watch-pop-item", { hasText: "Retirer de la watchlist" }).click();
  await expect(star).toContainText("Watchlist");
});

test("watchlist : jeu de convictions, résultat et application", async ({ page }) => {
  await routeWatchlist(page, {
    run: RUN_GAME,
    items: RUN_GAME.rows.map((row) => ({ ticker: row.ticker, tier: row.tier, added_at: 1 })),
  });
  await page.goto("/");
  await page.locator(".searchbar .btn.ghost", { hasText: "Watchlist" }).click();
  await page.locator(".btn", { hasText: "Tester mes convictions" }).click();
  await expect(page.locator(".modal.modal-conviction")).toBeVisible();

  const cards = page.locator(".cv-card");
  await expect(cards).toHaveCount(2);
  // Annulation : deux choix, un retour arrière, puis la suite.
  await cards.first().click();
  await page.waitForTimeout(30);
  await cards.first().click();
  await page.waitForTimeout(30);
  await expect(page.locator(".cv-progress-row")).toContainText("2 / 12 minimum");
  await page.locator(".cv-foot .btn", { hasText: "Annuler la dernière" }).click();
  await expect(page.locator(".cv-progress-row")).toContainText("1 / 12 minimum");
  // On fait gagner les valeurs des tiers bas (AI, OR) pour forcer un reclassement.
  for (let round = 0; round < 11; round += 1) {
    const count = await cards.count();
    let picked = false;
    let bestTier = -1;
    for (let index = 0; index < count; index += 1) {
      const text = await cards.nth(index).innerText();
      const match = text.match(/Tier (\d)/);
      const tier = match ? Number(match[1]) : 0;
      if (tier > bestTier) {
        bestTier = tier;
        picked = index;
      }
    }
    await cards.nth(picked).click();
    await page.waitForTimeout(25);
  }
  await expect(page.locator(".cv-progress-row")).toContainText("12 / 12 minimum");
  await page.locator(".cv-foot .btn", { hasText: "Voir le résultat" }).click();
  await expect(page.locator(".cv-result-table tbody tr")).toHaveCount(4);

  const calls = [];
  await page.route(/\/api\/watchlist\/items\/[^/]+$/, async (route) => {
    const ticker = decodeURIComponent(route.request().url().split("/").pop());
    const tier = route.request().postDataJSON().tier;
    calls.push({ ticker, tier });
    await route.fulfill({ json: { item: { ticker, tier } } });
  });
  const apply = page.locator(".cv-result-actions .btn", { hasText: "Appliquer les tiers" });
  await expect(apply).toBeEnabled();
  await apply.click();
  await expect(page.locator(".modal.modal-conviction")).toContainText("Tiers appliqués");
  expect(calls.length).toBeGreaterThan(0);

  await page.locator(".cv-result-actions .btn", { hasText: "Fermer" }).click();
  await expect(page.locator(".modal.modal-watchlist")).toBeVisible();
  await expect(page.locator(".modal.modal-conviction")).toBeHidden();
});

test("référence : le chip propose de définir la fenêtre affichée", async ({ page }) => {
  const calls = [];
  await page.route(/\/api\/watchlist\/ref\/RI\.PA$/, (route) => {
    calls.push({ method: route.request().method(), body: route.request().postDataJSON() });
    return route.fulfill({
      json: {
        ref: { start: "2012-01-04" },
        stats: {
          start: "2012-01-04",
          end: "2026-10-24",
          n_points: 3600,
          line: 120,
          z: -1.2,
          ecart_type_pct: 25,
          trend_gap_pct: 10,
          pente_pct: 4,
        },
        warning: null,
      },
    });
  });

  await page.goto("/#RI.PA/resume");
  await expect(page.locator(".header")).toBeVisible();
  const chip = page.locator(".watch-ref-btn");
  await expect(chip).toContainText("Réf. droite");
  await chip.click();
  await expect(page.locator(".watch-ref-pop")).toBeVisible();
  const define = page.locator(".watch-ref-item", { hasText: "Définir la fenêtre affichée" });
  await expect(define).toBeEnabled();
  await define.click();
  // Le PUT portait bien une date ISO (la poignée gauche de la fenêtre affichée).
  expect(calls).toHaveLength(1);
  expect(calls[0].method).toBe("PUT");
  expect(calls[0].body.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  // La fiche s'est rechargée et reste utilisable (la route /api/stock est réelle).
  await expect(page.locator(".header")).toBeVisible();
});

test("référence : la fiche suit la droite persistée et le popover est lisible", async ({ page }) => {
  // Injecte une référence cohérente sur ACA.PA sans écrire en base : on part du
  // payload réel (cours, dates, derniers points) et on ajoute un bloc `watch`.
  await page.route(/\/api\/stock\/ACA\.PA$/, async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    const dates = body.chart.dates;
    const lastDate = dates[dates.length - 1];
    const refStart = dates[Math.floor(dates.length / 2)];
    const price = body.identity.last_price;
    const line = price * 0.97; // cours 3 % au-dessus de la droite
    const b = Math.log(1.03); // +3 %/an
    const sigma = 0.2;
    const tEnd = (new Date(lastDate) - new Date(refStart)) / (365.25 * 864e5);
    const a = Math.log(line) - b * tEnd;
    body.watch = {
      tier: 1,
      ref: { start: refStart },
      ref_stats: {
        start: refStart,
        end: lastDate,
        n_points: 1000,
        a,
        b,
        sigma,
        line,
        z: Math.log(price / line) / sigma,
        ecart_type_pct: (Math.exp(sigma) - 1) * 100,
        trend_gap_pct: ((line - price) / line) * 100,
        pente_pct: (Math.exp(b) - 1) * 100,
      },
    };
    await route.fulfill({ json: body });
  });

  await page.goto("/#ACA.PA/resume");
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".watch-ref-btn")).toContainText("Réf.");

  const state = await page.evaluate(() => {
    const d = window.Alpine.$data(document.querySelector(".wrap"));
    return {
      withDividends: d.withDividends,
      sync: d.syncRegression,
      ref: d.referenceRegression(),
      stats: d.data.watch.ref_stats,
      live: d.live,
      lastDate: d.data.chart.dates[d.maxIdx()],
      price: d.data.identity.last_price,
    };
  });

  // Vue référence : prix bruts + synchro, et la droite est celle du serveur.
  expect(state.withDividends).toBe(false);
  expect(state.sync).toBe(true);
  expect(state.ref).not.toBeNull();
  expect(state.ref.a).toBeCloseTo(state.stats.a, 10);
  expect(state.lastDate).toBe(state.stats.end);

  // KPI = formules de la droite persistée (et non un re-fit de la décimée).
  const expectedZ = Math.log(state.price / state.stats.line) / state.stats.sigma;
  const expectedPot5 =
    ((state.stats.line * Math.exp(state.stats.b * 5)) / state.price) ** (1 / 5) - 1;
  expect(state.live.distance_sigma.value).toBeCloseTo(expectedZ, 2);
  expect(state.live.potential_5y.value).toBeCloseTo(expectedPot5 * 100, 1);
  await expect(page.locator(".kpi", { hasText: "Potentiel / an (5 ans)" })).toContainText(
    (expectedPot5 * 100).toFixed(1),
  );
  await expect(page.locator(".kpi", { hasText: "Performance passée" })).toContainText("3");

  // Popover : items bloc lisibles (définition sur deux lignes, autres sur une).
  await page.locator(".watch-ref-btn").click();
  const define = page.locator(".watch-ref-item", { hasText: "Définir la fenêtre affichée" });
  await expect(define).toContainText(`depuis le ${state.stats.start}`);
  expect(await define.evaluate((el) => el.getBoundingClientRect().height)).toBeLessThan(50);
  const view = page.locator(".watch-ref-item", { hasText: "Voir la référence" });
  expect(await view.evaluate((el) => el.getBoundingClientRect().height)).toBeLessThan(40);
  await page.screenshot({ path: "/tmp/watchlist-reference-e2e.png", fullPage: false });
});
