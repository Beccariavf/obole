---
objective: "Tenir une watchlist en 3 tiers, classer les favorites par marge de sécurité (prix juste enregistré ou droite de référence), aligner le « Prix juste » du Résumé sur la fenêtre de confiance, et exposer la watchlist au MCP (lecture + appartenance, jamais la référence)."
status: reviewed
---

# Plan: Watchlist à tiers, marges et fenêtre de confiance

## Overview

| Field | Value |
| --- | --- |
| **Goal** | Ajouter une watchlist persistée (tiers, référence par titre) qui lit la valorisation existante et réutilise le scan du screener, sans dupliquer aucune formule. |
| **Source** | `chantiers/25-watchlist.md` |
| **Impact** | 🟠 (touche `services/screen.py`, `services/screener.py`, `services/analysis.py` — pas la formule) |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Domaine persistant (schéma v8, config, SQL, backup) | [`phase-1.md`](./phase-1.md) |
| 2 | Fenêtrage + Résumé aligné | [`phase-2.md`](./phase-2.md) |
| 3 | Classement + API | [`phase-3.md`](./phase-3.md) |
| 4 | MCP | [`phase-4.md`](./phase-4.md) |
| 5 | Front | [`phase-5.md`](./phase-5.md) |
| 6 | E2E, doc, revue | [`phase-6.md`](./phase-6.md) |

## Decisions

| Decision | Why |
| --- | --- |
| 3 tiers fixes, `ticker` PK dans `watchlist_items` | Choix utilisateur ; une appartenance simple, pas de table de listes. |
| `ticker_refs` séparée de l'appartenance | La référence est un réglage d'analyse par titre : retirer de la watchlist ne l'efface pas, et le Résumé peut la lire. |
| Prix juste **lu** de `valuation_settings` | Une seule vérité ; le recalculer dans la watchlist créerait deux définitions. |
| Repli sur la droite de référence, badge visible | Choix utilisateur ; signalé par badge + légende + filtre, car la marge coïncide avec l'écart à la droite. |
| Défaut 20 ans pour tous | Aligné sur l'ouverture de la fiche et le « Prix juste » du Résumé. |
| Marge historique sur `raw` | La valorisation utilise `raw` ; `adjusted` sert la performance. |
| MCP : lecture + appartenance, pas de référence/prix juste | La confiance et l'objectif sont des jugements humains. |
| Pool/timeouts partagés avec le screener | Un seul budget, un seul comportement ; N borné à 200. |
