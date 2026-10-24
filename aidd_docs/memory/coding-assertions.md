# Coding Assertions

Les contrôles qui doivent passer pour que le code compte comme terminé. Courts, lancés
après chaque changement.

## Before commit

La porte rapide.

| Ordre | Commande | Vérifie |
| --- | --- | --- |
| 1 | `.venv/bin/ruff check .` | lint (E, F, I, B, UP ; `spikes/` exclu) |
| 2 | `.venv/bin/ruff format --check .` | formatage |
| 3 | `.venv/bin/mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py` | types du cœur, des cas d'usage, de la surface MCP et des contrats |
| 4 | `.venv/bin/python -m pytest -m "not network" -q -p no:cov` | suite backend hors réseau |

## Before push

La porte lourde, avant de pousser ou de fusionner.

| Ordre | Commande | Vérifie |
| --- | --- | --- |
| 1 | les quatre commandes ci-dessus | lint, format, types, tests backend |
| 2 | `cd web-tests && npm test` | Vitest : parité des seuils et de la régression + unitaires |
| 3 | `.venv/bin/pip-audit` | vulnérabilités des dépendances installées |
| 4 | `.venv/bin/python -m pytest -m network -q -p no:cov` | calibration `RI.PA` (`z = −3.81`) — obligatoire si l'impact Pernod est 🟠 ou 🔴 |

## Behavior

- Une assertion qui échoue se répare ; on n'élargit jamais le diff pour la faire passer.
- Ne jamais recopier un décompte de tests : `pytest --collect-only -q | tail -1` le donne.
- `pytest-cov` allonge la suite d'un facteur ~15 : garder `-p no:cov` en usage courant.
