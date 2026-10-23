"""Démarrage de la CLI : bind, port occupé, message de succès — sans réseau.

Un incident réel a montré le piège : `main()` imprimait « Obole prêt sur … »
**avant** `uvicorn.run()`. Sur un port déjà occupé, l'utilisateur voyait un
message de succès suivi d'un `[Errno 48] address already in use` sur stderr — et
croyait le serveur lancé alors qu'il était mort.

Les tests verrouillent quatre propriétés :

1. le message de succès n'apparaît **jamais** sans serveur à l'écoute ;
2. un port occupé produit un diagnostic actionnable (pas l'errno brut) ;
3. le code de sortie est non nul dans ce cas ;
4. l'arrêt reste **gracieux** (Ctrl+C) : le serveur doit tourner dans le thread
   principal, sinon `uvicorn.Server.capture_signals()` est un no-op.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
import time

import pytest

from obole import __main__ as cli


@pytest.fixture
def busy_port() -> int:
    """Port réellement occupé, libéré en fin de test."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.listen(1)
    yield port
    sock.close()


@pytest.fixture
def free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_port_is_busy_detects_listening_socket(busy_port):
    assert cli.port_is_busy("127.0.0.1", busy_port) is True


def test_port_is_busy_on_free_port(free_port):
    assert cli.port_is_busy("127.0.0.1", free_port) is False


def test_port_is_busy_handles_unresolvable_host():
    """Un hôte invalide est « rien à joindre », pas une exception."""
    assert cli.port_is_busy("hote.invalid", 8000) is False


def test_port_is_busy_handles_ipv6_loopback(free_port):
    """`::1` est un hôte accepté par `_check_bind` : il ne doit pas planter."""
    assert cli.port_is_busy("::1", free_port) is False


def test_busy_port_exits_nonzero_without_success_message(busy_port, capsys):
    """Le cœur de la régression : pas de « prêt » quand le bind va échouer."""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--port", str(busy_port)])

    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "prêt" not in captured.out
    assert "prêt" not in captured.err


def test_busy_port_message_is_actionnable(busy_port, capsys):
    with pytest.raises(SystemExit):
        cli.main(["--port", str(busy_port)])

    err = capsys.readouterr().err
    assert str(busy_port) in err
    # Pas l'errno brut d'uvicorn : c'est ce qui rendait le diagnostic opaque.
    assert "Errno 48" not in err


def test_busy_port_suggests_free_alternative(busy_port, capsys):
    """La commande de repli doit être présente telle quelle, port +1 inclus."""
    with pytest.raises(SystemExit):
        cli.main(["--port", str(busy_port)])

    err = capsys.readouterr().err
    assert f"--port {busy_port + 1}" in err


def test_free_port_passes_the_check(free_port, monkeypatch):
    """Sur un port libre, la pré-vérification ne bloque pas le démarrage."""
    called = {}

    def fake_serve(host, port):
        called["port"] = port

    monkeypatch.setattr(cli, "_serve", fake_serve)
    cli.main(["--port", str(free_port)])
    assert called["port"] == free_port


_GRACEFUL_SCRIPT = textwrap.dedent(
    """
    import sys
    from obole.__main__ import main
    main(["--port", sys.argv[1]])
    """
)


def test_sigint_shuts_down_gracefully(free_port):
    """Ctrl+C doit arrêter proprement — pas de traceback `KeyboardInterrupt`.

    Ce test verrouille le choix d'implémentation : si `_serve` relançait uvicorn
    dans un thread, `capture_signals()` deviendrait un no-op et SIGINT
    remonterait en traceback jusqu'à `thread.join()`.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", _GRACEFUL_SCRIPT, str(free_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=__import__("os").environ | {"PYTHONPATH": "src"},
    )
    try:
        started = time.monotonic()
        seen_ready = False
        while time.monotonic() - started < 25:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            if "prêt" in line:
                seen_ready = True
                break
        assert seen_ready, "le serveur n'a jamais annoncé son démarrage"

        proc.send_signal(__import__("signal").SIGINT)
        out, err = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()

    assert "Traceback" not in err, f"arrêt non gracieux :\n{err}"
    assert "KeyboardInterrupt" not in err
