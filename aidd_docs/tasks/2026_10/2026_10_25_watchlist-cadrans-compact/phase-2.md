---
status: done
---

# Instruction: preuves et tests

## Architecture projection

```txt
.
└── web-tests/e2e/watchlist.spec.js   ✏️ hauteur, Voir, ✕, a11y
```

## User Journey

```mermaid
flowchart TD
  A[Vue compacte] --> B[Hauterur ≤130]
  B --> C[Voir ouvre la fiche]
  C --> D[✕ retire la carte]
```

## Test Scope

```mermaid
---
title: Test scope
---
journey
  section Setup
    seed watchlist with five rows => ready: 5: api
  section Happy path
    open watchlist => card height <= 130: 5: browser
    click Voir => fiche opens: 5: browser
    click remove and accept => card disappears: 5: browser
  section Edge case - narrow viewport
    set 390 px => one column, no overflow: 1: browser
  section Teardown
    restore viewport => baseline: 5: browser
```

## Tasks to do

1. Ajouter la hauteur de carte ≤130 px, le Voir, le ✕ avec dialog accepté et les routes DELETE.
2. Vérifier le texte de tête `.wl-dial-text` (tier), le select, le 3/2/1 et le 390 px.
3. Capturer avant/après et lancer les suites front/backend/e2e.

## Test acceptance criteria

| Task | Acceptance criteria |
| ---- | ------------------- |
| 1 | L'e2e mesure une carte ≤130 px et Voir/✕ fonctionnent. |
| 2 | Le tier, le select, les colonnes et le 390 px restent corrects. |
| 3 | Les suites sont vertes et les captures montrent avant/après. |
