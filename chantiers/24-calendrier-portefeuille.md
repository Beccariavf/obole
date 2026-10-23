# #24 — Calendrier du portefeuille en séances de marché + contexte unique

> **Statut :** fait · **Priorité :** 🔴 Urgent (blocage : graphes faux) · **Impact Pernod :** 🟠
> **Branche :** `fix/portefeuille-calendrier` · **Taille :** ~2 sessions
> **Fiche parente :** [portefeuille/04-performance.md](portefeuille/04-performance.md)

---

## 1. Contexte

**Bug de fuseaux sur l'axe temps du portefeuille.** Les index Yahoo sont *tz-aware* et
**chaque place porte son fuseau** (`Europe/Paris` pour Paris, `UTC` pour une crypto cotée
24/7, `America/New_York` pour Wall Street). Les quatre sites qui construisaient l'axe par
`union` d'index (`services/portfolio.py`, ex-lignes ~264, ~617, ~999, ~1383) comparaient
donc des **instants** : une barre Paris D (00:00+02:00 = D−1 22:00 UTC) ne coïncide avec
aucune barre UTC et produisait **un second point à la même date calendaire**.

Conséquences mesurées sur la base réelle (`cache.sqlite`, 3 comptes, 22 tickers) :

- vue consolidée : **897 points** dont **527 distincts** au lieu de **371** — jusqu'à ~623
  points/an au lieu de ~257 (dents de scie + week-ends de la crypto) ;
- `realized_volatility` de la vue consolidée : **11,12 %** au lieu de **17,9 %** (l'échelle
  √252 appliquée sur un axe gonflé sous-estimait la volatilité) ;
- cours européens **décalés d'un jour** (le Close du jour affiché la veille).

**Duplication.** `summary()`, `_risk_context()` et `_performance_context()` réimplémentaient
la même orchestration (cours, axe, TWR, lignes) : c'est cette triplication qui a laissé le bug
se propager graphe par graphe.

**Lenteur de l'onglet Performance.** Les tickers sans comptes (BTC-EUR, CEMQ.DE, PRAB.DE,
GOLD.PA) renvoyaient 404 à chaque ouverture ; de plus `_IDENTITY_FIELDS` exigeait
`industry`/`website`/`address`, champs qu'un ETF/crypto n'a pas par nature — son identité
était donc **périmée à vie** et `info` + `calendar` étaient rejoués (2 tentatives) à chaque
affichage.

**Courses front.** Seule la Performance portait un jeton anti-course (`_pfPerfSeq`) ; un
changement rapide de compte/étiquette/période pouvait laisser une réponse périmée écraser
l'écran du Résumé ou du Risque.

## 2. Objectif

Un **axe temps unique = séances de marché**, en jours calendaires naïfs, partagé par toutes
les sections du portefeuille ; une **orchestration unique** (`_portfolio_context`) ; l'onglet
Performance sans aucune requête réseau en cache chaud ; et des **jetons anti-course** sur les
trois sections.

## 3. Non-objectifs

- **Cache d'analyse par ticker** (les 250 ms de l'onglet Performance) : reporté au chantier
  #25. Le coût résiduel est du CPU pur (`_analyze_lines` ≈ 1,1 s), pas du réseau ; un cache
  exigerait 4 sources d'invalidation (prix, comptes manuels, réglages MM, valorisation) pour
  un écran ouvert occasionnellement.
- Aucune modification de la **formule** TWR / drawdown / métriques.
- Aucun changement visuel des tracés : seule la **série reçue** change.

## 4. Exigences

- 4.1 Un helper unique `_trading_index(prices, bench, start, field)` (+ `_session_days`,
  `_align`) normalise chaque série en jours calendaires naïfs et construit l'axe = séances du
  benchmark ∪ séances des titres (hors actifs 24/7), dédoublonné, trié, sans week-end.
- 4.2 Les quatre sites d'union passent par ce helper.
- 4.3 `_portfolio_context(account_id, benchmark, period, tag)` est la **seule** orchestration,
  consommée par `summary`, `risk`/`correlation_test` et `performance`.
- 4.4 Cache négatif `fundamentals_missing` (`config.TTL_MISSING_FUNDAMENTALS`) pour les titres
  sans comptes.
- 4.5 `_IDENTITY_FIELDS` n'exige plus aucun champ d'entreprise (seul `model_version` périme).
- 4.6 Jetons anti-course `_pfSummarySeq` et `_pfRiskSeq`, sur le modèle de `_pfPerfSeq`.
- 4.7 Le payload HTTP des trois routes reste **identique** (aucun changement de contrat).

