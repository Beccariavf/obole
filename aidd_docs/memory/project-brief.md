# Project Brief

## What it is

- Obole — outil personnel d'analyse boursière long terme, mono-poste (localhost,
  mono-utilisateur, pas d'authentification).
- Il régresse `ln(prix)` sur le temps pour situer une action par rapport à sa **propre**
  tendance de fond, puis expose analyses et données à un assistant via le protocole
  **MCP**.

## Why it exists

- Répliquer la méthode « droite de régression » de référence (fiches Obole) et la rendre
  utilisable au quotidien : valorisation, potentiel et qualité d'une action, sans
  dépendre d'un service tiers.
- L'IA est le cerveau (elle raisonne, rédige une thèse) ; Obole calcule et persiste.
  Le serveur ne fait aucun appel de modèle.

## Domain language

| Terme | Sens |
| --- | --- |
| **Droite d'Obole** | Régression OLS de `ln(prix)` sur le temps (années). La pente annualisée est la performance de fond ; les résidus donnent σ. |
| **Distance σ** | Écart vertical du cours à la droite, en écarts-types de résidus → la **valorisation**. Négatif = sous sa tendance. |
| **Potentiel 5 / 10 ans** | Rendement annualisé nécessaire pour rejoindre la droite sur l'horizon. |
| **Qualité** | Score composite (croissance, rentabilité, endettement) affiché en label, calculé serveur uniquement. |
| **`raw` / `adjusted`** | `raw` = Close brut, sert la valorisation ; `adjusted` = Adj Close (dividendes réinvestis), sert la performance passée. Ne jamais les confondre. |
| **PRU** | Prix de revient unitaire d'une position (coût moyen pondéré). |
| **TWR** | Time-weighted return : performance du portefeuille neutralisant les flux. |
| **`CompanyKind`** | `INDUSTRIAL` ou `FINANCIAL` ; banques et assurances ont un schéma de comptes différent et une fenêtre de régression de 30 ans (20 sinon). |
| **Chantier** | Unité de travail du backlog : une fiche `chantiers/NN-….md` (spec) et une branche dédiée. |
| **Impact Pernod** | Rayon d'action d'un chantier sur la calibration de référence (`RI.PA`, `z = −3.81`) : 🟢 nul / 🟠 indirect / 🔴 direct. |

## Key features

- Fiche entreprise par sections (Résumé, Quantitatif, Dividende, Finance, Thèse & Société,
  Valorisation), deep-linkable (`#RI.PA/quantitatif`).
- Screener de l'univers français, indices personnalisés, portefeuille (comptes,
  transactions, positions, performance TWR, risque).
- Thèse d'entreprise (document markdown + profil société) et points de contrôle suivis.
- Surface MCP lecture + écriture : Obole comme mémoire de l'IA.

## Ce qu'il n'est pas

- Pas un conseil en investissement (voir `DISCLAIMER.md`).
- Pas un service multi-utilisateur : pas d'auth, pas de déploiement distant par défaut.
