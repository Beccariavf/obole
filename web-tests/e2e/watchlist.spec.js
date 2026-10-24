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
      target_yield: null,
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
      trend_bullish: true,
      warnings: [],
      error: null,
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

  // Compteurs : tous + par tier (source = appartenance).
  await expect(page.locator(".wl-tier-btn", { hasText: "Tous" })).toContainText("2");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 1" })).toContainText("1");
  await expect(page.locator(".wl-tier-btn", { hasText: "Tier 2" })).toContainText("1");
  await expect(page.locator(".wl-coverage")).toContainText("Prix justes définis : 1/2");

  // Deux lignes, badges de source distincts, marges colorées.
  const rows = page.locator(".wl-table tbody tr");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(0)).toContainText("RI.PA");
  await expect(rows.nth(0)).toContainText("calc");
  await expect(rows.nth(0)).toContainText("16,67 %");
  await expect(rows.nth(1)).toContainText("AI.PA");
  await expect(rows.nth(1)).toContainText("droite");
  await expect(rows.nth(1)).toContainText("-25 %");
  // Le repli affiche la même valeur que l'écart à la droite (par construction).
  await expect(rows.nth(1)).toContainText("-25 %");

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
  const define = page.locator(".watch-ref-pop .watch-pop-item", { hasText: "Définir depuis le" });
  await expect(define).toBeEnabled();
  await define.click();
  // Le PUT portait bien une date ISO (la poignée gauche de la fenêtre affichée).
  expect(calls).toHaveLength(1);
  expect(calls[0].method).toBe("PUT");
  expect(calls[0].body.start).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  // La fiche s'est rechargée et reste utilisable (la route /api/stock est réelle).
  await expect(page.locator(".header")).toBeVisible();
});
