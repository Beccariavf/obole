import { expect, test } from "@playwright/test";

// Espace Portefeuille (#17.0/#17.1) : le bouton ouvre la modale, les onglets
// horizontaux pilotent les sections, la saisie recalcule une position brute, et
// le Résumé trace la performance vs benchmark (avec zoom plein écran).
// Aucun appel réseau externe : toutes les routes /api/portfolio/* sont locales.
//
// On intercepte les routes pour isoler l'état (pas de pollution de la base
// réelle) : un compte et une transaction en mémoire, servis par le routeur.

// Routes « portefeuille » minimales : benchmarks + résumé vides (le socle de
// saisie n'en dépend pas, mais l'onglet Résumé est désormais la page d'accueil).
async function routeEmptyPortfolio(page, summary = null) {
  await page.route("**/api/portfolio/benchmarks", (route) =>
    route.fulfill({
      json: {
        benchmarks: [
          { key: "world", ticker: "CW8.PA", label: "MSCI World" },
          { key: "sp500", ticker: "ESE.PA", label: "S&P 500" },
        ],
        default: "CW8.PA",
        periods: ["ytd", "1a", "3a", "5a", "max"],
        period_default: "1a",
        top_n: 5,
      },
    }),
  );
  // Étiquettes (#17.6) : la portée par défaut (« toutes ») en renvoie la liste.
  await page.route("**/api/portfolio/tags**", (route) => route.fulfill({ json: { tags: [] } }));
  // Risque (#17.3) : payload vide par défaut (les tests dédiés le surchargent).
  await page.route("**/api/portfolio/risk**", (route) =>
    route.fulfill({
      json: {
        dates: [], period: "1a", period_start: null,
        benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
        drawdown: [], benchmark_drawdown: [], months: [],
        metrics: {
          max_drawdown_pct: 0, current_drawdown_pct: 0, recovered: true,
          longest_recovery_days: 0, volatility_pct: null,
          best_month_pct: null, worst_month_pct: null,
        },
        benchmark_metrics: {
          max_drawdown_pct: 0, current_drawdown_pct: 0, recovered: true,
          longest_recovery_days: 0, volatility_pct: null,
        },
        correlation: { tickers: [], matrix: [], excluded: [] },
        warnings: [],
      },
    }),
  );
  const empty = {
    dates: [], period: "1a", period_start: null,
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    portfolio: [], benchmark_curve: [],
    kpis: {}, accounts: [], holdings: [], account: null, top: [], flop: [], warnings: [],
  };
  await page.route("**/api/portfolio/summary**", (route) =>
    route.fulfill({ json: summary || empty }),
  );
}

test("portefeuille : bandeau de contexte unique (périmètre · période · benchmark)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const accounts = [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }];
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();

  // UN SEUL bandeau de contexte dans tout l'espace.
  const context = page.locator(".pf-context");
  await expect(context).toHaveCount(1);

  // Aucun ancien bandeau d'onglet ne subsiste (les quatre ont été supprimés).
  for (const gone of [".pf-risk-head", ".pf-perf-head", ".pf-div-head", ".pf-bench-row"]) {
    await expect(page.locator(gone)).toHaveCount(0);
  }

  // Hauteur UNIQUE des trois familles de contrôles (selects compte/benchmark et
  // chips de période) : c'était trois hauteurs différentes avant le chantier.
  const heights = await context.locator(".pf-ctl, .period-chip").evaluateAll((els) =>
    els.filter((e) => e.getBoundingClientRect().height > 0)
      .map((e) => Math.round(e.getBoundingClientRect().height)));
  expect(new Set(heights).size, `hauteurs: ${heights.join("/")}`).toBe(1);
  expect(heights[0]).toBeGreaterThanOrEqual(32);

  // Même RAYON et même CHEVRON pour les trois familles : une image de fond ne
  // peut pas hériter de `currentColor`, donc le chevron vient d'un token unique
  // et les selects partagent le même `background-image`.
  const shapes = await context.locator(".pf-ctl, .period-chip").evaluateAll((els) =>
    els.filter((e) => e.getBoundingClientRect().height > 0).map((e) => {
      const s = getComputedStyle(e);
      return {
        tag: e.tagName,
        radius: s.borderTopLeftRadius,
        chevron: e.tagName === "SELECT" ? s.backgroundImage : null,
      };
    }));
  expect(new Set(shapes.map((s) => s.radius)).size, "rayon unique").toBe(1);
  const chevrons = shapes.filter((s) => s.chevron).map((s) => s.chevron);
  expect(chevrons.length, "au moins deux selects").toBeGreaterThan(1);
  expect(new Set(chevrons).size, "chevron unique").toBe(1);
  expect(chevrons[0]).toContain("svg");

  // Capacités par section : le registre pilote l'affichage des groupes.
  const periodGroup = context.locator(".pf-context-group", { hasText: "Période" });
  const benchGroup = context.locator(".pf-context-group", { hasText: "Benchmark" });

  // Résumé : les trois.
  await expect(periodGroup).toBeVisible();
  await expect(benchGroup).toBeVisible();

  // Positions : périmètre seul.
  await page.locator(".pf-tabs .pf-tab[data-pf-section='positions']").click();
  await expect(periodGroup).toBeHidden();
  await expect(benchGroup).toBeHidden();

  // Dividende : périmètre seul aussi (ni période ni benchmark).
  await page.locator(".pf-tabs .pf-tab[data-pf-section='dividende']").click();
  await expect(periodGroup).toBeHidden();
  await expect(benchGroup).toBeHidden();

  // Risque : les trois reviennent.
  await page.locator(".pf-tabs .pf-tab[data-pf-section='risque']").click();
  await expect(periodGroup).toBeVisible();
  await expect(benchGroup).toBeVisible();

  // Performance : périmètre + benchmark, PAS de période (MAX par principe).
  await page.locator(".pf-tabs .pf-tab[data-pf-section='performance']").click();
  await expect(periodGroup).toBeHidden();
  await expect(benchGroup).toBeVisible();

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("portefeuille : le bandeau de contexte reste visible pendant le défilement", async ({ page }) => {
  const accounts = [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }];
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  // Un résumé long (Top/Flop remplis) rend la VUE réellement défilable.
  const long = {
    dates: [], period: "1a", period_start: null,
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    portfolio: [], benchmark_curve: [], kpis: {}, accounts: [], holdings: [],
    top: Array.from({ length: 5 }, (_, i) => ({ ticker: `T${i}.PA`, name: `Titre ${i}`,
      perf: i, gain: i * 10, weight_pct: 10 })),
    flop: [], account: null, warnings: [],
  };
  await routeEmptyPortfolio(page, long);

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  const context = page.locator(".pf-context");
  await expect(context).toBeVisible();
  expect(await context.evaluate((el) => getComputedStyle(el).position)).toBe("sticky");

  // Défilement RÉEL : dans une vue, c'est le DOCUMENT qui défile (plus de
  // `.pf-main` à hauteur imposée). Le bandeau se décolle de sa position de flux
  // puis s'accroche à `--head-top` : il ne bouge plus d'un pixel ensuite, sinon
  // le contexte se perd en bas d'un long tableau.
  await page.mouse.wheel(0, 700);
  await page.waitForTimeout(200);
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);
  const colle = await context.boundingBox();
  await page.mouse.wheel(0, 400);
  await page.waitForTimeout(200);
  const encore = await context.boundingBox();
  await expect(context).toBeVisible();
  expect(Math.round(encore.y), "bandeau accroché au défilement").toBe(Math.round(colle.y));
  expect(
    Math.abs(Math.round(colle.y) - 16),
    "accroché à la même hauteur que le rail (--head-top)",
  ).toBeLessThanOrEqual(1);
});

