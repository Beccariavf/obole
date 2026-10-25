# CLAUDE.md

This file provides guidance to the AI assistant when working with code in this repository.

Le contexte de fond vit dans `aidd_docs/memory/` (voir §Memory Management) : ce fichier ne
garde que ce qui doit être chargé à chaque session — commandes, invariants, workflow.

## Memory Management

Project docs, memory, specs, and plans live in `aidd_docs/`.

Read only task-relevant context and linked memory files; complete required reads.

<!-- aidd_project_memory:start -->
- `aidd_docs/memory/api.md`
- `aidd_docs/memory/architecture.md`
- `aidd_docs/memory/backlog.md`
- `aidd_docs/memory/codebase-map.md`
- `aidd_docs/memory/coding-assertions.md`
- `aidd_docs/memory/data.md`
- `aidd_docs/memory/design.md`
- `aidd_docs/memory/ecosystem.md`
- `aidd_docs/memory/project-brief.md`
- `aidd_docs/memory/testing.md`
- `aidd_docs/memory/vcs.md`
<!-- aidd_project_memory:end -->

- Load `aidd_docs/memory/external/*` only when asked.
- Load `aidd_docs/memory/internal/*` when relevant.

## Projet

Obole — outil perso d'analyse boursière long terme, monoposte (localhost, pas d'auth,
mono-utilisateur). On régresse `ln(prix)` sur le temps pour en déduire valorisation,
potentiel et qualité. La méthode et les seuils calibrés sont dans `PRD.md` §5 ; le
vocabulaire métier dans `aidd_docs/memory/project-brief.md`.

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

**Diagnostic (observabilité, #01) :**

```bash
curl -s http://127.0.0.1:8000/api/health   # état des briques ; 503 si SQLite/cache HS
OBOLE_LOG_LEVEL=DEBUG .venv/bin/python run.py   # logs verbeux (défaut INFO)
tail -f logs/obole.log                    # journal fichier (rotation, dossier gitignoré)
```

- Pas de `python` sur ce poste — utiliser `python3` ou `.venv/bin/python`. `run.py` lance
  sans `--reload` : redémarrer après un changement back ; le front se recharge seul.
- Lancement en tâche de fond : `.venv/bin/python -u run.py` ; le message « Obole prêt »
  sur **stdout** signale le bind réussi (jamais affiché si le port est occupé).
- `pytest-cov` allonge la suite d'environ 15× : garder `-p no:cov` en usage courant.
  **Ne jamais recopier un décompte de tests**, il dérive à chaque session.
- Port 8000 occupé : `OBOLE_E2E_PORT` / `OBOLE_SERVER_CMD` paramètrent l'e2e (exemple et
  détails dans `aidd_docs/memory/testing.md` §Browser QA).
- CI : 3 jobs (backend, frontend, e2e), sur toute branche poussée — détail dans
  `aidd_docs/memory/vcs.md`.

## Règles de travail

| Situation | Geste |
| --- | --- |
| Idée floue | `/01-brainstorm`, puis une fiche `chantiers/NN-….md` |
| Fiche prête | `/01-plan` → plan + phases sous `aidd_docs/tasks/<date>_<slug>/` |
| Plan validé | `/02-implement` (un commit par tâche validée) |
| Avant commit | `/03-assert` — portes de `aidd_docs/memory/coding-assertions.md` |
| Avant merge | `/05-review`, puis `/01-commit` et `/02-pull-request` |
| Décision durable | `/10-learn` (mémoire ou ADR) |

