import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// L'environnement jsdom réécrit `import.meta.url` en URL http : on résout donc
// les chemins des fichiers sources ici (le fichier de config tourne sous Node)
// et on les injecte sous forme de constantes utilisables par les tests.
const appJs = fileURLToPath(new URL("../src/obole/web/app.js", import.meta.url));
const configPy = fileURLToPath(new URL("../src/obole/config.py", import.meta.url));
const dividendJs = fileURLToPath(new URL("../src/obole/web/dividend.js", import.meta.url));
const valorisationJs = fileURLToPath(new URL("../src/obole/web/valorisation.js", import.meta.url));
const styleCss = fileURLToPath(new URL("../src/obole/web/style.css", import.meta.url));
const indexHtml = fileURLToPath(new URL("../src/obole/web/index.html", import.meta.url));
const regressionFixture = fileURLToPath(
  new URL("../tests/fixtures/regression_parity.json", import.meta.url),
);
const valuationFixture = fileURLToPath(
  new URL("../tests/fixtures/valuation_parity.json", import.meta.url),
);

export default defineConfig({
  define: {
    __APP_JS_PATH__: JSON.stringify(appJs),
    __CONFIG_PY_PATH__: JSON.stringify(configPy),
    __DIVIDEND_JS_PATH__: JSON.stringify(dividendJs),
    __VALORISATION_JS_PATH__: JSON.stringify(valorisationJs),
    __STYLE_CSS_PATH__: JSON.stringify(styleCss),
    __INDEX_HTML_PATH__: JSON.stringify(indexHtml),
    __REGRESSION_FIXTURE_PATH__: JSON.stringify(regressionFixture),
    __VALUATION_FIXTURE_PATH__: JSON.stringify(valuationFixture),
  },
  test: {
    // `app.js` est un script classique (non module) chargé par <script> : il
    // touche `document` au chargement (écoute `alpine:init`). jsdom fournit le
    // DOM minimal ; les tests l'évaluent ensuite dans le contexte courant.
    environment: "jsdom",
    include: ["**/*.test.js"],
    exclude: ["node_modules/**", "e2e/**"],
  },
});
