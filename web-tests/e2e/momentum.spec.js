import { expect, test } from "@playwright/test";

// Section Momentum (Clara Vallis, #30) : l'onglet, la table, la jauge et les
// deux tracés. On vérifie le rendu RÉEL — pas seulement la présence du HTML.

test("section Momentum : table, jauge et deux tracés", async ({ page }) => {
  await page.goto("/#RI.PA/momentum");
  await expect(page.locator(".section-tab.active")).toHaveText("Momentum");

  // Table : six mesures, six en-têtes.
  await expect(page.locator(".mom-table thead th")).toHaveCount(6);
  await expect(page.locator(".mom-table tbody td")).toHaveCount(6);

  // Jauge : role=meter, valeur annoncée, aiguille positionnée.
  const meter = page.locator(".mom-gauge");
  await expect(meter).toHaveAttribute("role", "meter");
  await expect(meter).toHaveAttribute("aria-valuenow", /\d/);
  await expect(page.locator(".mom-gauge .gauge-needle")).toBeVisible();

  // Deux tracés Plotly, et des formes de fond pour l'historique.
  await expect
    .poll(async () => page.locator("#mom-year .scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(0);
  await expect
    .poll(async () => page.locator("#mom-history .scatterlayer .trace").count(), {
      timeout: 20_000,
    })
    .toBeGreaterThan(0);
  await expect
    .poll(async () => page.locator("#mom-history .shapelayer path").count(), { timeout: 20_000 })
    .toBeGreaterThan(0);
});

test("section Momentum : changer de fenêtre change la table", async ({ page }) => {
  await page.goto("/#RI.PA/momentum");
  await expect(page.locator(".mom-table")).toBeVisible();
  const sigma = () => page.locator(".mom-table tbody td").first().textContent();
  const before = await sigma();
  await page.locator(".mom-card .period-chip", { hasText: "1A" }).click();
  await expect.poll(sigma).not.toBe(before);
});

test("ratio : l'onglet Momentum est désactivé", async ({ page }) => {
  await page.goto("/#RI.PA");
  await expect(page.locator(".header")).toBeVisible();
  // Le deep-link ne porte pas les ratios : on passe par le composant.
  await page.evaluate(() => {
    const c = window.Alpine.$data(document.querySelector(".wrap"));
    c.query = "CW8.PA/SPY";
    c.load();
  });
  await expect(page.locator(".section-tab", { hasText: "Momentum" })).toBeDisabled();
});
