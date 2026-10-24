# Phase 6 — E2E, doc, revue

## Scope

- `web-tests/e2e/watchlist.spec.js` (routes interceptées, pas de pollution de la base).
- Doc : mémoire (`api`, `data`, `design`, `codebase-map`), `CLAUDE.md`, `README.md`, `PRD.md`,
  renvoi #16, index #25.
- Revue : `/05-review`, corrections, `review.md`.

## Acceptance

- [ ] `pytest -m "not network"` + `pytest -m network` verts.
- [ ] `ruff check .`, `ruff format --check .`, `mypy` verts.
- [ ] `npm test`, `npm run test:e2e` verts.
- [ ] QA manuelle (RI.PA, BNP.PA, CW8.PA, ticker sans prix juste) passée.
- [ ] Revue sans constat bloquant.