test("portefeuille : bouton, onglets et saisie d'une position (décimales)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  // Backend en mémoire : comptes + transactions + positions recalculées côté test.
  const accounts = [];
  const transactions = [];
  await page.route("**/api/portfolio/accounts", async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const { name } = req.postDataJSON();
      const acc = { id: accounts.length + 1, name, currency: "EUR", created_at: 0 };
      accounts.push(acc);
      return route.fulfill({ json: { status: "ok", id: acc.id } });
    }
    return route.fulfill({ json: accounts });
  });
  await page.route("**/api/portfolio/transactions**", async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const body = req.postDataJSON();
      transactions.push({ id: transactions.length + 1, ...body });
      return route.fulfill({ json: { status: "ok", id: transactions.length } });
    }
    return route.fulfill({ json: transactions });
  });
  await page.route("**/api/portfolio/dividends**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/portfolio/positions**", (route) => {
    // Position dérivée de l'achat saisi (PRU = prix).
    const rows = transactions.map((tx) => ({
      ticker: tx.ticker,
      quantity: tx.quantity,
      pru: tx.price,
      cost_basis: tx.quantity * tx.price,
      realized: 0,
    }));
    return route.fulfill({ json: rows });
  });
  // Résumé (#17.1) : benchmarks + résumé servis en mémoire (aucun réseau).
  await routeEmptyPortfolio(page);

  await page.goto("/");

  // Le rail porte les espaces dans l'ordre validé : Paramètres vient en pied,
  // après Watchlist. La barre de recherche, elle, ne porte plus AUCUN espace.
  const railIds = await page
    .locator(".app-rail-btn")
    .evaluateAll((els) => els.map((e) => e.dataset.space));
  expect(railIds).toEqual(["analyse", "indices", "screener", "portfolio", "watchlist", "settings"]);
  await expect(page.locator(".searchbar .btn.ghost", { hasText: "Portefeuille" })).toHaveCount(0);

  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await expect(page.locator(".app-view.view-portfolio .view-head h3", { hasText: "Portefeuille" })).toBeVisible();

  // L'espace portefeuille est une PAGE de la coquille : elle occupe TOUTE la
  // colonne de contenu (`.app-main`) et le rail reste visible à sa gauche. Une
  // couche plein écran recouvrirait le rail — c'est précisément ce que la vue
  // supprime.
  const modal = page.locator(".app-view.view-portfolio");
  const box = await modal.boundingBox();
  const mainBox = await page.locator(".app-main").boundingBox();
  const railBox = await page.locator(".app-rail").boundingBox();
  expect(box, "vue portefeuille mesurable").not.toBeNull();
  expect(box.width, "la vue occupe la colonne de contenu").toBeGreaterThanOrEqual(
    mainBox.width - 1,
  );
  expect(railBox, "rail visible").not.toBeNull();
  expect(
    box.x,
    "la vue commence à droite du rail",
  ).toBeGreaterThanOrEqual(railBox.x + railBox.width - 1);
  // Et le rail reste cliquable : c'est lui qui commande le changement d'espace.
  await expect(page.locator(".app-rail-btn[data-space='analyse']")).toBeVisible();

  // Onglets horizontaux : 5 sections, « Résumé » active par défaut (#17.1).
  const tabs = page.locator(".pf-tabs .pf-tab");
  await expect(tabs).toHaveCount(5);
  expect(await tabs.evaluateAll((els) => els.map((e) => e.dataset.pfSection))).toEqual([
    "resume",
    "risque",
    "performance",
    "dividende",
    "positions",
  ]);
  await expect(page.locator(".pf-tabs .pf-tab.active")).toHaveAttribute(
    "data-pf-section",
    "resume",
  );
  // Toutes les sections sont livrées : aucun onglet n'est plus « à venir ».
  await expect(page.locator(".pf-tabs .pf-tab[data-pf-section='performance']")).toBeEnabled();
  await expect(page.locator(".pf-tabs .pf-tab[data-pf-section='risque']")).toBeEnabled();
  await expect(page.locator(".pf-tabs .pf-tab[data-pf-section='dividende']")).toBeEnabled();
  await expect(page.locator(".pf-tabs .pf-tab-soon:visible")).toHaveCount(0);

  // Bascule sur « Positions » (la section de saisie du socle).
  await page.locator(".pf-tabs .pf-tab[data-pf-section='positions']").click();
  await expect(page.locator(".pf-tabs .pf-tab.active")).toHaveAttribute(
    "data-pf-section",
    "positions",
  );

  // Création d'un compte.
  await page.locator(".pf-account-row input.search-input").fill("PEA");
  await page.locator(".pf-account-row button", { hasText: "Nouveau compte" }).click();
  await expect(page.locator(".pf-account-chips .chip")).toHaveCount(1);

  // Sélecteur de compte (vue consolidée « Tous » + le compte créé).
  const selector = page.locator(".pf-context .pf-account-select");
  await expect(selector.locator("option")).toHaveCount(2);
  await expect(selector.locator("option").first()).toHaveText("Tous les comptes");
  await expect(selector.locator("option").nth(1)).toHaveText("PEA");

  // Saisie d'une transaction d'achat AVEC DÉCIMALES À LA VIRGULE.
  const form = page.locator(".pf-form").first();
  await form.locator("input[type='text']").first().fill("RI.PA"); // ticker
  await form.locator("input[type='date']").fill("2024-01-02");
  const qty = form.locator("input[inputmode='decimal']").nth(0);
  const price = form.locator("input[inputmode='decimal']").nth(1);
  await qty.fill("1,5");
  await price.fill("60,50");
  await expect(qty).toHaveValue("1,5"); // la virgule n'est PAS effacée
  await page
    .locator(".pf-saisie")
    .locator("button", { hasText: "Ajouter la transaction" })
    .click();

  // La position brute est recalculée : 1,5 × 60,50.
  const positionRow = page.locator(".pf-feature", { hasText: "Positions" }).locator("tbody tr");
  await expect(positionRow).toHaveCount(1);
  await expect(positionRow).toContainText("RI.PA");
  await expect(positionRow).toContainText("1,5");
  await expect(positionRow).toContainText("60,50");

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("portefeuille : changer de contexte ne recharge QUE la section visible", async ({ page }) => {
  // Compteur de requêtes observées (côté page.route) par endpoint agrégé.
  const hits = { summary: 0, risk: 0, performance: 0, security: 0 };
  const accounts = [
    { id: 1, name: "PEA", currency: "EUR", created_at: 0 },
    { id: 2, name: "CTO", currency: "EUR", created_at: 0 },
  ];
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await page.route("**/api/portfolio/tags**", (route) => route.fulfill({ json: { tags: [] } }));
  await page.route("**/api/portfolio/risk**", (route) => {
    hits.risk += 1;
    return route.fulfill({ json: { dates: [], period: "1a", period_start: null,
      benchmark: { ticker: "CW8.PA", label: "MSCI World" }, drawdown: [],
      benchmark_drawdown: [], months: [], metrics: {}, benchmark_metrics: {},
      correlation: { tickers: [], matrix: [], excluded: [] }, warnings: [] } });
  });
  const perf = { table: [], monthly: [], retrospective: [], risk_adjusted: { periods: ["max"] } };
  await page.route("**/api/portfolio/performance**", (route) => {
    hits.performance += 1;
    return route.fulfill({ json: perf });
  });
  await page.route("**/api/portfolio/summary**", (route) => {
    hits.summary += 1;
    return route.fulfill({ json: { dates: [], period: "1a", period_start: null,
      benchmark: { ticker: "CW8.PA", label: "MSCI World" }, portfolio: [],
      benchmark_curve: [], kpis: {}, accounts: [], holdings: [], top: [], flop: [],
      account: null, warnings: [] } });
  });

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await expect(page.locator(".pf-context")).toBeVisible();

  // Sur l'onglet Risque, changer de COMPTE ne relance que le risque.
  await page.locator(".pf-tabs .pf-tab[data-pf-section='risque']").click();
  await expect.poll(() => hits.risk).toBeGreaterThan(0);
  const base = { ...hits };
  await page.locator(".pf-context .pf-account-select").selectOption("1");
  await expect.poll(() => hits.risk).toBe(base.risk + 1);
  expect(hits.summary, "le Résumé n'est pas rechargé hors écran").toBe(base.summary);
  expect(hits.performance, "la Performance n'est pas rechargée hors écran").toBe(base.performance);

  // Changer d'ÉTIQUETTE vide la sélection puis ne recharge que la section visible.
  const tagSel = page.locator(".pf-context .pf-tag-select");
  const base2 = { ...hits };
  await page.locator(".pf-context .pf-account-select").selectOption("");
  await expect.poll(() => hits.risk).toBe(base2.risk + 1);
  await expect(tagSel).toHaveValue("");
  expect(hits.summary).toBe(base2.summary);
});

