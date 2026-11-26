import { describe, expect, it } from "vitest";
import { loadApp, metaFromConfig, readConfigSource } from "./helpers/load-app.js";

// #33 : les fenêtres de la table Markovitz vivent dans config.py et passent par
// /api/meta. Ce test vérifie que le payload construit depuis config.py est bien
// celui que le front consomme — même mécanisme que labels-parity.test.js.
describe("Table Markovitz : source unique des fenêtres (/api/meta)", () => {
  const meta = metaFromConfig(readConfigSource());

  it("config.py porte les fenêtres du sélecteur", () => {
    expect(meta.markowitz.table_windows).toEqual([1, 5, 10, 20, 0]);
  });

  it("applyMeta expose le même objet au front", () => {
    const app = loadApp();
    app.applyMeta(meta);
    expect(app.MARKOWITZ).toEqual(meta.markowitz);
  });
});
