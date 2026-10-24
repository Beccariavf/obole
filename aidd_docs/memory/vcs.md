# VCS

Les conventions de versionnage du projet. `01-commit` et `02-pull-request` lisent ce
fichier : c'est lui qui les empêche d'appliquer leurs défauts anglais.

## Setup

- Branche principale : `main`.
- Plateforme : GitHub, dépôt privé `origin` = `git@github.com:Beccariavf/obole.git`
  (auth par clé SSH).
- CI : `.github/workflows/ci.yml`, sur toute branche poussée et sur les pull requests
  (3 jobs : backend, frontend, e2e).

## Branches

- Format : `type/slug-court`.
- Types utilisés : `feat/` (fonctionnalité), `fix/` (correction), `chore/` (outillage,
  doc, config). Le préfixe `feature/` est un vestige à ne pas réutiliser.
- Une branche par chantier ; jamais de travail de fond directement sur `main`.

## Commits

- Convention : *Conventional Commits*, **messages en français**.
- Format : `type(scope): description` à l'impératif (`feat:`, `fix:`, `chore:`, `docs:`,
  `test:`).
- Signature **DCO obligatoire** : `git commit -s` (ligne `Signed-off-by`).
- Staging ciblé : `git add <fichiers>`, **jamais `git add -A`**. Un commit = une
  préoccupation ; le corps dit *pourquoi*, pas *quoi*.
- Ne jamais citer de SHA ni figer un décompte de commits dans la documentation.

## Commit Strategy

L'IA commite **après chaque tâche validée** (`after task done`), avec son code, ses tests
et ses docs ensemble. Elle ne pousse que sur demande explicite. Elle ne fusionne jamais
d'elle-même sans accord.

## Merge

- `git merge --no-ff <branche>` systématique, **jamais de squash** : l'historique garde
  la trace des regroupements.
- La suite outillée doit être verte avant de fusionner ; un commit rouge ne part pas sur
  `main`.
- Après fusion : `git push origin main`, puis suppression de la branche
  (`git branch -d <branche>`).
- Jamais de `push --force` ; `--force-with-lease` seulement sur demande explicite.

## Pull request

- Toujours une **PR draft** d'abord, base `main`, l'utilisateur la promeut.
- Utiliser le template du dépôt : `.github/pull_request_template.md`.
- Les *branch protection rules* ne sont pas disponibles sur un dépôt privé en plan
  gratuit : le garde-fou est la CI + le template, pas un verrou serveur.

## History

L'historique a été aplati : il ne contient aucun merge, et les branches citées dans
`chantiers/` ne sont plus consultables. La règle `--no-ff` ci-dessus ne vaut que pour le
travail à venir. **Décrire le jalon, jamais le commit.** Le détail canonique vit dans
`CLAUDE.md` §Workflow git.
