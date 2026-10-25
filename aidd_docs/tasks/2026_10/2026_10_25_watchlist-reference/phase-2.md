# Phase 2 — Vue référence front

## Scope

- `web/search.js::load` : forcer `withDividends=false`, `syncRegression=true`,
  `winLocked=false`, `_winPrevSync=null` avant `initRange` quand `data.watch.ref.start`.
- `web/charts.js` : `referenceRegression()`, branche serveur de `drawChart` (droite/bandes),
  `computeLive` avec observation imposée (`identity.last_price`, `ref_stats.end`).
- `web/watchlist.js::clearWatchRef` : restaurer `withDividends=true` avant rechargement.
- Tests unitaires : conditions de `referenceRegression`, math `computeLive` avec override.

## Acceptance

- [ ] Fenêtre = référence + brut + synchro → la droite/bandes sont les params serveur.
- [ ] KPI = `ref_stats` (z, σ, perf, Pot. 5A), dernier cours réel.
- [ ] Plage déplacée / dividendes / synchro off → live actuel, `referenceRegression()` nul.
- [ ] Effacer la référence restaure la vue par défaut.
- [ ] `npm test` vert.
