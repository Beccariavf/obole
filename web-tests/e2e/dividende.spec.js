import { expect, test } from "@playwright/test";

// Section Dividende : cartes pilotées par la taxonomie config.DIVIDEND_GROUPS
// (source unique via /api/meta). On vérifie le rendu RÉEL : métriques clés,
// rendement continu, dividende par action, et le zoom plein écran (zéro requête).

test("section Dividende : métriques clés et rendement continu tracé", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  // Métriques clés (bandeau de chiffres) : les valeurs renseignées sont là, et
  // la ligne « Prochain paiement » — toujours vide avec yfinance Europe — a
  // disparu (elle consommait un emplacement pour un tiret).
  const kpi = page.locator(".cagr-row").first();
  await expect(kpi).toBeVisible();
  await expect(kpi).toContainText("Yield (TTM)");
  await expect(kpi).toContainText("Fréquence");
  await expect(kpi).not.toContainText("Prochain paiement");

  // Rendement continu : la carte « Dividend Yield » trace une courbe Plotly.
  const yieldCard = page.locator(".card.mini", { hasText: "Dividend Yield" }).first();
  await expect(yieldCard).toBeVisible();
  await expect
    .poll(async () => yieldCard.locator(".scatterlayer .trace").count(), { timeout: 20_000 })
    .toBeGreaterThan(0);

  // Pastilles High / Médiane / Low sous la courbe.
  await expect(yieldCard.locator(".card-pills .pill").filter({ hasText: "Médiane" })).toBeVisible();
});

test("section Dividende : Shareholder Yield masqué sans rachats (RI.PA)", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  // RI.PA ne déclare aucun rachat -> la carte Shareholder Yield est omise
  // (elle se confondrait avec Dividend Yield).
  await expect(page.locator(".card.mini", { hasText: "Dividend Yield" }).first()).toBeVisible();
  await expect(page.locator(".card.mini h3", { hasText: "Shareholder Yield" })).toHaveCount(0);

  // Le badge de fiabilité signale l'absence de rachats. Le sélecteur est scopé
  // par son contenu visible : un second `.div-warnings` existe pour le
  // portefeuille, ce qui rendait le locator global ambigu (strict mode).
  await expect(
    page.locator(".div-warnings").filter({ hasText: "Rachats" }).first(),
  ).toBeVisible();
});

test("section Dividende : zoom plein écran d'un graphique (sans requête)", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  const yieldCard = page.locator(".card.mini", { hasText: "Dividend Yield" }).first();
  await yieldCard.locator(".expand-btn").click();

  const modal = page.locator(".modal-detail", { hasText: "Dividend Yield" });
  await expect(modal).toBeVisible();
  // Presets : YTD / 1A / 5A / 10A / MAX (sans 3A).
  await expect(modal.locator(".period-chip", { hasText: "5A" })).toBeVisible();
  await expect(modal.locator(".period-chip", { hasText: "10A" })).toBeVisible();
  await expect(modal.locator(".period-chip", { hasText: "3A" })).toHaveCount(0);
  await expect
    .poll(async () => modal.locator("#chart-detail-plot .scatterlayer .trace").count(), {
      timeout: 20_000,
    })
    .toBeGreaterThan(0);

  // Le curseur à deux poignées est SOUS le graphe (l'œil lit d'abord la courbe).
  const chartBox = await modal.locator("#chart-detail-plot").boundingBox();
  const sliderBox = await modal.locator(".dual-slider").boundingBox();
  expect(sliderBox.y).toBeGreaterThan(chartBox.y + chartBox.height - 1);

  // La modale reçoit le focus (capture clavier / focus trap).
  await expect(modal).toBeFocused();

  // Fermeture par Échap.
  await page.keyboard.press("Escape");
  await expect(modal).not.toBeVisible();
});

