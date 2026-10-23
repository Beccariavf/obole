"""Démarrage de la CLI : bind, port occupé, message de succès — sans réseau.

Un incident réel a montré le piège : `main()` imprimait « Obole prêt sur … »
**avant** `uvicorn.run()`. Sur un port déjà occupé, l'utilisateur voyait un
message de succès suivi d'un `[Errno 48] address already in use` sur stderr — et
croyait le serveur lancé alors qu'il était mort.

Les tests verrouillent les trois propriétés qui empêchent ce mensonge :

1. le message de succès n'apparaît **jamais** sans serveur à l'écoute ;
2. un port occupé produit un diagnostic actionnable (pas l'errno brut) ;
3. le code de sortie est non nul dans ce cas.
"""

from __future__ import annotations

import socket

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
    assert "--port" in err
    # Pas l'errno brut d'uvicorn : c'est ce qui rendait le diagnostic opaque.
    assert "Errno 48" not in err


def test_busy_port_suggests_free_alternative(busy_port, capsys):
    with pytest.raises(SystemExit):
        cli.main(["--port", str(busy_port)])

    err = capsys.readouterr().err
    assert str(busy_port + 1) in err or "8001" in err


def test_free_port_passes_the_check(free_port, monkeypatch):
    """Sur un port libre, la pré-vérification ne bloque pas le démarrage."""
    called = {}

    def fake_serve(host, port):
        called["port"] = port

    monkeypatch.setattr(cli, "_serve", fake_serve)
    cli.main(["--port", str(free_port)])
    assert called["port"] == free_port
