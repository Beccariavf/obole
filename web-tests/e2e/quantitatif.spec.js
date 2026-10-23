import { expect, test } from "@playwright/test";

// Chantier Quantitatif : la section est pilotée par la taxonomie config.QUANT_GROUPS.
// On vérifie le rendu RÉEL (pas seulement les titres) : pastilles de dernière
// valeur, échelle temporelle honnête, et comparateur multi-métriques.

test("section Quantitatif : pastilles de dernière valeur sous les graphes", async ({ page }) => {
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();

  // Une pastille par métrique tracée, avec un libellé « nom : valeur ».
  const pills = page.locator(".card-pills .pill");
  await expect(pills.first()).toBeVisible();
  expect(await pills.count()).toBeGreaterThan(5);
  await expect(pills.filter({ hasText: "Marge brute" }).first()).toBeVisible();
  await expect(pills.filter({ hasText: "ROIC" }).first()).toBeVisible();

  // La puce de couverture dit la vérité sur l'axe (une série courte = peu d'années).
  await expect(page.locator(".card-span").filter({ hasText: "ans" }).first()).toBeVisible();
});

test("section Quantitatif : comparateur multi-métriques en base 100", async ({ page }) => {
  await page.goto("/#RI.PA/quantitatif");
  await expect(page.locator(".header")).toBeVisible();

  // Le sélecteur de métriques est présent (le graphe n'apparaît qu'à la sélection).
  await expect(page.locator(".compare-picker")).toBeVisible();
  await expect(page.locator(".compare-chip").first()).toBeVisible();

  // Sélection de 2 métriques -> le graphe est tracé (légende + traces).
  const cmp = page.locator("#compare-chart");
  await page.locator(".compare-chip", { hasText: "Chiffre d'affaires" }).click();
  await page.locator(".compare-chip", { hasText: "Marge nette" }).click();
  await expect(cmp).toBeVisible();
  await expect
    .poll(async () => cmp.locator(".legend .legendtext").count(), { timeout: 20_000 })
    .toBe(2);
  await expect
    .poll(async () => cmp.locator(".scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(0);
});
