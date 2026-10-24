"""Garde-fou anti-dérive documentaire.

La documentation du projet recopiait des faits que le code est seul à connaître
(nombre de tests, nombre de routes, liste des modules du front, URL du dépôt).
Ces chiffres se désynchronisent à chaque session et finissent faux — c'est
exactement ce que le chantier #10 « consolidation documentaire » décrit.

Ce module verrouille les valeurs **vérifiables** là où elles vivent désormais
(`aidd_docs/memory/`) :

1. le dépôt distant annoncé == le remote `origin` réel (ssh **ou** https) ;
2. le nombre de décorateurs de route annoncé == le comptage dans `api/app.py` ;
3. la liste des modules du front annoncée == le contenu de `src/obole/web/` ;
4. aucun décompte de tests figé en dur (il dérive à chaque session) ;
5. aucune référence git morte (SHA, ou merge affirmé quand il n'y en a aucun).

Un écart **fait échouer** le test : pas d'avertissement silencieux.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
APP_PY = ROOT / "src" / "obole" / "api" / "app.py"
WEB_DIR = ROOT / "src" / "obole" / "web"
MEMORY_DIR = ROOT / "aidd_docs" / "memory"
VCS_MD = MEMORY_DIR / "vcs.md"
API_MD = MEMORY_DIR / "api.md"
CODEBASE_MAP = MEMORY_DIR / "codebase-map.md"


def _git(*args: str) -> str:
    """Exécute git dans le dépôt et renvoie sa sortie (vide si git échoue)."""
    result = subprocess.run(  # noqa: S603 - commande fixe, sans entrée utilisateur
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""


def _repo_slug(url: str) -> str:
    """Réduit une URL de dépôt à `<owner>/<repo>`.

    La CI (`actions/checkout`) pose un remote **https sans `.git`** là où le
    poste de développement utilise un remote **ssh**. Comparer les chaînes brutes
    ferait échouer le test sur GitHub Actions : on ne compare donc que l'identité
    du dépôt.
    """
    url = url.strip().rstrip("/")
    match = re.search(r"[/:]([^/:]+)/([^/]+?)(?:\.git)?$", url)
    assert match, f"URL de dépôt non reconnue : {url!r}"
    return f"{match.group(1)}/{match.group(2)}"


def _read(path: Path) -> str:
    assert path.is_file(), f"{path.relative_to(ROOT)} est introuvable"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def vcs_text() -> str:
    return _read(VCS_MD)


@pytest.fixture(scope="module")
def api_text() -> str:
    return _read(API_MD)


@pytest.fixture(scope="module")
def codebase_map_text() -> str:
    return _read(CODEBASE_MAP)


class TestRemoteUrl:
    """Le dépôt distant documenté doit être le vrai."""

    def test_documented_remote_matches_git(self, vcs_text: str) -> None:
        documented = re.search(r"origin`?\s*=\s*`([^`]+)`", vcs_text)
        assert documented, "vcs.md doit documenter l'URL de `origin` entre backticks"

        remote = _git("remote", "get-url", "origin").strip()
        if not remote:
            pytest.skip("aucun remote `origin` (copie d'archive ou CI sans fetch)")

        assert _repo_slug(documented.group(1)) == _repo_slug(remote), (
            f"vcs.md documente {documented.group(1)!r}, " f"or `origin` pointe sur {remote!r}"
        )


class TestApiRouteCount:
    """Le nombre de routes documenté doit refléter `api/app.py`."""

    def test_documented_route_count_matches_code(self, api_text: str) -> None:
        documented = re.search(r"expose ~(\d+) routes", api_text)
        assert documented, "api.md doit annoncer le nombre de routes de `api/app.py`"

        source = APP_PY.read_text(encoding="utf-8")
        actual = len(re.findall(r"^@app\.(?:get|post|put|delete|patch)", source, re.M))
        # La documentation arrondit (`~`), mais l'écart toléré est borné : au-delà
        # de 5 routes, l'arrondi ne peut plus expliquer la différence.
        assert (
            abs(int(documented.group(1)) - actual) <= 5
        ), f"api.md annonce ~{documented.group(1)} routes, `api/app.py` en expose {actual}"


class TestWebModuleList:
    """Chaque module du front doit être cité dans `codebase-map.md`, et réciproquement."""

    def test_every_web_module_is_documented(self, codebase_map_text: str) -> None:
        actual = {p.name for p in WEB_DIR.glob("*.js")}
        assert actual, "aucun module trouvé dans `src/obole/web/`"

        missing = sorted(name for name in actual if f"`{name}`" not in codebase_map_text)
        assert not missing, (
            "modules du front absents de codebase-map.md : "
            + ", ".join(missing)
            + " — mettre à jour la section §Front"
        )

    def test_documented_modules_all_exist(self, codebase_map_text: str) -> None:
        """Aucun module fantôme : un nom cité dans §Front doit exister sur le disque.

        Le périmètre est la section `## Front` de `codebase-map.md`, bornée par le
        titre suivant. Si l'organisation du document change au point de rendre la
        section indétectable, le test échoue plutôt que de se taire.
        """
        parts = codebase_map_text.split("## Front", 1)
        assert len(parts) == 2, "section `## Front` de codebase-map.md introuvable"
        section = parts[1].split("\n## ", 1)[0]
        assert section.strip(), "section `## Front` de codebase-map.md vide"

        cited = set(re.findall(r"`([a-z0-9-]+\.js)`", section))
        assert cited, "aucun module cité dans la section `## Front` — test vide"

        ghost = sorted(name for name in cited if not (WEB_DIR / name).is_file())
        assert not ghost, "codebase-map.md cite des modules du front inexistants : " + ", ".join(
            ghost
        )


class TestNoFrozenCounts:
    """Aucun décompte que le code est seul à connaître ne doit être figé en prose."""

    def test_no_hardcoded_test_count(self) -> None:
        # Forme historique fautive : « les tests non-network sont **732** au total ».
        pattern = re.compile(r"tests?\s+non-?network\s+sont\s+\*\*\d+\*\*", re.I)
        offenders = [
            str(path.relative_to(ROOT))
            for path in DOC_FILES
            if path.is_file() and pattern.search(path.read_text(encoding="utf-8"))
        ]
        assert not offenders, (
            "un document fige un décompte de tests : il dérive à chaque session. "
            'Renvoyer à la commande `pytest -m "not network" --collect-only -q` '
            f"({', '.join(offenders)})."
        )

    def test_no_frozen_history_facts(self) -> None:
        """Ne pas figer de fait d'historique git (nombre de commits, merges).

        Le nombre de commits change à chaque commit : l'écrire en prose recrée la
        dérive que ce module combat. Formuler l'état (« historique aplati, aucun
        merge »), pas la mesure.
        """
        pattern = re.compile(r"\b(\d+)\s+commits?\b", re.I)
        allowed = {ROOT / "CONTRIBUTING.md"}  # aucune dérogation attendue aujourd'hui
        offenders = []
        for path in DOC_FILES:
            if not path.is_file() or path in allowed:
                continue
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                offenders.append(f"{path.relative_to(ROOT)}: « {match.group(0)} »")
        assert not offenders, (
            "décompte de commits figé dans la documentation (il change à chaque commit) : "
            + ", ".join(offenders)
            + " — décrire l'état, pas la mesure."
        )


#: Documents qui décrivent l'état des chantiers, de la méthode et de l'historique.
DOC_FILES = [
    ROOT / "CHANTIERS.md",
    ROOT / "CLAUDE.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "PRD.md",
    ROOT / "README.md",
    *sorted((ROOT / "chantiers").rglob("*.md")),
    *sorted(MEMORY_DIR.rglob("*.md")),
]

#: Un SHA collé dans un nom de branche (`feat/abc1234`) échappe au motif des
#: backticks ; ce second motif, appliqué au texte joint, le rattrape.
_SHA_ANYWHERE = re.compile(r"(?<![0-9a-f])[0-9a-f]{7,40}(?![0-9a-f])")
_SHA_ESCAPE = re.compile(r"`(test-data|dirty|decade|facade|defaced|acceded)`", re.I)


class TestNoDeadGitReferences:
    """Aucune référence git morte dans la documentation.

    L'historique de ce dépôt a été aplati : ni les branches de travail ni les
    SHAs de commit ne sont consultables. Citer un SHA crée une référence morte
    au premier aplatissement (c'est exactement ce qui s'était produit : 6 SHA
    fantômes).

    Limite assumée : les chaînes hexadécimales d'au moins 7 caractères sont
    détectées, entre backticks (`abc1234`) comme en texte libre. Un SHA tronqué
    à 6 caractères passe — le seuil est le compromis qui évite de confondre un
    mot de 6 lettres toutes en `a`-`f` avec un commit.
    """

    def test_no_commit_sha_in_docs(self) -> None:
        offenders = []
        for path in DOC_FILES:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            cleaned = _SHA_ESCAPE.sub("", text)
            for lineno, line in enumerate(cleaned.splitlines(), 1):
                if _SHA_ANYWHERE.search(line):
                    offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
        assert not offenders, (
            "SHA de commit cité dans la documentation (référence morte après un "
            "aplatissement) : " + ", ".join(offenders) + " — décrire le jalon, pas le commit."
        )

    def test_no_merge_claim_without_merge(self) -> None:
        """Ne pas affirmer un merge `--no-ff` quand l'historique n'en contient aucun.

        Les documents de méthode (`CLAUDE.md`, `CONTRIBUTING.md`, `CHANTIERS.md`,
        `PRD.md`, `memory/vcs.md`) énoncent la **règle** ; les fiches de chantier
        décrivent du **passé**. Ces dernières ne doivent donc pas affirmer avoir
        mergé en `--no-ff`. Le motif porte sur le **texte joint** : une
        revendication coupée sur deux lignes (`commit + merge\\n`--no-ff``) doit
        être vue.
        """
        if not _git("rev-parse", "--git-dir").strip():
            pytest.skip("dépôt git absent — impossible de statuer sur les merges")
        if _git("log", "--merges", "--oneline").strip():
            pytest.skip("l'historique contient des merges : la règle s'applique")

        claim = re.compile(r"merge\w*\s*`?\s*--no-ff", re.I)
        conventions = {
            ROOT / "CLAUDE.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "CHANTIERS.md",
            ROOT / "PRD.md",
            VCS_MD,
        }
        offenders = []
        for path in DOC_FILES:
            if not path.is_file() or path in conventions:
                continue
            text = path.read_text(encoding="utf-8")
            if claim.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        assert not offenders, (
            "ces fiches affirment un merge `--no-ff` alors que l'historique n'en contient "
            "aucun : " + ", ".join(offenders)
        )
