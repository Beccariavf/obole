# #10 — Consolidation documentaire (source unique de la doc)

> **Statut :** à faire · **Priorité :** 🟡 Q2 (important, non urgent — cas (c) évolutivité)
> **Impact Pernod :** 🟢 · **Branche proposée :** `docs/consolidation` · **Taille :** ~1-2 sessions

---

## 1. Contexte

La documentation s'est stratifiée au fil des chantiers et **huit sources se recouvrent
aujourd'hui**, dont deux se contredisent :

| Doc | Versionné | Rôle réel | Problème |
|---|:---:|---|---|
| `README.md` | ✅ | lancement + fonctionnalités | décrit aussi l'architecture (doublon) |
| `PRD.md` | ✅ | vision, features, archi, méthode, roadmap, MCP | v0.2 du 24/09 : déjà **factuellement périmé** (cf. §1.1) |
| `CLAUDE.md` | ✅ | commandes, git, couches, invariants | recouvre `PRD.md` §7 / §7bis |
| `CHANTIERS.md` | ✅ | index backlog + priorité | §3 « ordre d'attaque » double `PRD.md` §10 |
| `chantiers/*.md` | ✅ | specs exécutables | saines ; certaines citent `amélioration/` (non versionné) |
| `amélioration/docs/product/prd.md` | ❌ gitignored | **un second PRD** | **contredit** le premier : « portefeuille hors périmètre » vs « acté » |
| `amélioration/docs/specifications/*.md` | ❌ | formules de domaine | invisibles de la CI, perdues si la machine disparaît |
| `amélioration/references/*.pdf` | ❌ | sources de calibration | légitimement hors dépôt (droits, ~12 Mo) |

### 1.1 Preuves que le PRD versionné a pourri

- `PRD.md:411` — « On ne teste PAS le front ni yfinance (mock). » → **faux** : une suite front
  existe (`cd web-tests && npm test`, Vitest + jsdom) + un smoke e2e Playwright.
- `PRD.md:225` — cite `spike_calibration.py` à la racine ; le fichier vit dans `spikes/`
  (dossier exclu du lint).
- **Le décompte de tests, lui, a déjà disparu** : une version antérieure du PRD annonçait un
  nombre de tests non-network en dur (corrigé puis retiré). C'est la meilleure
  preuve du problème : un chiffre recopié à la main dans de la prose se désynchronise à chaque
  session, et finit par être retiré plutôt que corrigé.

**Ces trois points ont la même cause** : la doc recopie ce que le code est seul à savoir.

## 2. Objectif

Que la documentation redevienne une **source fiable et unique** : un document = une question,
tout le reste **pointe** vers lui au lieu de recopier, et le savoir utile au développement
(formules de domaine) est **versionné**.

## 3. Non-objectifs

- Pas de réécriture du contenu de méthode du `PRD.md` §5 (il est correct).
- Pas de génération automatique de doc (Sphinx, MkDocs) : le front et le back sont sans build,
  la doc reste en Markdown brut.
- Pas de suppression des PDF de référence : ils restent hors dépôt (droits, poids), seul leur
  **index** est versionné.
- Pas d'ajout de fonctionnalité produit.

## 4. Exigences

- 4.1 **Index unique** `docs/README.md` : la carte « quel document répond à quelle question »,
  seul point d'entrée ; les autres docs y renvoient d'une ligne.