Le backlog et les specs vivent dans **`CHANTIERS.md`** (index + matrice de priorité) et
**`chantiers/`** (une fiche spec par chantier, gabarit `chantiers/_gabarit.md`). Avant tout
travail de fond : lire la fiche, puis la mettre à jour en fin de session (statut dans
l'index, note de reprise dans la fiche). Chaque fiche indique son **impact Pernod**
(🟢/🟠/🔴), qui détermine si le test réseau est obligatoire.

## Workflow git

**Cycle** : branche → commit → vérif verte → merge `--no-ff` sur `main` → push →
suppression de la branche. Le détail (préfixes, commits français signés DCO, `git add`
ciblé, PR draft, CI) est dans `aidd_docs/memory/vcs.md`.

**Historique git aplati — règle de traçabilité (bloc canonique).** L'historique de ce dépôt a été **aplati** : il ne contient **aucun merge**, et les branches citées dans `chantiers/` ne sont plus consultables (elles y sont annotées « Branche (historique) »). Conséquences, valables partout :

- la règle « merge `--no-ff`, jamais de squash » ci-dessus reste la **règle à appliquer** pour tout nouveau travail ; elle n'est pas rétroactive ;
- **ne jamais citer un SHA de commit ou de merge**, ni figer un décompte de commits dans la documentation : ils deviennent faux au premier aplatissement ou au commit suivant. **Décrire le jalon, jamais le commit.** Vérifié par `tests/test_doc_coherence.py` ;
- si l'historique est aplati de nouveau, mettre à jour **ce seul paragraphe** — les autres documents y renvoient, ils ne recopient pas.

## Architecture : couches à sens unique `web → api → services → engine → data`

Les dépendances ne vont **jamais** dans l'autre sens ; `mcp/` entre par `services/`. C'est
l'invariant structurel principal.

Le détail (rôle de chaque couche, décisions, pièges) est dans
`aidd_docs/memory/architecture.md` ; la carte du dépôt dans `codebase-map.md` ; la surface
REST dans `api.md` ; le pipeline de données dans `data.md`.

## Invariants à ne pas casser

**La régression est calculée à TROIS endroits qui doivent rester cohérents :**
1. Serveur Python — `engine/regression.py::fit_log_regression` (`StockAnalysis` initial, historique complet).
2. Client JS — `src/obole/web/charts.js::drawChart` (fonction `olsLog` de `thresholds.js`), recalcule la droite à la volée selon la période / les toggles sans rappeler le serveur.
3. Client JS — `src/obole/web/charts.js::computeLive`, recalcule les indicateurs (σ, perf, écart-type, potentiels) sur la fenêtre courante.

Si tu modifies la formule de régression, **mets à jour les trois** (et régénère `tests/fixtures/regression_parity.json`). Le front recalcule côté client précisément pour éviter un aller-retour réseau à chaque déplacement du curseur.

**Les moyennes mobiles (MM court/long) sont PRÉCALCULÉES serveur**, pas côté client. `services/serialize.py` les calcule sur la série pleine résolution **puis** décime le résultat comme le cours. Calculer la MA côté client sur la série déjà décimée faussait la durée (200 points décimés ≫ 200 jours de bourse). Les fenêtres sont **réglables** via la modale « Paramètres » (mesure technique), persistées en base (table `settings`, helpers `cache.get_settings`/`set_settings`), défauts dans `config.SETTING_DEFS` (`TREND_MA_SHORT`/`TREND_MA_LONG`). La tendance boursière (`trend_is_bullish` dans `engine/` et `summary.py`) applique **les mêmes fenêtres** — cohérence tracé ↔ tendance. Le front lit `ma_short_raw`/`ma_long_raw`/`ma_short_adj`/`ma_long_adj` (action) ou `ma_short`/`ma_long` (ratio/indice) et affiche `MM{short}`/`MM{long}` (légende dynamique via `_maShort`/`_maLong`).

**Les seuils de labels sont désormais à source unique (`config.py` → `/api/meta`).** `config.py` (`DISTANCE_SIGMA_LABELS`, `ECART_TYPE_LABELS`, `PERF_LABELS`, `POTENTIAL_LABELS`, `QUALITY_LABELS`, `BETA_LABELS`, `CORR_LABELS`, `RATIO_THRESHOLDS`, `LABEL_POLARITY`) est la **seule** source : la route `GET /api/meta` les sérialise, et le front les charge au démarrage (`thresholds.js::applyMeta`) avant tout calcul dépendant d'un seuil. Plus aucun seuil littéral dans le JS. `QUALITY_LABELS` reste calculé serveur uniquement. Un test de parité (`web-tests/labels-parity.test.js`) vérifie que le payload `config.py` pilote bien le JS.

**La polarité couleur des labels prix vit dans `config.LABEL_POLARITY`** (sens + seuil), consommée par `engine/labels.py` **et** exposée au front via `/api/meta` — fin des seuils en dur (`good = z < 0`…) côté client.

**Calibration figée par un test réseau.** `tests/test_calibration_network.py` exige Pernod Ricard (`RI.PA`) `z = −3.81` (tolérance 0.15). C'est le garde-fou central de la méthode : tout changement de `fit_log_regression`/`distance_sigma` qui le casse est une régression métier, pas un détail. Les valeurs de calibration viennent de fiches référence Obole réelles (PDFs dans `exemple/`).

**Deux séries de prix, deux usages distincts :** `raw` (Close brut) sert la **valorisation** (distance σ) ; `adjusted` (Adj Close, dividendes réinvestis) sert la **performance passée**. `analysis.py` fait donc deux régressions (`reg_raw`, `reg_adj`). Ne pas les confondre.

**Mode « régression non synchronisée » (règle Obole).** Quand l'utilisateur décoche la synchro dans le front, la droite se calcule sur une fenêtre **fixe** : 20 ans (industrielles) ou 30 ans (financières), **dividendes toujours inclus**. Constantes : `REGRESSION_YEARS_DEFAULT` / `REGRESSION_YEARS_FINANCIAL` (config.py) et leur miroir `REG_YEARS_*` (thresholds.js). En mode synchro, la droite suit la période visible.

**Mode « fenêtre fixe » (exploration des cycles).** Case dans les toggles du graphe héro : elle **verrouille la distance temporelle des deux poignées du slider** à une taille réglable (select 2/5/10/15/20 ans, défaut 5). Bouger une poignée déplace l'autre en miroir → la fenêtre **glisse dans le temps** et la droite (synchro forcée) se recalcule à chaque position, pour observer l'évolution des cycles économiques. **Navigation clavier** : quand la zone période est focus (Tab) et la fenêtre fixe active, les flèches ←/→ déplacent la fenêtre (~1 mois de bourse/appui, `Shift` = ~1 jour), bornées à l'historique. Logique 100 % client dans `charts.js` (`winLocked`/`winYears`, helpers `idxStartBeforeWindow`/`idxEndForWindow`/`nudgeWindow`). Aucun changement serveur.

**Watchlist : une donnée, deux jugements.** La watchlist (`watchlist_items`, un tier 1..3 par ticker) et la fenêtre de confiance (`ticker_refs`, date de départ par titre) sont persistées ; le **prix juste n'est jamais dupliqué** — il est **lu** de `valuation_settings`. La marge est `engine.valuation_calc.safety_margin`, la fenêtre de référence est choisie par `services.analysis.reference_window` (référence persistée sinon 20 ans), et les indicateurs de fenêtre viennent de `services.screen.windowed_analysis` : **aucune formule de marge ou de `z` côté client**. La marge historique se calcule sur les **prix bruts** (`raw`). Le « Prix juste » du Résumé suit la référence au chargement, le prix juste enregistré restant prioritaire. Le MCP peut lire et organiser l'appartenance, **jamais** définir la référence ni le prix juste. **Vue référence** : quand la plage visible EST la référence (et seulement là), la fiche ouvre en prix bruts + synchro, dessine la régression persistée (`watch.ref_stats.a/b/sigma`) et lit ses KPI au dernier cours réel — même droite que la watchlist ; hors de cette plage, le client recalcule comme avant. `services/serialize._downsample` conserve toujours le dernier point (sinon graphe et KPI s'arrêtent avant le dernier cours).

**Schéma de comptes selon le type d'entreprise.** `CompanyKind` (`INDUSTRIAL` vs `FINANCIAL`) est détecté depuis le secteur (`config.FINANCIAL_SECTORS`). Banques/assurances ont un schéma de comptes différent (`data/fundamentals.py`) et une fenêtre de régression 30 ans. Le `kind` circule jusqu'au front (`identity.kind`).

## Skill Archify

Note locale (poste personnel, hors repo) : skill de diagrammes installé dans `~/.openfox/skills/archify`. Si présent, lire son `SKILL.md` avant toute génération de diagramme (architecture/workflow/sequence/dataflow/lifecycle) et utiliser `node bin/archify.mjs validate/deliver`.

## Vision de secours (poste personnel, hors repo)

La vision de secours d'OpenFox pointe sur `http://127.0.0.1:8888/v1` (OpenAI-compatible,
backend `openai`, modèle `unsloth/Qwen3.5-0.8B-GGUF`) — **pas** Ollama (`11434`). Ce réglage
vit dans la config globale de l'outil, hors dépôt : ne jamais l'éditer depuis une session
projet (détail : *Réglages → Vision* dans l'UI OpenFox).

## Conventions

- **Couleurs sémantiques : bleu = bien, rouge = mal** (jamais vert/rouge). Le champ `good`
  d'un `ScoredValue` pilote la couleur (True = bleu, False = rouge, None = neutre).
- **Rachats d'actions toujours en bleu**, jamais en rouge : c'est un retour à
  l'actionnaire, pas un signal négatif.
- Code et commentaires en **français** (le domaine et le PRD le sont).
- Règles de graphiques (≤ 6 points, area fill, palette unifiée, hauteurs de cartes) :
  `aidd_docs/memory/design.md`. Limites de yfinance et dégradation :
  `aidd_docs/memory/data.md`.
