#!/usr/bin/env python3
"""
Cek kesehatan IP terhadap DataDome GitHub.

Jalankan ini SEBELUM bikin akun, biar tahu IP kamu sudah kena flag atau belum.
Tidak membuat akun apa pun — cuma buka halaman signup dan cek hasilnya.

    python3 cek_ip.py                 # pakai IP saat ini (tanpa proxy)
    python3 cek_ip.py --proxy URL     # pakai proxy tertentu
    python3 cek_ip.py --pool          # coba semua proxy di proxies.txt
"""
import argparse
import json
import random
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from camoufox.sync_api import Camoufox


def ip_info(proxies=None):
    """Ambil info IP + reputasi dasar via ip-api.com."""
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(proxies) if proxies else urllib.request.BaseHandler()
        )
        url = "http://ip-api.com/json?fields=query,country,city,isp,org,as,proxy,hosting,mobile"
        with opener.open(url, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)[:120]}


def check_github(proxy_cfg=None, headless=True):
    """Buka github.com/signup, laporkan apakah kena DataDome."""
    opts = {
        "humanize": True,
        "os": random.choice(["windows", "macos"]),
        "enable_cache": True,
    }
    if proxy_cfg:
        opts["proxy"] = proxy_cfg
        opts["geoip"] = True

    try:
        with Camoufox(headless=headless, **opts) as browser:
            page = browser.new_page()

            # warm-up seperti manusia
            page.goto("https://github.com/", timeout=60000)
            time.sleep(random.uniform(2.5, 4.5))
            for _ in range(random.randint(2, 4)):
                page.mouse.move(random.randint(100, 1000), random.randint(100, 600))
                page.mouse.wheel(0, random.randint(250, 700))
                time.sleep(random.uniform(0.6, 1.5))

            page.goto("https://github.com/signup", timeout=60000)
            time.sleep(4)

            src = page.content().lower()
            body = ""
            try:
                body = page.inner_text("body").lower()
            except Exception:
                pass

            datadome = "captcha-delivery" in src
            restricted = "temporarily restricted" in body or "unusual activity" in body
            has_form = bool(page.query_selector('input#email, input[name="user[email]"]'))

            if has_form and not datadome:
                return "BERSIH", "form signup muncul — IP aman"
            if datadome or restricted:
                return "DIBLOKIR", "DataDome menahan akses (Access is temporarily restricted)"
            return "TIDAK JELAS", f"tidak ada form & tidak ada DataDome | title={page.title()!r}"
    except Exception as e:
        return "ERROR", str(e)[:150]


def parse_proxy_line(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(":")
    if len(parts) >= 4:
        host, port, user = parts[0], parts[1], parts[2]
        pw = ":".join(parts[3:])
        return {"server": f"http://{host}:{port}", "username": user, "password": pw}
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    if "://" in line:
        return {"server": line}
    return None


def main():
    ap = argparse.ArgumentParser(description="Cek kesehatan IP terhadap DataDome GitHub")
    ap.add_argument("--proxy", help="Proxy tunggal (host:port:user:pass atau URL)")
    ap.add_argument("--pool", action="store_true", help="Coba semua proxy di proxies.txt")
    ap.add_argument("--show", action="store_true", help="Tampilkan browser (tidak headless)")
    args = ap.parse_args()

    headless = not args.show

    targets = []
    if args.pool:
        f = Path(__file__).parent / "proxies.txt"
        if not f.exists():
            print("proxies.txt tidak ada")
            sys.exit(1)
        for line in f.read_text().splitlines():
            cfg = parse_proxy_line(line)
            if cfg:
                targets.append(cfg)
        if not targets:
            print("proxies.txt kosong")
            sys.exit(1)
    elif args.proxy:
        cfg = parse_proxy_line(args.proxy)
        if not cfg:
            print("format proxy tidak dikenali")
            sys.exit(1)
        targets.append(cfg)
    else:
        targets.append(None)  # tanpa proxy

    print()
    print("=" * 62)
    print("  Cek Kesehatan IP — DataDome GitHub")
    print("=" * 62)

    bersih = []

    for idx, cfg in enumerate(targets, 1):
        label = "IP saat ini (tanpa proxy)" if cfg is None else cfg["server"].split("://")[-1]
        print(f"\n[{idx}/{len(targets)}] {label}")

        pxy = None
        if cfg:
            server = cfg["server"].split("://")[-1]
            if cfg.get("username"):
                pxy = {"http": f"http://{cfg['username']}:{cfg['password']}@{server}",
                       "https": f"http://{cfg['username']}:{cfg['password']}@{server}"}
            else:
                pxy = {"http": f"http://{server}", "https": f"http://{server}"}

        info = ip_info(pxy)
        if "error" in info:
            print(f"   IP        : tidak terdeteksi ({info['error']})")
        else:
            tipe = []
            if info.get("hosting"):
                tipe.append("datacenter")
            if info.get("mobile"):
                tipe.append("mobile")
            if info.get("proxy"):
                tipe.append("proxy/vpn terdeteksi")
            if not tipe:
                tipe.append("residential")
            print(f"   IP        : {info.get('query')} ({info.get('country')}, {info.get('city')})")
            print(f"   ISP       : {info.get('isp')}")
            print(f"   Tipe      : {', '.join(tipe)}")

        status, detail = check_github(cfg, headless=headless)
        icon = {"BERSIH": "✅", "DIBLOKIR": "❌", "TIDAK JELAS": "⚠️ ", "ERROR": "⚠️ "}[status]
        print(f"   GitHub    : {icon} {status} — {detail}")

        if status == "BERSIH":
            bersih.append(label)

        if idx < len(targets):
            time.sleep(random.uniform(4, 8))

    print()
    print("=" * 62)
    if bersih:
        print(f"  Bisa dipakai ({len(bersih)}):")
        for b in bersih:
            print(f"    ✅ {b}")
        print()
        print("  Jalankan pembuatan akun dengan salah satu di atas.")
    else:
        print("  Tidak ada yang lolos DataDome.")
        print()
        print("  Yang bisa dicoba:")
        print("    1. Restart router (IP rumah biasanya dinamis)")
        print("    2. Tethering dari HP — IP seluler biasanya paling bersih")
        print("    3. Tunggu 2-6 jam, DataDome punya masa cooldown per IP")
        print("    4. Kurangi jumlah akun per sesi (1-2 saja), naikkan jeda")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
