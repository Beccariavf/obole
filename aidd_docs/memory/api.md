# API

La surface HTTP : son style, ses ressources et ses contrats.

## Style

- REST JSON, FastAPI ; `api/app.py` **expose ~77 routes** et sert aussi le front.
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
- Paramètres, sauvegarde/restauration, santé.

## Contracts

- `/api/meta` sérialise les seuils de `config.py` : **source unique** consommée par le
  front au démarrage. Aucun seuil littéral côté JS.
- `/api/health` renvoie 503 si SQLite ou le cache est hors service.
- Les erreurs remontent en `HTTPException` avec un message lisible ; les erreurs métier
  typées (`IndexNotFound`, `ThesisNotFound`) sont traduites en 404.
- Les uploads sont plafonnés avant lecture (CSV, archive de sauvegarde, image de thèse).
- La sérialisation vit dans `services/serialize.py`, partagée API ↔ MCP : `api/` ne
  contient pas de logique de présentation.
