import { expect, test } from "@playwright/test";

// UX #13 : parcours du screener SANS scan réseau. On intercepte
// `POST /api/screener/run` pour renvoyer une charge déterministe : le test
// vérifie la structure de l'écran, le repli des filtres, les chips et la
// colonne d'ancrage gelée — sans dépendre de yfinance (donc non flaky).
const RUN_ROWS = [
  {
    ticker: "RI.PA",
    name: "Pernod Ricard",
    market_cap: 25_000_000_000,
    z: -3.81,
    pente_pct: 6.8,
    ecart_type_pct: 32.7,
    pot_5y_pct: 32.5,
    pot_10y_pct: 19.0,
    trend_bullish: true,
    roe_pct: 12.5,
    per: 11.0,
    p_b: 1.4,
    p_fcf: 9.0,
    fcf_yield_pct: 8.5,
    quality_score: 62.0,
    error: null,
    colors: { z: "good", roe_pct: "good", quality_score: "good" },
  },
  {
    ticker: "TTE.PA",
    name: "TotalEnergies",
    market_cap: 130_000_000_000,
    z: -1.2,
    pente_pct: 4.5,
    ecart_type_pct: 28.0,
    pot_5y_pct: 11.0,
    pot_10y_pct: 9.0,
    trend_bullish: true,
    roe_pct: 14.0,
    per: 8.0,
    p_b: 1.2,
    p_fcf: 7.0,
    fcf_yield_pct: 12.0,
    quality_score: 70.0,
    error: null,
    colors: { z: "good", roe_pct: "good", quality_score: "good" },
  },
];

test("screener : accueil, filtres repliables et colonne Entreprise gelée", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  // Scan déterministe : aucune requête réseau n'est nécessaire.
  await page.route("**/api/screener/run", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ source: "test", count: RUN_ROWS.length, rows: RUN_ROWS }),
    }),
  );

  await page.goto("/");
  await page.getByRole("button", { name: "Screener" }).click();

  const modal = page.locator(".modal.modal-screen");
  await expect(modal).toBeVisible();

  // 1. Écran d'accueil : hero + CTA + presets (issus de /api/screener/meta).
  const home = modal.locator(".screen-home");
  await expect(home).toBeVisible();
  await expect(home.locator(".screen-home-cta")).toBeVisible();
  await expect
    .poll(async () => home.locator(".screen-preset").count(), { timeout: 15_000 })
    .toBeGreaterThanOrEqual(3);

  // 2. Plus aucun doublon de capitalisation (le libellé global a disparu).
  await expect(modal.getByText("Capi min univers")).toHaveCount(0);

  // 3. Le panneau de filtres est visible à l'ouverture, et repliable.
  const panel = modal.locator(".screen-filters-panel");
  await expect(panel).toBeVisible();
  await modal.getByRole("button", { name: /Filtres/ }).click();
  await expect(panel).toBeHidden();
  await modal.getByRole("button", { name: /Filtres/ }).click();
  await expect(panel).toBeVisible();

  // 4. Design A : un seul champ de capitalisation, avec suffixes min/max
  //    (plus de placeholder redondant « min Capi (Md€) »).
  //    Le groupe « Taille » est ouvert par défaut.
  await expect(panel.locator(".screen-group-name")).toHaveCount(4);
  await expect(panel.locator(".screen-filter-col", { hasText: "Capi" })).toHaveCount(1);
  await expect(panel.locator('.screen-filter-col input[placeholder]')).toHaveCount(0);

  // 5. Un preset pré-remplit les filtres et lance le scan -> les filtres se
  //    replient, les chips récapitulatifs apparaissent, le tableau s'affiche.
  await home.locator(".screen-preset").first().click();
  await expect(modal.locator(".screen-table")).toBeVisible({ timeout: 15_000 });
  await expect(panel).toBeHidden();
  await expect(modal.locator(".screen-chips .screen-chip").first()).toBeVisible();

  // 6. Colonne d'ancrage « Entreprise » présente et gelée (position: sticky).
  const anchor = modal.locator(".screen-table th.screen-col-anchor");
  await expect(anchor).toHaveText(/Entreprise/);
  const position = await anchor.evaluate((el) => getComputedStyle(el).position);
  expect(position).toBe("sticky");

  // 7. Le ticker et le nom sont dans la même cellule d'ancrage (identité de ligne).
  await expect(
    modal.locator(".screen-table tbody .screen-col-anchor .screen-ticker").first(),
  ).toHaveText("RI.PA");

  // 8. Défilement horizontal : l'ancre reste visible.
  const wrap = modal.locator(".screen-table-wrap");
  await wrap.evaluate((el) => { el.scrollLeft = el.scrollWidth; });
  await expect(anchor).toBeVisible();

  // 9. Retour à l'accueil : les presets redeviennent accessibles sans fermer la modale.
  await modal.getByRole("button", { name: "← Accueil" }).click();
  await expect(home).toBeVisible();
  await expect(modal.locator(".screen-table")).toBeHidden();

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

