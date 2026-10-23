import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { loadApp } from "./helpers/load-app.js";

// Miroir JS de `tests/test_regression_parity_fixture.py` : les deux tests lisent
// la MÊME fixture (sorties de `engine.regression.fit_log_regression`). Si la
// formule dérive d'un côté, l'autre test reste vert -> divergence détectée.
const FIXTURE = JSON.parse(readFileSync(__REGRESSION_FIXTURE_PATH__, "utf8"));

// Conversion date -> années IDENTIQUE à celle de `drawChart` (app.js).
function yearsFromDates(dates) {
  const t0 = new Date(dates[0]);
  return dates.map((d) => (new Date(d) - t0) / (365.25 * 864e5));
}

describe("parité régression Python (fit_log_regression) <-> JS (olsLog)", () => {
  const { olsLog } = loadApp();

  for (const c of FIXTURE.cases) {
    it(c.name, () => {
      const { a, b, sigma } = olsLog(yearsFromDates(c.dates), c.prices);
      // Normal equations (JS) vs moindres carrés numpy : écart ~1e-10.
      expect(a).toBeCloseTo(c.a, 8);
      expect(b).toBeCloseTo(c.b, 8);
      expect(sigma).toBeCloseTo(c.sigma, 8);
    });
  }

  it("renvoie des valeurs finies sur un cas dégénéré minimal", () => {
    const { a, b, sigma } = olsLog([0, 1], [100, 100]);
    expect(Number.isFinite(a)).toBe(true);
    expect(Number.isFinite(b)).toBe(true);
    expect(b).toBeCloseTo(0, 12);
    expect(sigma).toBeCloseTo(0, 12);
  });
});
