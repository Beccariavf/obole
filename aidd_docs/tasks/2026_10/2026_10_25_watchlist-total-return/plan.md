---
objective: "La ligne de watchlist est en total-return (dividendes réinvestis) et, sans prix juste enregistré, son prix juste est le prix d'entrée à 12 %/an jusqu'à la droite à 5 ans."
status: in-progress
---

# Plan: watchlist total-return + prix juste 12 %

## Overview

| Field | Value |
| --- | --- |
| **Goal** | Aligner la watchlist sur le rendement réel de l'investisseur (dividendes) tout en gardant la fiche en valorisation brute (#25.1). |
| **Source** | `chantiers/25.2-watchlist-total-return.md` |
| **Impact** | 🟠 (row builder service + légende front) |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Backend : ligne total-return + prix 12 % | [`phase-1.md`](./phase-1.md) |
| 2 | Front : légende/infobulles + e2e | [`phase-2.md`](./phase-2.md) |
| 3 | Vérification ACA/VIE, captures, doc, revue | [`phase-3.md`](./phase-3.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Toute la ligne watchlist en `regression_adj` | Choix utilisateur : rendement réel (dividendes réinvestis). |
| Prix juste sans valorisation = droite projetée H=5 / 1,12^5 | Garde la référence 12 % pour les droites ; marge comparable à la calculatrice. |
| Conversion en unités du cours brut | Le prix juste affiché reste comparable au cours ; les marges/z/pot sont des ratios. |
| Prix juste enregistré prioritaire | La cible de l'utilisateur prime sur la cible 12 % par défaut. |
| Fiche inchangée (brute) | Décision #25.1 ; la watchlist est la vue total-return, la fiche la valorisation brute. |
