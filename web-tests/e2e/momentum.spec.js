import { expect, test } from "@playwright/test";

// Section Momentum (Clara Vallis, #30) : l'onglet, la table, la jauge et les
// deux tracés. On vérifie le rendu RÉEL — pas seulement la présence du HTML.

test("section Momentum : table, jauge et deux tracés", async ({ page }) => {
  await page.goto("/#RI.PA/momentum");
  await expect(page.locator(".section-tab.active")).toHaveText("Momentum");

  // Table « monde de Markovitz » : six mesures, six en-têtes. Scopée à sa carte :
  // la table de fiabilité porte elle aussi la classe `.mom-table`.
  await expect(page.locator(".mom-card .mom-table thead th")).toHaveCount(6);
  await expect(page.locator(".mom-card .mom-table tbody td")).toHaveCount(6);

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
  await expect(page.locator(".mom-card .mom-table")).toBeVisible();
  const sigma = () => page.locator(".mom-card .mom-table tbody td").first().textContent();
  const before = await sigma();
  await page.locator(".mom-card .period-chip", { hasText: "1A" }).click();
  await expect.poll(sigma).not.toBe(before);
});

test("section Momentum : fiabilité, huit mesures et deux colonnes", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#RI.PA/momentum");

  const table = page.locator(".mom-backtest-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  await expect(table.locator("tbody tr")).toHaveCount(8);
  await expect(table.locator("thead th")).toHaveCount(3);
  await expect(table.locator("caption")).toContainText("Comparaison");
  for (const th of await table.locator("thead th").all()) {
    await expect(th).toHaveAttribute("scope", "col");
  }

  // Changer la fenêtre relance le calcul : au moins un chiffre bouge.
  const cagr = () => table.locator("tbody tr").first().locator("td").first().textContent();
  const before = await cagr();
  await page.locator(".mom-history-card .period-chip", { hasText: "1A" }).click();
  await expect.poll(cagr).not.toBe(before);

  // Aucune erreur console sur la fiche.
  expect(errors).toEqual([]);
});

test("fiabilité : le tableau défile dans sa carte sous 640 px", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 900 });
  await page.goto("/#RI.PA/momentum");
  await expect(page.locator(".mom-backtest-table")).toBeVisible({ timeout: 30_000 });
  const layout = await page.evaluate(() => {
    const card = document.querySelector(".mom-backtest-card");
    const wrap = card.querySelector(".mom-table-wrap");
    const c = card.getBoundingClientRect();
    const w = wrap.getBoundingClientRect();
    return {
      scrolls: wrap.scrollWidth > wrap.clientWidth,
      inside: w.right <= c.right + 1 && w.left >= c.left - 1,
    };
  });
  expect(layout.scrolls).toBe(true);
  expect(layout.inside).toBe(true);
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
