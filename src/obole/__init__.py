"""Obole — outil perso d'analyse boursière long terme (droite de régression).

`__version__` est la **source unique** de la version du paquet : `pyproject.toml`
la lit en dynamique (`[tool.setuptools.dynamic]`), donc le packaging et la
surface MCP (`mcp/server.py`) ne peuvent pas diverger.
"""

from __future__ import annotations

__version__ = "0.1.0"
