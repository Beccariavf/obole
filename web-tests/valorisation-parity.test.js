import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fairPrice, safetyMargin, estimatedReturn, targetEntryPrice, matrixGrid, colorBucket } from "../src/obole/web/valorisation.js";

// Parité de la calculatrice de prix juste : le miroir JS doit reproduire
// EXACTEMENT `engine/valuation_calc.py`, vérifié par
// `tests/test_valuation_parity_fixture.py` sur la même fixture. Même invariant
// que la régression (calculée serveur ET client, verrouillée par une fixture).
const FIXTURE = JSON.parse(readFileSync(__VALUATION_FIXTURE_PATH__, "utf8"));

function same(actual, expected) {
  if (expected === null || expected === undefined) return actual === null || actual === undefined;
  return actual != null && Math.abs(actual - expected) < 1e-9;
}

describe("Valorisation — parité JS/Python (fixture partagée)", () => {
  it("la fixture est bien celle du chantier #20", () => {
    expect(FIXTURE.cases.length).toBeGreaterThan(5);
    expect(FIXTURE.matrix_cases.length).toBeGreaterThan(0);
  });

  for (const c of FIXTURE.cases) {
    it(`reproduit le cas « ${c.name} »`, () => {
      const fair = fairPrice(c.metric, c.multiple, c.net_debt_per_share);
      expect(same(fair, c.fair_price)).toBe(true);
      expect(same(safetyMargin(fair, c.price), c.safety_margin)).toBe(true);
      const ret = estimatedReturn(
        c.metric, c.price, c.growth, c.multiple, c.horizon, c.dividend, c.net_debt_per_share,
      );
      expect(same(ret, c.estimated_return)).toBe(true);
      const entry = targetEntryPrice(
        c.metric, c.growth, c.multiple, c.horizon, c.target, c.dividend, c.net_debt_per_share,
      );
      expect(same(entry, c.target_entry_price)).toBe(true);
    });
  }

  for (const c of FIXTURE.matrix_cases) {
    it(`reproduit la grille « ${c.name} » (grid + buckets)`, () => {
      const grid = matrixGrid(c.growth, c.multiple, c.rows, c.cols, c.growth_step, c.multiple_step);
      expect(grid.growths).toEqual(c.growths);
      expect(grid.multiples).toEqual(c.multiples);
      // Rendement de chaque cellule = estimatedReturn(metric, price, g, m, ...).
      for (let i = 0; i < grid.growths.length; i++) {
        for (let j = 0; j < grid.multiples.length; j++) {
          const v = estimatedReturn(
            c.metric, c.price, grid.growths[i], grid.multiples[j], c.horizon, c.dividend,
            c.net_debt_per_share,
          );
          expect(same(v, c.matrix[i][j]), `matrix ${c.name} [${i}][${j}]`).toBe(true);
          const bucket = colorBucket(v, c.target, c.color_ratios);
          expect(bucket, `bucket ${c.name} [${i}][${j}]`).toBe(c.buckets[i][j]);
        }
      }
    });
  }
});