test("portefeuille : la période choisie survit à un rechargement de page", async ({ page }) => {
  // `portfolio_period` est un réglage persisté, comme le benchmark : le serveur
  // le renvoie au chargement et le front le réapplique.
  let saved = "1a";
  await page.route("**/api/settings**", async (route) => {
    const req = route.request();
    if (req.method() === "PUT") {
      const body = req.postDataJSON();
      const values = body.values || body;
      if (values.portfolio_period) saved = values.portfolio_period;
      return route.fulfill({ json: { values: { portfolio_period: saved } } });
    }
    return route.fulfill({ json: { values: { portfolio_period: saved }, defs: {}, groups: [] } });
  });
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: [] }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  const context = page.locator(".pf-context");
  await expect(context.locator(".period-chip.active")).toHaveText("1A");

  // Choisir 3A mémorise le réglage côté serveur…
  await context.locator(".period-chip", { hasText: "3A" }).click();
  await expect(context.locator(".period-chip.active")).toHaveText("3A");
  expect(saved).toBe("3a");

  // … et un rechargement complet de la page réapplique 3A (plus de retour à 1A
  // pendant que le benchmark, lui, restait mémorisé).
  await page.reload();
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await expect(page.locator(".pf-context .period-chip.active")).toHaveText("3A");
});

test("portefeuille : la bascule Transaction/Dividende change le formulaire", async ({ page }) => {
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: [] }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  // Le Résumé est la page d'accueil : on bascule sur « Positions » (saisie).
  await page.locator(".pf-tabs .pf-tab[data-pf-section='positions']").click();
  const saisie = page.locator(".pf-saisie");
  await expect(saisie).toBeVisible();

  // Par défaut : formulaire transaction (champ Sens visible).
  await expect(saisie.locator("label", { hasText: "Sens" })).toBeVisible();

  // Bascule sur Dividende : le champ Sens disparaît, « Date de paiement » apparaît.
  await saisie.locator(".pf-seg button", { hasText: "Dividende" }).click();
  await expect(saisie.locator("label", { hasText: "Sens" })).toBeHidden();
  await expect(saisie.locator("label", { hasText: "Date de paiement" })).toBeVisible();
  await expect(saisie.locator(".pf-actions button", { hasText: "Ajouter le dividende" })).toBeVisible();
});

test("portefeuille : revenir à « Tous les comptes » recharge sans 422", async ({ page }) => {
  // Régression : `<option :value="null">` + `x-model.number` faisait valoir la
  // chaîne "null" -> `?account_id=null` -> 422 -> tableaux vides. On vérifie que
  // le retour à la vue consolidée repart bien sans paramètre de compte.
  const requests = [];
  const accounts = [
    { id: 1, name: "PEA", currency: "EUR", created_at: 0 },
    { id: 2, name: "CTO", currency: "EUR", created_at: 0 },
  ];
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => {
      requests.push(route.request().url());
      return route.fulfill({ json: [] });
    });
  }
  await routeEmptyPortfolio(page);

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await expect(page.locator(".app-view.view-portfolio .view-head h3")).toBeVisible();

  const selector = page.locator(".pf-context .pf-account-select");
  await selector.selectOption("1"); // compte précis
  await selector.selectOption(""); // retour à « Tous les comptes »
  await expect(page.locator(".app-view.view-portfolio")).toBeVisible();

  // Aucune requête ne doit porter `account_id=null` (ou "null").
  expect(requests.some((u) => /account_id=(null|%22null%22)/.test(u))).toBe(false);
  // Et la dernière salve consolidée part sans paramètre de compte.
  expect(requests[requests.length - 1]).not.toContain("account_id=");
});

