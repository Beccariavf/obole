import { expect, test } from "@playwright/test";

// Curseur du graphe héro : overlay SVG superposé à Plotly. Ces tests couvrent ce
// que les helpers purs (cursor.test.js) NE PEUVENT PAS voir — la géométrie RÉELLE
// de Plotly (marges, échelles, alias) et le cycle de vie du DOM Alpine :
//   - la croix doit pointer EXACTEMENT sous la souris (offset marges) ;
//   - le câblage doit survivre à la recréation de `#chart` (2e fiche) ;
//   - après zoom, la correspondance pixel→date passe par l'échelle réelle.

async function loadHero(page, ticker) {
  await page.goto(`/#${encodeURIComponent(ticker)}`);
  await expect(page.locator(".header")).toBeVisible({ timeout: 30_000 });
  const chart = page.locator("#chart");
  await expect
    .poll(async () => chart.locator(".scatterlayer .trace").count(), { timeout: 30_000 })
    .toBeGreaterThan(0);
}

async function plotGeometry(page) {
  return page.evaluate(() => {
    const gd = document.getElementById("chart");
    const fl = gd._fullLayout;
    const r = gd.getBoundingClientRect();
    return { left: r.left, top: r.top, plotLeft: fl._size.l, plotTop: fl._size.t, plotW: fl._size.w, plotH: fl._size.h };
  });
}

async function hoverPlot(page, fx, fy) {
  const geo = await plotGeometry(page);
  const x = geo.left + geo.plotLeft + geo.plotW * fx;
  const y = geo.top + geo.plotTop + geo.plotH * fy;
  await page.mouse.move(x, y);
  await page.waitForTimeout(120);
  return { x, y, geo };
}

// Position x (coordonnée viewBox = coordonnée div) de la croix du curseur.
async function crosshairX(page) {
  return page.evaluate(() => {
    const line = document.querySelector(".cursor-overlay .cur-line");
    return line ? Number(line.getAttribute("x1")) : null;
  });
}

// x pixel du dernier point de la série (courbe « Cours » = dernière trace).
async function lastPointX(page) {
  return page.evaluate(() => {
    const gd = document.getElementById("chart");
    const fl = gd._fullLayout;
    const traces = gd.data;
    const cours = traces.find((t) => t.name === "Cours");
    const last = cours.x[cours.x.length - 1];
    return fl._size.l + fl.xaxis.d2p(typeof last === "number" ? last : Date.parse(last));
  });
}

test("à l'ouverture, le readout est posé sur le dernier point (aucun survol)", async ({ page }) => {
  await loadHero(page, "RI.PA");
  // Aucune souris sur le graphe : l'overlay doit déjà afficher le dernier point.
  const cx = await crosshairX(page);
  const lx = await lastPointX(page);
  expect(cx, "readout de repos présent sans survol").not.toBeNull();
  expect(Math.abs(cx - lx), "posé sur le dernier point").toBeLessThan(2);
  const badge = page.locator(".cursor-overlay .cur-badge");
  await expect(badge, "badge prix·σ visible au repos").toBeVisible();
});

test("le curseur suit exactement la souris (pas d'offset de marge)", async ({ page }) => {
  await loadHero(page, "RI.PA");
  const { x, geo } = await hoverPlot(page, 0.5, 0.5);
  const cx = await crosshairX(page);
  expect(cx, "la croix doit être présente au survol").not.toBeNull();
  // La croix est snappée au point de données le plus proche (≤ ~1 px sur du
  // quotidien) : elle doit rester sous le curseur, PAS décalée de `size.l` (52 px).
  expect(Math.abs(cx - (x - geo.left))).toBeLessThan(4);
});

test("à la sortie du graphe, le readout revient sur le dernier point", async ({ page }) => {
  await loadHero(page, "RI.PA");
  const lx = await lastPointX(page);
  // Survol au milieu, puis sortie du graphe.
  await hoverPlot(page, 0.2, 0.5);
  await page.mouse.move(5, 5);
  await page.waitForTimeout(120);
  const cx = await crosshairX(page);
  expect(cx, "readout de repos restauré après sortie").not.toBeNull();
  expect(Math.abs(cx - lx), "revenu sur le dernier point").toBeLessThan(2);
});

