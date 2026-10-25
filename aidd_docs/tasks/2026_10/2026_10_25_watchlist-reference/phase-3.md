# Phase 3 — Popover, e2e, captures, doc, revue

## Scope

- `web/index.html` : items `watch-ref-item`, définition sur deux lignes (libellé + date).
- `web/style.css` : layout bloc, largeur 320, date en sous-ligne.
- `web-tests/e2e/watchlist.spec.js` : injection d'une référence sur `/api/stock/ACA.PA`,
  toggles, KPI calculé, hauteur des items du popover.
- Captures avant/après (ACA fiche/KPI, popover VIE, modale watchlist).
- Doc : #25.1, #25 « corrections post-livraison », CLAUDE.md, api.md, design.md, data.md.
- `/05-review`, puis merge `--no-ff`.

## Acceptance

- [x] Popover lisible : items ≤ 50 px, libellés sur une/deux lignes, stats en bas.
- [x] E2E Chromium + WebKit verts.
- [x] Captures après jointes ; comparaison avec les captures avant.
- [x] Doc à jour ; revue sans constat bloquant ; merge.
