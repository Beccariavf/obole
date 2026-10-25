---
objective: "Quand une valeur a une référence persistée, la fiche affiche la même droite et les mêmes lectures que la watchlist (prix bruts, régression serveur), le dernier point du graphe est le dernier cours réel, et le popover de référence est lisible."
status: in-progress
---

# Plan: cohérence référence / performance 5 ans + popover

## Overview

| Field | Value |
| --- | --- |
| **Goal** | Supprimer les deux sources d'écart fiche ↔ watchlist (série ajustée vs brute, re-fit client vs régression persistée) et le dernier point de décimation perdu. |
| **Source** | `chantiers/25.1-watchlist-reference.md` |
| **Impact** | 🟠 (touche `services/serialize.py`, `services/watchlist.py`, `web/charts.js`) |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Backend : décimation, paramètres de référence, pente brute | [`phase-1.md`](./phase-1.md) |
| 2 | Vue référence front (chargement, graphe, KPI) | [`phase-2.md`](./phase-2.md) |
| 3 | Popover, e2e, captures, doc, revue | [`phase-3.md`](./phase-3.md) |

## Decisions

| Decision | Why |
| --- | --- |
| La référence ouvre la fiche en prix bruts + synchro | La droite persistée est une droite de valorisation (`raw`) ; laisser les dividendes cochés affichait la droite ajustée, d'où 7,6 % vs 2,9 %. |
| La droite/KPI utilisent `a/b/sigma` serveur si la plage = référence | Supprime le re-fit sur la série décimée (0,28/2,4 vs 0,15/2,9) et fait de la watchlist la source. |
| `_downsample` garde le dernier point | Le graphe s'arrêtait au 19 oct. / 15,30 € alors que l'en-tête était au 23 oct. / 14,92 €. |
| `pente_pct` brute dans la ligne de watchlist | La ligne était incohérente (perf ajustée, z/potentiels bruts). |
| Popover en items bloc | La grille 16 px/1fr héritée cassait les libellés en un mot par ligne. |
