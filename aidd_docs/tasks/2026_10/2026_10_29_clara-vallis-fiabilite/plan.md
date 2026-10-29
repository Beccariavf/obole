---
objective: "L'onglet Momentum dit « satisfaite » et « frustrée », offre le chip Réf. sur l'historique, et affiche sous lui une table qui compare buy & hold à la stratégie sur la fenêtre visible."
status: pending
---

# Plan: Fiabilité de la Clara Vallis

## Overview

| Field      | Value                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------- |
| **Goal**   | Jauge simplifiée, chip « Réf. » sur l'historique, table de fiabilité buy & hold vs stratégie.      |
| **Source** | `chantiers/31-clara-vallis-fiabilite.md` + brainstorm validé du 2026-10-29                        |

## Phases

| #   | Phase                 | File                         |
| --- | --------------------- | ---------------------------- |
| 1   | Jauge et chip Réf.    | [`phase-1.md`](./phase-1.md) |
| 2   | Moteur du backtest    | [`phase-2.md`](./phase-2.md) |
| 3   | Service et routes     | [`phase-3.md`](./phase-3.md) |
| 4   | Table et chargement   | [`phase-4.md`](./phase-4.md) |
| 5   | Finitions et doc      | [`phase-5.md`](./phase-5.md) |

## Decisions

| Decision                                                              | Why                                                                                                                                  |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Backtest calculé côté SERVEUR, sur la série pleine                    | La grille du graphe est décimée (un point toutes les ~4 séances sur 20 ans) : un backtest dessus raterait des croisements et fausserait drawdown et trades. |
| Hystérésis 0,35 / 0,60, signal décalé d'un jour                        | Le score de `t` ne décide que `t+1` : pas de fuite du futur. L'hystérésis évite de trader sur chaque oscillation du seuil.           |
| Mesures réutilisées de `engine/portfolio`                             | Sharpe, Sortino et drawdown existent déjà et sont testés : une seule implémentation, pas de seconde formule.                          |
| Le backtest suit la bascule brut/ajusté                               | Le module promet qu'un toggle change tout ; la légende dit que le brut ignore les dividendes.                                         |
| La part de satisfaits reste dehors                                    | La moyenne pèse l'intensité, la part compte les gens ; deux chiffres sur une jauge invitent à la mauvaise lecture.                    |
| Le défaut de l'historique reste 10 ans, « Réf. » est un chip          | La table lit le long terme, l'historique lit le régime récent ; le chip donne le repère sans imposer 20 ans à l'ouverture.            |
| Frais 0,1 % **par ordre** (0,2 % l'aller-retour)                     | Une commission se paie à l'entrée ET à la sortie ; le libellé de la table dit « par ordre » pour ne pas laisser croire à 0,1 % l'aller-retour. |
