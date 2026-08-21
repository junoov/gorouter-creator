"""
Bridge proxy lokal: HTTP proxy tanpa auth  ->  upstream SOCKS5/HTTP dengan auth.

Firefox (Camoufox) tidak mendukung SOCKS5 dengan username/password.
Modul ini menjalankan HTTP CONNECT proxy di 127.0.0.1 yang meneruskan
trafik ke proxy upstream, sehingga Camoufox cukup memakai
{"server": "http://127.0.0.1:<port>"} tanpa autentikasi.
"""
import select
import socket
import threading
from urllib.parse import urlparse

try:
    import socks  # PySocks
except ImportError:  # pragma: no cover
    socks = None

from logger import log

_BUF = 65536


def _pipe(a, b):
    """Salin data dua arah sampai salah satu sisi tertutup."""
    socks_pair = [a, b]
    try:
        while True:
            r, _, x = select.select(socks_pair, [], socks_pair, 60)
            if x or not r:
                break
            for s in r:
                other = b if s is a else a
                data = s.recv(_BUF)
                if not data:
                    return
                other.sendall(data)
    except OSError:
        pass
    finally:
        for s in socks_pair:
            try:
                s.close()
            except OSError:
                pass


class ProxyBridge:
    """HTTP proxy lokal tanpa auth yang meneruskan ke upstream proxy ber-auth."""

    def __init__(self, upstream_url, host="127.0.0.1", port=0):
        self.upstream = self._parse(upstream_url)
        self.host = host
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((host, port))
        self._srv.listen(64)
        self.port = self._srv.getsockname()[1]
        self._stop = threading.Event()
        self._thread = None

    @staticmethod
    def _parse(url):
        u = urlparse(url if "://" in url else f"socks5://{url}")
        scheme = (u.scheme or "socks5").lower()
        if scheme in ("socks5", "socks5h"):
            kind = socks.SOCKS5 if socks else None
        elif scheme == "socks4":
            kind = socks.SOCKS4 if socks else None
        elif scheme in ("http", "https"):
            kind = socks.HTTP if socks else None
        else:
            raise ValueError(f"skema proxy tidak didukung: {scheme}")
        return {
            "kind": kind,
            "scheme": scheme,
            "host": u.hostname,
            "port": u.port or (1080 if "socks" in scheme else 8080),
            "user": u.username,
            "password": u.password,
        }

    # --- server loop ---

    def start(self):
        if socks is None:
            raise RuntimeError("PySocks belum terpasang: pip install pysocks")
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        log(f"  ├─ [PROXY] bridge lokal aktif di 127.0.0.1:{self.port} "
            f"→ {self.upstream['scheme']}://{self.upstream['host']}:{self.upstream['port']}")
        return f"http://127.0.0.1:{self.port}"

    def _serve(self):
        while not self._stop.is_set():
            try:
                client, _ = self._srv.accept()
            except OSError:
                break
            threading.Thread(target=self._handle, args=(client,), daemon=True).start()

    def _upstream_socket(self):
        s = socks.socksocket()
        s.set_proxy(
            self.upstream["kind"],
            self.upstream["host"],
            self.upstream["port"],
            rdns=True,
            username=self.upstream["user"],
            password=self.upstream["password"],
        )
        s.settimeout(30)
        return s

    def _handle(self, client):
        try:
            client.settimeout(30)
            head = b""
            while b"\r\n\r\n" not in head:
                chunk = client.recv(_BUF)
                if not chunk:
                    client.close()
                    return
                head += chunk
                if len(head) > 65536:
                    client.close()
                    return

            request_line = head.split(b"\r\n", 1)[0].decode("latin-1")
            parts = request_line.split()
            if len(parts) < 2:
                client.close()
                return
            method, target = parts[0], parts[1]

            if method.upper() == "CONNECT":
                host, _, port = target.partition(":")
                port = int(port or 443)
                remote = self._upstream_socket()
                remote.connect((host, port))
                client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
                remote.settimeout(None)
                client.settimeout(None)
                _pipe(client, remote)
                return

            # Plain HTTP (bukan CONNECT)
            u = urlparse(target)
            host = u.hostname
            port = u.port or 80
            if not host:
                client.close()
                return
            remote = self._upstream_socket()
            remote.connect((host, port))
            remote.sendall(head)
            remote.settimeout(None)
            client.settimeout(None)
            _pipe(client, remote)
        except Exception:
            try:
                client.close()
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        try:
            self._srv.close()
        except OSError:
            pass


def needs_bridge(cfg):
    """True kalau proxy butuh bridge (SOCKS + auth), karena Firefox tidak mendukungnya."""
    if not cfg:
        return False
    server = cfg.get("server", "")
    return server.startswith(("socks5://", "socks5h://", "socks4://")) and bool(cfg.get("username"))


def wrap_for_camoufox(cfg):
    """
    Terima config proxy Camoufox. Kalau SOCKS+auth, jalankan bridge dan
    kembalikan (config_baru, bridge). Kalau tidak, kembalikan apa adanya.
    """
    if not needs_bridge(cfg):
        return cfg, None

    url = cfg["server"]
    scheme, rest = url.split("://", 1)
    user = cfg.get("username")
    password = cfg.get("password", "")
    upstream = f"{scheme}://{user}:{password}@{rest}"

    bridge = ProxyBridge(upstream)
    local = bridge.start()
    return {"server": local}, bridge
