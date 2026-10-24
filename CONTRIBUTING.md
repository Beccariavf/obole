# Contribuer à Obole

Merci de l'intérêt. Ce document décrit le minimum attendu pour qu'une contribution soit
intégrable sans allers-retours.

## DCO — Developer Certificate of Origin

Obole utilise le **DCO** (pas de CLA). Concrètement : chaque commit doit être signé pour
attester que vous avez le droit de proposer le code sous la licence du projet.

```bash
git commit -s -m "feat: votre message"
```

La ligne `Signed-off-by: Prénom Nom <email@exemple>` est ajoutée automatiquement. Un commit
non signé bloque la fusion. Le texte de référence est le
[DCO 1.1](https://developercertificate.org/).

## Licence des contributions

En proposant une contribution, vous acceptez qu'elle soit distribuée sous
[AGPL-3.0-or-later](LICENSE), sans condition additionnelle.

## Mise en place

Python **3.11+** et Node **22+** (uniquement pour les tests du front).

```bash
git clone git@github.com:Beccariavf/obole.git
cd obole
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

cd web-tests && npm ci
```

## Cycle de travail

1. **Ouvrez une issue** avant un travail de fond (bug, fonctionnalité, refactor). Cela évite
   de coder quelque chose qui sera refusé pour des raisons de périmètre.
2. **Créez une branche** dédiée, jamais de travail directement sur `main`.
   Préfixes : `feat/`, `fix/`, `chore/`.
3. **Commits en français**, en *Conventional Commits* (`feat:`, `fix:`, `chore:`, `docs:`, `test:`).
   `git add` ciblé, jamais `-A`.
4. **Vérifiez localement** avant de pousser (voir ci-dessous). Une branche rouge ne sera pas fusionnée.
5. **Merge `--no-ff`** — pas de squash : l'historique garde la trace des regroupements.

> **Note.** L'historique de ce dépôt a été aplati : la règle `--no-ff` ci-dessus ne vaut que pour
> le travail à venir. Traçabilité (SHA, décomptes de commits, branches historiques) :
> cf. `CLAUDE.md` §Workflow git.

## Vérifications obligatoires

```bash
ruff check . && ruff format --check .
mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py
pytest -m "not network"
pip-audit

cd web-tests && npm test
```

Si votre changement touche au calcul (ou à un code qui l'appelle), lancez aussi
`pytest -m network` : ce test verrouille la calibration de référence (`RI.PA`, `z = −3.81`).
Le casser est une régression métier, pas un détail.

## Règles d'architecture

Les dépendances ne vont **que** dans un sens :

```
web → api → services → engine → data
```

- **`engine/` est pur** : zéro I/O, zéro réseau, uniquement numpy/pandas. Il n'importe jamais
  `data/` ni `services/`.
- **`data/` est la seule couche** qui touche le réseau et le disque. Aucun autre module
  n'appelle yfinance.
- **`config.py` est la source unique** des constantes et seuils. Aucun nombre magique ailleurs.
- **Le front n'a pas de build** et n'a aucune dépendance CDN : les bibliothèques sont
  vendorisées dans `web/vendor/`.
- **Tous les `fetch` passent par `web/api.js`** — un `fetch` ailleurs fait échouer le test de
  structure.

Si vous modifiez la formule de régression, mettez à jour **les trois implémentations**
(serveur Python + deux calculs côté client) et régénérez `tests/fixtures/regression_parity.json`.

## Style

- Code et commentaires **en français** (le domaine l'est).
- Pas de commentaire qui raconte *ce que* fait le code : commentez *pourquoi*.
- Pas de `TODO` d'abandon : si c'est nécessaire, c'est fait maintenant ; sinon, c'est une issue.
- Tests déterministes, sans réseau (sauf marqueur `network`), couvrant cas nominal, bornes et
  erreurs attendues.

## Sécurité

Ne committez **jamais** de secret (clé, token, mot de passe, chemin absolu personnel). Pour une
vulnérabilité, n'ouvrez pas d'issue publique : voir [SECURITY.md](SECURITY.md).
