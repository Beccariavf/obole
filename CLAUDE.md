# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Projet

Obole — outil perso d'analyse boursière long terme, monoposte (localhost, pas d'auth, mono-utilisateur). Réplique la méthode « droite de régression » de référence Obole : on régresse `ln(prix)` sur le temps et on en déduit valorisation, potentiel et qualité. La référence produit est `PRD.md` (la méthode et les seuils calibrés sont au §5).

## Commandes

```bash
./start.sh                        # crée le venv (uv/python -m venv), installe, sert
# ou manuellement :
uv pip install --python .venv/bin/python -e ".[dev]"   # pins (yfinance fragile)
.venv/bin/python run.py           # -> http://127.0.0.1:8000 (uvicorn, pas de reload)

pytest -m "not network" -p no:cov -p no:flask -p no:mock  # tests purs, rapides
pytest -m network                 # garde-fou Pernod z=−3.81 (appelle yfinance, peut skip si offline)
pytest tests/test_regression.py::test_xxx   # un seul test

ruff check .                      # lint (E, F, I, B, UP ; E501 ignoré, spikes/ exclu)
ruff format .                     # formatage
mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py   # types (cœur + cas d'usage + surface MCP + contrats)
pip-audit                         # audit des dépendances installées

cd web-tests && npm test          # tests front : parité seuils/régression + unitaires (Vitest+jsdom)
cd web-tests && npm run test:e2e  # smoke Playwright (Chromium + WebKit) — démarre le serveur
```

**Si le port 8000 est déjà pris** (autre serveur sur le poste), inutile de dupliquer
la config Playwright : le port est paramétrable. `OBOLE_SERVER_CMD` change la
commande de lancement, `OBOLE_E2E_PORT` l'URL surveillée et le `baseURL`.

```bash
cd web-tests && OBOLE_E2E_PORT=8012 \
  OBOLE_SERVER_CMD="PYTHONPATH=../src ../.venv/bin/python -m uvicorn obole.api.app:app --host 127.0.0.1 --port 8012" \
  npm run test:e2e
```

Lancer uvicorn sur une base **neuve** (`config.CACHE_DB` redirigé) reproduit la CI :
elle part d'un checkout sans `cache.sqlite`, donc **aucune donnée utilisateur**. Un
test e2e qui présuppose une thèse existante doit semer sa propre fixture via l'API
et la restaurer — sinon il est vert en local et **rouge en CI**.

