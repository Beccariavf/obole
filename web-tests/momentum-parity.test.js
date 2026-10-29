import { describe, expect, it } from "vitest";
import { loadApp, metaFromConfig, readConfigSource } from "./helpers/load-app.js";

// #30 : les bornes de la Clara Vallis vivent dans config.py et passent par
// /api/meta. Ce test vérifie que le payload construit depuis config.py est bien
// celui que le front consomme — même mécanisme que labels-parity.test.js.
describe("Clara Vallis : source unique des seuils (/api/meta)", () => {
  const meta = metaFromConfig(readConfigSource());

  it("config.py porte les bornes calibrées", () => {
    expect(meta.momentum.window).toBe(250);
    expect(meta.momentum.low).toBeCloseTo(0.35, 6);
    expect(meta.momentum.high).toBeCloseTo(0.6, 6);
    expect(meta.momentum.table_windows).toEqual([1, 5, 10, 20, 0]);
  });

  it("applyMeta expose le même objet au front", () => {
    const app = loadApp();
    app.applyMeta(meta);
    expect(app.MOMENTUM).toEqual(meta.momentum);
  });
});
