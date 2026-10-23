import { expect, test } from "@playwright/test";

// Parcours minimal mais réel : ouvrir la fiche d'une valeur et vérifier que le
// graphe héro est bien tracé. Couvre la chaîne complète front (Alpine + Plotly
// vendorisés, app.js, API) sans mocker quoi que ce soit.
test("fiche RI.PA : le graphe héro se trace", async ({ page }) => {
  const externalRequests = [];
  const consoleErrors = [];

  page.on("request", (req) => {
    const { hostname } = new URL(req.url());
    if (!["127.0.0.1", "localhost"].includes(hostname)) externalRequests.push(req.url());
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await page.goto("/");
  await expect(page).toHaveTitle(/Obole/);

  const search = page.locator(".searchbar .search-wrap input.search-input");
  await search.fill("RI.PA");
  await search.press("Enter");

  // Le header de la fiche affiche le ticker une fois l'analyse chargée.
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".header .chip", { hasText: "RI.PA" })).toBeVisible();

  // Plotly a bien rendu le graphe héro (SVG + courbe).
  const chart = page.locator("#chart");
  await expect(chart.locator("svg").first()).toBeVisible();
  await expect
    .poll(async () => chart.locator(".scatterlayer .trace").count(), { timeout: 30_000 })
    .toBeGreaterThan(0);

  // Les indicateurs de la fiche sont calculés (pas d'état vide).
  await expect(page.locator(".kpi").first()).toBeVisible();

  expect(externalRequests, "aucune requête hors localhost (C14)").toEqual([]);
  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});