test("portefeuille : le Résumé trace la performance et s'agrandit en plein écran", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const accounts = [{ id: 1, name: "PEA Trade Republic", currency: "EUR", created_at: 0 }];
  const dates = ["2023-01-02", "2023-06-01", "2024-01-02", "2024-06-03"];
  const summary = {
    dates, period: "1a", period_start: "2023-01-02",
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    portfolio: [0, 12.5, 25.0, 30.85],
    benchmark_curve: [0, 8.0, 12.0, 14.58],
    kpis: {
      total_value: 2126.82, invested: 1836.5, total_return: 290.33, total_return_pct: 15.81,
      period_return_pct: 30.85, annualized_pct: 25.16, dividends: 72.97,
      dividend_yield_pct: 3.97, benchmark_period_pct: 14.58,
    },
    accounts: [{ account_id: 1, name: "PEA Trade Republic", value: 2126.82 }],
    holdings: [{ ticker: "EDEN.PA", name: "Edenred SE", value: 1200.0 }],
    account: { account_id: 1, name: "PEA Trade Republic", since: "2025-04-04", fees: 14.56, taxes: 0.0, balance: 23.92 },
    top: [{ ticker: "EDEN.PA", name: "Edenred SE", perf: 55.69, gain: 36.38 },
          { ticker: "DSY.PA", name: "Dassault Systèmes SE", perf: 12.95, gain: 2.18 }],
    flop: [{ ticker: "WO61.PA", name: "Worldline SA", perf: -21.09, gain: -4.63 },
           { ticker: "RI.PA", name: "Pernod Ricard S.A.", perf: -4.09, gain: -0.44 }],
    warnings: [],
  };
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await page.route("**/api/portfolio/benchmarks", (route) =>
    route.fulfill({
      json: {
        benchmarks: [
          { key: "world", ticker: "CW8.PA", label: "MSCI World" },
          { key: "sp500", ticker: "ESE.PA", label: "S&P 500" },
        ],
        default: "CW8.PA", periods: ["ytd", "1a", "3a", "5a", "max"],
        period_default: "1a", top_n: 5,
      },
    }),
  );
  await page.route("**/api/portfolio/summary**", (route) => route.fulfill({ json: summary }));
  // Réglages : on fige le benchmark mémorisé sur CW8.PA pour que le choix de
  // ESE.PA déclenche bien un recalcul (sinon l'état persistant du serveur peut
  // déjà valoir ESE.PA et le garde-fou de setPfBenchmark sortirait tôt).
  await page.route("**/api/settings", async (route) => {
    if (route.request().method() === "PUT") {
      return route.fulfill({ json: { values: { portfolio_benchmark: "ESE.PA" } } });
    }
    return route.fulfill({ json: { values: { trend_ma_short: 11, trend_ma_long: 200, portfolio_benchmark: "CW8.PA" }, defs: {}, groups: [] } });
  });

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();

  // L'onglet par défaut est « Résumé » (page d'accueil du portefeuille).
  await expect(page.locator(".pf-tabs .pf-tab.active")).toHaveAttribute("data-pf-section", "resume");

  // Les 3 KPI et le Top/Flop sont rendus (nom + initiales + montant).
  await expect(page.locator(".pf-kpis .card.kpi")).toHaveCount(3);
  await expect(page.locator(".pf-kpis")).toContainText("2");
  const topRow = page.locator(".pf-rank-row", { hasText: "EDEN.PA" });
  await expect(topRow).toBeVisible();
  await expect(topRow).toContainText("Edenred SE"); // nom
  await expect(topRow.locator(".pf-rank-logo")).toHaveText("ES"); // initiales
  await expect(topRow).toContainText("+36,38 €"); // montant du gain
  await expect(page.locator(".pf-rank-row", { hasText: "WO61.PA" })).toBeVisible();

  // La courbe et le donut sont tracés (Plotly : traces présentes).
  await expect(page.locator("#pf-summary-plot .plot-container")).toBeVisible();
  await expect(page.locator("#pf-summary-donut .plot-container")).toBeVisible();

  // Donut CENTRÉ : le disque occupe le conteneur (marges nulles, domaine plein
  // cadre). Sans ce correctif, Plotly figeait le SVG à la largeur du 1er rendu et
  // le disque se décalait à gauche dès que la carte changeait de largeur.
  const donutGeom = () =>
    page.evaluate(() => {
      const d = document.getElementById("pf-summary-donut");
      const svg = d.querySelector("svg.main-svg");
      const slice = d.querySelector("g.slice path, path.slice");
      const dr = d.getBoundingClientRect();
      const sr = svg.getBoundingClientRect();
      const slr = slice.getBoundingClientRect();
      return {
        donutW: Math.round(dr.width),
        svgW: Math.round(sr.width),
        dx: Math.round(slr.left + slr.width / 2 - (dr.left + dr.width / 2)),
        dy: Math.round(slr.top + slr.height / 2 - (dr.top + dr.height / 2)),
        sliceW: Math.round(slr.width),
        sliceH: Math.round(slr.height),
      };
    });

  const before = await donutGeom();
  expect(Math.abs(before.dx), "donut centré horizontalement").toBeLessThanOrEqual(2);
  expect(Math.abs(before.dy), "donut centré verticalement").toBeLessThanOrEqual(2);
  expect(Math.abs(before.sliceW - before.sliceH), "disque circulaire").toBeLessThanOrEqual(2);
  expect(before.svgW, "SVG à la largeur du conteneur").toBeLessThanOrEqual(before.donutW + 1);

  // Le repli média 1 colonne change la largeur SANS événement fenêtre : le
  // ResizeObserver doit recentrer le donut tout seul. On attend que la géométrie
  // soit STABLE et correcte (le conteneur s'élargit avant que Plotly ne re-trace).
  const originalViewport = page.viewportSize();
  await page.setViewportSize({ width: 820, height: originalViewport?.height ?? 720 });
  await expect
    .poll(
      async () => {
        const g = await donutGeom();
        return (
          g.donutW > before.donutW &&
          Math.abs(g.dx) <= 2 &&
          Math.abs(g.sliceW - g.sliceH) <= 2 &&
          g.svgW <= g.donutW + 1
        );
      },
      { timeout: 5000 },
    )
    .toBe(true);
  const after = await donutGeom();
  expect(after.donutW, "la carte s'est bien élargie (repli média)").toBeGreaterThan(before.donutW);
  expect(Math.abs(after.dx), "donut recentré après repli média").toBeLessThanOrEqual(2);
  expect(Math.abs(after.sliceW - after.sliceH), "disque circulaire après resize").toBeLessThanOrEqual(2);
  expect(after.svgW, "SVG recalculé à la largeur du conteneur").toBeLessThanOrEqual(after.donutW + 1);

  // Aucun libellé de part ne doit être rogné par le bord du SVG (les libellés
  // sont DANS le disque : `textposition: "inside"`).
  const clippedLabels = await page.evaluate(() => {
    const d = document.getElementById("pf-summary-donut");
    const dr = d.getBoundingClientRect();
    return [...d.querySelectorAll(".slice text")].filter((t) => {
      if (getComputedStyle(t).display === "none") return false;
      const r = t.getBoundingClientRect();
      return r.left < dr.left - 1 || r.right > dr.right + 1;
    }).length;
  });
  expect(clippedLabels, "aucun libellé rogné par le bord du SVG").toBe(0);

  await page.setViewportSize(originalViewport ?? { width: 1280, height: 720 });

  // Les chips de période viennent de l'API (YTD / 1A / … / MAX).
  const chips = page.locator(".pf-context .pf-presets .period-chip");
  await expect(chips).toHaveCount(5);
  await expect(chips.first()).toHaveText("YTD");
  // La puce active porte bien la classe (fond accent) — la période par défaut est 1A.
  await expect(page.locator(".pf-context .pf-presets .period-chip.active")).toHaveText("1A");

  // Le bandeau compte affiche depuis / frais / taxes / dividendes nets.
  await page.locator(".pf-context .pf-account-select").selectOption("1");
  const banner = page.locator(".pf-account-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("Frais");
  await expect(banner).toContainText("Taxes");
  await expect(banner).toContainText("Dividendes nets de frais");

  // Zoom plein écran : état PROPRE (n'utilise pas la modale du héro).
  await page.locator(".pf-perf-card .expand-btn").click();
  const modal = page.locator("#pf-detail-modal");
  await expect(modal).toBeVisible();
  await expect(modal.locator(".pf-detail-chart")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(modal).toBeHidden();

  // Le sélecteur de benchmark (liste) recalcule : on vérifie qu'une nouvelle
  // requête /api/portfolio/summary part bien avec le ticker choisi.
  const summaryReq = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/summary") && r.url().includes("benchmark=ESE.PA"),
    { timeout: 10000 },
  );
  await page.locator(".pf-context .pf-bench-select").selectOption("ESE.PA");
  await summaryReq;

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("portefeuille : la section Risque trace le drawdown et la matrice de corrélation", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const accounts = [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }];
  const dates = ["2024-01-02", "2024-03-01", "2024-05-02", "2024-07-01"];
  const risk = {
    dates, period: "1a", period_start: "2024-01-02",
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    drawdown: [0, -5.2, -12.4, -3.1],
    benchmark_drawdown: [0, -3.0, -8.0, -1.5],
    metrics: {
      max_drawdown_pct: -12.4, current_drawdown_pct: -3.1, recovered: false,
      longest_recovery_days: 120, volatility_pct: 18.2,
      best_month_pct: 6.4, worst_month_pct: -7.1,
      peak_at: "2024-01-02", trough_at: "2024-05-02",
    },
    benchmark_metrics: {
      max_drawdown_pct: -8.0, current_drawdown_pct: -1.5, recovered: false,
      longest_recovery_days: 90, volatility_pct: 14.5,
    },
    months: [],
    corr_avg: 0.3933,
    correlation: {
      tickers: ["AI.PA", "RI.PA", "OR.PA"],
      matrix: [
        [1.0, 0.82, 0.15],
        [0.82, 1.0, 0.21],
        [0.15, 0.21, 1.0],
      ],
      excluded: [{ ticker: "MC.PA", obs: 8 }],
    },
    warnings: [],
  };
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);
  await page.route("**/api/portfolio/risk**", (route) => route.fulfill({ json: risk }));
  // Réglages FIGÉS : le benchmark mémorisé en base réelle ferait varier le bandeau
  // (« vs CACC.PA » au lieu de « vs MSCI World ») -> test déterministe.
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { values: { trend_ma_short: 11, trend_ma_long: 200, portfolio_benchmark: "CW8.PA" }, defs: {}, groups: [] } }),
  );

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab[data-pf-section='risque']").click();

  // Bandeau de contexte unique + courbe drawdown + matrice (≥ 2 lignes → heatmap).
  const context = page.locator(".pf-context");
  await expect(context).toContainText("Tous les comptes");
  await expect(page.locator("#pf-risk-drawdown .plot-container")).toBeVisible();
  await expect(page.locator("#pf-risk-corr .plot-container")).toBeVisible();

  // Périmètre, période ET benchmark vivent dans le MÊME bandeau : le Risque ne
  // redéclare plus rien (l'ancien texte mort « vs MSCI World » a disparu).
  const scope = context;
  await expect(scope.locator(".pf-account-select").first()).toBeVisible();
  await expect(scope.locator(".pf-account-select").first()).toContainText("Tous les comptes");
  await expect(scope.locator(".pf-bench-select")).toBeVisible();

  // Métriques : portefeuille vs référence (perte max, récupération, meilleur mois).
  const table = page.locator(".pf-risk-table");
  await expect(table).toContainText("Perte maximale");
  await expect(table).toContainText("12,4 %");
  await expect(table).toContainText("120 j");

  // Ligne écartée faute d'historique : badge explicite.
  await expect(page.locator(".pf-risk-card .reliability-badge")).toContainText("MC.PA");

  // Corrélation moyenne du périmètre, affichée à droite du titre de la matrice.
  await expect(page.locator(".pf-corr-avg")).toContainText("corrélation moyenne");

  // Changer de période recalcule le risque (nouvelle requête).
  const req = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/risk") && r.url().includes("period=3a"),
    { timeout: 10000 },
  );
  await page.locator(".pf-context .period-chip", { hasText: "3A" }).click();
  await req;

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("portefeuille : le bandeau Risque porte le sélecteur de périmètre (#17.3/#17.6)", async ({ page }) => {
  const accounts = [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }];
  const risk = {
    dates: ["2024-01-02", "2024-05-02"], period: "1a", period_start: "2024-01-02",
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    drawdown: [0, -12.4], benchmark_drawdown: [0, -8.0], months: [],
    metrics: { max_drawdown_pct: -12.4, current_drawdown_pct: -3.1, recovered: false,
      longest_recovery_days: 120, volatility_pct: 18.2, best_month_pct: 6.4, worst_month_pct: -7.1 },
    benchmark_metrics: { max_drawdown_pct: -8.0, current_drawdown_pct: -1.5, recovered: false,
      longest_recovery_days: 90, volatility_pct: 14.5 },
    correlation: { tickers: [], matrix: [], excluded: [] },
    warnings: [],
  };
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);
  // Une étiquette existe dans le compte : le sélecteur du bandeau doit l'exposer.
  await page.route("**/api/portfolio/tags**", (route) => route.fulfill({ json: { tags: ["Dividende"] } }));
  await page.route("**/api/portfolio/risk**", (route) => route.fulfill({ json: risk }));

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab[data-pf-section='risque']").click();

  // Choisir une étiquette DANS le bandeau de contexte re-scope le risque.
  const tagSel = page.locator(".pf-context .pf-tag-select").first();
  await expect(tagSel).toBeVisible();
  const req = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/risk") && r.url().includes("tag=Dividende"),
    { timeout: 10000 },
  );
  await tagSel.selectOption("Dividende");
  await req;
});