**Diagnostic (observabilité, #01) :**

```bash
curl -s http://127.0.0.1:8000/api/health   # état des briques ; 503 si SQLite/cache HS
OBOLE_LOG_LEVEL=DEBUG .venv/bin/python run.py   # logs verbeux (défaut INFO)
tail -f logs/obole.log                    # journal fichier (rotation, dossier gitignoré)
```

**CI** (`.github/workflows/ci.yml`) : 3 jobs — `backend` (ruff + mypy + pytest hors réseau +
pip-audit), `frontend` (Vitest), `e2e` (Playwright Chromium + WebKit, nécessite le réseau
pour la fiche RI.PA).

Pas de `python` sur ce poste — utiliser `python3` ou `.venv/bin/python` si présent. `run.py` lance sans `--reload` : redémarrer manuellement après un changement back. Le front (HTML/JS/CSS) est servi en statique, donc un simple rechargement de page suffit côté navigateur.

**Lancement avec background_process :** utiliser `background_process` (action=start) avec `.venv/bin/python -u run.py`. Le message `"  Obole prêt sur http://127.0.0.1:8000"` apparaît sur **stdout** une fois le serveur réellement à l'écoute (~3-4s) — émis par `_serve` après le bind, donc jamais affiché si le port est occupé (dans ce cas un diagnostic actionnable part sur stderr et le process sort en code 1). Uvicorn écrit ses logs sur stderr (non visible dans background_process). Si le serveur ne répond pas, attendre 4s puis `curl http://127.0.0.1:8000/`.

**Tests lents avec pytest-cov :** `pytest-cov` instrumente `yfinance` et allonge les tests de 15× (~4-5 min au lieu de 17s). Passer `-p no:cov` pour désactiver la couverture. Les tests non-network sont **732** au total (~6s avec `.venv/bin/python`).

**Tests front (`web-tests/`)** — Node/Vitest+jsdom, aucun build du front. Le front est
découpé en **modules ES natifs** (`web/app.js` = composant Alpine seul qui assemble les
mixins `search/screener/indices/charts/cursor/exportcsv/events/settings/sections/summary/portfolio/dividend/valorisation/thesis/suivi` ; `api.js` centralise les
`fetch` ; `thresholds.js` porte les maths et reçoit les seuils de `/api/meta`). Les tests
importent ces modules réellement. Garde-fous de **parité** :
`labels-parity.test.js` (parse `config.py` et compare au payload `/api/meta` consommé par
`thresholds.js`) et `regression-parity.test.js` (même fixture que
`tests/test_regression_parity_fixture.py`). `modules.test.js` verrouille la structure
(0 `fetch` hors `api.js`, `app.js` < 500 lignes). La fixture est régénérée par
`tests/fixtures/generate_regression_parity.py` : toute modification de la formule de
régression doit la régénérer (sinon les deux tests cassent).

## Chantiers (backlog)

Le backlog vit dans **`CHANTIERS.md`** (index + matrice de priorité) et **`chantiers/`** (une fiche spec par chantier). Avant tout travail de fond, vérifier s'il existe une fiche ; la lire avant de coder et la **mettre à jour en fin de session** (statut dans l'index, note de reprise dans la fiche). Chaque fiche indique son **impact Pernod** (🟢/🟠/🔴), qui détermine si le test réseau est obligatoire.

## Workflow git

Dépôt distant : `origin` = `git@github.com:Beccariavf/Marge.git` (privé, auth par clé SSH — aucun mot de passe demandé).

**Cycle d'une modification :**

```
branche → commit → vérif (verte) → merge --no-ff sur main → push → suppression de la branche
```

1. **Branche dédiée** — jamais de travail de fond directement sur `main`. Préfixes : `feat/` (fonctionnalité), `fix/` (correction), `chore/` (outillage, doc, config). Le préfixe `feature/` est un vestige à ne pas réutiliser.
2. **Commit** — messages **en français**, en *Conventional Commits* (`feat:`, `fix:`, `chore:`, `docs:`, `test:`). `git add <fichiers>` ciblé, **jamais `-A`**.
3. **Vérification** — la suite outillée doit être verte **avant** de fusionner (lint, types, tests hors réseau) : voir §Commandes. Un commit rouge ne part pas sur `main`.
4. **Fusion** — **merge commit `--no-ff`** systématique (`git merge --no-ff <branche>`), jamais de squash : l'historique garde la trace des regroupements (ex. « Merge feat/observability : chantier #01 »).
5. **Push** — `git push` puis, après fusion, `git push origin main`. Une branche peut aussi être poussée pendant le travail : la CI tourne alors dessus et sert de garde-fou avant le merge.
6. **Nettoyage** — la branche fusionnée est supprimée (`git branch -d <branche>`) ; seules les branches réellement mergées peuvent disparaître (`-d` refuse le reste).

**Commande `Commit & Push`.** La commande OpenFox générique est surchargée au niveau du projet par `.openfox/commands/commit-push.command.md` (même `id: commit-push`, donc elle remplace la version par défaut ici). Elle connaît les chemins réels du dépôt (`.venv/bin/ruff`, `.venv/bin/pytest`, `cd web-tests && npm test`) et vérifie **avant** de pousser. Pour l'invoquer : « commit & push » ou « crée une branche `feat/xxx` ».

Ce cycle prolonge celui des chantiers (cf. **`CHANTIERS.md` §4**) : une fiche passe « à faire » → « en cours » (branche dédiée) → « fait » (merge sur `main`). Mettre à jour le statut dans l'index et la note de reprise dans la fiche en fin de session.

