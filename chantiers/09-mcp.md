# #09 — MCP (surface de pilotage IA)

> **Statut :** **fait** (09.0, 09.1, 09.2, 09.3, 09.4 ✅) · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche proposée :** `feat/mcp-socle` · **Taille :** 3 jalons + extensions
> **Fiche parente :** — (chantier racine) · **Dépend de :** #15 (`services/`)
> **Source :** `PRD.md` §12 (Projet MCP) et §10 (feuille de route, lignes MCP-A → MCP-E)

---

## 1. Contexte

`PRD.md` §12 acte le MCP comme **colonne vertébrale des évolutions futures** : « la même app, une
surface de plus », permettant à une IA (Claude, etc.) de **consommer ET d'alimenter** Obole sans
passer par le front web. `CLAUDE.md` documente la couche `mcp/` comme **planifiée et non
implémentée** — le module n'existe pas encore dans le dépôt.

Prérequis levé : le socle s'appuie sur une couche `services/` propre (#05, #15), sans quoi il
dupliquerait l'orchestration des cas d'usage.

**Invariants non négociables** (`PRD.md` §12.1) :

- Réutiliser `services/` + `engine/` + `data/` ; **aucune duplication** de formule ni de seuil.
- Respecter `web → api → services → engine → data` : le MCP est une couche de transport à sens
  unique vers `services`/`engine`/`data`, il ne contourne pas le cœur.
- Les seuils restent **exclusivement** dans `config.py`. Le MCP ne définit **aucun** seuil.
- Le test de calibration réseau (Pernod `z = −3.81`) et les tests non-network restent **verts**.
- Le MCP ne touche jamais `web/` ni `api/app.py`.

## 2. Objectif

Exposer Obole à une IA via un serveur MCP local : d'abord en **lecture** (fiches, ratios,
recherche, indices, screener), puis en **écriture pilotée** (portefeuille, thèse, DCF,
Monte-Carlo) — sans dupliquer une seule ligne de logique métier.

## 3. Non-objectifs

- **Aucun appel LLM côté serveur** : l'IA est le cerveau, Obole fournit données et persistance
  (`PRD.md` §12.1).
- Pas de transport HTTP par défaut (option ultérieure, `PRD.md` §12.3).
- Pas de modification de `web/` ni de `api/app.py`.
- Pas de nouveau seuil ni de nouvelle formule : tout vient de `config.py`/`engine/`.

## 4. Exigences

- 4.1 Couche `src/obole/mcp/` : `server.py` (instance `MCPServer`, SDK v2) + `tools/` (un module par outil).
- 4.2 Transport **stdio** par défaut (`PRD.md` §12.3).
- 4.3 Les outils sont des **verbes** aux docstrings descriptives (= la doc de l'IA).
- 4.4 **Famille 1 — lecture** : analyse fiche, ratio A/B, recherche, CRUD indices, screener FR.
- 4.5 **Famille 2 — écriture pilotée** : portefeuille (import à validation stricte), thèse,
  DCF, Monte-Carlo — chacun spécifié par sa propre fiche.
- 4.6 Toute entrée venue de l'IA est **hostile par défaut** : validation stricte avant
  persistance.
- 4.7 Aucun appel réseau non-cache introduit par un outil de lecture.
- 4.8 Dépendance MCP épinglée dans `requirements.txt` (nom et version **vérifiés**).

## 5. Critères d'acceptation

- [x] `src/obole/mcp/server.py` existe et démarre en stdio
- [x] Au moins un outil exposé et appelable
- [x] La dépendance MCP est épinglée dans `requirements.txt` (version réelle vérifiée)
- [x] `grep` : aucun import de `web/` dans `mcp/`
- [x] Aucun seuil ni formule dupliqué (délégation à `engine`/`services`)
- [x] Suite hors réseau verte (`pytest -m "not network" -q`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`, ±0.15) reste verte.
- Règle de couches `web → api → services → engine → data` respectée par la couche `mcp/`.
- Les seuils restent **exclusivement** dans `config.py` (`PRD.md` §12.1).
- Aucun appel LLM côté serveur (`PRD.md` §12.1).

## 7. Jalons

Sous-fiches dans `chantiers/mcp/` (jalons MCP-A + thèse) :

- **09.0 — Socle.** Serveur `MCPServer` (SDK v2), transport stdio, outil de vérification.
  → `mcp/00-socle.md`
- **09.1 — Outils de lecture.** Stock, ratio, search, indices.
  → `mcp/01-outils-lecture.md`
- **09.2 — Screener FR.** `screen_french_stocks` sur univers FR éditable.
  → `mcp/02-screener-fr.md` (**fait**)
- **09.3 — Thèse d'entreprise.** `write_thesis` + persistance SQLite.
  → `mcp/03-these-entreprise.md` (**fait**)
- **09.4 — Portefeuille (MCP-B) + suivi.** Comptes, transactions, dividendes, positions,
  résumé TWR, points de contrôle suivis.
  → `mcp/04-portefeuille-suivi.md` (**fait**)

**Extensions (règle).** Les outils MCP sont ajoutés **au fil des nouvelles fonctionnalités** de
Obole, chacun avec sa propre fiche au moment de le démarrer (gabarit `_gabarit.md`) — pas de
backlog d'extensions pré-spécifiées.

## 8. Note de reprise

**Fiche racine créée lors du tri du dossier `chantiers/`.** Le chantier #09 n'avait pas de fiche
racine : l'index pointait directement sur la sous-fiche `mcp/00-socle.md`, contrairement au patron
retenu pour #17 (fiche racine + dossier de sous-fiches). Aucun contenu de jalon n'a été modifié :
cette fiche **agrège** ce qui existait (index + `PRD.md` §12).

**Prochaine action.** Aucun jalon MCP-A restant. Les nouveaux outils MCP sont ajoutés **au fil des
nouvelles fonctionnalités** d'Obole, chacun avec sa propre fiche au moment de le démarrer. Le jalon
**09.4 (portefeuille MCP-B + suivi)** est la dernière extension : après lui, restent **MCP-D DCF** et
**MCP-E Monte-Carlo** (sans fiche), et l'**évaluation « attentes vs réalisé »** des thèses
(schéma `5 → 6`), explicitement reportée comme fonctionnalité ultérieure.

**Historique.** Jalon 09.0 (socle) → 09.1 (outils de lecture) → 09.2 (screener FR) → 09.3
(thèse d'entreprise) → **09.4 (portefeuille MCP-B + points de contrôle)**. Seuls les jalons font
foi : cf. `CLAUDE.md` §Workflow git pour la traçabilité des branches.