test("portefeuille : test de corrélation d'un ticker candidat (#17.3)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  const accounts = [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }];
  const risk = {
    dates: ["2024-01-02", "2024-05-02"], period: "1a", period_start: "2024-01-02",
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    drawdown: [0, -12.4], benchmark_drawdown: [0, -8.0], months: [],
    metrics: { max_drawdown_pct: -12.4, current_drawdown_pct: -3.1, recovered: false,
      longest_recovery_days: 120, volatility_pct: 18.2, best_month_pct: 6.4, worst_month_pct: -7.1 },
    benchmark_metrics: { max_drawdown_pct: -8.0, current_drawdown_pct: -1.5, recovered: false,
      longest_recovery_days: 90, volatility_pct: 14.5 },
    correlation: { tickers: ["AI.PA", "RI.PA"], matrix: [[1.0, 0.3], [0.3, 1.0]], excluded: [] },
    corr_avg: 0.3,
    warnings: [],
  };
  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: accounts }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);
  await page.route("**/api/portfolio/risk**", (route) => route.fulfill({ json: risk }));
  // Route la PLUS SPÉCIFIQUE en dernier : elle prime sur `risk**` (ordre
  // d'enregistrement Playwright) pour le chemin `.../risk/correlation-test`.
  await page.route("**/api/portfolio/risk/correlation-test**", (route) =>
    route.fulfill({
      json: {
        ticker: "MC.PA", tickers: ["AI.PA", "RI.PA"], row: [0.2, 0.5], obs: 250,
        current_avg: 0.17, new_avg: 0.21, delta: 0.04, warning: null,
      },
    }),
  );
  // Recherche par nom (#17.3) : la saisie passe par `/api/search` (nom OU code).
  await page.route("**/api/search**", (route) =>
    route.fulfill({
      json: [
        { symbol: "MC.PA", name: "LVMH", exchange: "PAR" },
        { symbol: "MOH.DE", name: "LVMH EO 0,3", exchange: "GER" },
      ],
    }),
  );

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab[data-pf-section='risque']").click();

  // Recherche par NOM : taper un nom affiche des suggestions de tickers.
  const input = page.locator(".pf-corr-test-input");
  await expect(input).toBeVisible();
  await input.fill("lvmh");
  const sugg = page.locator(".pf-corr-test-field .suggestion-item");
  await expect(sugg.first()).toBeVisible();
  await expect(sugg.first()).toContainText("MC.PA");

  // Clic sur la suggestion -> ticker figé + test lancé.
  const req = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/risk/correlation-test") && r.url().includes("ticker=MC.PA"),
    { timeout: 10000 },
  );
  await sugg.first().click();
  await req;
  await expect(input).toHaveValue("MC.PA");

  // Ligne de résultat tracée + impact affiché (hausse de corrélation = rouge).
  await expect(page.locator("#pf-risk-corr-test .plot-container")).toBeVisible();
  const impact = page.locator(".pf-corr-test-impact");
  await expect(impact).toContainText("corrélation moyenne");
  await expect(impact).toContainText("+0,04");
  await expect(impact).toHaveClass(/bad/);

  // Un CODE exact saisi à la main teste directement (pas de liste).
  const req2 = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/risk/correlation-test") && r.url().includes("ticker=MC.PA"),
    { timeout: 10000 },
  );
  await input.fill("MC.PA");
  await req2;
  await expect(page.locator(".pf-corr-test-field .suggestion-item")).toHaveCount(0);

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("portefeuille : étiqueter une position crée un portefeuille virtuel (#17.6)", async ({ page }) => {
  // Les routes « socle » (benchmarks, résumé, risque, étiquettes vides) d'abord,
  // puis les routes dynamiques QUI LES SURCHARGENT (Playwright : dernière route
  // enregistrée prioritaire).
  await routeEmptyPortfolio(page);

  const accounts = [];
  const transactions = [];
  await page.route("**/api/portfolio/accounts", async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const { name } = req.postDataJSON();
      const acc = { id: accounts.length + 1, name, currency: "EUR", created_at: 0 };
      accounts.push(acc);
      return route.fulfill({ json: { status: "ok", id: acc.id } });
    }
    return route.fulfill({ json: accounts });
  });
  await page.route("**/api/portfolio/transactions**", async (route) => {
    const req = route.request();
    if (req.method() === "POST") {
      const body = req.postDataJSON();
      transactions.push({ id: transactions.length + 1, ...body });
      return route.fulfill({ json: { status: "ok", id: transactions.length } });
    }
    const url = new URL(req.url());
    const tag = url.searchParams.get("tag");
    return route.fulfill({ json: tag ? transactions.filter((t) => t.tag === tag) : transactions });
  });
  await page.route("**/api/portfolio/positions**", (route) => {
    const url = new URL(route.request().url());
    const tag = url.searchParams.get("tag");
    const txs = transactions.filter((t) => t.tag && (!tag || t.tag === tag));
    return route.fulfill({
      json: txs.map((tx) => ({
        ticker: tx.ticker, quantity: tx.quantity, pru: tx.price,
        cost_basis: tx.quantity * tx.price, realized: 0, tags: [tx.tag],
      })),
    });
  });
  await page.route("**/api/portfolio/positions/tag", async (route) => {
    const { ticker, tag } = route.request().postDataJSON();
    for (const tx of transactions) if (tx.ticker === ticker) tx.tag = tag;
    return route.fulfill({ json: { status: "ok", updated: transactions.length } });
  });
  await page.route("**/api/portfolio/dividends**", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/portfolio/tags**", (route) =>
    route.fulfill({ json: { tags: [...new Set(transactions.map((t) => t.tag).filter(Boolean))] } }),
  );

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab[data-pf-section='positions']").click();

  // Créer un compte + saisir un achat AVEC étiquette.
  await page.locator(".pf-account-row input.search-input").fill("PEA");
  await page.locator(".pf-account-row button", { hasText: "Nouveau compte" }).click();
  await expect(page.locator(".pf-account-chips .chip")).toHaveCount(1);
  const form = page.locator(".pf-form").first();
  await form.locator("input[type='text']").first().fill("RI.PA");
  await form.locator("input[type='date']").fill("2024-01-02");
  await form.locator("input[inputmode='decimal']").nth(0).fill("10");
  await form.locator("input[inputmode='decimal']").nth(1).fill("100");
  // Le champ « Étiquette » (datalist) + la note coexistent.
  await expect(form.locator("label", { hasText: "Note (optionnel)" })).toBeVisible();
  const tagInput = form.locator("input[list='pf-tag-options']");
  await tagInput.fill("Actions dividende");
  await page.locator(".pf-saisie button", { hasText: "Ajouter la transaction" }).click();

  // La position porte la pastille d'étiquette et le sélecteur de portefeuille
  // virtuel apparaît en tête.
  const row = page.locator(".pf-feature tbody tr").first();
  await expect(row.locator(".pf-tag-chip")).toHaveText("Actions dividende");
  const tagSelect = page.locator(".pf-context .pf-tag-select");
  await expect(tagSelect).toBeVisible();
  await expect(tagSelect.locator("option")).toHaveCount(2);

  // Filtrer par étiquette recharge la portée (tag=… dans la requête).
  const req = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/transactions") && r.url().includes("tag="),
    { timeout: 10000 },
  );
  await tagSelect.selectOption("Actions dividende");
  await req;
  await expect(tagSelect).toHaveValue("Actions dividende");

  // Changer de compte RÉINITIALISE l'étiquette (elle peut ne pas exister dans le
  // nouveau périmètre) : pas d'écran vide silencieux.
  await page.locator(".pf-context .pf-account-select").selectOption("");
  await expect(tagSelect).toHaveValue("");
});

