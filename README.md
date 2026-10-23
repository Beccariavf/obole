# Obole

**Analyse boursière long terme pilotée par une IA.** Obole régresse `ln(prix)` sur le temps
pour situer une action par rapport à sa propre tendance de fond — puis expose l'ensemble à un
assistant (Claude, etc.) via le protocole **MCP**, qui peut lire les analyses *et* alimenter
le portefeuille.

Local, mono-utilisateur, sans compte à créer : vos données restent chez vous, dans un SQLite.

> ⚠️ Obole n'est **pas un conseil en investissement**. Voir [DISCLAIMER.md](DISCLAIMER.md).

## La méthode : la droite d'Obole

On régresse le logarithme du cours sur le temps (moindres carrés ordinaires). La droite obtenue
représente la **tendance de fond** de la valeur ; l'écart vertical à cette droite, exprimé en
écarts-types (σ), mesure la **valorisation** : au-dessus, la valeur est chère par rapport à sa
propre trajectoire ; en dessous, décotée.

- **Distance σ** = valorisation (prix brut, historique complet).
- **Pente annualisée** = performance de fond.
- **Potentiels 5 / 10 ans** = retour annualisé nécessaire pour rejoindre la droite.
- **Performance passée** = lue sur les prix **dividendes réinvestis** (série ajustée).
- **Tendance** = moyennes mobiles (fenêtres réglables).

Deux séries, deux usages : `raw` pour la valorisation, `adjusted` pour la performance. Les
confondre fausse tout — c'est l'invariant central du projet.

## Installation

Python **3.11+** requis.

```bash
git clone git@github.com:Beccariavf/obole.git
cd obole
./start.sh          # crée le venv, installe, sert sur http://127.0.0.1:8000
```

Ou via [pipx](https://pipx.pypa.io/), sans cloner :

```bash
pipx install git+https://github.com/Beccariavf/obole.git
obole               # -> http://127.0.0.1:8000
```

Vos données (base, logs, images de thèses) vivent hors du paquet : dans la racine du dépôt en
développement, sinon dans `~/.local/share/obole` (surchargeable par `OBOLE_DATA_DIR`).

## Utilisation

Tapez un ticker (`RI.PA`, `AAPL`, `BNP.PA`) et cliquez **Analyser**.

La fiche se navigue par sections — `Résumé`, `Quantitatif`, `Dividende`, `Finance`,
`Thèse & Société`, `Valorisation` — et l'adresse reflète la section (`#RI.PA/quantitatif`),
donc un lien est partageable. Autres écrans : **screener** de l'univers français,
**indices** personnalisés (paniers equal-weight chaînés en total return) et **portefeuille**
(comptes, transactions, dividendes, positions, performance TWR face à un benchmark, risque).

## Le MCP : l'IA comme cerveau, Obole comme mémoire

Obole embarque un serveur **MCP** (transport stdio). Une IA cliente peut alors lire les
analyses, chercher un ticker, lancer un screener, rédiger une thèse — et **écrire** dans le
portefeuille.

```bash
obole --mcp                        # tous les outils : lecture + écriture
obole --mcp --read-only            # lecture seule : les outils d'écriture ne sont pas exposés
```

En mode nominal, chaque écriture pilotée par l'IA **copie la base** au préalable
(`cache.sqlite.bak`) : une hallucination ne détruit pas vos données sans filet.

Le serveur ne fait **aucun** appel de modèle : il expose des données et des opérations.
L'IA raisonne, rédige et propose ; Obole calcule et persiste.

Exemple de configuration cliente (Claude Desktop) :

```json
{
  "mcpServers": {
    "obole": {
      "command": "obole",
      "args": ["--mcp"]
    }
  }
}
```

## Sécurité

Obole est un outil **mono-poste, sans authentification**. Il refuse par défaut d'écouter sur une
adresse non locale : `obole --host 0.0.0.0` échoue, sauf `OBOLE_ALLOW_REMOTE=1` explicite.
L'exposer sur un réseau le rendrait accessible à quiconque.

Le MCP écrit dans vos données : donnez-lui un répertoire de travail dédié
(`OBOLE_DATA_DIR`) plutôt que votre fichier de comptes réel. Détails et procédure de
signalement dans [SECURITY.md](SECURITY.md).

## Architecture

Couches à sens unique — une dépendance ne remonte jamais :

```
web → api → services → engine → data
```

```
src/obole/
  data/      # yfinance + cache SQLite (seule couche réseau & disque)
  engine/    # cœur pur : régression log, distance σ, potentiels, labels, qualité
  services/  # cas d'usage : orchestration data+engine (analyse, screener, thèse, portfolio)
  api/       # FastAPI : exposition JSON + service du front
  mcp/       # surface de pilotage IA (outils verbe, aucun seuil dupliqué)
  web/       # front HTML + Alpine.js + Plotly (sans build, vendorisé)
  config.py  # constantes & seuils — source unique
  models.py  # contrats typés entre couches
```

La régression est calculée à **trois endroits qui doivent rester cohérents** : le serveur
Python (`engine/regression.py`), et deux fois côté client (`web/charts.js`) pour recalculer à
la volée sans aller-retour réseau. Un test de parité (`web-tests/regression-parity.test.js`)
verrouille l'alignement.

## Développement

```bash
pip install -e ".[dev]"

ruff check . && ruff format --check .
mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py
pytest -m "not network"           # suite rapide, hors réseau
pytest -m network                 # garde-fou de calibration (appelle yfinance)
pip-audit                         # vulnérabilités des dépendances

cd web-tests && npm test          # tests du front (Vitest + jsdom)
cd web-tests && npm run test:e2e  # smoke Playwright
```

Les contributions sont bienvenues — voir [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[AGPL-3.0-or-later](LICENSE). Les composants tiers vendorisés (Plotly, Alpine.js, marked,
DOMPurify, Inter) sont listés dans [THIRD-PARTY.md](THIRD-PARTY.md).

## Notes

- yfinance fournit ~20-30 ans de cours mais seulement ~4-5 ans de comptes, et plafonne la
  recherche à ~5 résultats : ces manques sont signalés par des avertissements, jamais par un crash.
- Cache agressif (prix 1 jour, comptes 7 jours) ; bouton ↻ pour rafraîchir.
- Schéma de comptes adapté aux financières (banques, assurances).
