"""Garde-fou de la banque mémoire AIDD.

Le port DSH n'a pas le hook `update_memory.js` du framework : le bloc
`aidd_project_memory` de `CLAUDE.md` et l'index de `memory/README.md` sont
maintenus à la main. Ces tests remplacent le hook — un fichier ajouté sans
câblage fait échouer la suite, au lieu de passer muet.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = ROOT / "CLAUDE.md"
MEMORY_DIR = ROOT / "aidd_docs" / "memory"
MEMORY_README = MEMORY_DIR / "README.md"

_BLOCK = re.compile(
    r"<!-- aidd_project_memory:start -->(.*?)<!-- aidd_project_memory:end -->",
    re.DOTALL,
)
_FILES_BLOCK = re.compile(r"<!-- files:start -->(.*?)<!-- files:end -->", re.DOTALL)
_MD_LINK = re.compile(r"`([^`]+\.md)`")


def _memory_files() -> set[str]:
    """Fichiers de la banque, hors index (le README n'est pas une mémoire)."""
    return {p.name for p in MEMORY_DIR.glob("*.md") if p.name != MEMORY_README.name}


def _listed(block: str, where: str) -> set[str]:
    """Noms de fichiers listés dans un bloc de type index.

    Une ligne = une entrée : on ne retient que le **premier** lien markdown de la
    ligne, pour qu'une description puisse citer un autre fichier sans polluer
    l'index.
    """
    names = set()
    for line in block.splitlines():
        match = _MD_LINK.search(line)
        if match:
            names.add(Path(match.group(1)).name)
    assert names, f"aucun fichier listé dans {where}"
    return names


def test_block_markers_present() -> None:
    """Le bloc de câblage existe une seule fois dans `CLAUDE.md`."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    assert text.count("<!-- aidd_project_memory:start -->") == 1
    assert text.count("<!-- aidd_project_memory:end -->") == 1
    assert _BLOCK.search(text), "bloc `aidd_project_memory` introuvable ou mal fermé"


def test_block_lists_every_memory_file() -> None:
    """Le câblage et le disque décrivent exactement le même ensemble."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    match = _BLOCK.search(text)
    assert match, "bloc `aidd_project_memory` introuvable"

    liste = _listed(match.group(1), "le bloc de CLAUDE.md")
    attendu = _memory_files()
    assert liste == attendu, (
        "le bloc de CLAUDE.md et aidd_docs/memory/ divergent — "
        f"manquants : {sorted(attendu - liste)} ; en trop : {sorted(liste - attendu)}"
    )


def test_memory_readme_index_matches() -> None:
    """L'index de `memory/README.md` suit le disque, comme le bloc."""
    text = MEMORY_README.read_text(encoding="utf-8")
    match = _FILES_BLOCK.search(text)
    assert match, "bloc `<!-- files -->` introuvable dans aidd_docs/memory/README.md"

    liste = _listed(match.group(1), "l'index de memory/README.md")
    attendu = _memory_files()
    assert liste == attendu, (
        "l'index de memory/README.md et le disque divergent — "
        f"manquants : {sorted(attendu - liste)} ; en trop : {sorted(liste - attendu)}"
    )


def test_memory_files_are_filled() -> None:
    """Aucun fichier mémoire n'est un brouillon ou un modèle non rempli."""
    en_defaut: list[str] = []
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name == MEMORY_README.name:
            continue
        text = path.read_text(encoding="utf-8")
        raisons = []
        if not text.startswith("# "):
            raisons.append("pas de titre `# `")
        if len(text.splitlines()) < 8:
            raisons.append("trop court")
        if "TODO" in text:
            raisons.append("contient TODO")
        if "<placeholder" in text:
            raisons.append("contient un placeholder")
        if re.search(r"\{[A-Za-z_][^}]*\}", text):
            raisons.append("contient un gabarit `{…}` non rempli")
        if raisons:
            en_defaut.append(f"{path.name} ({', '.join(raisons)})")

    assert not en_defaut, "fichiers mémoire non remplis : " + ", ".join(en_defaut)