**CI.** `.github/workflows/ci.yml` tourne sur **toute branche poussée** (`push.branches: ["**"]`) et sur les pull requests : 3 jobs (`backend` = ruff + mypy + pytest hors réseau + `pip-audit`, `frontend` = Vitest, `e2e` = Playwright). Attention : les *branch protection rules* ne sont pas disponibles sur un dépôt privé en plan gratuit — le garde-fou est donc la CI + le template de PR (`.github/pull_request_template.md`), pas un verrou de serveur.

## Architecture : couches à sens unique `web → api → services → engine → data`

Les dépendances ne vont **jamais** dans l'autre sens. Respecter cette règle est l'invariant structurel principal.

- **`data/`** — seule couche qui touche le réseau et le disque. `yahoo.py` (yfinance + retry + dégradation gracieuse : un bloc qui échoue renvoie `None`, jamais de crash), `cache.py` (SQLite, blobs picklés, TTL ; porte aussi les tables utilisateur et les migrations de schéma), `backup.py` (export/restauration JSON des données utilisateur) et `health.py` (contrôle des briques pour `/api/health`). Tout passe par le cache ; rien d'autre ne doit appeler yfinance.
- **`engine/`** — cœur **100 % pur** (zéro I/O, zéro réseau, numpy/pandas only). `regression.py` est le cœur mathématique. **N'importe jamais `data/` ni `services/`** (vérifiable par `grep`). Le screener y garde sa partie pure (`screen.py` : `filter_and_sort`, `composite_score`).
- **`services/`** — **cas d'usage** (orchestration) : assemble `data/` + `engine/` sans logique métier propre. `analysis.py` (analyse action/ratio/indice/panier, `summarize_index`, et les façades `analyze_ticker`/`analyze_ratio_tickers`/`analyze_index` partagées API ↔ MCP), `indices.py` (façade CRUD indices, erreur typée `IndexNotFound`), `screen.py` (`screen_stock`), `screener.py` (cas d'usage `run_screen` + validation partagée API ↔ MCP `validate_filters`/`validate_sort_by`/`validate_score_keys`, déplacée hors de `api/` au jalon 09.2), `thesis.py` (cas d'usage thèse : `write_thesis` — prompt + `analysis_to_dict` sans `chart` — et CRUD à erreur typée `ThesisNotFound`, jalon 09.3), `imports.py` (staging d'import #23 : `propose_import` n'écrit qu'un **brouillon**, `apply_draft` est la seule écriture et n'est branchée que sur une route REST — jamais un outil MCP) et `serialize.py` (transformation des analyses → payload JSON, partagé API ↔ MCP ; ancien `api/serialize.py`, déplacé au jalon 09.1). C'est ici que vit l'orchestration I/O, appelée par `api/` **et** par le MCP. La règle documentée devient `web → api → services → engine → data`.
- **`api/`** — FastAPI fin. `app.py` expose ~38 routes (stock, ratio, search, refresh, indices, événements, saisie manuelle, **imports pilotés** `GET/POST/DELETE /api/imports`, screener, settings, sauvegarde/restauration, health) + sert le front ; il appelle `services/`, jamais `engine/analysis`. La sérialisation vit dans `services/serialize.py` (déplacée hors de `api/` au jalon MCP 09.1 pour que le MCP partage le même code sans importer `api/`) ; `api/serialize.py` **n'existe plus**. `static_files.py` sert les assets avec versionnage par hash de contenu (`/static/x.js?v=<hash>` → cache immuable) et `no-cache` sinon.
- **`web/`** — front **sans build**, découpé en **modules ES natifs** (`<script type="module">`) : `app.js` = composant Alpine seul (< 500 l.) qui assemble un mixin par domaine — `search.js`, `screener.js`, `indices.js`, `charts.js`, `cursor.js` (overlay du curseur du graphe héro : readout prix·σ·date, survol + repos), `exportcsv.js`, `events.js`, `settings.js`, `sections.js`, `summary.js`, `portfolio.js`, `dividend.js`, `valorisation.js`, `thesis.js`, `suivi.js` ; `api.js` centralise **tous** les `fetch` (aucun `fetch` ailleurs) ; `thresholds.js` porte les maths (`olsLog`, `scored`…) et reçoit les seuils de `/api/meta` (source unique `config.py`) via `applyMeta` ; `theme.js` (charte couleur), `util.js` (slug, `parseCSV`/`detectDelimiter`/`parseNumber` — miroir de `data/manual` pour l'aperçu d'import). **Aucune dépendance CDN** : Plotly, Alpine et Inter sont vendorisés dans `web/vendor/`. Test de structure : `web-tests/modules.test.js`.
- **`mcp/`** — **surface de pilotage IA** (projet acté, cf. `PRD.md` §12) : `src/obole/mcp/server.py` porte l'instance unique `mcp` (`MCPServer`, SDK **v2**, transport **stdio** par défaut), l'outil de vérification `obole_status` et l'enregistrement des outils (`tools/`). Jalons **09.0** (socle), **09.1** (lecture : `get_stock_analysis`, `get_ratio_analysis`, `search_tickers`, CRUD indices), **09.2** (screener FR : `screen_french_stocks`), **09.3** (thèse : `write_thesis` + `save_thesis`/`list_theses`/`get_thesis`/`delete_thesis`, persistance `theses`) livrés et **09.4** (**portefeuille MCP-B** : comptes, transactions, dividendes, positions, résumé TWR — `mcp/tools/portfolio.py` ; **suivi** : `list_checkpoints`/`add_checkpoint`/`update_checkpoint`/`delete_checkpoint` — `mcp/tools/checkpoints.py`) livré, plus **#23** (**staging d'import** : `propose_import` — `mcp/tools/imports.py` — qui crée un **brouillon** `pending` et **n'applique jamais** ; l'application est une route REST réservée à l'utilisateur). Couche de transport à sens unique vers `services`/`engine`/`data` : les outils sont des **verbes** aux docstrings descriptives (= doc de l'IA), **aucune formule ni seuil dupliqué** (toujours `config.py`), **aucune I/O** hors de `data/`. Ne touche pas `web/` ni `api/app.py`. **stdout est le canal du protocole stdio** : jamais de `print()` dans cette couche, la journalisation passe par `observability` (stderr). Les erreurs métier remontent en `ToolError` (message lisible). Tests : `tests/test_mcp_server.py` (structurels, dont le garde-fou « aucun outil n'applique un import ») et `tests/test_mcp_tools.py` (parité outil ↔ API).
- **`models.py`** — contrats typés (dataclasses) échangés entre couches. Tout champ potentiellement absent de yfinance est `Optional` explicite : l'absence se gère partout, jamais de crash sur un champ vide.
- **`config.py`** — toutes les constantes et seuils calibrés. Aucun nombre magique ailleurs.
- **`observability.py`** — module **feuille** (stdlib + `config`, comme `config.py`) : toutes les couches peuvent l'importer, il n'importe rien de l'app. Fournit `configure_logging()` (console **stderr** + fichier `logs/obole.log` à rotation, idempotente ; niveau via `OBOLE_LOG_LEVEL`), `get_logger()`, `safe_label()` (anti-injection de logs) et le compteur d'échecs d'appels externes lu par `/api/health`. **Ne jamais journaliser un payload** (résultat yfinance, données saisies) : uniquement ticker/contexte, durée, étape, type d'exception.

## Invariants à ne pas casser

**La régression est calculée à TROIS endroits qui doivent rester cohérents :**
1. Serveur Python — `engine/regression.py::fit_log_regression` (`StockAnalysis` initial, historique complet).
2. Client JS — `web/charts.js::drawChart` (fonction `olsLog` de `thresholds.js`), recalcule la droite à la volée selon la période / les toggles sans rappeler le serveur.
3. Client JS — `web/charts.js::computeLive`, recalcule les indicateurs (σ, perf, écart-type, potentiels) sur la fenêtre courante.

Si tu modifies la formule de régression, **mets à jour les trois** (et régénère `tests/fixtures/regression_parity.json`). Le front recalcule côté client précisément pour éviter un aller-retour réseau à chaque déplacement du curseur.

**Les moyennes mobiles (MM court/long) sont PRÉCALCULÉES serveur**, pas côté client. `api/serialize.py` les calcule sur la série pleine résolution **puis** décime le résultat comme le cours. Calculer la MA côté client sur la série déjà décimée faussait la durée (200 points décimés ≫ 200 jours de bourse). Les fenêtres sont **réglables** via la modale « Paramètres » (mesure technique), persistées en base (table `settings`, helpers `cache.get_settings`/`set_settings`), défauts dans `config.SETTING_DEFS` (`TREND_MA_SHORT`/`TREND_MA_LONG`). La tendance boursière (`trend_is_bullish` dans `engine/` et `summary.py`) applique **les mêmes fenêtres** — cohérence tracé ↔ tendance. Le front lit `ma_short_raw`/`ma_long_raw`/`ma_short_adj`/`ma_long_adj` (action) ou `ma_short`/`ma_long` (ratio/indice) et affiche `MM{short}`/`MM{long}` (légende dynamique via `_maShort`/`_maLong`).

**Les seuils de labels sont désormais à source unique (`config.py` → `/api/meta`).** `config.py` (`DISTANCE_SIGMA_LABELS`, `ECART_TYPE_LABELS`, `PERF_LABELS`, `POTENTIAL_LABELS`, `QUALITY_LABELS`, `BETA_LABELS`, `CORR_LABELS`, `RATIO_THRESHOLDS`, `LABEL_POLARITY`) est la **seule** source : la route `GET /api/meta` les sérialise, et le front les charge au démarrage (`thresholds.js::applyMeta`) avant tout calcul dépendant d'un seuil. Plus aucun seuil littéral dans le JS. `QUALITY_LABELS` reste calculé serveur uniquement. Un test de parité (`web-tests/labels-parity.test.js`) vérifie que le payload `config.py` pilote bien le JS.

**La polarité couleur des labels prix vit dans `config.LABEL_POLARITY`** (sens + seuil), consommée par `engine/labels.py` **et** exposée au front via `/api/meta` — fin des seuils en dur (`good = z < 0`…) côté client.

**Calibration figée par un test réseau.** `tests/test_calibration_network.py` exige Pernod Ricard (`RI.PA`) `z = −3.81` (tolérance 0.15). C'est le garde-fou central de la méthode : tout changement de `fit_log_regression`/`distance_sigma` qui le casse est une régression métier, pas un détail. Les valeurs de calibration viennent de fiches référence Obole réelles (PDFs dans `exemple/`).

**Deux séries de prix, deux usages distincts :** `raw` (Close brut) sert la **valorisation** (distance σ) ; `adjusted` (Adj Close, dividendes réinvestis) sert la **performance passée**. `analysis.py` fait donc deux régressions (`reg_raw`, `reg_adj`). Ne pas les confondre.

**Mode « régression non synchronisée » (règle Obole).** Quand l'utilisateur décoche la synchro dans le front, la droite se calcule sur une fenêtre **fixe** : 20 ans (industrielles) ou 30 ans (financières), **dividendes toujours inclus**. Constantes : `REGRESSION_YEARS_DEFAULT` / `REGRESSION_YEARS_FINANCIAL` (config.py) et leur miroir `REG_YEARS_*` (thresholds.js). En mode synchro, la droite suit la période visible.

**Mode « fenêtre fixe » (exploration des cycles).** Case dans les toggles du graphe héro : elle **verrouille la distance temporelle des deux poignées du slider** à une taille réglable (select 2/5/10/15/20 ans, défaut 5). Bouger une poignée déplace l'autre en miroir → la fenêtre **glisse dans le temps** et la droite (synchro forcée) se recalcule à chaque position, pour observer l'évolution des cycles économiques. **Navigation clavier** : quand la zone période est focus (Tab) et la fenêtre fixe active, les flèches ←/→ déplacent la fenêtre (~1 mois de bourse/appui, `Shift` = ~1 jour), bornées à l'historique. Logique 100 % client dans `charts.js` (`winLocked`/`winYears`, helpers `idxStartBeforeWindow`/`idxEndForWindow`/`nudgeWindow`). Aucun changement serveur.

**Schéma de comptes selon le type d'entreprise.** `CompanyKind` (`INDUSTRIAL` vs `FINANCIAL`) est détecté depuis le secteur (`config.FINANCIAL_SECTORS`). Banques/assurances ont un schéma de comptes différent (`data/fundamentals.py`) et une fenêtre de régression 30 ans. Le `kind` circule jusqu'au front (`identity.kind`).

## Skill Archify

Note locale (poste personnel, hors repo) : skill de diagrammes installé dans `~/.openfox/skills/archify`. Si présent, lire son `SKILL.md` avant toute génération de diagramme (architecture/workflow/sequence/dataflow/lifecycle) et utiliser `node bin/archify.mjs validate/deliver`.

## Vision de secours (poste personnel, hors repo)

La vision de secours d'OpenFox pointe sur `http://127.0.0.1:8888/v1` (OpenAI-compatible,
backend `openai`, modèle `unsloth/Qwen3.5-0.8B-GGUF`) — **pas** Ollama (`11434`). Ce réglage
vit dans la config globale de l'outil, hors dépôt : ne jamais l'éditer depuis une session
projet (détail : *Réglages → Vision* dans l'UI OpenFox).

## Conventions

- **Couleurs sémantiques : bleu = bien, rouge = mal** (pas vert/rouge). Constantes `COLOR_*` (config.py) et `C` (theme.js). Le champ `good` d'un `ScoredValue` pilote la couleur (True=bleu, False=rouge, None=neutre).
- **Rachats d'actions toujours en bleu** (C.accent), jamais en rouge. Les rachats sont un retour à l'actionnaire, pas un signal négatif.
- **Graphiques ≤6 points** : toujours en ligne+marqueurs, jamais en barres (aspect histogramme vide). Concerne les rachats (4-5 ans), la génération de cash, les mono-montants courts.
- **Area fill** : ajouté sous les courbes simples (mono, combo, rachats) avec opacité 6-8%, pour un rendu premium (inspiré Baggr). Pas de fill sur les multi-séries (superposition illisible).
- **Palette unifiée** des mini-charts (charts.js `drawMulti`, `drawBars`) : `[#2563EB (bleu), #0D9488 (teal), #7C3AED (violet), #F59E0B (ambre), #F59E0B (or)]`. Pas de rouge ni de vert dans la palette catégorielle.
- **Cartes wide** (pleine largeur) : dividend-kpi, dividend-hist, buyback-hist. Les échelles temporelles différentes (dividendes 20-40 ans vs rachats 4-5 ans) sont séparées visuellement.
- **Hauteur mini-charts** : 220px (CSS `.mini-chart`), cohérent avec le layout Plotly.
- **Sobriété assumée** : cache agressif (prix 1j, comptes 7j, recherche 1j), pas d'ORM, pas de build front, dépendances minimales. Préférer une fonction pure à une abstraction.
- **yfinance est limité** : ~20-30 ans de cours mais seulement ~4-5 ans de comptes ; `yf.Search` plafonne à ~5 résultats côté Yahoo (limite réelle de l'API, pas contournable via `max_results`). Gérer ces manques par des `warnings` (badges de fiabilité), pas par des crashs.
- Code et commentaires en **français** (le domaine et le PRD le sont).
- Les `spikes/spike_*.py` sont des scripts de calibration jetables (exploration des seuils), pas du code applicatif : le dossier `spikes/` est **exclu du lint et du format** (`pyproject.toml`).
