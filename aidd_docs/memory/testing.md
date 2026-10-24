# Testing

Comment le projet est testé : les couches, les outils, les conventions et la QA navigateur.

## Strategy

- **Backend** : pytest unitaire et d'intégration dans `tests/`. Le marqueur `network`
  isole les tests qui appellent yfinance (calibration Pernod, fiche `RI.PA`).
- **Front** : Vitest + jsdom dans `web-tests/`. Deux familles : la **parité** avec le
  serveur (`labels-parity.test.js`, `regression-parity.test.js`) et les unitaires des
  mixins.
- **E2E** : Playwright dans `web-tests/e2e/`, Chromium + WebKit, sur un vrai serveur.
- **Documentation** : `tests/test_doc_coherence.py` verrouille les faits chiffrés ;
  `tests/test_aidd_memory.py` verrouille la banque mémoire et son câblage.

## Tools

- pytest (marqueur `network`), ruff, mypy, pip-audit.
- Vitest + jsdom, Playwright (`@playwright/test`).
- Fixture de parité générée par `tests/fixtures/generate_regression_parity.py` : toute
  modification de la formule de régression doit la régénérer.

## Conventions

- Tests déterministes, sans réseau sauf marqueur `network`.
- Cas nominal, bornes et erreurs attendues.
- Un test de parité ne duplique pas la formule : il compare deux implémentations réelles.
- Les e2e sèment leurs fixtures via l'API et les restaurent ; ils ne présupposent jamais
  une base utilisateur existante.

## Run

- `cd web-tests && npm test` — Vitest.
- `cd web-tests && npm run test:e2e` — Playwright (démarre le serveur).
- `.venv/bin/python -m pytest -m "not network" -q -p no:cov` — backend rapide.

## Browser QA

- **Entry** : `http://127.0.0.1:8000` (`./start.sh` ou `.venv/bin/python run.py`).
- **Auth** : aucune — outil mono-utilisateur, localhost.
- **State** : base jetable via `OBOLE_CACHE_DB` (les e2e utilisent `web-tests/.tmp-cache/`).
  Ne jamais pointer un test qui écrit vers la base réelle.
- **Port occupé** : `OBOLE_E2E_PORT` fixe l'URL surveillée et le `baseURL` ;
  `OBOLE_SERVER_CMD` change la commande de lancement. Un e2e qui présuppose une thèse
  existante doit semer sa propre fixture, sinon il est vert en local et rouge en CI.
