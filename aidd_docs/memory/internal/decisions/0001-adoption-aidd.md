# Adopter le cadre AIDD (sous-ensemble) sur Obole

- Date: 2026-10-24
- Status: Accepted

## Context

Les skills du framework AIDD sont installées globalement (port DSH, `~/.dsh/skills`) mais
Obole n'avait aucun artefact AIDD : pas de `aidd_docs/`, pas de banque mémoire, aucune
skill branchée sur les conventions du projet. Chaque session redécouvrait l'architecture
et les règles dans un `CLAUDE.md` monolithique ; les skills génériques appliquaient leurs
défauts (commits anglais, squash, `git add -A`, base supposée) au lieu des règles du
dépôt. Le port DSH ne fournit ni marketplace ni hooks : `aidd setup` ne connaît pas
l'outil et n'écrirait rien d'utile.

Le projet a déjà l'essentiel du reste : `PRD.md` (référence produit), `CHANTIERS.md` et
`chantiers/` (backlog et specs), 1 173 tests hors réseau, une CI à trois jobs, un template
de PR, un test de cohérence documentaire.

## Decision

Adopter **la couche contexte et le fil de livraison** d'AIDD, et rien de plus :

- une banque mémoire `aidd_docs/memory/` (11 fichiers courts) câblée dans `CLAUDE.md` ;
- le fil `/01-plan` → `/02-implement` → `/03-assert` → `/05-review` → `/01-commit` →
  `/02-pull-request`, branché sur les fiches `chantiers/` existantes ;
- des garde-fous de test qui remplacent le hook absent : cohérence du bloc mémoire et
  des faits chiffrés ;
- `10-learn` pour les décisions durables (ADR en `memory/internal/decisions/`).

`CHANTIERS.md` reste le backlog d'autorité ; la couche PM, l'orchestrateur asynchrone,
l'acceptance QA et la télémétrie ne sont pas adoptés.

## Alternatives

- **Ne rien faire** : `CLAUDE.md` continue de grossir, les conventions des skills restent
  contredites, et rien ne relie une fiche à son exécution.
- **Tout installer** (PM, epics, stories, defects, async) : migration de 30 fiches vers un
  autre formalisme, des semaines de travail pour un projet solo, sans gain produit.
- **`aidd setup` / CLI** : ne connaît pas DSH ; écrirait une configuration Claude Code
  inutile et un manifeste trompeur.

## Consequences

- Plus facile : une session démarre avec le bon contexte ; un chantier produit un plan
  daté, reprenable et relu ; les skills respectent les commits français signés et le
  `--no-ff`.
- Plus difficile : `CLAUDE.md` doit rester mince, sinon la duplication revient ; deux
  endroits à mettre à jour quand un fait chiffré change (fichier mémoire + test).
- Verrouillé : un fait n'a qu'un domicile ; les invariants et les commandes restent dans
  `CLAUDE.md`, les explications vont en mémoire ; la télémétrie reste désactivée sans
  consentement explicite.
- Pas de hook : la dérive est détectée par `tests/test_aidd_memory.py` et
  `tests/test_doc_coherence.py`. Après une mise à jour du framework (`sync-aidd.sh`),
  relancer une revue de la banque (`/02-project-memory check`).
