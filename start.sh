#!/usr/bin/env bash
# Obole — lancement idempotent : crée le venv si absent, installe les deps, sert.
# Usage : ./start.sh   ->   http://127.0.0.1:8000
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
PY_MIN_MINOR=11  # pyproject : requires-python >=3.11

# Un interpréteur convient s'il est en 3.>=11.
py_ok() {
    "$1" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, '"$PY_MIN_MINOR"') else 1)' \
        >/dev/null 2>&1
}

# 1. Trouver un Python ≥3.11 (les pins numpy/pandas n'ont pas de wheel cp314 :
#    3.11 → 3.13 sont les seules versions supportées).
if [ ! -d "$VENV" ]; then
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3; do
        if command -v "$candidate" >/dev/null 2>&1 && py_ok "$candidate"; then
            PYTHON="$candidate"
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        echo "Erreur : aucun Python >=3.11 trouvé (requis par pyproject.toml)." >&2
        echo "Installe Python 3.11+ (ex. python3.13) puis relance ./start.sh." >&2
        exit 1
    fi
    echo "Création du venv avec $PYTHON…"
    "$PYTHON" -m venv "$VENV"
fi

# 2. Vérifier la version du venv existant.
if [ -d "$VENV" ]; then
    if ! py_ok "$VENV/bin/python"; then
        echo "Erreur : le venv existe mais son Python est <3.$PY_MIN_MINOR." >&2
        echo "Supprime .venv/ et relance ./start.sh pour en créer un avec un Python récent." >&2
        exit 1
    fi
fi

# 3. Installer / synchroniser les deps (rapide si déjà satisfaites).
#    Un venv créé par `uv venv` n'a PAS de pip : on préfère uv s'il est là,
#    sinon on retombe sur le pip du venv (créé par `python -m venv`).
echo "Installation des dépendances…"
if command -v uv >/dev/null 2>&1; then
    uv pip install -q --python "$VENV/bin/python" -e ".[dev]"
elif "$VENV/bin/python" -m pip --version >/dev/null 2>&1; then
    "$VENV/bin/python" -m pip install -q --upgrade pip
    "$VENV/bin/python" -m pip install -q -e ".[dev]"
else
    echo "Erreur : ni uv ni pip disponibles pour installer les dépendances." >&2
    echo "Installe uv (https://docs.astral.sh/uv/) puis relance ./start.sh." >&2
    exit 1
fi

# 4. Lancer.
echo "Démarrage : http://127.0.0.1:8000"
exec "$VENV/bin/python" run.py
