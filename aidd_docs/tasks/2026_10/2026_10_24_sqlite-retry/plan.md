---
objective: "Une écriture SQLite concurrente ne doit plus échouer sur un verrou temporaire, et un verrou permanent doit remonter une erreur claire après un nombre borné de tentatives."
status: in-progress
---

# Plan: Retry SQLite sur `database is locked`

## Overview

| Field | Value |
| --- | --- |
| **Goal** | Rendre les écritures concurrentes robustes (screener multi-thread, UI + MCP) sans changer le modèle de concurrence ni la couche cache. |
| **Source** | `chantiers/11-sqlite-retry.md` |

## Phases

| # | Phase | File |
| --- | --- | --- |
| 1 | Retry de connexion + constantes | [`phase-1.md`](./phase-1.md) |
| 2 | Tests verrou temporaire / permanent | [`phase-2.md`](./phase-2.md) |

## Decisions

| Decision | Why |
| --- | --- |
| Retry au niveau de `Connection.execute` | couvre toutes les écritures (une trentaine de fonctions) sans les décorer une à une ; `BEGIN IMMEDIATE` et `COMMIT` des migrations passent aussi par là |
| Back-off linéaire borné, constantes dans `config.py` | pas de nombre magique ; un verrou permanent échoue en moins d'une seconde |
| Aucun changement du modèle de concurrence | le `ThreadPoolExecutor` du screener reste ; on amortit seulement le verrou |
