---
objective: "La vue cadrans conserve toutes ses informations et son mini-cadran par carte, mais la carte passe de 209 px à ≤130 px et la tête de tier de 86 px à ≤50 px, sans backend ni changement de données."
status: in-progress
---

# Plan: cadrans compacts (option A)

## Overview

| Field      | Value |
| ---------- | ----- |
| **Goal**   | Mini-cadran 44 px + valeur hors SVG + grille 2 colonnes ; tête de tier 58 px. |
| **Source** | `chantiers/26.1-watchlist-cadrans-compact.md` + plan validé (option A) |

## Phases

| #   | Phase                      | File                         |
| --- | -------------------------- | ---------------------------- |
| 1   | Carte et tête compactes    | [`phase-1.md`](./phase-1.md) |
| 2   | Preuves et tests           | [`phase-2.md`](./phase-2.md) |
| 3   | Documentation et revue     | [`phase-3.md`](./phase-3.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Mini-cadran 44 × 26 décoratif, valeur en HTML | garde l'identité ; le texte SVG serait illisible à cette taille. |
| Tête de tier 58, valeur 15 px hors SVG | 86 → 42,6 px ; la moyenne reste lisible. |
| Métriques 2 colonnes, Prix juste pleine largeur | la carte descend à 118 px sans déborder à 280 px. |
| Titre en `span`, Voir seule action, ✕ nommé | 3 arrêts de tabulation et un nom accessible correct. |
| CSS scopé `.wl-card`/`.wl-tier-head` | `.wl-dial`/`.wl-card-k` sont partagés avec le duel. |
