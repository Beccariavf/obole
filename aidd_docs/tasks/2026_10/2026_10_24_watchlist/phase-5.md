# Phase 5 — Front

## Scope

- `web/api.js` : 6 appels watchlist.
- `web/watchlist.js` : mixin + helpers purs.
- `web/app.js`, `web/thresholds.js` : état + méta `watch`.
- `web/index.html` : bouton topbar, étoile + popover, chip de référence, modale.
- `web/style.css` : `.wl-*`, réutilisation `.screen-table`/`.cell-*`.
- `web/charts.js` : `initRange` (référence), `applyRefWindow`, `defineRef`, `clearRef`,
  rechargement après changement de référence.
- Tests : `web-tests/watchlist.test.js`, `helpers/load-app.js`, `vitest.config.js`.

## Acceptance

- [ ] Bouton `★ Watchlist` entre Portefeuille et Paramètres.
- [ ] Étoile : ajout / déplacement / retrait, état local (pas de rechargement).
- [ ] Modale : tiers + compteurs, tri, badges, états vides/erreurs, ligne → fiche.
- [ ] Référence : définir/voir/effacer ; la fiche se recharge et le Résumé suit.
- [ ] Aucun seuil littéral JS ; `app.js` < 500 ; `fetch` uniquement dans `api.js`.