## 5. Critères d'acceptation

- [x] **C1a** helper unique + 4 sites migrés (`grep` : plus d'`union` ni de `reindex(idx)`).
- [x] **C1b** axe consolidé : `len(dates)==len(set(dates))`, monotonie, 0 week-end,
  257,6 pts/an (avant 623), `RI.PA` jour J → cours J (0 décalage / 371 dates) ; vol consolidée
  **17,9 %** ∈ [15 %, 21 %] et > 15 (avant 11,12 %).
- [x] **C1c** non-régression PEA (compte 2, `max`) : 371 points, dates identiques, **diff max
  courbe TWR = 0.0**, vol 19,09 % inchangée.
- [x] **C1d** test jouet `[CW8.PA, BTC-EUR]` : pas de doublon, monotonie, pas de week-end,
  `len(dates)` = nombre de séances distinctes attendues.
- [x] **C2a** cache négatif comptes en place.
- [x] **C2b** `_IDENTITY_FIELDS = ()` ; test : 2ᵉ appel = 0 requête réseau sur un ETF.
- [x] **C2c** `performance()` 2× sur la base réelle : **0 requête HTTP** au 2ᵉ appel
  (mesuré : 1,0 s → 0,98 s ; les 250 ms sont hors périmètre, cf. non-objectifs).
- [x] **C3** `_portfolio_context` unique ; **payloads identiques** (18 combinaisons
  compte × période, 0 mismatch) ; tests automatisés du contexte partagé.
  `correlation_test` reste inchangé **fonctionnellement** : son candidat passe par
  `_align` (l'axe du contexte est naïf, un `reindex` direct ne matcherait rien) ;
  test de régression tz-aware ajouté (`test_tz_aware_series_are_aligned_not_dropped`).
- [x] **C4** `_pfSummarySeq`/`_pfRiskSeq` + test Vitest (réponses inversées → la dernière gagne).
- [x] **C5** `ruff`, `mypy`, `pytest -m "not network"`, `npm test` verts.
- [ ] **C5bis** calibration réseau Pernod (`z = −3.81`) — à rejouer (`pytest -m network`).

## 6. Invariants préservés

- Formule TWR, drawdown et métriques **inchangées** (diff courbe PEA = 0.0).
- Calibration Pernod (`z = −3.81`, ±0.15) : indépendante du portefeuille, à rejouer par garde-fou.
- Aucun nouveau seuil littéral : `TTL_MISSING_FUNDAMENTALS` vit dans `config.py`.
- Contrats HTTP identiques (aucun changement de payload).

## 7. Jalons

- **J1** — Helper `_trading_index` + `_session_days` + `_align`, 4 sites migrés (C1a–C1d).
- **J2** — Cache négatif comptes + fraîcheur d'identité (C2a–C2c).
- **J3** — `_portfolio_context` unique (C3).
- **J4** — Jetons anti-course front (C4).
- **J5** — Vérification outillée (C5).

## 8. Note de reprise

Chantier livré sur `fix/portefeuille-calendrier`. Reste à faire avant merge : rejouer le test
réseau (`pytest -m network`, Pernod `z = −3.81`) — vert à la clôture.

**Revue de code (9 findings)** : 8 résolus, 1 écarté hors périmètre.
- `correlation_test` tz-aware (via `_align`) + test de régression.
- Pas de cache négatif sur ÉCHEC réseau : `fetch_identity` ne mémorise rien si `info` est
  vide ; `fundamentals_missing` n'est posé que si Yahoo a répondu (3 tests).
- `_FUNDAMENTALS_FIELDS = ()` : `health_rows` est Optional, l'exiger provoquait un re-fetch
  perpétuel.
- `_is_round_the_clock` proportionnel (`PORTFOLIO_ROUND_CLOCK_WEEKEND_RATIO`) + log : une barre
  de week-end parasite ne prive plus une action de ses séances.
- `div` porté par `PortfolioContext` (fin du double `list_dividends` + scoping dans `summary`).
- `backup._purge_derived_cache` purge aussi `fundamentals_missing` (+ tests).
- `ruff format .` appliqué ; commentaires morts nettoyés dans `yahoo.py`.
- Écarté : `loadPortfolioDividends` n'a pas de jeton anti-course (hors exigence 4.6) → à ouvrir
  en chantier séparé.

Le chantier **#25 (cache d'analyse par ticker)** n'est pas ouvert : il porterait les
250 ms de l'onglet Performance, hors du périmètre de celui-ci.
