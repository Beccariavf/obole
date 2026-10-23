"""Point d'entrée console de l'application Obole.

`pipx install` (ou `pip install`) expose la commande `obole`, qui démarre le
serveur local sur `127.0.0.1`. Aucune configuration n'est requise : la base de
cache est créée au premier appel.

Sécurité : le serveur refuse par défaut un bind non-loopback. Obole est un outil
mono-poste **sans authentification** ; l'exposer sur un réseau le rendrait
accessible à quiconque sans mot de passe. Le dépassement est explicite
(`--host 0.0.0.0` ou `OBOLE_ALLOW_REMOTE=1`), jamais implicite.
"""

from __future__ import annotations

import argparse
import os
import sys

LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="obole",
        description="Analyse boursière long terme — serveur local (http://127.0.0.1:8000).",
    )
    parser.add_argument(
        "--host",
        default=LOOPBACK_HOST,
        help=f"adresse d'écoute (défaut {LOOPBACK_HOST} ; non-loopback refusé sans "
        "OBOLE_ALLOW_REMOTE=1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"port d'écoute (défaut {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--mcp",
        action="store_true",
        help="démarre la surface MCP (transport stdio) au lieu du serveur web",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="avec --mcp : n'expose que les outils de lecture (les outils d'écriture ne sont pas enregistrés)",
    )
    return parser


def _is_loopback(host: str) -> bool:
    normalized = host.strip().lower()
    return normalized in {"127.0.0.1", "localhost", "::1"} or normalized.startswith("127.")


def _check_bind(host: str) -> None:
    """Refuse un bind non-loopback sans dépassement explicite."""
    if _is_loopback(host):
        return
    if os.environ.get("OBOLE_ALLOW_REMOTE") == "1":
        return
    print(
        f"Erreur : Obole n'a pas d'authentification et refuse d'écouter sur {host!r}.\n"
        "Pour un accès distant, place-le derrière un reverse proxy authentifié, puis\n"
        "relance avec OBOLE_ALLOW_REMOTE=1 si le risque est assumé.",
        file=sys.stderr,
    )
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)

    if args.mcp:
        # Le drapeau est porté par l'environnement : le serveur MCP lit sa
        # configuration au chargement du module, pas à l'appel de `run()`.
        if args.read_only:
            os.environ["OBOLE_MCP_READ_ONLY"] = "1"
        from obole.mcp.server import main as mcp_main

        mcp_main()
        return

    _check_bind(args.host)

    import uvicorn

    print(f"  Obole prêt sur http://{args.host}:{args.port}", flush=True)
    uvicorn.run("obole.api.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
