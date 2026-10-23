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
import socket
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


def port_is_busy(host: str, port: int) -> bool:
    """Un serveur répond-il déjà sur `host:port` ?

    On **essaie** de se connecter plutôt que de tester le bind : un test de bind
    peut échouer pour d'autres raisons (privilèges, interface absente) et donner
    un faux positif. `create_connection` gère IPv4 **et** IPv6 (`::1`,
    `localhost`), contrairement à un socket `AF_INET` en dur.

    Un échec de résolution ou de connexion signifie « rien à joindre » : c'est
    un `False`, jamais une exception (un nom d'hôte invalide ne doit pas
    produire une trace alors que le serveur saurait peut-être démarrer).
    """
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _check_port_free(host: str, port: int) -> None:
    """Échoue tôt et clairement si le port est déjà pris.

    Sans cette garde, uvicorn lève `[Errno 48]` sur stderr **après** que le
    message de succès a été affiché : l'utilisateur croit son serveur lancé.
    """
    if not port_is_busy(host, port):
        return
    alternative = port + 1
    print(
        f"Erreur : le port {port} est déjà utilisé sur {host}.\n"
        f"Un autre serveur y répond probablement (un Obole déjà lancé ?).\n"
        f"Relance avec un autre port :  obole --port {alternative}",
        file=sys.stderr,
    )
    raise SystemExit(1)


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
    _check_port_free(args.host, args.port)
    _serve(args.host, args.port)


def _serve(host: str, port: int) -> None:
    """Démarre uvicorn et n'annonce le succès qu'une fois le bind réussi.

    On sous-classe `uvicorn.Server` et surcharge `startup()` : le message est
    émis **après** le `super().startup()`, donc uniquement si le port a
    réellement été lié. Le serveur tourne ensuite dans le **thread principal**,
    ce qui préserve `capture_signals()` — donc Ctrl+C et SIGTERM restent des
    arrêts gracieux (`INFO: Shutting down`). Lancer `run()` dans un thread
    (première version de ce correctif) rendait `capture_signals()` inopérant et
    laissait un traceback `KeyboardInterrupt` à l'utilisateur.
    """
    import uvicorn

    class _AnnouncingServer(uvicorn.Server):
        """Serveur qui annonce son adresse une fois le socket lié.

        Depuis cette version d'uvicorn, `startup()` est une coroutine : la
        surcharge doit donc être `async` et attendre (`await`) la version
        parente, sinon elle ne s'exécute jamais.
        """

        async def startup(self, sockets=None) -> None:
            await super().startup(sockets=sockets)
            if self.started:
                print(f"  Obole prêt sur http://{host}:{port}", flush=True)

    server = _AnnouncingServer(
        uvicorn.Config("obole.api.app:app", host=host, port=port, reload=False)
    )
    try:
        server.run()
    except KeyboardInterrupt:
        # `capture_signals()` ré-émet le signal après l'arrêt gracieux (pour
        # rendre la main au shell comme le ferait un process interrompu). Sans
        # cette capture, Ctrl+C afficherait un traceback — c'est exactement ce
        # que `uvicorn.run()` masque et ce que `Server.run()` ne masque pas.
        return
    except OSError as exc:
        # Bind impossible pour une raison autre qu'un port occupé (permission,
        # interface absente) : on nomme la cause au lieu d'un échec muet.
        print(f"Erreur : impossible d'écouter sur {host}:{port} ({exc}).", file=sys.stderr)
        raise SystemExit(1) from None

    if not server.started:
        print(
            f"Erreur : le serveur n'a pas démarré sur http://{host}:{port} "
            "(voir le journal ci-dessus).",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
