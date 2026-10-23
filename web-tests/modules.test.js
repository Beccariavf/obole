import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { searchMixin } from "../src/obole/web/search.js";
import { screenerMixin } from "../src/obole/web/screener.js";
import { indicesMixin } from "../src/obole/web/indices.js";
import { chartsMixin } from "../src/obole/web/charts.js";
import { cursorMixin } from "../src/obole/web/cursor.js";
import { exportMixin } from "../src/obole/web/exportcsv.js";
import { eventsMixin } from "../src/obole/web/events.js";
import { settingsMixin } from "../src/obole/web/settings.js";
import { sectionsMixin } from "../src/obole/web/sections.js";
import { summaryMixin } from "../src/obole/web/summary.js";
import { portfolioMixin } from "../src/obole/web/portfolio.js";
import { dividendMixin } from "../src/obole/web/dividend.js";
import { valorisationMixin } from "../src/obole/web/valorisation.js";
import { thesisMixin } from "../src/obole/web/thesis.js";
import { checkpointsMixin } from "../src/obole/web/suivi.js";
import { obole } from "../src/obole/web/app.js";

// #04 : découpage du front en modules ES natifs. Ce test verrouille la
// structure : chaque domaine expose un mixin, aucun `fetch` hors `api.js`,
// et le composant `obole` assemble bien tous les modules.

const WEB_DIR = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "obole", "web");

const MIXINS = {
  "search.js": searchMixin,
  "screener.js": screenerMixin,
  "indices.js": indicesMixin,
  "charts.js": chartsMixin,
  "cursor.js": cursorMixin,
  "exportcsv.js": exportMixin,
  "events.js": eventsMixin,
  "settings.js": settingsMixin,
  "sections.js": sectionsMixin,
  "summary.js": summaryMixin,
  "portfolio.js": portfolioMixin,
  "dividend.js": dividendMixin,
  "valorisation.js": valorisationMixin,
  "thesis.js": thesisMixin,
  "suivi.js": checkpointsMixin,
};

describe("découpage du front (modules ES)", () => {
  it("chaque domaine expose son mixin", () => {
    for (const [file, mixin] of Object.entries(MIXINS)) {
      expect(mixin, `${file} doit exporter un objet mixin`).toBeTypeOf("object");
      expect(Object.keys(mixin).length, `${file} ne doit pas être vide`).toBeGreaterThan(0);
    }
  });

  it("le composant obole assemble tous les mixins", () => {
    const comp = obole();
    for (const m of ["load", "searchScreener", "openIndices", "drawChart", "doExport", "openEvents", "openSettings", "setSection", "onHashChange", "openPortfolio", "setPortfolioSection", "loadThesis", "startThesisEdit", "thesisToggleTask", "loadCheckpoints", "cpAdd", "cpToggle", "openDrafts", "applyDraft", "rejectDraft"]) {
      expect(comp[m], `obole() doit exposer ${m}`).toBeTypeOf("function");
    }
    expect(comp.metaReady).toBe(false);
    expect(comp.query).toBe("RI.PA");
  });

  it("la section « Thèse & Société » est active (plus « à venir »)", () => {
    const src = readFileSync(join(WEB_DIR, "sections.js"), "utf8");
    expect(src).toMatch(/PLANNED_SECTIONS = new Set\(\)/);
  });

  it("aucun fetch en dehors de api.js", () => {
    const files = readdirSync(WEB_DIR).filter((f) => f.endsWith(".js") && f !== "api.js");
    for (const f of files) {
      const src = readFileSync(join(WEB_DIR, f), "utf8");
      expect(src, `${f} ne doit contenir aucun fetch()`).not.toMatch(/\bfetch\s*\(/);
    }
    const api = readFileSync(join(WEB_DIR, "api.js"), "utf8");
    expect(api).toMatch(/\bfetch\s*\(/);
  });

  it("app.js reste le composant seul (< 500 lignes)", () => {
    const lines = readFileSync(join(WEB_DIR, "app.js"), "utf8").split("\n").length;
    expect(lines).toBeLessThan(500);
  });

  it("les seuils vivent dans thresholds.js, pas dans app.js", () => {
    const app = readFileSync(join(WEB_DIR, "app.js"), "utf8");
    expect(app).not.toMatch(/DISTANCE_SIGMA_LABELS|RATIO_THRESHOLDS\s*=/);
  });
});
