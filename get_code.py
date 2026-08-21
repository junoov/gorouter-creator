#!/usr/bin/env python3
"""
Ambil kode verifikasi GitHub (device verification / launch code) dari inbox noov.

Contoh:
    python3 get_code.py 4q4byn7e2@noov.app
    python3 get_code.py lmb62wyvsz          # boleh pakai username GitHub
    python3 get_code.py 4q4byn7e2@noov.app --watch
"""
import argparse
import os
import re
import sys
import time
from email.header import decode_header as _dh
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from noov_email import find_noov_user_id, read_noov_inbox

GITHUB_KEYS = Path(__file__).parent / "github_keys.txt"


def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def decode(s):
    try:
        return "".join(
            p.decode(e or "utf-8", "ignore") if isinstance(p, bytes) else p
            for p, e in _dh(s or "")
        )
    except Exception:
        return s or ""


def resolve_email(target):
    """Terima email, atau username/partial dari github_keys.txt."""
    if "@" in target:
        return target, None

    if not GITHUB_KEYS.exists():
        return None, None

    for ln in GITHUB_KEYS.read_text().splitlines():
        parts = ln.strip().split(":")
        if len(parts) < 3:
            continue
        email, password, username = parts[0], parts[1], parts[2]
        if target.lower() in (username.lower(), email.split("@")[0].lower()):
            return email, password
    return None, None


def find_codes(cookie, user_id):
    """Kembalikan daftar (jenis, kode, subject) dari email GitHub terbaru."""
    out = []
    for msg in read_noov_inbox(cookie, user_id):
        sender = (msg.get("from") or "").lower()
        if "github" not in sender:
            continue

        subject = decode(msg.get("subject"))
        body = msg.get("body") or ""
        blob = f"{subject}\n{body}".lower()

        if "verify your device" in blob or "device verification" in blob:
            kind = "device verification"
        elif "launch code" in blob:
            kind = "launch code (signup)"
        else:
            continue

        m = re.search(r"\b(\d{6,8})\b", body)
        if m:
            out.append((kind, m.group(1), subject))
    return out


def main():
    load_env()

    ap = argparse.ArgumentParser(description="Ambil kode verifikasi GitHub dari inbox noov")
    ap.add_argument("target", help="Email noov atau username GitHub")
    ap.add_argument("--watch", action="store_true", help="Pantau terus sampai kode baru masuk")
    ap.add_argument("--timeout", type=int, default=180, help="Batas waktu --watch (detik)")
    args = ap.parse_args()

    cookie = os.environ.get("NOOV_COOKIE", "")
    if not cookie:
        print("❌ NOOV_COOKIE belum diisi di .env")
        sys.exit(1)

    email, password = resolve_email(args.target)
    if not email:
        print(f"❌ Tidak ketemu akun untuk '{args.target}'")
        print("   Pakai email noov lengkap, atau username yang ada di github_keys.txt")
        sys.exit(1)

    user_id = find_noov_user_id(cookie, email)
    if not user_id:
        print(f"❌ Mailbox '{email}' tidak ada di noov")
        sys.exit(1)

    print(f"\n  📧 {email}")
    if password:
        print(f"  🔑 password GitHub: {password}")
    print(f"  📮 mailbox id: {user_id}\n")

    if not args.watch:
        codes = find_codes(cookie, user_id)
        if not codes:
            print("  (belum ada kode di inbox)")
            print("  Tip: klik 'Continue with GitHub' dulu, lalu jalankan dengan --watch")
            return
        for kind, code, subject in codes:
            print(f"  ➜ {code}   ({kind})")
        return

    print(f"  ⏳ Menunggu kode baru (maks {args.timeout}s)...\n")
    seen = {c for _, c, _ in find_codes(cookie, user_id)}
    t0 = time.time()

    while time.time() - t0 < args.timeout:
        try:
            for kind, code, subject in find_codes(cookie, user_id):
                if code not in seen:
                    print(f"  ✅ KODE BARU: {code}   ({kind})")
                    return
        except Exception as e:
            print(f"  ...error: {str(e)[:70]}")
        time.sleep(5)

    print("  ❌ Tidak ada kode baru sampai batas waktu")


if __name__ == "__main__":
    main()
