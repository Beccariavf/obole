# Composants tiers

Obole intègre des bibliothèques tierces **vendorisées** dans `src/obole/web/vendor/` : le front
n'a pas de build et n'a **aucune dépendance CDN**, donc chaque bibliothèque est copiée telle
quelle dans le dépôt. Leurs licences sont rappelées ici, conformément à leurs obligations
d'attribution.

## Bibliothèques du front (vendorisées)

| Composant | Version | Licence | Usage |
|---|---|---|---|
| [Plotly.js](https://github.com/plotly/plotly.js) | 2.35.2 | MIT | Graphes interactifs (héro, mini-charts) |
| [Alpine.js](https://github.com/alpinejs/alpine) | 3.14.1 | MIT | Réactivité du front, composant unique |
| [marked](https://github.com/markedjs/marked) | 15.0.7 | MIT | Rendu markdown des thèses |
| [DOMPurify](https://github.com/cure53/DOMPurify) | 3.2.4 | Apache-2.0 OU MPL-2.0 | Assainissement du HTML des thèses |
| [Inter](https://rsms.me/inter/) | 4.1 (variable) | SIL Open Font License 1.1 | Typographie |

Les textes intégraux de ces licences accompagnent chaque fichier dans son en-tête (MIT, Apache,
OFL) ou sont disponibles aux liens ci-dessus. Aucune de ces licences n'impose de restriction
incompatible avec l'AGPL-3.0 : elles sont toutes permissives (ou, pour DOMPurify, duales avec
une option permissive).

## Dépendances Python

Les dépendances de l'application sont déclarées dans `pyproject.toml` et installées depuis PyPI
(elles ne sont **pas** vendorisées). Pour en obtenir la liste avec leurs licences :

```bash
pip install -e ".[dev]"
pip-licenses --format=markdown
```

Principales : `yfinance` (Apache-2.0), `pandas` (BSD-3-Clause), `numpy` (BSD-3-Clause),
`fastapi` / `starlette` / `uvicorn` (BSD-3-Clause), `mcp` (MIT), `peewee` (MIT),
`certifi` (MPL-2.0), `frozendict` (LGPL-3.0).

### Points d'attention sur les licences des dépendances

Deux dépendances transitives ne sont pas sous licence permissive ; aucune n'empêche la
distribution d'Obole sous AGPL-3.0, mais elles doivent être connues :

- **`frozendict` (LGPL-3.0)**, tirée par `yfinance`. Elle est utilisée comme bibliothèque
  liée dynamiquement, sans modification, ce que la LGPL autorise explicitement depuis une
  œuvre sous AGPL. Aucun code d'Obole n'en dérive.
- **`certifi` (MPL-2.0)**, tirée par `yfinance`/`requests`. La MPL est fichier par fichier ;
  elle n'impose rien sur le code d'Obole.

`pip-licenses` peut signaler des paquets `UNKNOWN` : c'est le cas de `peewee`, dont la
métadonnée de licence est absente alors que son fichier `LICENSE` est un MIT classique
(vérifié : `Copyright (c) 2010 Charles Leifer`).

Les dépendances de **développement** (`pytest`, `ruff`, `mypy`, `pip-audit`, `pip-licenses`)
ne sont pas distribuées avec l'application et n'affectent pas la licence du produit.

## Données

Obole ne redistribue **aucune donnée de marché**. Les cours et comptes sont récupérés à
l'exécution par `yfinance`, sur la machine de l'utilisateur, et mis en cache dans son propre
fichier SQLite — jamais dans le dépôt. Voir [DISCLAIMER.md](DISCLAIMER.md) pour la
non-affiliation à Yahoo.