// --- Performance (#17.4) -----------------------------------------------------

// Payload complet de /api/portfolio/performance (stats, mensuels, contribution,
// ratios ajustés au risque, rétrospective) + le détail d'un titre (/api/stock).
function perfPayload() {
  const months = (vals) => {
    const m = {};
    for (let i = 1; i <= 12; i++) m[String(i)] = vals[i - 1] ?? null;
    return m;
  };
  return {
    period: "1a", period_start: "2024-01-02",
    benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" },
    stat_groups: [
      { id: "general", title: "Général", metrics: [
        { key: "count", label: "Nombre d'actions", unit: "num" },
        { key: "top5_weight", label: "Top 5 du portefeuille", unit: "pct" },
      ] },
      { id: "marges", title: "Marges", metrics: [
        { key: "gross_margin", label: "Marge brute", unit: "pct" },
      ] },
      { id: "risque", title: "Rendement ajusté au risque", metrics: [
        { key: "sharpe", label: "Ratio de Sharpe", unit: "num" },
      ] },
    ],
    stats: {
      count: { value: 2, good: null },
      top5_weight: { value: 88.0, good: null },
      gross_margin: { value: 42.5, good: true },
      sharpe: { value: null, good: null },
    },
    monthly: {
      months: 12,
      portfolio: { years: [2024], rows: [{ year: 2024, months: months([2.0, null, -1.0]), total: 0.98 }] },
      benchmark: { years: [2024], rows: [{ year: 2024, months: months([1.0, null, 0.5]), total: 1.5 }] },
    },
    contributions: {
      items: [
        { ticker: "RI.PA", name: "Pernod Ricard", weight_pct: 60, perf_pct: 10, contribution_pct: 6 },
        { ticker: "AI.PA", name: "Air Liquide", weight_pct: 40, perf_pct: -5, contribution_pct: -2 },
      ],
      total_pct: 4.0,
    },
    risk_adjusted: {
      risk_free_pct: 0,
      periods: ["ttm", "max"],
      by_period: {
        ttm: { portfolio: { sharpe: 1.2, sortino: 1.8 }, benchmark: { sharpe: 0.9, sortino: 1.1 } },
        max: { portfolio: { sharpe: 0.8, sortino: 1.0 }, benchmark: { sharpe: 0.6, sortino: 0.7 } },
      },
      portfolio: { sharpe: 0.8, sortino: 1.0 },
      benchmark: { sharpe: 0.6, sortino: 0.7 },
    },
    retrospective: [
      { id: 1, ticker: "RI.PA", side: "buy", date: "2024-01-02", quantity: 10, price: 100, delta_pct: 5.0 },
      { id: 2, ticker: "RI.PA", side: "buy", date: "2024-06-03", quantity: 5, price: 120, delta_pct: -3.2 },
    ],
    table: [
      { ticker: "RI.PA", name: "Pernod Ricard", weight_pct: 60, perf_pct: 10, contribution_pct: 6, market_value: 6000 },
      { ticker: "AI.PA", name: "Air Liquide", weight_pct: 40, perf_pct: -5, contribution_pct: -2, market_value: 4000 },
    ],
    warnings: [],
  };
}

function securityDetailPayload(benchmark) {
  const dates = ["2024-01-02", "2024-06-03", "2024-12-02"];
  const bench = benchmark === "ESE.PA"
    ? { key: "sp500", ticker: "ESE.PA", label: "S&P 500" }
    : { key: "world", ticker: "CW8.PA", label: "MSCI World" };
  return {
    ticker: "RI.PA",
    benchmark: bench,
    chart: { dates, price_adj: [100, 120, 110], price_raw: [100, 120, 110] },
    benchmark_curve: [400, 440, 420],
  };
}

async function routePerformance(page) {
  await page.route("**/api/portfolio/benchmarks", (route) =>
    route.fulfill({
      json: {
        benchmarks: [{ key: "world", ticker: "CW8.PA", label: "MSCI World" },
          { key: "eurostoxx", ticker: "ESE.PA", label: "S&P 500" }],
        default: "CW8.PA", periods: ["ytd", "1a", "3a", "5a", "max"],
        period_default: "1a", top_n: 5,
        detail_horizons: ["ttm", "3a", "5a", "10a", "max"],
        detail_horizon_default: "5a",
      },
    }),
  );
  await page.route("**/api/portfolio/accounts", (route) =>
    route.fulfill({ json: [{ id: 1, name: "PEA", currency: "EUR", created_at: 0 }] }),
  );
  for (const kind of ["transactions", "dividends", "positions", "tags"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) =>
      route.fulfill({ json: kind === "tags" ? { tags: [] } : [] }),
    );
  }
  await page.route("**/api/portfolio/summary**", (route) =>
    route.fulfill({ json: { dates: [], period: "1a", benchmark: { key: "world", ticker: "CW8.PA", label: "MSCI World" }, portfolio: [], benchmark_curve: [], kpis: {}, accounts: [], holdings: [], account: null, top: [], flop: [], warnings: [] } }),
  );
  await page.route("**/api/portfolio/performance**", (route) =>
    route.fulfill({ json: perfPayload() }),
  );
  await page.route("**/api/portfolio/security**", (route) => {
    const bench = new URL(route.request().url()).searchParams.get("benchmark");
    return route.fulfill({ json: securityDetailPayload(bench) });
  });
  await page.route("**/api/settings", (route) =>
    route.fulfill({ json: { values: { portfolio_benchmark: "CW8.PA" }, defs: {}, groups: [] } }),
  );
}