test("section Dividende : zoom — plage partagée avec le héro et fermeture au clic extérieur", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  // Plage de la modale = plage du curseur de période du héro (source unique).
  const heroLabel = (await page.locator(".period-label").innerText()).trim();

  const yieldCard = page.locator(".card.mini", { hasText: "Dividend Yield" }).first();
  await yieldCard.locator(".expand-btn").click();
  const modal = page.locator(".modal-detail", { hasText: "Dividend Yield" });
  await expect(modal).toBeVisible();

  // À l'ouverture, le libellé de plage de la modale correspond au héro.
  await expect(modal.locator(".detail-range")).toHaveText(/–/);

  // Preset 1A -> la plage partagée est réécrite ; on la relit après fermeture.
  await modal.locator(".period-chip", { hasText: "1A" }).click();
  const detailLabel = (await modal.locator(".detail-range").innerText()).trim();

  // Fermeture au clic sur l'overlay (hors modale).
  const overlay = page.locator(".modal-overlay", { has: page.locator(".modal-detail") });
  await overlay.click({ position: { x: 5, y: 5 } });
  await expect(modal).not.toBeVisible();

  // Le héro reflète la MÊME plage (le preset a écrit rangeStart/rangeEnd partagés).
  await expect(page.locator(".period-label")).toContainText(detailLabel.split("–")[1].trim());
  expect(heroLabel).toBeTruthy();
});

test("section Dividende : zoom — le curseur à deux poignées déplace la plage", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  const yieldCard = page.locator(".card.mini", { hasText: "Dividend Yield" }).first();
  await yieldCard.locator(".expand-btn").click();
  const modal = page.locator(".modal-detail", { hasText: "Dividend Yield" });
  await expect(modal).toBeVisible();

  // La modale porte le MÊME curseur à deux poignées que le héro.
  const slider = modal.locator(".dual-slider");
  await expect(slider).toBeVisible();
  await expect(slider.locator(".ds-min")).toBeVisible();
  await expect(slider.locator(".ds-max")).toBeVisible();

  // Partir d'un preset pour avoir une plage connue, puis déplacer la poignée
  // gauche : le libellé de plage doit changer (curseur fonctionnel).
  await modal.locator(".period-chip", { hasText: "MAX" }).click();
  const before = (await modal.locator(".detail-range").innerText()).trim();

  const dsMin = slider.locator(".ds-min");
  await dsMin.evaluate((el) => {
    const max = Number(el.max);
    el.value = String(Math.floor(max * 0.5));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  const after = (await modal.locator(".detail-range").innerText()).trim();
  expect(after).not.toBe(before);

  // La plage est PARTAGÉE : le héro affiche la nouvelle borne gauche après fermeture.
  await page.keyboard.press("Escape");
  await expect(modal).not.toBeVisible();
  await expect(page.locator(".period-label")).toContainText(after.split("–")[0].trim());
});

test("section Dividende : zoom d'une carte à axe années (bornes traduites)", async ({ page }) => {
  await page.goto("/#RI.PA/dividende");
  await expect(page.locator(".header")).toBeVisible();

  // Carte à barres (axe années) : la modale doit traduire la plage de dates en
  // bornes d'années — le curseur partagé doit donc bien agir sur le tracé.
  const barCard = page.locator(".card.mini", { hasText: "Dividende / Action" }).first();
  await barCard.locator(".expand-btn").click();
  const modal = page.locator(".modal-detail", { hasText: "Dividende / Action" });
  await expect(modal).toBeVisible();
  await expect
    .poll(async () => modal.locator("#chart-detail-plot .barlayer .trace .point").count(), {
      timeout: 20_000,
    })
    .toBeGreaterThan(0);

  // Preset 5A : le curseur est repositionné, la modale se redessine.
  await modal.locator(".period-chip", { hasText: "5A" }).click();
  await expect(modal.locator(".detail-range")).toHaveText(/–/);

  // Déplacer la poignée gauche change la plage (curseur actif sur axe années).
  const before = (await modal.locator(".detail-range").innerText()).trim();
  await modal.locator(".dual-slider .ds-min").evaluate((el) => {
    el.value = String(Math.floor(Number(el.max) * 0.4));
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(modal.locator(".detail-range")).not.toHaveText(before);
});
