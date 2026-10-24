# #01 — Observabilité (logs structurés, `/api/health`)

> **Statut :** **fait** · **Priorité :** 🟡 Q2 (importante, non urgente — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche (historique) :** `feat/observability` · **Taille :** ~1 session

---

## 1. Contexte

Le diagnostic d'un dysfonctionnement est aujourd'hui impossible sans lancer un navigateur :

- `grep -rn "logging\|logger" src/obole/` → **0 résultat**. Un seul `print()` : `api/app.py::lifespan`
  (« Obole pret sur … »).
- Deux `except Exception` avalent la cause sans la tracer :
  - `data/yahoo.py::_with_retry` — `except Exception:  # yfinance lève des exceptions variées`
  - `data/screener.py::fetch_universe` — `except Exception:  # réseau KO, quota, changement d'API…`
- Aucun endpoint de santé : impossible de savoir en un appel si yfinance, SQLite ou le cache
  répondent.

C'est la cause directe du « ça ne marche pas » de la session d'audit : le symptôme était
invisible côté serveur, il a fallu piloter un navigateur headless pour comprendre.

## 2. Objectif

Pouvoir répondre en une commande à : *« qu'est-ce qui a échoué, où, et pourquoi ? »* — sans
navigateur, et sans modifier le code pour ajouter un `print` temporaire.

## 3. Non-objectifs

- Pas de service externe (Sentry, Datadog, OpenTelemetry) : outil perso monoposte.
- Pas de rotation de logs avancée : un fichier local borné suffit.
- Pas de refonte des `except` : on ajoute une trace, on ne change pas la logique de dégradation.

## 4. Exigences

- 4.1 Un module `logging` configuré une fois (niveau via variable d'environnement, sortie console
  + fichier local).
- 4.2 Les deux `except Exception` larges tracent la cause (`logger.warning(..., exc_info=True)`)
  au lieu de l'avaler silencieusement.
- 4.3 Les événements critiques sont tracés avec métadonnées utiles : ticker, étape, durée,
  cause. Les appels yfinance lents (> seuil) sont signalés.
- 4.4 Un endpoint `GET /api/health` teste et renvoie un statut par brique : yfinance,
  SQLite (`cache.sqlite` ouvrable), cache (lecture/écriture).
- 4.5 **Aucune donnée sensible loggée** : tickers et durées OK ; jamais de contenu brut, jamais
  de payload non assaini.

## 5. Critères d'acceptation

- [x] `logging` configuré dans un module dédié, importé au démarrage de l'app
- [x] `yahoo.py::_with_retry` et `screener.py::fetch_universe` tracent la cause (`exc_info`) et non plus rien
- [x] `GET /api/health` renvoie 200 avec un statut par brique, et **503** si une brique critique est HS
- [x] Test : un échec simulé de yfinance produit une ligne de log exploitable
- [x] Test : `/api/health` renvoie les 3 briques attendues
- [x] Aucun secret ni payload brut dans les logs (relecture)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- La dégradation gracieuse de `data/` est conservée : un échec renvoie toujours `None`/fallback,
  jamais de crash (on ajoute une trace, on ne remonte pas l'exception).
- Aucun nouvel appel réseau : `/api/health` réutilise le cache, il ne déclenche pas de fetch massif.

## 7. Jalons

- **J1** ✅ — Module de logging + configuration au démarrage (aucun comportement modifié).
- **J2** ✅ — Traçage des deux `except` larges.
- **J3** ✅ — `GET /api/health` + tests.
- **J4** ✅ — Traçage des durées d'appels yfinance.

## 8. Note de reprise

**Terminé.** Implémentation livrée sur `feat/observability`.

**Livrables**

- **`src/obole/observability.py`** (nouveau) — module **feuille** (stdlib + `config`, comme
  `config.py`) : toutes les couches peuvent l'importer sans casser `web → api → engine → data`.
  `configure_logging()` (idempotente), `get_logger()`, `safe_label()`, `resolve_level()`, et le
  compteur d'échecs (`record_failure` / `recent_failures` / `last_failure` / `reset_stats`).
- **`src/obole/data/health.py`** (nouveau) — contrôle des briques. Placé dans `data/` car il touche
  le disque (invariant : seule `data/` fait de l'I/O) ; l'API ne fait que l'exposer.
- **`src/obole/data/yahoo.py`** — `_with_retry` devient le **point d'instrumentation unique** de
  tous les appels yfinance : durée (appel lent → WARNING), échecs (debug par tentative, warning
  `exc_info=True` à l'abandon, alimentation du compteur). Nouveau paramètre `context` (optionnel,
  rétro-compatible) propagé depuis tous les appelants (`prices RI.PA`, `financials RI.PA`, …).
- **`src/obole/data/screener.py`** — le repli sur `UNIVERSE_FR` est tracé (`exc_info=True`).
- **`src/obole/api/app.py`** — `GET /api/health` + `configure_logging()` dans le `lifespan`.
- **`config.py`** — `LOG_DIR` / `LOG_FILE` / `LOG_MAX_BYTES` / `LOG_BACKUP_COUNT` / `SLOW_CALL_MS` /
  `HEALTH_FAILURE_WINDOW_S` (aucun nombre magique ailleurs).
- **`.gitignore`** — `logs/` (même motif que `.ruff_cache/`, `.pytest_cache/`, `.mypy_cache/`).

**Décisions**

1. **Le `print("  Obole pret sur …")` est conservé tel quel sur stdout** : c'est un contrat (CLAUDE.md
   + détection de démarrage par le harnais). Les logs vont sur **stderr** précisément pour ne pas
   l'enterrer — un test verrouille cette séparation.
2. **`yfinance` n'est pas une brique critique.** La dégradation gracieuse est un principe du projet :
   yfinance HS → statut `degraded` mais **200** (l'app reste utilisable). Seuls `sqlite` et `cache`
   sont critiques → **503**. La fiche ne tranchait pas.
3. **`/api/health` ne fait aucun appel réseau.** La brique yfinance rapporte l'importabilité, la
   version et les **échecs récents observés** (fenêtre `HEALTH_FAILURE_WINDOW_S`). Un simple test
   d'import ne répondrait pas à « yfinance répond-il ? » ; le compteur est le signal réel, à coût nul.
   Un test interdit tout appel à `yf.Ticker`/`download`/`Search` pendant la requête.
4. **Instrumentation centralisée dans `_with_retry`** plutôt que dispersée : un seul point mesure
   *tous* les appels yfinance. Tentative ratée en `debug` (pas de bruit), abandon en `warning`.
5. **`safe_label()`** : les libellés viennent de l'extérieur (ticker d'URL, requête de recherche) et
   un saut de ligne permettrait de forger une fausse entrée d'audit. Les caractères non imprimables
   sont remplacés et la longueur bornée. La requête de recherche n'est **pas** journalisée (saisie
   libre) : le libellé est simplement `search`.
6. **Jamais de payload dans les logs** : uniquement libellé, durée, type d'exception. Un test passe
   un résultat contenant un marqueur et vérifie son absence dans la sortie capturée.
7. **Fichier de log inaccessible → dégradation console seule** (droits, disque plein) : le démarrage
   ne doit pas échouer pour un problème de journalisation.

**Preuve par mutation** (8 mutations, toutes détectées par les tests) : retirer `exc_info` ;
retirer le signalement des appels lents ; rendre yfinance critique ; envoyer la console sur stdout ;
retirer l'idempotence ; retirer la purge de la clé sentinelle ; journaliser le payload ; retirer
`logs/` du `.gitignore`.

**Vérifications**

- `tests/test_observability.py` : config/idempotence/stdio, `safe_label`, logs
  d'échec et de lenteur, compteur borné + fenêtre, 3 briques, codes HTTP, absence de réseau,
  gitignore.
- Suite complète `pytest -m "not network" -q` verte ; `-m network` vert (calibration Pernod
  intacte). `ruff check`, `ruff format --check`, `mypy` verts.
- **Manuel (serveur réel)** : `GET /api/health` → 200, les 3 briques OK
  (`yfinance 0.2.66`, `sqlite schema_version=1`, `cache ok`) ; défaillance simulée → ligne WARNING
  avec traceback dans `logs/obole.log` **et** sur stderr, compteur à 1, brique `degraded` ;
  `print` de démarrage toujours sur stdout ; `GET /api/stock/RI.PA` et `/api/indices` → 200.