test("performance : donut, stats pondérées, mensuels et contribution (#17.4)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await routePerformance(page);
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();

  // La Performance est toujours demandée en période MAX (choix produit figé).
  const perfReq = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/performance") && r.url().includes("period=max"),
    { timeout: 10000 },
  );

  // L'onglet Performance n'est plus « à venir » : il est cliquable.
  const tab = page.locator(".pf-tabs .pf-tab", { hasText: "Performance" });
  await expect(tab).not.toHaveClass(/disabled/);
  await tab.click();
  await perfReq;
  await expect(page.locator(".pf-tabs .pf-tab.active")).toHaveAttribute("data-pf-section", "performance");

  // Bandeau de contexte : benchmark (liste curée) présent, PAS de groupe
  // Période (la Performance est toujours en durée MAX par principe).
  const context = page.locator(".pf-context");
  await expect(context.locator(".pf-bench-select")).toBeVisible();
  await expect(context.locator(".pf-context-group", { hasText: "Période" })).toBeHidden();

  // Donut « Répartition des titres » tracé.
  await expect(page.locator("#pf-perf-donut .plot-container")).toBeVisible();

  // Stats pondérées : groupe + valeur ; une stat nulle affiche « -- ».
  const panel = page.locator(".pf-stat-panel");
  await expect(panel).toContainText("Marges");
  await expect(panel).toContainText("Marge brute");
  await expect(panel).toContainText("42,5 %");
  await expect(panel).toContainText("Ratio de Sharpe");
  await expect(panel.locator(".pf-stat-value", { hasText: "--" })).toBeVisible();

  // Rendements mensuels : graphe de barres groupées, période = chip « TTM » +
  // sélecteur d'année (même duo que le héros Dividende).
  await expect(page.locator("#pf-perf-monthly-plot .plot-container")).toBeVisible();
  const monthlyCard = page.locator(".pf-perf-monthly");
  await expect(monthlyCard.locator(".pf-period-pick .period-chip")).toHaveText("TTM");
  await expect(monthlyCard.locator(".pf-period-pick .period-chip")).toHaveClass(/active/);
  await expect(monthlyCard.locator("select.pf-year-select")).toBeVisible();
  await expect(monthlyCard.locator(".pf-legend")).toContainText("Portefeuille");
  // Sélection d'une année : la chip se désactive, le grain change (re-trace).
  await monthlyCard.locator("select.pf-year-select").selectOption("2024");
  await expect(monthlyCard.locator(".pf-period-pick .period-chip")).not.toHaveClass(/active/);
  // Retour à TTM : la chip se réactive.
  await monthlyCard.locator(".pf-period-pick .period-chip").click();
  await expect(monthlyCard.locator(".pf-period-pick .period-chip")).toHaveClass(/active/);

  // Contribution à la performance : graphe de barres (pas de tableau) + total.
  const contrib = page.locator(".pf-perf-contrib");
  await expect(contrib.locator("#pf-perf-contrib-plot .plot-container")).toBeVisible();
  await expect(contrib.locator("table")).toHaveCount(0);
  await expect(contrib.locator(".pf-contrib-total")).toContainText("4 %");
  // Ordre de lecture : la PIRE contribution à gauche, la meilleure à droite.
  const contribOrder = await contrib.locator("#pf-perf-contrib-plot").evaluate((el) => ({
    labels: el._fullData[0].x,
    values: el._fullData[0].y,
    ySuffix: el._fullLayout.yaxis.ticksuffix,
    yGrid: el._fullLayout.yaxis.showgrid,
  }));
  expect(contribOrder.values).toEqual([-2, 6]);
  expect(contribOrder.labels).toEqual(["Air Liquide", "Pernod Ricard"]);
  // Cohérence avec le graphe voisin (rendements mensuels) : même axe Y en %.
  expect(contribOrder.ySuffix).toBe(" %");
  expect(contribOrder.yGrid).toBe(true);

  // Ratios ajustés au risque, par période : défaut MAX (0,8 / 0,6), puis TTM
  // (1,2 / 1,1) après clic sur la chip — recalcul sans refetch.
  const ra = page.locator(".pf-perf-ra");
  await expect(ra).toContainText("Sharpe");
  await expect(ra.locator(".pf-presets .period-chip.active")).toHaveText("MAX");
  await expect(ra).toContainText("0,8");
  await ra.locator(".pf-presets .period-chip", { hasText: "TTM" }).click();
  await expect(ra.locator(".pf-presets .period-chip.active")).toHaveText("TTM");
  await expect(ra).toContainText("1,2");

  expect(consoleErrors).toEqual([]);
});

test("performance : clic ligne -> détail + sélection d'un point d'entrée (#17.4)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await routePerformance(page);
  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab", { hasText: "Performance" }).click();

  // Clic sur une ligne du grand tableau -> fenêtre de détail + graphe tracé.
  await page.locator(".pf-clickable tbody tr", { hasText: "Pernod Ricard" }).click();
  const modal = page.locator(".modal-pf-detail", { hasText: "détail" });
  await expect(modal).toBeVisible();
  await expect(page.locator("#pf-security-plot .plot-container")).toBeVisible();

  // Graphe façon Résumé : plus de toggle log, plus de régression. Courbes de
  // perf cumulée (%, rebasées à 0) sur un axe en pourcentage.
  await expect(modal.locator(".pf-detail-log")).toHaveCount(0);
  // Aucune trace de régression résiduelle.
  await expect.poll(async () =>
    page.locator("#pf-security-plot").evaluate((el) =>
      (el.data || []).some((t) => /r[ée]gression|droite/i.test(t.name || ""))),
  ).toBe(false);

  // Horizons TTM/3A/5A/10A/MAX, défaut 5A actif (source unique config.py).
  const horizons = modal.locator(".pf-detail-horizons .period-chip");
  await expect(horizons).toHaveCount(5);
  await expect(modal.locator(".pf-detail-horizons .period-chip.active")).toHaveText("5A");
  await expect(horizons.filter({ hasText: "TTM" })).toHaveCount(1);
  await expect(horizons.filter({ hasText: "MAX" })).toHaveCount(1);

  // Le graphe de détail trace réellement les DEUX courbes (titre + benchmark) et
  // les triangles achat/vente (marqueurs scatter) — inspection des traces Plotly.
  const traceNames = async () =>
    page.locator("#pf-security-plot").evaluate((el) => (el.data || []).map((t) => t.name || t.marker?.symbol));
  await expect.poll(async () => (await traceNames()).includes("Titre")).toBe(true);
  await expect.poll(async () => (await traceNames()).includes("MSCI World")).toBe(true);
  await expect.poll(async () => (await traceNames()).includes("triangle-up")).toBe(true);

  // Axe en pourcentage.
  await expect.poll(async () =>
    page.locator("#pf-security-plot").evaluate((el) => el.layout?.yaxis?.ticksuffix),
  ).toBe(" %");

  // Changement d'horizon : recadrage pur client (aucun refetch) — un seul clic
  // suffit et la sélection des chips suit.
  await horizons.filter({ hasText: "TTM" }).click();
  await expect(horizons.filter({ hasText: "TTM" })).toHaveClass(/active/);
  await expect(modal.locator(".pf-detail-horizons .period-chip.active")).toHaveText("TTM");

  // La modale porte SON propre sélecteur de benchmark, restreint à la liste
  // curée : on compare à un autre indice sans quitter la fiche. Le choix est
  // LOCAL (la norme globale du bandeau ne bouge pas).
  const detailBench = modal.locator(".pf-detail-bench-select");
  await expect(detailBench).toBeVisible();
  await expect(detailBench).toHaveValue("CW8.PA");
  const securityReq = page.waitForRequest(
    (r) => r.url().includes("/api/portfolio/security") && r.url().includes("benchmark=ESE.PA"),
    { timeout: 10000 },
  );
  await detailBench.selectOption("ESE.PA");
  await securityReq;
  // Le libellé de la trace suit le nouveau benchmark (rechargé)…
  await expect.poll(async () =>
    page.locator("#pf-security-plot").evaluate((el) => (el.data || []).some((t) => t.name === "S&P 500")),
  ).toBe(true);
  // … et la norme globale du bandeau n'a PAS changé (choix local uniquement).
  await expect(page.locator(".pf-context .pf-bench-select")).toHaveValue("CW8.PA");

  // Légende : titre + benchmark.
  await expect(modal.locator(".pf-legend")).toContainText("Titre");

  // Sélection d'un point d'entrée : le titre « Points d'entrée/sortie » ouvre un
  // menu FLOTTANT en surimpression ; choisir un point recadre le graphe ET
  // referme le menu. Le graphe ne doit jamais être redimensionné.
  const pick = modal.locator(".pf-entry-pick");
  await expect(pick.locator(".pf-entry-trigger")).toBeVisible();
  await expect(pick.locator(".pf-entry-menu")).toBeHidden();
  const plotBoxBefore = await page.locator("#pf-security-plot").boundingBox();
  await pick.locator(".pf-entry-trigger").click();
  await expect(pick.locator(".pf-entry-menu")).toBeVisible();
  const plotBoxOpen = await page.locator("#pf-security-plot").boundingBox();
  // Ouvrir le menu ne décale PAS le graphe (surimpression, même largeur).
  expect(plotBoxOpen.width).toBe(plotBoxBefore.width);
  expect(plotBoxOpen.x).toBe(plotBoxBefore.x);

  // Le bouton porte l'écart au benchmark ; le choisir recadre ET referme le menu.
  const entry = pick.locator(".pf-entry-btn").first();
  await expect(entry).toContainText("2024-01-02");
  await expect(entry).toContainText("+5 %");
  await entry.click();
  await expect(entry).toHaveClass(/on/);
  await expect(pick.locator(".pf-entry-menu")).toBeHidden();
  const plotBoxAfter = await page.locator("#pf-security-plot").boundingBox();
  expect(plotBoxAfter.width).toBe(plotBoxBefore.width);

  expect(consoleErrors).toEqual([]);
});

