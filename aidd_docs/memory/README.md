# memory/ — Project Memory

Le contexte structuré que l'assistant lit au début d'une session, pour ne pas
redécouvrir le projet chaque fois.

## How it loads

Les fichiers racine sont listés dans le bloc `<!-- aidd_project_memory -->` de
`CLAUDE.md`, donc visibles à chaque session. L'assistant lit ceux qui sont pertinents
pour la tâche, pas tous indistinctement. `internal/` et `external/` ne se lisent que
sur demande.

## Files

<!-- files:start -->
- `project-brief.md` — ce qu'est Obole, son vocabulaire métier.
- `architecture.md` — les couches, les décisions et les pièges.
- `codebase-map.md` — les zones du dépôt, les points d'entrée, les modules du front.
- `coding-assertions.md` — les portes à passer avant commit et avant push.
- `testing.md` — la stratégie de test, les outils, la QA navigateur.
- `vcs.md` — branches, commits français signés, merge `--no-ff`, PR.
- `backlog.md` — `CHANTIERS.md` fait autorité ; pont vers les plans d'exécution.
- `api.md` — la surface REST, les contrats, `/api/meta`.
- `data.md` — yfinance, cache SQLite, pipeline, deux séries de prix.
- `ecosystem.md` — humain, agent, MCP, git, CI, yfinance.
- `design.md` — couleurs sémantiques et règles de graphiques.
<!-- files:end -->

## Maintaining it

La banque est écrite par l'assistant et corrigée à la main quand le code change. Règles :

- un fichier par préoccupation, court ; une information n'a qu'un seul domicile ;
- capturer le macro et le non-dérivable (décisions, conventions, pièges), pointer vers le
  code plutôt que le recopier ;
- état courant uniquement : pas de brouillon, pas de TODO, pas de numéro de version.

`tests/test_aidd_memory.py` vérifie que le bloc de `CLAUDE.md` et l'index ci-dessus
listent exactement les fichiers présents.

## Subdirectories

- `internal/` : décisions et notes internes (`decisions/` pour les ADR).
- `external/` : références externes, lues uniquement sur demande.
