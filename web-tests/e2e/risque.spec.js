import { expect, test } from "@playwright/test";

// #33 — onglet « Risque & dynamique » : le graphique à deux étages se trace
// (SVG Plotly réellement dimensionné) et les trois lignes factuelles vivent dans
// l'info-bulle ⓘ de la barre de période (repliée par défaut, clic et clavier).
// Le parcours sème d'abord sa fiche via l'API (aucune base préexistante n'est
// présupposée) puis vérifie l'absence d'erreur console.

test("onglet Risque & dynamique : graphique tracé et lignes factuelles (#33)", async ({
  page,
  request,
}) => {
  // Fixture : la fiche RI.PA (prix + chart.risk) est demandée via la même API
  // que celle qui sert le front. Elle réchauffe le cache et vérifie le contrat.
  const seeded = await request.get("/api/stock/RI.PA");
  expect(seeded.ok()).toBeTruthy();
  const payload = await seeded.json();
  expect(payload.chart?.risk?.now).toBeTruthy();

  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });

  await page.goto("/#RI.PA/risque");
  await expect(page.locator(".header")).toBeVisible();
  await expect(page.locator(".section-tab.active")).toHaveAttribute("data-section", "risque");
  await expect(page.locator(".section h2", { hasText: "Risque & dynamique" })).toBeVisible();

  // SVG Plotly présent ET largeur réelle > 0 (un conteneur masqué donne 0).
  const largeur = () =>
    page.evaluate(() => {
      const svg = document.querySelector("#risk-chart svg");
      return svg ? Math.round(svg.getBoundingClientRect().width) : 0;
    });
  await expect(page.locator("#risk-chart svg").first()).toBeVisible({ timeout: 30_000 });
  await expect.poll(largeur, { timeout: 30_000 }).toBeGreaterThan(0);

  // Deux étages au minimum : chute + volatilité (la 3e trace, rouge, n'existe
  // que si un seuil d'anomalie est calculable).
  await expect
    .poll(
      async () => page.locator("#risk-chart .scatterlayer .trace").count(),
      { timeout: 30_000 },
    )
    .toBeGreaterThanOrEqual(2);

  // La note de lecture est repliée par défaut dans l'info-bulle ⓘ de la barre
  // de période : les trois lignes de la fiche §4.7 existent mais sont masquées.
  const infoBtn = page.locator(".risk-toolbar .info-btn");
  const infoPanel = page.locator(".risk-card > .info-panel");
  await expect(infoBtn).toHaveAttribute("aria-expanded", "false");
  await expect(infoBtn).toHaveAttribute("aria-label", "Comment lire ce graphique");
  await expect(infoBtn).toHaveText("ⓘ");
  await expect(infoPanel).toBeHidden();
  await expect(page.locator(".risk-line")).toHaveCount(3);
  await expect(page.locator(".risk-line:visible")).toHaveCount(0);

  // Un clic déplie la note : les trois lignes factuelles deviennent visibles et
  // la largeur du graphe n'est pas cassée par l'ouverture du panneau.
  await infoBtn.click();
  await expect(infoBtn).toHaveAttribute("aria-expanded", "true");
  await expect(infoBtn).toHaveText("✕");
  await expect(infoPanel).toBeVisible();
  await expect(page.locator(".risk-line")).toHaveCount(3);
  for (let i = 0; i < 3; i += 1) {
    await expect(page.locator(".risk-line").nth(i)).toBeVisible();
  }
  await expect(page.locator(".risk-line").nth(0)).toContainText("Chute depuis le plus haut");
  await expect(page.locator(".risk-line").nth(1)).toContainText(/Volatilité \d+ j/);
  await expect(page.locator(".risk-line").nth(2)).toContainText("12-1 (hors dividendes)");
  await expect.poll(largeur, { timeout: 30_000 }).toBeGreaterThan(0);

  // Second clic : la note se replie, le graphe garde sa largeur.
  await infoBtn.click();
  await expect(infoBtn).toHaveAttribute("aria-expanded", "false");
  await expect(infoBtn).toHaveText("ⓘ");
  await expect(infoPanel).toBeHidden();
  await expect(page.locator(".risk-line:visible")).toHaveCount(0);
  await expect.poll(largeur, { timeout: 30_000 }).toBeGreaterThan(0);

  // Puces de période : 1A / 5A / 10A / 20A / MAX (10A actif par défaut).
  const chips = page.locator(".risk-toolbar .period-chip");
  await expect(chips).toHaveCount(5);
  await expect(page.locator(".risk-toolbar .period-chip.active")).toHaveText("10A");
  await expect(page.locator(".risk-toolbar .period-chip", { hasText: "MAX" })).toBeVisible();

  // Max retrace l'histoire complète, sans casser le graphe.
  await page.locator(".risk-toolbar .period-chip", { hasText: "MAX" }).click();
  await expect(page.locator(".risk-toolbar .period-chip.active")).toHaveText("MAX");
  await expect.poll(largeur, { timeout: 30_000 }).toBeGreaterThan(0);

  // Au clavier : la pastille est focusable, Espace ouvre la note, Entrée la referme.
  await infoBtn.focus();
  await expect(infoBtn).toBeFocused();
  await page.keyboard.press("Space");
  await expect(infoBtn).toHaveAttribute("aria-expanded", "true");
  await expect(infoPanel).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(infoBtn).toHaveAttribute("aria-expanded", "false");
  await expect(infoPanel).toBeHidden();

  expect(errors).toEqual([]);
});
