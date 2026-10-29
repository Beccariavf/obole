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

test("section Momentum : fiabilité, trois colonnes in/out et pied des trades", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/#RI.PA/momentum");

  const table = page.locator(".mom-backtest-table");
  await expect(table).toBeVisible({ timeout: 30_000 });
  // Sept lignes de mesures et TROIS colonnes de valeurs sous l'en-tête « Mesure ».
  await expect(table.locator("tbody tr")).toHaveCount(7);
  await expect(table.locator("thead th")).toHaveCount(4);
  await expect(table.locator("thead th").nth(1)).toHaveText("Buy & hold");
  await expect(table.locator("thead th").nth(2)).toHaveText(/^in$/i);
  await expect(table.locator("thead th").nth(3)).toHaveText(/^out$/i);
  for (const tr of await table.locator("tbody tr").all()) {
    await expect(tr.locator("td")).toHaveCount(3);
  }
  // Le caption et les en-têtes de colonne sont annoncés au lecteur d'écran.
  await expect(table.locator("caption")).toContainText("séances in et out");
  for (const th of await table.locator("thead th").all()) {
    await expect(th).toHaveAttribute("scope", "col");
  }

  // Pied : les trades et le rendement réel de la stratégie, hors des colonnes.
  const foot = page.locator(".mom-backtest-trades");
  await expect(foot).toBeVisible();
  await expect(foot).toContainText(/\d+ trades? · stratégie -?[\d,]+ %\/an/);
  // L'information ne dépend pas de la couleur : la légende dit le drawdown
  // conditionnel en toutes lettres.
  await expect(page.locator(".mom-backtest-note")).toContainText("conditionnel");

  // Changer la fenêtre relance le calcul : au moins un chiffre bouge.
  const cagr = () => table.locator("tbody tr").first().locator("td").first().textContent();
  const before = await cagr();
  await page.locator(".mom-history-card .period-chip", { hasText: "1A" }).click();
  await expect.poll(cagr).not.toBe(before);

  // Aucune erreur console sur la fiche.
  expect(errors).toEqual([]);
});

test("fiabilité : la polarité de out est inversée, celle de in ne l'est pas", async ({
  page,
}) => {
  await page.goto("/#RI.PA/momentum");
  const table = page.locator(".mom-backtest-table");
  await expect(table).toBeVisible({ timeout: 30_000 });

  // Payload déterministe : le MÊME CAGR positif dans les deux paniers. Le rendu
  // réel doit colorer in en bleu et out en rouge — la convention locale de #32.
  await page.evaluate(() => {
    const comp = window.Alpine.$data(document.querySelector(".wrap"));
    const block = (cagr) => ({
      cagr_pct: cagr,
      volatility_pct: 18.2,
      sharpe: 0.4,
      sortino: 0.5,
      max_drawdown_pct: -20,
      calmar: 0.2,
      sessions_pct: 64,
    });
    comp.momBacktest = {
      buy_hold: block(6.8),
      in: block(2.4),
      out: block(2.4),
      window: { start: "2015-01-02", end: "2024-12-31", sessions: 2561 },
      trades: 27,
      strategy_cagr_pct: 4.2,
    };
  });

  const cagrRow = table.locator("tbody tr").first();
  await expect(cagrRow.locator("td").nth(0)).toHaveText("6,80 %");
  await expect(cagrRow.locator("td").nth(1)).toHaveText("2,40 %");
  await expect(cagrRow.locator("td").nth(2)).toHaveText("2,40 %");
  await expect(cagrRow.locator("td").nth(1)).toHaveClass(/good/);
  await expect(cagrRow.locator("td").nth(2)).toHaveClass(/bad/);
  // Les mesures non signées restent neutres : aucune classe de couleur.
  const volatilityRow = table.locator("tbody tr").nth(1);
  await expect(volatilityRow.locator("td").nth(1)).not.toHaveClass(/good|bad/);
  await expect(volatilityRow.locator("td").nth(2)).not.toHaveClass(/good|bad/);
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
