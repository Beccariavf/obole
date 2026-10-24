# Project AI Docs

Le contexte structuré que lit l'assistant pour travailler sur Obole, sans redécouvrir
le dépôt à chaque session.

## Ce qui vit ici

- `memory/` : la banque mémoire projet, chargée à chaque session. Voir
  [`memory/README.md`](memory/README.md).
- `tasks/` : plans, phases et revues d'exécution, créés au fil des chantiers
  (`tasks/<yyyy_mm>/<yyyy_mm_dd>_<slug>/`).
- `memory/internal/` : traces internes (décisions, notes de revue) — lues à la demande.
- `memory/external/` : références externes — lues uniquement sur demande.

## Comment c'est maintenu

Le port DSH n'a pas de hooks AIDD : rien n'est régénéré automatiquement. La banque est
écrite et corrigée **à la main**, et deux garde-fous l'empêchent de dériver :

- `tests/test_aidd_memory.py` vérifie que le bloc `<!-- aidd_project_memory -->` de
  `CLAUDE.md` et l'index de `memory/README.md` listent exactement les fichiers présents.
- `tests/test_doc_coherence.py` vérifie que les faits chiffrés (routes annoncées, modules
  du front, remote) correspondent au code.

Pour changer ce que voit l'assistant : ajouter ou retirer un fichier sous `memory/`, puis
mettre à jour le bloc de `CLAUDE.md` et l'index de `memory/README.md`. Ne pas éditer le
bloc à la main sans le test.

## Le cadre retenu

Le projet n'utilise qu'un sous-ensemble d'AIDD : la couche contexte (mémoire + câblage),
le fil de livraison (plan → implémentation → assertions → revue → commit → PR) et la
boucle d'apprentissage (`10-learn`). Le reste du marketplace n'est pas adopté — la
décision et ses raisons sont dans
[`memory/internal/decisions/0001-adoption-aidd.md`](memory/internal/decisions/0001-adoption-aidd.md).

## Le framework

Les skills sont installées globalement (`~/.dsh/skills`) ; elles ne sont pas copiées dans
ce dépôt. Catalogue, guide d'installation et workflow complet :
<https://github.com/ai-driven-dev/framework>.