test("portefeuille : Dividende — TTM par défaut + sélecteur d'année (#17.5)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  await page.route("**/api/portfolio/accounts", (route) => route.fulfill({ json: [] }));
  for (const kind of ["transactions", "dividends", "positions"]) {
    await page.route(`**/api/portfolio/${kind}**`, (route) => route.fulfill({ json: [] }));
  }
  await routeEmptyPortfolio(page);

  // Payload de la page Dividende : deux années de versements.
  const month = (v) => ({ "1": null, "2": null, "3": null, "4": null, "5": null, "6": v,
    "7": null, "8": null, "9": null, "10": null, "11": null, "12": null });
  const none = month(null);
  await page.route("**/api/portfolio/dividend-metrics**", (route) => route.fulfill({
    json: {
      income: {
        years: [2024, 2025],
        rows: [
          { year: 2024, months: { "6": 35.0 }, by_ticker: { "RI.PA": { months: { "6": 35.0 }, proposed: none } },
            total_confirmed: 35.0, total_proposed: 0.0, count: 1 },
          { year: 2025, months: { "6": 40.0 }, by_ticker: { "RI.PA": { months: { "6": 40.0 }, proposed: none } },
            total_confirmed: 40.0, total_proposed: 0.0, count: 1 },
        ],
        by_company: [{ ticker: "RI.PA", amount: 75.0, share_pct: 100.0 }],
        total_confirmed: 75.0, total_proposed: 0.0, last_year: 2025,
      },
      stats: {}, concentration: {}, lines: [], warnings: [],
    },
  }));

  await page.goto("/");
  await page.locator(".app-rail-btn[data-space='portfolio']").click();
  await page.locator(".pf-tabs .pf-tab[data-pf-section='dividende']").click();

  // DEUX contrôles seulement : la chip TTM et le sélecteur d'année. Une chip par
  // année débordait de l'en-tête dès quelques années d'historique.
  const period = page.locator(".pf-div-period");
  await expect(period.locator(".period-chip")).toHaveCount(1);
  await expect(period.locator(".period-chip")).toHaveText("TTM");
  await expect(period.locator(".period-chip")).toHaveClass(/active/);
  await expect(period.locator("select.pf-div-year-select")).toBeVisible();
  // 3 options : le libellé d'invite (« Année… », en mode TTM) + les deux années.
  await expect(period.locator("select.pf-div-year-select option")).toHaveCount(3);

  // Le graphe est tracé en TTM.
  await expect(page.locator("#pf-div-monthly .plot-container")).toBeVisible();

  // Choisir 2024 sort du mode TTM : la chip n'est plus active, le graphe reste.
  await period.locator("select.pf-div-year-select").selectOption("2024");
  await expect(period.locator(".period-chip")).not.toHaveClass(/active/);
  await expect(page.locator("#pf-div-monthly .plot-container")).toBeVisible();

  // Revenir à TTM réactive la chip.
  await period.locator(".period-chip").click();
  await expect(period.locator(".period-chip")).toHaveClass(/active/);

  expect(consoleErrors, "aucune erreur JS en console").toEqual([]);
});

test("performance : marqueurs de transactions sur le graphe héro, hors régression (#17.4)", async ({ page }) => {
  const consoleErrors = [];
  page.on("console", (msg) => { if (msg.type() === "error") consoleErrors.push(msg.text()); });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));

  // On utilise la VRAIE fiche RI.PA (comme les autres e2e) : seul le portefeuille
  // est mocké, avec deux transactions datées dans l'historique réel.
  await page.route("**/api/portfolio/transactions**", (route) =>
    route.fulfill({
      json: [
        { id: 1, account_id: 1, ticker: "RI.PA", side: "buy", trade_date: "2024-01-15", quantity: 10, price: 100, fees: 0, currency: "EUR", note: null, tag: null },
        { id: 2, account_id: 1, ticker: "RI.PA", side: "sell", trade_date: "2024-06-14", quantity: 5, price: 110, fees: 0, currency: "EUR", note: null, tag: null },
      ],
    }),
  );

  await page.goto("/#RI.PA");
  // La fiche et le graphe héro sont chargés (traces Plotly présentes).
  await expect(page.locator(".header")).toBeVisible({ timeout: 30_000 });
  const traceCount = () =>
    page.evaluate(() => {
      const el = document.getElementById("chart");
      return el && el.data ? el.data.length : -1;
    });
  await expect.poll(traceCount, { timeout: 30_000 }).toBeGreaterThan(0);

  const before = await traceCount();

  // Cocher « Transactions » ajoute des traces de marqueurs (achat + vente).
  const box = page.locator(".toggles label", { hasText: "Transactions" }).locator("input");
  await expect(box).toBeEnabled({ timeout: 15_000 });
  await box.check();
  await expect.poll(async () => (await traceCount()) - before).toBeGreaterThan(0);

  // Les marqueurs sont des scatter à symboles triangulaires, bleu (achat) / rouge
  // (vente). La droite de régression et ses bandes sont inchangées (annotations).
  const markers = await page.evaluate(() => {
    const el = document.getElementById("chart");
    const out = [];
    for (const t of el.data) {
      if (t.mode === "markers" && t.marker && /triangle/.test(t.marker.symbol || "")) {
        out.push({ symbol: t.marker.symbol, color: t.marker.color, n: t.x.length });
      }
    }
    return out;
  });
  const ups = markers.filter((m) => m.symbol === "triangle-up");
  const downs = markers.filter((m) => m.symbol === "triangle-down");
  expect(ups.length).toBeGreaterThan(0);
  expect(downs.length).toBeGreaterThan(0);

  // Décocher retire les marqueurs (retour au nombre de traces initial).
  await box.uncheck();
  await expect.poll(traceCount).toBe(before);

  expect(consoleErrors).toEqual([]);
});
