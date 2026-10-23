import { defineConfig, devices } from "@playwright/test";

// Smoke e2e : un seul parcours (fiche RI.PA + graphe), joué sur Chromium ET
// WebKit (moteur Safari — le navigateur réellement utilisé sur ce poste).
// Le serveur Obole est démarré par Playwright (réutilisé s'il tourne déjà).
// Playwright lance la commande depuis `web-tests/` : le chemin vers run.py est
// donc relatif (../run.py). run.py insère lui-même `src/` dans sys.path.

// Port paramétrable. `OBOLE_SERVER_CMD` permet de changer la COMMANDE (ex. uvicorn
// avec PYTHONPATH) mais pas l'URL surveillée par `webServer.url` ni `baseURL` :
// sur ce poste le port 8000 peut être occupé par un autre serveur, et sans ces
// deux variables la seule issue serait un fichier de config en double (dérive
// garantie avec celui-ci). On paramètre donc le port UNE fois, ici.
//
//   OBOLE_E2E_PORT=8012 OBOLE_SERVER_CMD="PYTHONPATH=../src ../.venv/bin/python -m uvicorn obole.api.app:app --host 127.0.0.1 --port 8012" npm run test:e2e
const PORT = Number(process.env.OBOLE_E2E_PORT ?? 8000);
const BASE_URL = `http://127.0.0.1:${PORT}`;

// Base de cache JETABLE. La suite e2e écrit (thèses, points de contrôle) : elle ne
// doit jamais taper la base réelle. `OBOLE_CACHE_DB` est lue par `config.py` ; on
// la force ici pour le serveur que Playwright démarre lui-même. Un serveur déjà
// lancé sur le port (reuseExistingServer) n'est PAS concerné : ne pas pointer
// OBOLE_E2E_PORT vers un serveur branché sur la vraie base si un test écrit.
const E2E_CACHE_DB = process.env.OBOLE_CACHE_DB ?? new URL(".tmp-cache/e2e.sqlite", import.meta.url).pathname;

const SERVER_COMMAND =
  process.env.OBOLE_SERVER_CMD ??
  `OBOLE_CACHE_DB=${E2E_CACHE_DB} ../.venv/bin/python -u ../run.py --port ${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: {
    command: SERVER_COMMAND,
    url: `${BASE_URL}/`,
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