test("après zoom, le readout de repos reste sur le dernier point VISIBLE", async ({ page }) => {
  await loadHero(page, "RI.PA");
  const geo = await plotGeometry(page);
  // Zoom pur (relayout, sans redraw) : on garde la première moitié de la plage.
  await page.evaluate(() => {
    const gd = document.getElementById("chart");
    const ax = gd._fullLayout.xaxis;
    const [lo, hi] = ax.range.map((v) => (typeof v === "number" ? v : Date.parse(v)));
    return Plotly.relayout(gd, { "xaxis.range": [lo, lo + (hi - lo) / 2] });
  });
  await page.waitForTimeout(200);
  // Aucune souris sur le graphe : le point de repos doit rester DANS le cadre,
  // au bord droit visible — pas une indexation d'avant zoom (x ~1680 hors plot).
  const cx = await crosshairX(page);
  expect(cx, "readout de repos après zoom").not.toBeNull();
  const right = geo.plotLeft + geo.plotW;
  expect(cx, "posé près du bord droit visible").toBeGreaterThan(right - 12);
  expect(cx, "jamais hors cadre").toBeLessThanOrEqual(right + 2);
});

test("le curseur reste câblé après un changement de fiche (DOM recréé par x-if)", async ({ page }) => {
  await loadHero(page, "RI.PA");
  await hoverPlot(page, 0.5, 0.5);
  expect(await crosshairX(page), "1re fiche : croix présente").not.toBeNull();

  // Nouvelle fiche : Alpine détruit puis recrée `#chart` (loading → data=null).
  await loadHero(page, "MC.PA");
  const { x, geo } = await hoverPlot(page, 0.5, 0.5);
  const cx = await crosshairX(page);
  expect(cx, "2e fiche : le curseur doit rester réactif").not.toBeNull();
  expect(Math.abs(cx - (x - geo.left))).toBeLessThan(4);
});

test("l'infobulle d'une annotation d'événement reste accessible (hovermode:false)", async ({
  page, request,
}) => {
  // Le passage à `hovermode:false` supprime le tooltip natif du CURSEUR, mais les
  // descriptions d'événements reposent sur `annotation.hovertext` (indépendant de
  // hovermode) : on verrouille que survoler une annotation affiche bien sa note.
  const r = await request.post("/api/events/stock?ref=RI.PA", {
    data: { date: "2019-06-01", label: "E2E event", description: "Description E2E" },
  });
  const id = r.ok() ? (await r.json()).id : null;
  try {
    await loadHero(page, "RI.PA");
    // Active la case « Événements » (annotations datées visibles sur le héro).
    await page.evaluate(() => {
      const root = document.querySelector("[x-data]");
      const d = Alpine.$data(root);
      d.showEvents = true;
      d.drawChart();
    });
    const ann = page.locator("#chart .annotation", { hasText: "E2E event" });
    await expect(ann).toBeVisible({ timeout: 20_000 });
    await ann.hover();
    await expect(page.locator("#chart .hoverlayer")).toContainText("Description E2E");
  } finally {
    if (id != null) await request.delete(`/api/events/${id}`);
  }
});

test("après zoom, la croix reste alignée sur la souris (échelle réelle)", async ({ page }) => {
  await loadHero(page, "RI.PA");
  // Zoom programmatique sur la seconde moitié de la plage visible.
  await page.evaluate(() => {
    const gd = document.getElementById("chart");
    const ax = gd._fullLayout.xaxis;
    const [lo, hi] = ax.range.map((v) => (typeof v === "number" ? v : Date.parse(v)));
    const mid = lo + (hi - lo) / 2;
    return Plotly.relayout(gd, { "xaxis.range": [mid, hi] });
  });
  await page.waitForTimeout(200);
  const { x, geo } = await hoverPlot(page, 0.25, 0.5);
  const cx = await crosshairX(page);
  expect(cx, "après zoom : croix présente").not.toBeNull();
  // Sans le correctif p2c, la croix tombait sur une x littérale négative (hors cadre).
  expect(cx).toBeGreaterThan(geo.plotLeft - 2);
  expect(cx).toBeLessThan(geo.plotLeft + geo.plotW + 2);
  expect(Math.abs(cx - (x - geo.left))).toBeLessThan(6);
});
