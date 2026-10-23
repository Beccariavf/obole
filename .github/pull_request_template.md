## Objet

<!-- Ce que change cette PR, en deux ou trois lignes. -->

Closes #<!-- numéro d'issue, si pertinent -->

## Vérifications

- [ ] `ruff check .` et `ruff format --check .` verts
- [ ] `mypy src/obole/engine src/obole/services src/obole/mcp src/obole/models.py` vert
- [ ] `pytest -m "not network"` vert
- [ ] `pip-audit` sans vulnérabilité connue
- [ ] `cd web-tests && npm test` vert (si le front a bougé)
- [ ] Diff relu (`git diff`) — aucun fichier temporaire, aucun debug oublié
- [ ] Commits signés (`git commit -s`, DCO — cf. `CONTRIBUTING.md`)

## Invariants du projet

- [ ] Si la **formule de régression** a changé : les trois implémentations sont à jour
      (serveur `engine/regression.py`, client `charts.js::drawChart`, client
      `charts.js::computeLive`) et `tests/fixtures/regression_parity.json` a été régénérée
- [ ] Si un **seuil de label** a changé : il vit uniquement dans `config.py` (le front le
      reçoit par `/api/meta`), sinon `web-tests/labels-parity.test.js` casse
- [ ] Si les **moyennes mobiles** sont touchées : précalcul serveur conservé
      (`services/serialize.py`), fenêtres issues de `config.SETTING_DEFS`
- [ ] Les couches respectent `web → api → services → engine → data` (aucune remontée)
- [ ] Aucun secret, token ou payload brut journalisé ou committé

## Impact sur la calibration

<!-- Rayon d'action sur le cœur de la méthode : 🟢 nul (doc, I/O, infra) / 🟠 indirect (refactor,
     front, code qui appelle la régression) / 🔴 direct (la formule elle-même).
     Si 🟠 ou 🔴, `pytest -m network` (garde-fou RI.PA z = −3.81) est obligatoire. -->

## Notes pour la relecture

<!-- Ce sur quoi tu veux un regard particulier, ou les compromis assumés. -->
