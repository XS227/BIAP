"""Staging-only network guard: while installed, any socket connection or DNS lookup to a non-loopback address raises.

Used by ``tools/staging_offline_server.py`` so a whole-universe Risk/Performance run reads only the stored data copy and never downloads
filings from external sources. Nothing in the production server imports this module, so production behaviour is unchanged.
"""
from __future__ import annotations

import ipaddress
import socket

_installed = False
_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_getaddrinfo = socket.getaddrinfo


class NetworkBlocked(OSError):
    """Raised instead of opening an outbound connection."""


def _is_local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(str(host).split("%")[0]).is_loopback
    except ValueError:
        return False


def _connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        raise NetworkBlocked(f"offline mode: outbound connection to {address[0]} blocked")
    return _orig_connect(self, address)


def _connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_local(address[0]):
        raise NetworkBlocked(f"offline mode: outbound connection to {address[0]} blocked")
    return _orig_connect_ex(self, address)


def _getaddrinfo(host, *args, **kwargs):
    if not _is_local(host):
        raise NetworkBlocked(f"offline mode: DNS lookup for {host} blocked")
    return _orig_getaddrinfo(host, *args, **kwargs)


def install() -> None:
    global _installed
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex
    socket.getaddrinfo = _getaddrinfo
    _installed = True


def uninstall() -> None:
    global _installed
    socket.socket.connect = _orig_connect
    socket.socket.connect_ex = _orig_connect_ex
    socket.getaddrinfo = _orig_getaddrinfo
    _installed = False


def installed() -> bool:
    return _installed
