#!/usr/bin/env python3
"""
GoRouter Creator — full workflow:
  1. Create GitHub account (noov temp email + OTP)
  2. Sign up GoRouter via GitHub OAuth
  3. Generate GoRouter API key
"""
import argparse
import os
import random
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from camoufox.sync_api import Camoufox
from logger import log, set_log_file
from noov_email import create_noov_mailbox, find_noov_user_id
from proxy_pool import load_proxies, pick_proxy, describe as describe_proxy
from signup_camoufox import create_github_account_on_page
from router9 import add_api_key as router_add_api_key
from gorouter import signup_gorouter_via_github, generate_gorouter_api_key


LOG_DIR = Path(__file__).parent / "logs"


def setup_logging():
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logfile = LOG_DIR / f"run-{stamp}.log"
    set_log_file(logfile)
    return logfile


def load_env():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def ask(prompt, default=None, cast=str, choices=None):
    """Prompt the user with a default value shown in brackets."""
    while True:
        hint = f" [{default}]" if default is not None else ""
        try:
            raw = input(f"  {prompt}{hint}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if not raw:
            if default is None:
                continue
            return default

        if choices and raw.lower() not in choices:
            print(f"     pilih salah satu: {', '.join(choices)}")
            continue

        try:
            return cast(raw)
        except ValueError:
            print("     input tidak valid")


def ask_yes_no(prompt, default=False):
    d = "y" if default else "n"
    ans = ask(prompt + " (y/n)", default=d, choices=["y", "n", "yes", "no"])
    return str(ans).lower() in ("y", "yes")


def interactive_setup(args, aff_default):
    """Menu setting sebelum run."""
    label = "🟢 GoRouter Creator"

    while True:
        print()
        print("  " + "=" * 52)
        print(f"  {label} — Setting")
        print("  " + "=" * 52)
        print(f"   1) Jumlah akun        : {args.count}")
        print(f"   2) Kode referral      : {aff_default or '(kosong)'}")
        print(f"   3) Mode browser       : {'headless (disembunyikan)' if args.headless else 'tampil di layar'}")
        print(f"   4) Import ke 9Router  : {'ya' if args.router else 'tidak'}")
        src_txt = "akun GitHub lama" if args.use_existing else "buat GitHub baru"
        if args.use_existing and args.line:
            src_txt += f" (baris {args.line})"
        print(f"   5) Sumber akun        : {src_txt}")
        if args.proxy:
            pstat = f"manual ({args.proxy})"
        elif args.proxy_pool:
            pstat = "pool (proxies.txt)"
        else:
            pstat = "tidak pakai"
        print(f"   6) Proxy              : {pstat}")
        print("  " + "-" * 52)
        print("   [enter] mulai   |   nomor = ubah   |   q = keluar")

        pick = ask("Pilih", default="enter")
        pick = str(pick).strip().lower()

        if pick in ("enter", "", "start", "mulai", "go"):
            print()
            return args, aff_default

        if pick in ("q", "quit", "exit", "keluar"):
            print("\n  Dibatalkan.")
            sys.exit(0)

        if pick == "1":
            args.count = max(1, ask("Jumlah akun", default=args.count, cast=int))

        elif pick == "2":
            v = ask("Kode referral (- untuk kosongkan)", default=aff_default or "-")
            aff_default = None if str(v).strip() in ("", "-") else str(v).strip()

        elif pick == "3":
            print("     1. tampil di layar (non-headless)")
            print("     2. headless (disembunyikan)")
            m = ask("Mode browser", default="2" if args.headless else "1", choices=["1", "2"])
            args.headless = str(m).strip() == "2"

        elif pick == "4":
            args.router = ask_yes_no("Import API key ke 9Router?", default=bool(args.router))

        elif pick == "5":
            print("     1. buat akun GitHub baru")
            print("     2. pakai akun GitHub lama (github_keys.txt)")
            m = ask("Sumber akun", default="2" if args.use_existing else "1", choices=["1", "2"])
            args.use_existing = str(m).strip() == "2"
            if args.use_existing:
                n = ask("Nomor baris (0 = otomatis dari belakang)", default=args.line or 0, cast=int)
                args.line = n or None
            else:
                args.line = None

        elif pick == "6":
            print("     1. tidak pakai proxy")
            print("     2. proxy pool (proxies.txt, rotasi per akun)")
            print("     3. satu proxy manual")
            cur = "3" if args.proxy else ("2" if args.proxy_pool else "1")
            m = str(ask("Mode proxy", default=cur, choices=["1", "2", "3"])).strip()
            if m == "1":
                args.proxy = None
                args.proxy_pool = False
            elif m == "2":
                args.proxy = None
                args.proxy_pool = True
            else:
                v = ask("Proxy (host:port:user:pass atau http://user:pass@host:port)",
                        default=args.proxy or "-")
                args.proxy = None if str(v).strip() in ("", "-") else str(v).strip()
                args.proxy_pool = False

        else:
            print("     pilihan tidak dikenal")


def main():
    load_env()
    logfile = setup_logging()

    parser = argparse.ArgumentParser(description="GoRouter Creator (GitHub + GoRouter + API key)")
    parser.add_argument("--count", type=int, default=None,
                        help="Jumlah akun (override COUNT di .env)")
    parser.add_argument("--headless", action="store_true", default=None,
                        help="Run headless (overrides HEADLESS in .env)")
    parser.add_argument("--no-headless", dest="headless", action="store_false",
                        help="Force visible browser (overrides HEADLESS in .env)")
    parser.add_argument("--proxy", type=str, help="Satu proxy manual (mis. http://user:pass@ip:port)")
    parser.add_argument("--proxy-file", type=str, default=None,
                        help="File daftar proxy (default: proxies.txt)")
    parser.add_argument("--no-proxy-pool", dest="proxy_pool", action="store_false", default=None,
                        help="Jangan pakai proxy pool")
    parser.add_argument("--proxy-pool", dest="proxy_pool", action="store_true",
                        help="Pakai proxy pool dari file")
    parser.add_argument("--output", type=str, default="gorouter_keys.txt", help="Output file for API keys")
    parser.add_argument("--github-output", type=str, default="github_keys.txt", help="Output file for GitHub accounts")
    parser.add_argument("--aff", type=str, default=None,
                        help="GoRouter referral code (overrides GR_AFF_CODE in .env)")
    parser.add_argument("--use-existing", action="store_true",
                        help="Skip GitHub signup, reuse account from --github-output")
    parser.add_argument("--line", type=int, default=None,
                        help="With --use-existing: 1-based line number to use (default: last)")
    parser.add_argument("--router", dest="router", action="store_true", default=None,
                        help="Import API key ke 9Router (override ADD_TO_ROUTER di .env)")
    parser.add_argument("--no-router", dest="router", action="store_false",
                        help="Jangan import ke 9Router")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Skip the interactive setup and use flags/.env as-is")
    args = parser.parse_args()

    # Any explicit flag also skips the prompt
    flags_given = any([
        args.count is not None, args.headless is not None, args.proxy,
        args.aff, args.use_existing, args.line, args.router is not None,
    ])

    # headless: CLI flag wins, otherwise fall back to HEADLESS in .env
    if args.headless is None:
        args.headless = os.environ.get("HEADLESS", "0").strip().lower() in ("1", "true", "yes", "on")

    # count: CLI flag wins, otherwise COUNT in .env
    if args.count is None:
        try:
            args.count = max(1, int(os.environ.get("COUNT", "1")))
        except ValueError:
            args.count = 1

    # Proxy pool: CLI flag menang, kalau tidak pakai USE_PROXY_POOL di .env
    if args.proxy_pool is None:
        args.proxy_pool = os.environ.get("USE_PROXY_POOL", "0").strip().lower() in ("1", "true", "yes", "on")

    # 9Router: CLI flag wins, otherwise ADD_TO_ROUTER in .env
    if args.router is None:
        args.router = os.environ.get("ADD_TO_ROUTER", "0").strip().lower() in ("1", "true", "yes", "on")

    # referral code: CLI flag wins, otherwise GR_AFF_CODE in .env
    aff_code = args.aff or os.environ.get("GR_AFF_CODE", "").strip() or None

    # Prompt hanya kalau INTERACTIVE=1 di .env, tidak ada flag, dan terminal interaktif.
    # Set INTERACTIVE=0 (default) supaya langsung jalan pakai .env.
    interactive_env = os.environ.get("INTERACTIVE", "0").strip().lower() in ("1", "true", "yes", "on")
    if interactive_env and not args.yes and not flags_given and sys.stdin.isatty():
        args, aff_code = interactive_setup(args, aff_code)

    noov_cookie = os.environ.get("NOOV_COOKIE", "")
    if not noov_cookie:
        log("❌ NOOV_COOKIE not set in .env")
        sys.exit(1)

    log("🔵 GoRouter Creator")
    log(f"   Log file: {logfile}")
    log(f"   Accounts: {args.count}")
    log(f"   Headless: {args.headless}")
    log(f"   Referral: {aff_code or '(none)'}")
    wf = "GitHub signup → GoRouter OAuth → API key"
    if args.router:
        wf += " → 9Router"
    log(f"   Workflow: {wf}")
    if args.router:
        log(f"   9Router: {os.environ.get('ROUTER_URL', 'http://127.0.0.1:20128')}")
    if args.proxy:
        log(f"   Proxy: manual ({args.proxy})")
    elif args.proxy_pool:
        log(f"   Proxy: pool dari {args.proxy_file or 'proxies.txt'}")
    else:
        log("   Proxy: tidak pakai")
    log(f"   Output: {args.output}")
    log()

    proxy_list = []
    if args.proxy_pool and not args.proxy:
        proxy_list = load_proxies(args.proxy_file)
        if proxy_list:
            log(f"   Proxy pool: {len(proxy_list)} proxy dimuat")
        else:
            log("   Proxy pool: file kosong / tidak ada — lanjut tanpa proxy")

    existing = []
    if args.use_existing:
        gh_file = Path(args.github_output)
        if not gh_file.exists():
            log(f"❌ {args.github_output} not found")
            sys.exit(1)
        for ln in gh_file.read_text().splitlines():
            ln = ln.strip()
            parts = ln.split(":")
            if len(parts) >= 3:
                existing.append({"email": parts[0], "password": parts[1], "username": parts[2]})
        if not existing:
            log(f"❌ No valid accounts in {args.github_output}")
            sys.exit(1)
        if args.line:
            existing = [existing[args.line - 1]]
        log(f"   Reusing GitHub accounts: {len(existing)} available")

    success = 0
    fail = 0

    def build_camoufox_args():
        """Bangun argumen Camoufox; proxy dirotasi tiap akun + opsi anti-deteksi."""
        cf = {
            # gerakan kursor manusiawi (DataDome memantau pola mouse)
            "humanize": True,
            # rotasi OS fingerprint tiap akun
            "os": random.choice(["windows", "macos", "linux"]),
            # cache aktif -> profil terlihat seperti browser terpakai, bukan baru
            "enable_cache": True,
        }

        if args.proxy:
            cf["proxy"] = {"server": args.proxy}
            cf["geoip"] = True
        elif proxy_list:
            cfg = pick_proxy(proxy_list)
            if cfg:
                cf["proxy"] = cfg
                cf["geoip"] = True
                log(f"  🌐 Proxy: {describe_proxy(cfg)}")

        return cf

    for i in range(args.count):
        log(f"\n{'='*60}")
        log(f"  Account {i+1}/{args.count}")
        log(f"{'='*60}")

        try:
            acct = None
            if args.use_existing:
                acct = existing[-1] if len(existing) == 1 else existing[-(i + 1)]
                email = acct["email"]
                log(f"\n  ♻️  Reusing GitHub: {acct['username']} ({email})")
                user_id = find_noov_user_id(noov_cookie, email)
                if user_id:
                    log(f"  Mailbox id: {user_id}")
                else:
                    log("  ⚠️  Mailbox not found on noov — device verification will fail")
            else:
                log("\n  📧 Creating noov mailbox...")
                mailbox = create_noov_mailbox(noov_cookie)
                email = mailbox["email"]
                user_id = mailbox["user_id"]
                log(f"  Email: {email}")

            # One browser session for entire workflow
            log(f"\n  🦊 Launching Camoufox (headless={args.headless})...")
            t0 = time.time()

            camoufox_args = build_camoufox_args()
            with Camoufox(headless=args.headless, **camoufox_args) as browser:
                page = browser.new_page()
                log(f"  Browser ready ({time.time()-t0:.1f}s)")

                log(f"\n  {'─'*50}")
                if args.use_existing:
                    log("  STEP 1/3: SKIPPED — reusing existing GitHub account")
                    log(f"  {'─'*50}")
                    gh = {"success": True, **acct}
                else:
                    log("  STEP 1/3: Create GitHub account")
                    log(f"  {'─'*50}")
                    gh = create_github_account_on_page(page, email, noov_cookie, user_id)

                    if not gh.get("success"):
                        raise Exception("GitHub account creation failed")

                    gh_line = f"{gh['email']}:{gh['password']}:{gh['username']}"
                    with open(args.github_output, "a") as f:
                        f.write(gh_line + "\n")
                    log(f"  ✅ GitHub saved: {gh_line}")

                # Step 3: GoRouter OAuth
                log(f"\n  {'─'*50}")
                log("  STEP 2/3: Sign up GoRouter via GitHub")
                log(f"  {'─'*50}")
                signup_gorouter_via_github(page, gh["username"], gh["password"], noov_cookie, user_id, aff_code)
                log("  ✅ GoRouter account ready")

                # Step 4: generate API key
                log(f"\n  {'─'*50}")
                log("  STEP 3/3: Generate GoRouter API key")
                log(f"  {'─'*50}")
                key_data = generate_gorouter_api_key(page)

                line = f"{gh['email']}|{gh['username']}|{key_data['name']}|{key_data['key']}"
                with open(args.output, "a") as f:
                    f.write(line + "\n")

                # Step 4: import ke 9Router (opsional)
                if args.router:
                    log(f"\n  {'─'*50}")
                    log("  STEP 4/4: Import API key ke 9Router")
                    log(f"  {'─'*50}")
                    try:
                        r = router_add_api_key(
                            api_key=key_data["key"],
                            name=f"gr-{gh['username']}",
                        )
                        if r.get("added"):
                            log("  ✅ Key terdaftar di 9Router")
                        else:
                            log(f"  ⚠️  Tidak diimport: {r.get('reason')}")
                    except Exception as e:
                        log(f"  ⚠️  9Router gagal (akun & key tetap tersimpan): {str(e)[:160]}")

                success += 1
                log(f"\n  ✅ DONE — API key: {key_data['key']}")
                log(f"     Saved to: {args.output}")

        except Exception as e:
            fail += 1
            log(f"\n  ❌ Error: {e}")
            log("  ── TRACEBACK ──")
            for tl in traceback.format_exc().splitlines():
                log(f"  {tl}")

        if i < args.count - 1:
            base = int(os.environ.get("DELAY_BETWEEN_ACCOUNTS", "90"))
            # back off harder right after a failure
            wait = base if fail == 0 else base * 2
            wait += random.randint(0, 25)
            log(f"\n  ⏳ Waiting {wait}s before next account (anti rate-limit)...")
            time.sleep(wait)

    log(f"\n{'='*60}")
    log(f"  DONE — ✅ {success} success, ❌ {fail} failed")
    log(f"{'='*60}")
    if success > 0:
        log(f"\n  📄 API keys: {args.output}")
        log(f"  📄 GitHub accounts: {args.github_output}")


if __name__ == "__main__":
    main()
