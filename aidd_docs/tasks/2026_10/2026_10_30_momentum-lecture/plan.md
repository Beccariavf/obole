---
objective: "La fiche Momentum situe le score dans l'histoire du titre (percentile) et montre le rendement qui a suivi chaque zone (médiane, dispersion, épisodes), sans ajouter de signal prédictif."
status: reviewed
---

# Plan: Lecture du score Momentum — percentile et rendement conditionnel

## Overview

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| **Goal**   | Deux aides de lecture sur l'onglet Momentum : où le score se situe dans l'histoire du titre, et ce qui a suivi ce niveau. |
| **Source** | Conversation du 2026-10-30 — les deux features proposées après l'étude d'orientation. |

## Phases

| #   | Phase                  | File                         |
| --- | ---------------------- | ---------------------------- |
| 1   | Percentile historique  | [`phase-1.md`](./phase-1.md) |
| 2   | Rendement conditionnel | [`phase-2.md`](./phase-2.md) |

## Decisions

| Decision | Why |
| -------- | --- |
| Nouveau module `engine/momentum_stats.py` plutôt que d'étendre `clara_vallis` | Le score reste une définition pure ; les statistiques descriptives du score vivent à part et se testent seules. |
| Percentile et conditionnel suivent la bascule brut/ajusté | Le payload porte déjà `score_raw`/`score_adj` ; une seule lecture à la fois, comme la jauge. |
| Les statistiques conditionnelles portent sur toutes les fenêtres, mais le nombre d'épisodes indépendants est affiché à part | Les fenêtres de 12 mois se chevauchent : la dispersion serait sous-estimée, et un « n » de séances ferait croire à des observations indépendantes. |
| La clé de cache du payload change de suffixe | Un payload mis en cache avant le déploiement n'a pas les nouveaux champs ; sans bump, la fiche resterait muette jusqu'à expiration du TTL. |
| Hors périmètre : témoin de stabilité du signe et plancher d'annualisation | Proposés lors de la même revue, non demandés ici ; ils touchent la table de fiabilité, pas la lecture du score. |
