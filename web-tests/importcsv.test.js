import { describe, expect, it } from "vitest";

import { detectDelimiter, parseCSV, parseNumber } from "../src/obole/web/util.js";
import { exportMixin } from "../src/obole/web/exportcsv.js";

// #23 : le front doit reconnaître les MÊMES formats que le serveur (délimiteur,
// nombres) et signaler les valeurs rejetées avec leur raison — l'utilisateur voit
// ce qui sera écrit avant de valider.

describe("détection du délimiteur (miroir de data/manual)", () => {
  it("virgule (norme CSV)", () => {
    expect(detectDelimiter("year,Chiffre d'affaires\n2015,1000")).toBe(",");
  });

  it("point-virgule (Excel FR) — le cas qui cassait", () => {
    expect(detectDelimiter("year;Chiffre d'affaires;Bénéfice net\n2015;1;2")).toBe(";");
  });

  it("tabulation (collage de tableau)", () => {
    expect(detectDelimiter("year\tChiffre d'affaires\n2015\t1000")).toBe("\t");
  });

  it("repli sur la virgule si aucun délimiteur", () => {
    expect(detectDelimiter("year\n2015")).toBe(",");
  });
});

describe("parseCSV respecte le délimiteur détecté", () => {
  it("découpe un CSV à point-virgule", () => {
    expect(parseCSV("year;CA\n2015;1000")).toEqual([
      ["year", "CA"],
      ["2015", "1000"],
    ]);
  });

  it("gère les champs entre guillemets", () => {
    expect(parseCSV('year,CA\n2015,"1,5"')).toEqual([
      ["year", "CA"],
      ["2015", "1,5"],
    ]);
  });
});

describe("parseNumber (miroir de data/manual._parse_number)", () => {
  const cases = {
    "8 500 000": 8500000,
    "8\u00a0500\u00a0000": 8500000,
    "8\u202f500\u202f000": 8500000,
    "8'500'000": 8500000,
    "1.234,56": 1234.56,
    "1,234.56": 1234.56,
    "1,5": 1.5,
    "1,234": 1234,
    "(1 234)": -1234,
    "€ 1 234": 1234,
  };
  for (const [raw, expected] of Object.entries(cases)) {
    it(`normalise « ${raw} »`, () => expect(parseNumber(raw)).toBe(expected));
  }

  it("rejette une cellule non numérique (lettre)", () => {
    expect(parseNumber("pomme")).toBeNull();
    expect(parseNumber("pomme0")).toBeNull();
    expect(parseNumber("")).toBeNull();
  });
});

describe("aperçu d'import (_buildPreview)", () => {
  const mkApp = (fundamentals) => ({
    data: { identity: { ticker: "RI.PA" }, fundamentals },
    importError: "",
    ...exportMixin,
    _meta: { FUNDAMENTAL_METRICS: null },
  });

  // Le mixin lit FUNDAMENTAL_METRICS depuis le module ; on l'alimente via le
  // meta du front (thresholds) déjà chargé dans l'app réelle. Ici on simule un
  // sous-ensemble réaliste de la taxonomie.
  it("liste les colonnes ignorées et les rejets avec leur raison", async () => {
    const mod = await import("../src/obole/web/thresholds.js");
    mod.applyMeta({
      fundamental_metrics: [
        { name: "Chiffre d'affaires", role: "source" },
        { name: "Bénéfice net", role: "source" },
        { name: "Marge nette", role: "derived" },
      ],
    });
    // L'écrasement se compte sur les entrées MANUELLES (comme le serveur), pas
    // sur les années yfinance.
    const app = mkApp({
      years: [2020, 2021],
      manual_entries: [{ year: 2020, metric: "Chiffre d'affaires" }],
    });
    app._buildPreview("year;Chiffre d'affaires;Marge nette;Commentaire\n2020;1000;15;x\nn/a;pomme;1;y");
    expect(app.importError).toBe("");
    const p = app.importPreview;
    expect(p.entries.length).toBe(1);
    expect(p.entries[0]).toMatchObject({ year: 2020, metric: "Chiffre d'affaires", value: 1000 });
    expect(p.overrideCount).toBe(1); // 2020 + Chiffre d'affaires existent en manuel
    expect(p.derivedColumns).toContain("Marge nette");
    expect(p.unknownColumns).toContain("Commentaire");
    // La ligne à l'année illisible est consignée comme telle.
    expect(p.rejected.some((r) => r.reason === "bad_year")).toBe(true);
    expect(p.rejectedTotal).toBe(p.rejected.length);
  });

  it("une année yfinance seule n'est PAS un écrasement (miroir serveur)", async () => {
    const mod = await import("../src/obole/web/thresholds.js");
    mod.applyMeta({
      fundamental_metrics: [{ name: "Chiffre d'affaires", role: "source" }],
    });
    // Année présente côté yfinance, mais aucune entrée manuelle -> ajout, pas écrasement.
    const app = mkApp({ years: [2020], manual_entries: [] });
    app._buildPreview("year,Chiffre d'affaires\n2020,1000");
    expect(app.importPreview.overrideCount).toBe(0);
    expect(app.importPreview.entries[0].override).toBe(false);
  });

  it("libellés français des raisons de rejet", () => {
    const app = mkApp(null);
    expect(app.rejectReason("unparseable")).toContain("non numérique");
    expect(app.rejectReason("bad_year")).toContain("année");
    expect(app.rejectReason("derived_column")).toContain("calculé");
  });

  it("erreur explicite si la colonne year manque", () => {
    const app = mkApp(null);
    app._buildPreview("montant,CA\n1,2");
    expect(app.importError).toContain("year");
  });
});