// Design A + #14 : groupes de filtres, hiérarchie de tri et score composite.
test("screener : design A (groupes, badges) et score par compromis", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  // Jeu déterministe où le compromis (B) doit battre les extrêmes (A, D).
  const sent = [];
  await page.route("**/api/screener/run", (route) => {
    sent.push(JSON.parse(route.request().postData() || "{}"));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        source: "test",
        count: 4,
        rows: [
          { ticker: "B", name: "Compromis", roe_pct: 25, p_fcf: 9, score: 66.7, colors: {} },
          { ticker: "A", name: "RoeTop", roe_pct: 30, p_fcf: 30, score: 50, colors: {} },
          { ticker: "D", name: "Cheap", roe_pct: 10, p_fcf: 5, score: 50, colors: {} },
          { ticker: "C", name: "Moyen", roe_pct: 20, p_fcf: 10, score: 33.3, colors: {} },
        ],
      }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Screener" }).click();
  const modal = page.locator(".modal.modal-screen");
  await modal.locator(".screen-home").waitFor();

  // Design A : 4 groupes thématiques, repliables, badge visible même replié.
  await expect(modal.locator(".screen-group-name")).toHaveCount(4);
  const rentabilite = modal.locator(".screen-group-head", { hasText: "Rentabilité" });
  await rentabilite.click();
  await modal.locator(".screen-filter-col", { hasText: "ROE %" }).locator("input").first().fill("10");
  await rentabilite.click();  // replier avec un filtre posé
  await expect(modal.locator(".screen-group-badge", { hasText: "1" })).toBeVisible();

  // Plus aucun placeholder « min … (Md€) » (suffixes à la place).
  await expect(modal.locator('.screen-filters-panel input[placeholder]')).toHaveCount(0);

  // Scan (mocké) puis sélection de 2 critères -> score composite.
  await modal.locator(".screen-preset").first().click();
  await modal.locator(".screen-table").waitFor();
  await modal.locator(".screen-table th", { hasText: "ROE %" }).click();
  await modal.locator(".screen-table th", { hasText: "P/FCF" }).click();

  // Hiérarchie de tri explicite + bascule Compromis/Cascade.
  await expect(modal.locator(".screen-sort-label")).toContainText("Compromis sur");
  await expect(modal.locator(".screen-mode-toggle")).toBeVisible();
  await expect(modal.locator(".screen-mode-toggle button.active")).toHaveText("Compromis");

  // Colonne Score + classement par compromis (B en tête, pas A le 1er en ROE).
  await expect(modal.locator(".screen-table th", { hasText: "Score" })).toBeVisible();
  await expect(modal.locator(".screen-table tbody tr").first().locator(".screen-ticker")).toHaveText("B");
  // En compromis, les badges de rang cascade sont masqués (sinon l'affichage ment).
  await expect(modal.locator(".screen-th-rank:visible")).toHaveCount(0);

  // Le serveur a bien reçu les critères du score et le tri sur `score`.
  expect(sent.at(-1).score_keys).toEqual(["roe_pct", "p_fcf"]);
  expect(sent.at(-1).sort_by[0]).toEqual(["score", "desc"]);

  // Bascule en cascade : le tri repasse en lexicographique, les rangs reviennent.
  await modal.locator(".screen-mode-toggle button", { hasText: "Cascade" }).click();
  await expect
    .poll(() => sent.at(-1).sort_by, { timeout: 10_000 })
    .toEqual([["roe_pct", "desc"], ["p_fcf", "asc"]]);
  await expect(modal.locator(".screen-sort-label")).toContainText("1. ROE %");
  await expect(modal.locator(".screen-th-rank:visible").first()).toBeVisible();

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

// Régression (fix/screener-filtre-capi) : un filtre MANUEL de capitalisation
// partait en TypeError (`const` réassigné dans `_buildFilters`), ce qui laissait
// le spinner bloqué et n'émettait AUCUNE requête. Ce test pose une borne Capi et
// vérifie que le scan part réellement avec le bon body (Md€ -> EUR).
test("screener : filtre manuel Capi -> requête émise avec les bornes converties", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const sent = [];
  await page.route("**/api/screener/run", (route) => {
    sent.push(JSON.parse(route.request().postData() || "{}"));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ source: "test", count: 1, rows: RUN_ROWS.slice(0, 1) }),
    });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Screener" }).click();
  const modal = page.locator(".modal.modal-screen");
  await modal.locator(".screen-home").waitFor();

  // Le groupe « Taille » (capi) est ouvert par défaut : on saisit la borne min.
  const capiMin = modal.locator(".screen-filter-col", { hasText: "Capi" }).locator("input").first();
  await capiMin.fill("5");

  await modal.getByRole("button", { name: "Rechercher" }).click();

  // Le tableau se remplit (le scan est bien parti) et le body porte le filtre.
  await expect(modal.locator(".screen-table")).toBeVisible();
  await expect.poll(() => sent.length, { timeout: 10_000 }).toBeGreaterThan(0);
  expect(sent.at(-1).filters.market_cap).toEqual([5e9, null]);
  expect(sent.at(-1).min_market_cap).toBe(5e9);

  // Le spinner est retombé (aucun état « Calcul du scan en cours… » persistant).
  await expect(modal.getByText("Calcul du scan en cours…")).toHaveCount(0);

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});
