"""
9Router integration — daftarkan API key GoRouter ke 9Router.
"""
import os
import json
import urllib.request
import urllib.error

from logger import log

ROUTER_URL = os.environ.get("ROUTER_URL", "http://127.0.0.1:20128").rstrip("/")
ROUTER_PASS = os.environ.get("ROUTER_PASS", "")

# Provider node GoRouter di 9Router
NODE_NAME = os.environ.get("ROUTER_NODE_NAME", "gorouter")
NODE_PREFIX = os.environ.get("ROUTER_NODE_PREFIX", "go")
NODE_BASE_URL = os.environ.get("ROUTER_NODE_BASE_URL", "https://gorouter.app/v1")
NODE_API_TYPE = "chat"
NODE_TYPE = "openai-compatible"

DEFAULT_MODEL = os.environ.get("ROUTER_DEFAULT_MODEL", "gpt")


class RouterError(Exception):
    pass


def _request(method, path, body=None, cookie=None, timeout=20):
    url = f"{ROUTER_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    if cookie:
        req.add_header("Cookie", cookie)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "ignore")
            set_cookie = resp.headers.get("set-cookie")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"_raw": raw[:300]}
            return parsed, set_cookie
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "ignore")
        raise RouterError(f"HTTP {e.code} on {method} {path}: {raw[:200]}")
    except urllib.error.URLError as e:
        raise RouterError(f"Tidak bisa konek ke 9Router di {ROUTER_URL} ({e.reason})")


def _login():
    """Login kalau ROUTER_PASS diisi. Kembalikan cookie auth atau None."""
    if not ROUTER_PASS:
        return None
    data, set_cookie = _request("POST", "/api/auth/login", {"password": ROUTER_PASS})
    if not data.get("success"):
        raise RouterError("Login 9Router gagal — cek ROUTER_PASS")
    if set_cookie:
        for part in set_cookie.split(","):
            piece = part.split(";")[0].strip()
            if piece.startswith("auth_token="):
                return piece
    return None


def ensure_provider_node(cookie=None):
    """Cari provider node GoRouter, buat kalau belum ada. Kembalikan id-nya."""
    data, _ = _request("GET", "/api/provider-nodes", cookie=cookie)
    nodes = data.get("nodes", data if isinstance(data, list) else [])

    for n in nodes:
        if n.get("prefix") == NODE_PREFIX or n.get("name") == NODE_NAME:
            log(f"  ├─ [9R] Provider node '{n.get('name')}' ({n.get('prefix')}) sudah ada")
            return n["id"]

    log(f"  ├─ [9R] Membuat provider node '{NODE_NAME}'...")
    created, _ = _request("POST", "/api/provider-nodes", {
        "name": NODE_NAME,
        "prefix": NODE_PREFIX,
        "apiType": NODE_API_TYPE,
        "baseUrl": NODE_BASE_URL,
        "type": NODE_TYPE,
    }, cookie=cookie)

    node_id = created.get("id") or (created.get("node") or {}).get("id")
    if not node_id:
        raise RouterError(f"Gagal membuat provider node: {str(created)[:200]}")
    log(f"  ├─ [9R] Provider node dibuat: {node_id}")
    return node_id


def add_api_key(api_key, name, priority=1, default_model=None, skip_duplicate=True):
    """
    Tambahkan API key GoRouter ke 9Router.
    Kembalikan dict: {"added": bool, "reason": str}
    """
    cookie = _login()
    node_id = ensure_provider_node(cookie)

    if skip_duplicate:
        try:
            data, _ = _request("GET", "/api/providers", cookie=cookie)
            conns = data.get("connections", data if isinstance(data, list) else [])
            for c in conns:
                if c.get("provider") == node_id and c.get("apiKey") == api_key:
                    log("  ├─ [9R] Key sudah terdaftar, dilewati")
                    return {"added": False, "reason": "already exists"}
        except RouterError as e:
            log(f"  ├─ [9R] Cek duplikat gagal: {str(e)[:80]}")

    body = {
        "provider": node_id,
        "name": name,
        "apiKey": api_key,
        "priority": priority,
        "proxyPoolId": None,
        "testStatus": "active",
        "defaultModel": default_model or DEFAULT_MODEL,
    }

    log(f"  ├─ [9R] Import key sebagai '{name}'...")
    res, _ = _request("POST", "/api/providers", body, cookie=cookie)

    if res.get("error"):
        raise RouterError(f"Import gagal: {res['error']}")

    log("  ├─ [9R] ✅ Key masuk ke 9Router")
    return {"added": True, "reason": "imported", "response": res}
