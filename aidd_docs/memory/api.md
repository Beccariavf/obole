# API

La surface HTTP : son style, ses ressources et ses contrats.

## Style

- REST JSON, FastAPI ; `api/app.py` **expose ~83 routes** et sert aussi le front.
- Base `/api` ; routes **fines** : elles valident et délèguent à `services/`, jamais à
  `engine/` directement.
- Assets statiques servis par `api/static_files.py` avec un hash de contenu
  (`/static/x.js?v=<hash>`) : cache immuable pour une URL versionnée, `no-cache` sinon.

## Resources

- Analyse : stock, ratio, recherche, refresh.
- Indices personnalisés (catégories + compositions), événements, saisie manuelle.
- Imports pilotés : `GET/POST/DELETE /api/imports` — l'IA ne crée qu'un brouillon, seule
  une route REST applique (jamais un outil MCP).
- Screener de l'univers français.
- Watchlist (#25) : `GET /api/watchlist`, `PUT`/`DELETE` sur `api/watchlist/items/<ticker>`,
  `PUT`/`DELETE` sur `api/watchlist/ref/<ticker>`, `POST /api/watchlist/run`. `GET /api/stock`
  porte un bloc `watch` (tier, référence, stats) ajouté par la route, et `/api/meta`
  expose `watch` (tiers, points minimum d'une référence, plafond).
- Paramètres, sauvegarde/restauration, santé.

## Contracts

- `/api/meta` sérialise les seuils de `config.py` : **source unique** consommée par le
  front au démarrage. Aucun seuil littéral côté JS. La table Markovitz y lit ses
  fenêtres (`markowitz.table_windows`).
- `/api/health` renvoie 503 si SQLite ou le cache est hors service.
- Les erreurs remontent en `HTTPException` avec un message lisible ; les erreurs métier
  typées (`IndexNotFound`, `ThesisNotFound`) sont traduites en 404.
- Les uploads sont plafonnés avant lecture (CSV, archive de sauvegarde, image de thèse).
- La sérialisation vit dans `services/serialize.py`, partagée API ↔ MCP : `api/` ne
  contient pas de logique de présentation.
- Watchlist (#25/#25.2) : la ligne est en **total-return** (dividendes réinvestis,
  `regression_adj`) ; le prix juste enregistré est **lu** de `valuation_settings` et prime ;
  à défaut, le prix juste est le prix d'entrée à **12 %/an** jusqu'à la droite à 5 ans
  (`fair_price_source="regression"`, `target_yield=12`), converti en unités du cours brut.
  La marge est `engine.valuation_calc.safety_margin` et la fenêtre de confiance
  `services.analysis.reference_window` (référence persistée sinon 20 ans). La marge de
  repli ne coïncide donc plus avec `trend_gap_pct`. La fiche (`/api/stock`) garde la
  droite **brute** de valorisation. Les routes de référence ne sont pas exposées en
  écriture MCP (jugement humain).
- `/api/watchlist/run` : chaque ligne porte `pot_5y_pct` et `pot_5y_source`
  (`valuation` si un prix juste enregistré existe, `regression` sinon) ; le summary MCP
  inclut ces champs. Le Pot. 10A reste `regression`.
- `GET /api/stock` expose `watch.ref_stats` (`start`, `end`, `n_points`, `a`, `b`, `sigma`,
  `line`, `z`, `ecart_type_pct`, `trend_gap_pct`, `pente_pct`) : `a`/`b`/`sigma` permettent
  au front de retracer exactement la droite persistée quand la fenêtre affichée est la
  référence.
- `GET /api/stock/<ticker>` et `GET /api/index/<id>` portent `chart.risk` (#33), un
  objet à quatre clés : `drawdown_pct` et `vol_pct` (listes alignées 1:1 sur
  `chart.dates`, même longueur), `vol_threshold_pct` (float ou `null`) et `now`
  (sept scalaires : `drawdown_pct`, `peak_date`, `vol_pct`, `vol_percentile`,
  `bench_vol_pct`, `mom_12_1_pct`, `bench_mom_12_1_pct`). Les séries sont
  calculées sur la pleine résolution ajustée (série du panier pour un indice),
  puis décimées ; le 12-1 est mesuré sur les cours bruts (pour un panier, une
  seconde série chaînée sur les cours bruts des membres). Le benchmark est
  `^FCHI`, lu via `data/` (cache TTL) ; un benchmark indisponible laisse ses
  deux champs à `None`, sans erreur.
  `chart.risk` est absent quand `include_chart=False` (outils MCP en `summary`).
  `/api/meta` expose le bloc `risk` (`vol_window`, `vol_anomaly_pctile`,
  `vol_min_points`, `mom_lookback`, `mom_skip`, `benchmark`, `default_years`) et
  `chart_heights.risk` ; aucun seuil littéral dans `risk.js`.
