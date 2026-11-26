"""The staging offline guard blocks outbound network calls and still allows loopback (no real network is used)."""
import socket
import urllib.request

import pytest

from global_markets import offline_guard as og


@pytest.fixture
def guarded():
    og.install()
    try:
        yield
    finally:
        og.uninstall()


def test_blocks_outbound_connect_and_dns(guarded):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(og.NetworkBlocked):
        s.connect(("93.184.216.34", 443))
    assert s.connect_ex.__func__ is not None
    with pytest.raises(og.NetworkBlocked):
        s.connect_ex(("93.184.216.34", 443))
    s.close()
    with pytest.raises(og.NetworkBlocked):
        socket.getaddrinfo("example.org", 443)
    with pytest.raises(Exception) as e:
        urllib.request.urlopen("https://example.org/", timeout=2)
    assert "offline mode" in str(e.value)


def test_loopback_still_works(guarded):
    srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
    c = socket.socket(); c.connect(("127.0.0.1", srv.getsockname()[1])); c.close(); srv.close()
    assert socket.getaddrinfo("localhost", 80)


def test_uninstall_restores_and_production_does_not_import_it():
    og.install(); og.uninstall()
    assert socket.socket.connect is og._orig_connect and not og.installed()
    from pathlib import Path
    src = "".join(p.read_text() for p in (Path(og.__file__).parent.parent).glob("global_*.py"))
    assert "offline_guard" not in src
