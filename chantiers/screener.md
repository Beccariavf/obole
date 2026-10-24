# Screener Obole — plan de construction (document de reprise)

> **Priorité :** 🔵 Q3 (urgent, pas important — extension d'un outil qui fonctionne)
> **Impact Pernod :** 🟠 · **Branche :** `feat/screener-j6` (J6 restant, à créer)

> **Statut :** en cours — J0–J5 + retour sans re-scan consolidés ; **J6 (extension Europe) restant**.
> Reprise possible à n'importe quel jalon.
> Ce fichier est la **mémoire de session** du screener : tout le plan, l'architecture et les
> critères de validation y sont inscrits pour être repris (et validés) étape par étape.
> Cohérence garantie avec `PRD.md` (§12 Projet MCP), `CLAUDE.md` (couche `mcp/`) et la règle
> `web → api → engine → data`.

---

## 1. Contexte & décisions actées

- **Objectif** : screener d'actions selon la méthode « droite d'Obole » déjà calibrée
  (`engine/regression.py`, `PRD.md §5`). Le screener s'expose **via MCP** (projet acté §12) mais
  on le construit **d'abord en web** (modale + tableau) pour valider visuellement la méthode.
- **Scope phase 1** : **France uniquement** (univers ~200 titres : CAC 40 + midcaps FR).
  L'extension **Europe** est un jalon ultérieur (J6).
- **Pré-filtrage optionnel côté Yahoo** : la passe 1 (pays, capitalisation, secteur) se fait
  côté Yahoo (`yf.screen` / `EquityQuery`) AVANT tout calcul Obole. **Optionnel** — l'utilisateur
  peut laisser vide pour tout scanner.
- **Fonctionnalité phare** : après scan, **tri multi-critères** (2 critères chaînés) à la volée
  (ex. trier par écart-type, puis par distance σ).
- **Aucune duplication de formule ni de seuil** : le moteur réutilise `engine/` (regression,
  valuation, labels, analysis). Les seuils restent **exclusivement** dans `config.py`.

---

## 2. Architecture (couches, invariant `web → api → engine → data`)

```
data/screener.py      # I/O : univers FR (yf.screen) + cache SQLite + fallback statique. ping().
engine/screen.py      # logique PURE : screen_stock() + filter_and_sort() (tri multi-critères).
api/screener.py       # APIRouter FastAPI : /api/screener/ping, /universe, /run. Monte dans app.py.
web/                  # bouton "Screener" + modale (filtres) + tableau triable (J4).
```

- **Passe 1** (pré-filtre Yahoo) : pays / capi / secteur → univers restreint.
- **Passe 2** (moteur Obole) : sur chaque survivant, `analyze()` → z, pente, σ, tendance,
  potentiels 5/10a, puis fondamentaux (ROE, PER, P/B, P/FCF, FCF yield).
- **Cache agressif** obligatoire (un scan = N appels yfinance). Réutiliser `data/cache.py`.

---

## 3. Jalons (J0 → J6) — étapes validables isolément

> On n'attaque un jalon qu'une fois le précédent validé. J0–J5 validés ; le jalon courant
> est **J6 (extension Europe)**.

### J0 — Socle visible : bouton + ping backend ✅ validé
**But :** bouton « Screener » dans la barre + endpoint backend minimal, SANS logique métier.
Preuve de liaison front↔back.
- [x] Branche `feat/screener` créée + doc de reprise écrite.
- [x] `data/screener.py` : `ping()` → `{"ok": True, "service": "screener"}`.
- [x] `api/screener.py` : route `GET /api/screener/ping` dans `api/app.py`.
- [x] `index.html` : bouton « Screener » dans la barre de recherche (`@click="openScreener()"`).
- [x] `app.js` : état `screenerOpen` + `openScreener()` (ping + modale placeholder vivante).
- [x] **Tests** : suite hors réseau verte ; `/api/screener/ping` → `{"ok":true,"service":"screener"}`; bouton présent dans le front.
- [ ] _Prochain jalon : J1 (univers FR)._

### J1 — Couche univers FR ✅ validé
- [x] `config.py` : `UNIVERSE_FR` (CAC 40 + midcaps, éditable) + `FR_REGIONS` (`["fr"]`) + `FR_EXCHANGES` (`["PAR"]`) + `TTL_UNIVERSE` + `SCREEN_PAGE_SIZE` + `SCREEN_EXCLUDE_MARKERS`.
- [x] `data/screener.py` : `fetch_universe()` via `yf.screen(EquityQuery(...))` paginé + cache SQLite + fallback statique si Yahoo casse (y compris lot vide).
- [x] Filtre client : quoteType EQUITY, non-crypto, symbole commençant par une lettre (exclut warrants/obligations numériques), nom sans marqueur ETP/obligation.
- [x] Fusion : l'union avec `UNIVERSE_FR` garantit la présence des grandes valeurs.
- [x] Pré-filtres optionnels (`min_market_cap`, `sectors`) passés côté Yahoo ; un appel filtré **by-passe le cache** et **n'empoisonne pas** le cache plein.
- [x] `api/app.py` : route `GET /api/screener/universe`.
- [x] Tests : tests screener (mock yfinance) + suite hors réseau verte ; endpoint réel : plein=653, capi>5Md=69, cache non empoisonné.
- [ ] _Prochain jalon : J2 (moteur de calcul pur `engine/screen.py`)._

### J2 — Moteur de calcul pur (`engine/screen.py`) ✅ validé
- [x] `screen_stock(ticker, prices, regression_window=None)` : délègue à `analyze()` puis
      réduit en `ScreenResult` (z, pente, σ, tendance, pot5/10, ROE, PER, P/B, P/FCF, FCF yield).
- [x] `filter_and_sort(screens, filters, sort_by)` : bornes min/max par critère + tri
      multi-colonnes chaîné (sens par défaut selon la nature du critère).
- [x] `ScreenResult` (models.py) : champs numériques triables + `error` (ticker isolé).
- [x] Décisions tranchées : **fenêtre** (σ+pente sur la fenêtre définie, sinon complet) ;
      **scan** (rapide capi >1Md par défaut, option univers complet — appliqué au J3).
- [x] Tests purs (mock prix) : tests screen verts + suite hors réseau verte ; ruff check vert.
- [ ] _Prochain jalon : J3 (endpoint screener)._

### J3 — Endpoint screener (assemblage) ✅ validé
- [x] `POST /api/screener/run` : pré-filtre passe 1 (`fetch_universe`) + passe 2
      (`fetch_prices` + `screen_stock`) + cache de scan SQLite. Réponse : `{"source",
      "count", "tickers_count", "rows": [dict]}` où `rows` est déjà filtré+trié.
- [x] Réutilise `engine/screen.filter_and_sort` pour les `filters`/`sort_by` (à la
      volée, servi depuis le cache de scan — pas de re-scan réseau).
- [x] Cache de scan : clé dérivée de (min_market_cap, sectors, regression_window),
      TTL `TTL_UNIVERSE` ; contient `{results, source}`.
- [x] Décision « scan rapide » : `min_market_cap` défaut `SCREEN_DEFAULT_MIN_CAP`
      (1 Md€) ; `null` explicite = univers complet.
- [x] Dégradation : un `TickerNotFound` en passe 2 isole la ligne (`error`), jamais
      de crash global ; `sort`/`filters` invalides (clé inconnue, bornes malformées/
      inversées, sens non « asc/desc ») -> 422 via `_validate_filters`/`_validate_sort_by`.
- [x] Tests : tests screener-run (route mockée + validation) + suite hors réseau verte ;
      ruff vert.
- [ ] _Prochain jalon : J4 (front : modale + tableau triable)._

> **Note d'écart architecture (J3) :** le plan prévoyait un routeur dédié
> `api/screener.py` monté dans `app.py`. En pratique les routes screener
> (`ping`, `universe`) sont déjà **inline dans `api/app.py`** (choix J0). Pour la
> cohérence, `/run` est aussi inline dans `app.py` — pas de nouveau module routeur.

### J4 — Front : modale + tableau triable ✅ validé
- [x] Modale `screenerOpen` (style cohérent « Mes indices ») : remplace le placeholder J0.
- [x] Champs : capi min (input, vide = défaut 1 Md€), fenêtre « droite d'Obole »
      (select 5→30 ans = `regression_window`, « Complète » = historique complet).
      (Secteur multi-select et pays Europe : reportés au J6 via le body `sectors`.)
- [x] Bouton « Rechercher » → `POST /api/screener/run` (body = filtres + `sort_by`).
- [x] **Tableau triable** : clic 1ᵉʳ en-tête = critère principal, clic 2ᵉ = second critère
      (chaîné, `screenerSort`), re-clic = inverse le sens (flèche ▲/▼). Clic ligne =
      ouvre la fiche valeur (`loadTicker`). Lignes `error` grisées (chip ⚠), non triées.
- [x] Indicateur de progression (« Calcul du scan en cours… ») + badge source
      (`yahoo`/`cache`/`fallback`) + compteur de lignes.
- [x] **Aucun seuil dupliqué** : les couleurs (bleu=bon/rouge=mauvais) sont calculées
      CÔTÉ SERVEUR (`config.SCREEN_COLORS` + `serialize._polarity`, seuils dérivés des
      labels/RATIO_THRESHOLDS calibrés) et exposées par cellule (`rows[].colors`). Le
      front ne fait que consommer `row.colors` — zéro seuil en dur. Les sens de tri par
      défaut viennent de `config.SCREEN_SORT_DESC` (source unique, consommée par
      `engine.screen.DEFAULT_SORT_ORDER`) exposée via `/api/screener/meta`. Fini le doublon
      Python/JS : le client lit `screenerSortDesc` et `_defaultDir` s'y réfère.
- [x] `/api/screener/meta` : expose `sort_desc` + `colors` (source unique pour le front).
- [x] Tests : suite hors réseau verte (screener incl. polarité + /meta + coerce) ;
      ruff vert ; front validé visuellement (ping + page + `app.js` servi). Le scan plein
      réseau est
      lent (dépend de yfinance, traitement au J5 : coût/robustesse).
- [x] **Robustesse saisie (correction post-J4)** : le front coercit `min_market_cap`
      et `regression_window` en nombre (`Number`, chaîne vide/null -> absent) ; le
      backend `_cast_capi`/`_cast_window` tolère les chaînes numériques et les falsy
      (`""`, `0`, `null`) sans 422 intempestif. Fini les erreurs « Capi invalide » /
      « Fenêtre invalide : 0 » venant de x-model.
- [ ] _Prochain jalon : J5 (polissage coût & robustesse)._

### J4+ — Retour depuis la fiche vers le screener (sans re-scan) ✅ validé
- [x] Sélection d'une ligne du screener → `selectRow` pose `backTo={source:'screener', name:'Screener'}`
      et **ferme la modale** avant `loadTicker` (la fiche prend toute la place).
- [x] Bouton générique « ← Retour à « … » » (déjà présent pour les indices) affiché ;
      le titre devient `Revenir à « Screener »` (fini « l'indice » en dur).
- [x] `backToIndex()` branché : si `source==='screener'`, on **rouvre la modale** sans re-fetch
      (lignes, filtres, source, tri mémorisés) ; sinon comportement indice inchangé.
      → retour **instantané** (aucun re-scan réseau, cache de scan exploité).
- [x] Le bouton « Analyser » purge `backTo` (`@click="backTo = null; load()"`) : une
      recherche manuelle ne laisse pas traîner un « ← Retour au Screener » obsolète.
- [x] Tests : suite hors réseau verte, `node --check` OK, `ruff` clean ;
      Playwright E2E (screener → fiche → retour → table restaurée, source cache).

### J5 — Polissage coût & robustesse ✅ validé
- [x] **Scan parallèle** : `_scan_universe` (`api/app.py`) exécute la passe 2 via
      `ThreadPoolExecutor` (stdlib) borné par `config.SCREEN_WORKERS` (**défaut 8**).
      Le bottleneck est l'I/O yfinance (history/info/comptes) → I/O-bound, parallélisable ;
      gain ~10× pour ~40 lignes, sans nouvelle dépendance.
- [x] **Cache concurrent-safe** : `data/cache.py::_conn()` passe en
      `PRAGMA journal_mode=WAL` + `busy_timeout` (`config.SQLITE_BUSY_TIMEOUT` = 5000 ms)
      + `timeout=` au connect. Prise en charge des écritures simultanées des threads (plus
      de `sqlite3.OperationalError: database is locked`).
- [x] **Garde-fou anti-scan-infini** : budget **global** = `SCREEN_WORKERS × SCREEN_FETCH_TIMEOUT`
      (20 s × workers), PAS une limite par ticker. À l'expiration, les tickers non-aboutis sont
      isolés `error="timeout"` et le pool est arrêté **sans attendre**
      (`shutdown(wait=False, cancel_futures=True)`) : les threads déjà lancés ne sont pas
      préemptables, mais le scan rend la main sans les attendre. Un `TickerNotFound` /
      série trop courte reste isolé `error`, sans crash.
- [x] **Aucun seuil dupliqué** : inchangé (couleurs serveur `SCREEN_COLORS`, tri via
      `SCREEN_SORT_DESC` / `/api/screener/meta`). Le front ne porte aucune valeur magique.
- [x] Progression : on garde le texte statique « Calcul du scan en cours… » (pas de
      compteur % — YAGNI, cf. §7bis.4 : un scan devenu rapide n'a pas besoin de polling).
- [x] Tests : suite hors réseau verte (nouveaux `tests/test_screener_j5.py` :
      parallélisation rapide < temps séquentiel, ticker cassé isolé, timeout isolé,
      cache multi-thread sans `locked`, mode WAL actif). `ruff check src tests` vert ;
      `node --check src/obole/web/app.js` OK.
- [ ] **À ajuster au premier scan réel** : `SCREEN_WORKERS` (8) et `SCREEN_FETCH_TIMEOUT`
      (20 s) à recaler selon le rate-limit yfinance observé.

> **Note de reprise (2026-09-22, mesure de latence).** Scan à froid mesuré sur ce poste :
> **26,6 s** pour 139 tickers (défaut 1 Md€), **64,4 s** pour 664 tickers (univers complet,
> cas « borne max seule » qui pose `min_market_cap=0`). À chaud (cache SQLite de scan), le
> même scan rend en **< 0,2 s** (filtrage à la volée). `yfinance.exceptions.YFRateLimitError`
> (« Too Many Requests ») observé dans `logs/obole.log` pendant un scan plein : avec 8 workers,
> les 664 tickers (~4 appels chacun : prices/info/financials/dividends) saturent Yahoo.
> Pistes (chantier à part, **pas** de tuning dans le fix des filtres) : baisser
> `SCREEN_WORKERS` (4-6), espacer les appels, ou mettre les tickers en échec `error` en
> tête de scan ; le cache de scan (TTL 24 h) amortit déjà les re-scans à critères constants.

### J5bis — Pré-filtres par critère + redimensionnement ✅ validé
- [x] **Rangée de pré-filtres** (min/max) dans la modale pour 8 critères clés :
      Capi, Pente %, Écart-type %, ROE %, Pot. 5a %, PER, FCF yield %, Qualité.
      Labels/directions lus depuis `/api/screener/meta` — **aucun seuil en dur**
      (le `body.filters` {critère:[min,max]} est validé par `_validate_filters`).
- [x] **Construction du `body.filters`** : `_buildFilters()` pur et déterministe —
      chaque borne coercée à `Number`/`''`→`null`, filtre **omis** si les deux bornes
      vides **ou** si min > max (évite un 422), jamais de NaN. Bouton « ↺ filtres »
      (resetScreenerRanges) vide tous les pré-filtres.
- [x] **Redimensionnement** : modale screener élargie (`modal-screen` ~1200px/95vw)
      + wrapper `.screen-table-wrap` en `overflow-x: auto` → **scroll horizontal
      interne** (plus aucune colonne coupée sur scan réel ~61/142 valeurs).
- [x] Tests : suite hors réseau verte (nouveaux tests : filtres multi-critères ET,
      bornes unilatérales côté engine ; multiples critères bornés côté API).
      `ruff check src tests` vert ; `node --check src/obole/web/app.js` OK.
- [x] Front validé visuellement (Playwright) : grille 4 colonnes, filtre ROE ≥ 10
      → 142→61 valeurs, tableau scrollable horizontalement.
- [x] **Harmonisation (bug scroll vertical)** : `overflow:hidden` retiré de la modale,
      `.modal-screen` en flex-column `max-height:92vh` ; seul `.screen-table-wrap`
      scrolle en Y **et** X (`overflow:auto`, `flex:1`). **En-têtes `thead th` sticky**
      (libellés toujours visibles en défilant). Grille de pré-filtres en `auto-fit`,
      compteur fixe en bas (`screen-table-foot`), padding cellules réduit.
      Corrige « impossible de scroller vers le bas » + colonnes tronquées à droite.
- [x] **Unités harmonisées** : Capi (min univers passe 1 ET pré-filtre par critère)
      en **Md€** (placéholders « min Capi (Md€) »), converties en EUR brut serveur
      (×1e9). Le filtre global Capi min est libellé « Capi min univers (Md€) — restreint
      le scan (passe 1) » pour le distinguer du pré-filtre market_cap (passe 2).
- [x] Décision UX : pas d'auto-rescan à la saisie des bornes (cohérent avec le bouton
      « Rechercher » global ; un debounce serait sur-ingénierie, YAGNI §7bis.4).

### J5ter — Correction : filtre manuel Capi bloquait le scan ✅ validé

- [x] **Bug** : `web/app.js::_buildFilters()` déclarait `const lo` / `const hi` puis les
      **réassignait** pour convertir la capitalisation (Md€ → EUR, ×1e9). Dès qu'une borne
      Capi était posée, `TypeError: Assignment to constant variable` — levée **hors** du
      `try/finally` de `searchScreener`, donc `screenerLoading` restait `true` et **aucun
      `fetch`** n'était émis : spinner infini, jamais de résultat. Seuls les filtres manuels
      touchant la capitalisation étaient concernés (ROE, σ, P/FCF… fonctionnaient ; les
      presets aussi, car aucun ne pose de borne capi).
- [x] **Correctif** : `let lo` / `let hi` (la conversion réassigne). Extraction du body dans
      `_scanBody()` et isolement de son échec dans `searchScreener()` : plus jamais de spinner
      bloqué, même si la préparation des filtres lève.
- [x] **Tests** : unitaires Vitest sur `_buildFilters` (capi min/max/les deux, non-capi,
      vide, bornes inversées) + 1 E2E Playwright (Chromium + WebKit) qui pose une borne Capi
      et vérifie que la requête part avec `filters.market_cap=[5e9,null]` et le tableau affiché.
      Les deux étaient **rouges avant** le correctif (reproduit), **verts après**.
- [x] **Validé en réel** : filtre manuel Capi ≥ 5 Md€ → 61 valeurs, spinner retombé.
- [ ] Reste ouvert (chantier à part) : latence à froid et rate-limit Yahoo (cf. note §J5).

### J6 — Extension Europe (post-phase 1)
- [ ] `EU_REGIONS` (liste régions UE). Pré-filtre pays multi-select. Tests d'extension.
- [ ] *(Priméarisé ensuite)* : fenêtre « droite d'Obole » non adaptée (notée,
      traitée après les pré-filtres et l'extension Europe).

---

## 4. Cohérence avec l'existant

- Le moteur n'introduit **aucune formule** : `screen_stock` délègue à `engine/analysis.analyze`
  (qui assemble `regression` + `valuation` + `labels`), exactement comme `api/app.py`.
- Les seuils des critères screener (σ, ROE, PER, P/B, FCF…) sont lus depuis `config.py`
  (`RATIO_THRESHOLDS`, `DISTANCE_SIGMA_LABELS`…) et leur miroir `app.js` — pas de nouveaux chiffres.
- Le bouton « Screener » s'insère dans la `searchbar` à côté de « Mes indices » (cohérence UI).
- Pas de changement sur `engine/`, `web/` hors ajout, `models.py`. Les routes screener
  (`ping`, `universe`, `run`, `meta`) sont **inline dans `api/app.py`** (pas de module
  routeur dédié — choix acté au J0, cf. note d'écart J3).

---

## 7. Note de reprise (à la prochaine session)

1. Le travail consolidé (J0 → J5 + retour sans re-scan) est sur `main` ; repartir d'une branche
   neuve `feat/screener-j6` pour le jalon restant.
2. Lire ce fichier : le jalon courant est marqué ci-dessus.
3. **J0 à J5 + retour sont validés.** J5 (coût & robustesse) : scan **parallèle**
   (`ThreadPoolExecutor`, `config.SCREEN_WORKERS` = 8), cache SQLite **WAL + busy_timeout**
   (`SQLITE_BUSY_TIMEOUT` = 5000 ms), garde-fou `SCREEN_WORKERS × SCREEN_FETCH_TIMEOUT`
   (20 s) isole un ticker lent en `error="timeout"`. **Prochain jalon : J6 (extension Europe)**
   puis, hors phase 1, le **MCP screener** (§12).
4. Toujours : lancer `pytest -m "not network" -p no:cov -p no:anyio -p no:flask -p no:mock`
   avant et après chaque jalon.
5. **Recaler `SCREEN_WORKERS` / `SCREEN_FETCH_TIMEOUT` au premier scan réel**
   (rate-limit yfinance observé) — constantes laissées aux défauts (8 / 20 s).
6. Respecter la règle `web → api → engine → data` et **jamais** de seuil dupliqué.
