"""
Proxy pool — baca proxies.txt, normalisasi format, rotasi per akun.
"""
import os
import random
import time
from pathlib import Path

from logger import log

PROXY_FILE = Path(__file__).parent / os.environ.get("PROXY_FILE", "proxies.txt")

# ip:port -> waktu terakhir dipakai (buat cooldown)
_last_used = {}


def _normalize(raw):
    """
    Ubah berbagai format proxy jadi URL yang dimengerti Camoufox/Playwright.
    Kembalikan (server_url, username, password) atau None kalau tidak valid.
    """
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None

    # Sudah berupa URL: http://user:pass@host:port
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        user = password = None
        if "@" in rest:
            creds, hostport = rest.rsplit("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
            else:
                user = creds
        else:
            hostport = rest
        return f"{scheme}://{hostport}", user, password

    parts = raw.split(":")

    # host:port:user:pass
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        password = ":".join(parts[3:])
        return f"http://{host}:{port}", user, password

    # host:port
    if len(parts) == 2:
        return f"http://{parts[0]}:{parts[1]}", None, None

    return None


def load_proxies(path=None):
    """Baca semua proxy valid dari file."""
    p = Path(path) if path else PROXY_FILE
    if not p.exists():
        return []

    out = []
    for line in p.read_text().splitlines():
        n = _normalize(line)
        if n:
            out.append(n)
    return out


def _key(server):
    return server.split("://", 1)[-1]


def pick_proxy(proxies, cooldown=None, shuffle=True):
    """
    Pilih satu proxy yang paling lama tidak dipakai.
    Kembalikan dict siap dipakai Camoufox: {"server":..., "username":..., "password":...}
    """
    if not proxies:
        return None

    if cooldown is None:
        cooldown = int(os.environ.get("PROXY_COOLDOWN", "600"))

    pool = list(proxies)
    if shuffle:
        random.shuffle(pool)

    now = time.time()

    # utamakan yang belum pernah dipakai / sudah lewat cooldown
    ready = [p for p in pool if now - _last_used.get(_key(p[0]), 0) >= cooldown]
    chosen = ready[0] if ready else min(pool, key=lambda p: _last_used.get(_key(p[0]), 0))

    server, user, password = chosen
    _last_used[_key(server)] = now

    if not ready:
        waited = int(now - _last_used.get(_key(server), now))
        log(f"  ├─ [PROXY] semua proxy masih cooldown, pakai yang terlama ({waited}s)")

    cfg = {"server": server}
    if user:
        cfg["username"] = user
    if password:
        cfg["password"] = password
    return cfg


def describe(cfg):
    """Tampilkan proxy tanpa membocorkan password."""
    if not cfg:
        return "(tidak pakai proxy)"
    host = cfg["server"].split("://", 1)[-1]
    return f"{host} (user: {cfg.get('username', '-')})"
