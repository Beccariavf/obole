---
objective: "Après le jeu de convictions, chaque valeur reçoit un tier proposé par des seuils absolus (indice 0-100, seuils 57/43 réglables), les tiers vides sont possibles, et l'application passe par la route tier existante."
status: reviewed
---

# Plan: conviction → tiers par seuils absolus

## Overview

| Field      | Value                                                                 |
| ---------- | --------------------------------------------------------------------- |
| **Goal**   | Remplacer le percentile et les effectifs conservés par un indice absolu et deux seuils réglables, pour classer directement les valeurs dans les tiers. |
| **Source** | Demande utilisateur du 2026-10-26 + débat contradictoire (agents) + fiche `chantiers/27-conviction-tiers.md` |

## Phases

| #   | Phase                    | File                         |
| --- | ------------------------ | ---------------------------- |
| 1   | Moteur de conviction absolu | [`phase-1.md`](./phase-1.md) |
| 2   | Réglages des seuils      | [`phase-2.md`](./phase-2.md) |
| 3   | Résultat et application  | [`phase-3.md`](./phase-3.md) |
| 4   | Preuves et documentation | [`phase-4.md`](./phase-4.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Abandonner le percentile pour un indice absolu 0-100 | Un seuil sur un percentile est un quota déguisé : il y a toujours un 0 et un 100, et le nombre de Tier 1 varie avec la taille du groupe. |
| Seuils par défaut 57/43, réglables | Ce sont les milieux des ancres 1600/1500/1400 ; à couverture suffisante, ils reproduisent les tiers actuels, et l'utilisateur peut les ajuster. |
| Pas d'hystérésis | Mesurée à 24 points, elle bloquait une promotion légitime (1557 < 1574) ; le badge « limite » signale le bruit sans changer la règle. |
| Couverture minimale de 2 duels | Une valeur vue une seule fois garde son tier ; on ne classe pas sur un duel isolé. |
| Tiers vides autorisés | La règle doit pouvoir dire « personne ne mérite le Tier 1 » ; la vue cadrans gère déjà une colonne vide. |
| Seuils lus via `/api/settings` à l'ouverture du jeu | Aucun défaut dupliqué côté JS ; une modification dans Paramètres est prise en compte sans rechargement. |
| Aucun schéma, aucune route, aucun outil MCP | Les seuils vivent dans la table `settings` existante ; l'application utilise la route tier existante. |

## Contract

| Field | Value |
| --- | --- |
| Gate | `.venv/bin/python -m pytest -m "not network" -q -p no:cov -p no:flask -p no:mock && (cd web-tests && npm test)` |
| Max iterations | 12 |

| ID | Criterion | Phase | Proof | Verified by |
| --- | --- | --- | --- | --- |
| C1 | `convictionIndex(1500) = 50`, `convictionIndex(1600) = 64`, `convictionIndex(1400) = 36`. | 1 | — | gate + verifier |
| C2 | `thresholdDistance(58, { tier1: 57, tier2: 43 })` renvoie le seuil 57 et la distance 1. | 1 | — | gate + verifier |
| C3 | Les ratings 1600/1500/1400 avec deux duels donnent Tier 1/2/3. | 1 | — | gate + verifier |
| C4 | Une valeur à un seul duel conserve son tier actuel. | 1 | — | gate + verifier |
| C5 | Avec les seuils 75/65, aucune valeur n'est proposée en Tier 1. | 1 | — | gate + verifier |
| C6 | Les tests ajoutés passent ; les tests existants du percentile et des effectifs restent verts. | 1 | — | gate + verifier |
| C7 | `GET /api/settings` renvoie les défauts 57 et 43, et le groupe `conviction`. | 2 | — | gate + verifier |
| C8 | `PUT /api/settings` avec 60/40 renvoie 200 et persiste ; 40/50 renvoie 422. | 2 | — | gate + verifier |
| C9 | La modale Paramètres affiche les deux seuils et une seule paire d'actions. | 2 | — | gate + verifier |
| C10 | Enregistrer 55/41 puis rouvrir la modale affiche 55/41 ; Rétablir affiche 57/43. | 2 | — | gate + verifier |
| C11 | Aucune migration, aucun changement de schéma. | 2 | — | gate + verifier |
| C12 | `finishConviction` produit des lignes avec un indice entier, un tier suggéré et les seuils utilisés. | 3 | — | gate + verifier |
| C13 | Une valeur à moins de 2 duels garde son tier et porte `tested: false`. | 3 | — | gate + verifier |
| C14 | Le résultat affiche les seuils, l'indice, les duels et les compteurs par tier. | 3 | — | gate + verifier |
| C15 | Un tier vide est affiché avec zéro, jamais comblé. | 3 | — | gate + verifier |
| C16 | Sans changement, le message s'affiche et Appliquer est désactivé. | 3 | — | gate + verifier |
| C17 | Plus aucun code de tiers ne lit le percentile ni les effectifs. | 3 | — | gate + verifier |
| C18 | Les tests du moteur et du mixin passent ; l'application utilise la route tier existante. | 3 | — | gate + verifier |
| C19 | Le parcours du jeu affiche les seuils, quatre lignes et applique un changement T3 → T2. | 4 | — | gate + verifier |
| C20 | Le cas sans changement affiche le message et laisse Appliquer désactivé. | 4 | — | gate + verifier |
| C21 | La modale affiche les deux seuils, capture 55/41 et les actions une seule fois. | 4 | — | gate + verifier |
| C22 | La fiche, l'index et `CLAUDE.md` décrivent les seuils et la couverture ; aucun SHA cité. | 4 | — | gate + verifier |
| C23 | Les captures montrent le résultat et les Paramètres, y compris à 390 px. | 4 | — | gate + verifier |
| C24 | Les nouveaux parcours passent sur Chromium et WebKit ; les échecs WebKit pré-existants restent hors périmètre. | 4 | — | gate + verifier |