- 4.2 **Fusion des deux PRD** : absorber `amélioration/docs/product/prd.md` dans `PRD.md`
  (ou le supprimer après report). Trancher la contradiction de périmètre : le portefeuille est
  **acté** (`PRD.md` §10/§12, fiche #17).
- 4.3 **Rapatrier les textes de spécification** : `amélioration/docs/specifications/*.md` →
  `docs/specs/*.md` (versionnés — ils portent les formules de domaine).
- 4.4 **Index de références** `docs/references/README.md` (versionné) : décrit chaque PDF et son
  usage ; les PDF eux-mêmes restent gitignored.
- 4.5 **ADR** `docs/decisions/` : une décision tranchée = un fichier daté court (contexte,
  décision, conséquence). Amorcer avec les points 🔶 ouverts du PRD §9 (dont Q4 « modèle de
  données portefeuille », tranché par la fiche #17).
- 4.6 **Purge du doublon de roadmap** : `CHANTIERS.md` §3 « ordre d'attaque » renvoie à
  `PRD.md` §10 au lieu de le redire ; une seule source pour la vision/lots, une seule pour
  l'exécution/priorité.
- 4.7 **Règle « zéro chiffre recopiable »** : consigner dans `CLAUDE.md` que tout chiffre
  dérivable du code (nombre de tests, valeurs de calibration, chemins) ne s'écrit **pas** dans
  la prose — on cite la commande ou le test.
- 4.8 **Garde-fou outillé** `tests/test_docs.py` : vérifie que les liens internes des `.md`
  versionnés résolvent et que les fichiers cités existent. Pas de vérification de chiffres
  (fragile) — uniquement l'intégrité des liens.
- 4.9 **Corriger les erreurs factuelles** de `PRD.md` (§1.1) — ou les faire disparaître par la
  4.7 (chiffre remplacé par la commande).
- 4.10 **Purger le décompte de tests en dur de `CLAUDE.md`** (`CLAUDE.md:46` annonce un nombre de
  tests non-network figé) → remplacé par la commande `pytest -m "not network"`, sans chiffre :
  la règle 4.7 ne peut pas s'énoncer au-dessus d'un contre-exemple vivant.
- 4.11 **Garde-fou de cohérence du dossier `chantiers/`** : étendre `tests/test_docs.py` (ou une
  vérification dédiée) pour contrôler, sur les fiches du backlog, (a) que les **liens internes**
  résolvent, (b) que le **statut de l'index `CHANTIERS.md`** concorde avec l'en-tête de la fiche,
  (c) qu'aucune fiche ne porte de **décompte de tests en dur** (règle 4.7). C'est ce qui empêche
  le désordre documentaire de revenir après la consolidation.

## 5. Critères d'acceptation

- [ ] `docs/README.md` existe : index « question → document », aucune duplication de contenu
- [ ] Un **seul** PRD subsiste ; l'autre est supprimé ou marqué comme absorbé (lien)
- [ ] `docs/specs/*.md` existe et est **versionné** (git track) ; `amélioration/docs/specifications/`
      n'est plus la seule copie
- [ ] `docs/references/README.md` indexe chaque PDF ; `git check-ignore` confirme que les PDF
      restent hors dépôt
- [ ] `docs/decisions/` contient au moins 1 ADR (Q4 portefeuille) référencé depuis la fiche #17
- [ ] `CHANTIERS.md` §3 ne redit plus la roadmap du PRD (renvoi, pas duplication)
- [ ] `CLAUDE.md` porte la règle « zéro chiffre recopiable »
- [ ] Le garde-fou de cohérence `chantiers/` passe (liens, statuts index ↔ fiche, aucun chiffre
      figé) ; il **échoue** si un lien est cassé ou un statut divergent (test du test)
- [ ] `tests/test_docs.py` passe ; il **échoue** si un lien interne est cassé (test du test)
- [ ] L'affirmation « on ne teste pas le front » est corrigée (`PRD.md:411`)
- [ ] Les chemins de spikes pointent vers `spikes/` (`PRD.md:225`)
- [ ] Plus aucun décompte de tests en dur dans `PRD.md` **ni** dans `CLAUDE.md` (remplacé par la commande)
- [ ] Suite hors réseau verte (`pytest -m "not network"`)

## 6. Invariants préservés

- La calibration Pernod (`z = −3.81`) reste décrite exactement comme dans le code (ou par renvoi
  au test).
- `PRD.md` §5 (méthode et seuils) n'est **pas** modifié dans son contenu.
- Aucun code applicatif modifié : ce chantier est **documentaire** (+ `tests/test_docs.py`).
- Les PDF de référence ne sont ni commités ni supprimés.

## 7. Jalons

- **J1** — `docs/README.md` (index unique) + règle « zéro chiffre recopiable » dans `CLAUDE.md`.
- **J2** — Fusion des deux PRD ; purge du doublon de roadmap `CHANTIERS.md` §3.
- **J3** — Rapatriement `docs/specs/` + `docs/references/README.md`.
- **J4** — `docs/decisions/` (ADR, amorcé par Q4 portefeuille).
- **J5** — `tests/test_docs.py` (liens internes) + corrections factuelles résiduelles.
- **J6** — Garde-fou de cohérence du dossier `chantiers/` (liens, statuts index ↔ fiche,
  absence de chiffre figé) — exigence 4.11.

## 8. Note de reprise

_(vide — chantier non commencé)_

> **Historique.** Cette fiche était initialement « Nettoyage doc (PRD obsolète) », limitée à
> trois corrections ponctuelles (🔵 Q3, 5 min). Le diagnostic ci-dessus montre que le problème
> est **structurel** (huit sources, deux PRD, chiffres recopiés) : la fiche a été réécrite en
> périmètre « Consolidation documentaire » et relevée en 🟡 Q2. Les trois corrections d'origine
> deviennent l'exigence 4.9.
