#!/usr/bin/env python3
"""
GoRouter (gorouter.app) signup via GitHub OAuth + API key generation
"""
import os
import time
import random
import string
from logger import log

GR_BASE_URL = os.environ.get("GR_BASE_URL", "https://gorouter.app").rstrip("/")
GR_KEYS_URL = f"{GR_BASE_URL}/keys"

# Referral / affiliate code (can be overridden by .env or CLI)
GR_AFF_CODE = os.environ.get("GR_AFF_CODE", "")


def build_signup_url(aff_code=None):
    """Build the GoRouter signup URL for a given referral code."""
    code = (aff_code or GR_AFF_CODE or "").strip()
    if not code:
        return f"{GR_BASE_URL}/sign-up"
    return f"{GR_BASE_URL}/sign-up?aff={code}"


def generate_key_name():
    """Generate random API key name"""
    return "gr-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))


def kill_overlays(page):
    """Remove tooltips/overlays that block clicks"""
    try:
        page.evaluate("""() => {
            document.querySelectorAll('[role="tooltip"], .tooltipped, [popover], tool-tip').forEach(t => {
                t.style.display = 'none';
                t.style.pointerEvents = 'none';
            });
        }""")
    except Exception:
        pass


def wait_for_device_code(noov_cookie, noov_user_id, max_attempts=30):
    """Read GitHub's device verification code from the noov inbox."""
    import re as _re
    from email.header import decode_header as _dh
    from noov_email import read_noov_inbox

    for attempt in range(1, max_attempts + 1):
        log(f"  ├─ [GR] Polling noov for device code ({attempt}/{max_attempts})...")
        try:
            for msg in read_noov_inbox(noov_cookie, noov_user_id):
                sender = msg.get("from", "")
                raw_subject = msg.get("subject", "")
                body = msg.get("body", "")

                subject = raw_subject
                try:
                    subject = "".join(
                        p.decode(enc or "utf-8") if isinstance(p, bytes) else p
                        for p, enc in _dh(raw_subject)
                    )
                except Exception:
                    pass

                if "github" not in sender.lower():
                    continue
                blob = f"{subject}\n{body}".lower()
                if not any(k in blob for k in ("device verification", "verification code", "authentication code")):
                    continue

                m = _re.search(r"\b(\d{6,8})\b", body)
                if m:
                    return m.group(1)
        except Exception as e:
            log(f"  ├─ [GR] Device code poll error: {str(e)[:70]}")
        time.sleep(5)

    raise Exception("GitHub device verification code not received")


def signup_gorouter_via_github(page, github_username, github_password, noov_cookie=None, noov_user_id=None, aff_code=None):
    """
    Sign up / sign in to GoRouter using GitHub OAuth.
    Assumes GitHub session may already be active in the same browser.
    """
    signup_url = build_signup_url(aff_code)
    log(f"\n  ├─ [GR] Referral code: {aff_code or GR_AFF_CODE or '(none)'}")
    log(f"  ├─ [GR] Navigating to: {signup_url}")
    page.goto(signup_url, timeout=60000)
    time.sleep(3)

    log(f"  ├─ [GR] URL: {page.url}")
    log(f"  ├─ [GR] Title: {page.title()}")

    # GoRouter pakai Cloudflare Turnstile. Tombol GitHub bisa diklik lebih awal,
    # tapi OAuth baru jalan setelah widget selesai — jadi tunggu dulu.
    log("  ├─ [GR] Menunggu Cloudflare Turnstile...")
    for _ in range(30):
        try:
            state = page.evaluate("""() => {
                const inp = document.querySelector('input[name="cf-turnstile-response"], input[name="cf_turnstile_response"]');
                const txt = (document.body.innerText || '').toLowerCase();
                const gh = Array.from(document.querySelectorAll('button, a'))
                    .find(b => /continue with github/i.test(b.textContent || ''));
                return {
                    token: inp ? !!inp.value : null,
                    success: txt.includes('success!'),
                    ghDisabled: gh ? !!gh.disabled : null,
                };
            }""")
        except Exception:
            state = None

        if state and (state.get("token") or state.get("success")):
            log("  ├─ [GR] ✅ Turnstile siap")
            break
        time.sleep(1)
    else:
        log("  ├─ [GR] ⚠️ Turnstile belum selesai, lanjut saja")

    time.sleep(1.5)

    # Klik "Continue with GitHub" — JS click sering ditelan React/Turnstile,
    # jadi pakai klik mouse asli dan verifikasi URL benar-benar pindah.
    log("  ├─ [GR] Klik 'Continue with GitHub'...")
    kill_overlays(page)

    def left_signup_page():
        try:
            u = page.url
        except Exception:
            return False
        return ("gorouter.app/sign-up" not in u) and ("gorouter.app/sign-in" not in u)

    clicked = False

    for attempt in range(1, 5):
        # 1) klik mouse asli (trusted event) — paling ampuh untuk React
        try:
            btn = page.get_by_role("button", name="Continue with GitHub")
            if btn.count() == 0:
                btn = page.locator('button:has-text("Continue with GitHub")')
            btn.first.scroll_into_view_if_needed(timeout=5000)
            time.sleep(0.4)
            btn.first.click(timeout=8000)
            log(f"  ├─ [GR] Klik mouse asli (try {attempt})")
        except Exception as e:
            log(f"  ├─ [GR] Klik asli gagal: {str(e)[:70]}")

            # 2) fallback: klik via koordinat tengah tombol
            try:
                box = page.evaluate("""() => {
                    const b = Array.from(document.querySelectorAll('button, a'))
                        .find(x => /continue with github/i.test(x.textContent || ''));
                    if (!b) return null;
                    b.scrollIntoView({ block: 'center' });
                    const r = b.getBoundingClientRect();
                    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
                }""")
                if box:
                    page.mouse.move(box["x"], box["y"])
                    time.sleep(0.2)
                    page.mouse.click(box["x"], box["y"])
                    log(f"  ├─ [GR] Klik koordinat (try {attempt})")
            except Exception as e2:
                log(f"  ├─ [GR] Klik koordinat gagal: {str(e2)[:70]}")

        # tunggu sampai halaman benar-benar pindah
        for _ in range(10):
            time.sleep(1)
            if left_signup_page():
                clicked = True
                break

        if clicked:
            try:
                log(f"  ├─ [GR] ✅ Pindah ke: {page.url}")
            except Exception:
                pass
            break

        # 3) fallback terakhir: buka endpoint OAuth langsung
        if attempt == 3:
            log("  ├─ [GR] Coba trigger OAuth langsung...")
            try:
                href = page.evaluate("""() => {
                    const a = Array.from(document.querySelectorAll('a'))
                        .find(x => /github/i.test(x.href || ''));
                    return a ? a.href : null;
                }""")
                if href:
                    page.goto(href, timeout=60000)
                    time.sleep(3)
                    if left_signup_page():
                        clicked = True
                        log(f"  ├─ [GR] ✅ OAuth via link: {page.url}")
                        break
            except Exception as e:
                log(f"  ├─ [GR] OAuth langsung gagal: {str(e)[:70]}")

        log(f"  ├─ [GR] ⚠️ Masih di halaman sign-up, ulangi (try {attempt}/4)")
        kill_overlays(page)
        time.sleep(2)

    if not clicked:
        try:
            log(f"  ├─ [GR] [DEBUG] URL: {page.url}")
            log(f"  ├─ [GR] [DEBUG] Body: {page.inner_text('body')[:400]}")
        except Exception:
            pass
        raise Exception("Tombol 'Continue with GitHub' tidak memicu OAuth")

    # Wait for GitHub OAuth page or redirect back.
    # Every DOM read is guarded — navigations destroy the execution context.
    log("  ├─ [GR] Waiting for GitHub OAuth...")

    def safe_url():
        try:
            return page.url
        except Exception:
            return ""

    def safe_body():
        try:
            return page.inner_text("body")
        except Exception:
            return ""

    def safe_q(sel):
        try:
            return page.query_selector(sel)
        except Exception:
            return None

    login_submitted = False
    device_verified = False

    for i in range(70):
        time.sleep(1)
        url = safe_url()
        body = safe_body()
        body_low = body.lower()

        if not url:
            continue

        # Back at GoRouter = done
        if "gorouter.app" in url and "sign-up" not in url and "sign-in" not in url:
            log(f"  ├─ [GR] ✅ Redirected back to GoRouter: {url}")
            return True

        # OAuth authorize page — handle BEFORE login check
        if "/login/oauth/authorize" in url:
            log("  ├─ [GR] Authorize page, clicking Authorize...")
            try:
                res = page.evaluate("""() => {
                    const btn = document.querySelector('button[name="authorize"][value="1"]') ||
                                Array.from(document.querySelectorAll('button, input[type=submit]'))
                                     .find(b => /authorize|continue/i.test(b.textContent || b.value || ''));
                    if (!btn) return 'not-found';
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.click();
                    return 'clicked';
                }""")
                log(f"  ├─ [GR] Authorize: {res}")
            except Exception as e:
                log(f"  ├─ [GR] Authorize skipped ({str(e)[:50]})")
            time.sleep(4)
            continue

        # GitHub login form — fill once
        login_field = safe_q('input#login_field')
        if login_field and not login_submitted:
            log("  ├─ [GR] GitHub login form, signing in...")
            try:
                pass_field = safe_q('input#password')
                if pass_field:
                    login_field.click(force=True, timeout=8000)
                    login_field.fill(github_username)
                    time.sleep(0.4)
                    pass_field.click(force=True, timeout=8000)
                    pass_field.fill(github_password)
                    time.sleep(0.4)
                    page.keyboard.press("Enter")
                    login_submitted = True
                    log("  ├─ [GR] Credentials submitted")
                    time.sleep(6)
            except Exception as e:
                log(f"  ├─ [GR] Login fill error: {str(e)[:70]}")
            continue

        if login_field and login_submitted:
            if "incorrect" in body_low or "invalid" in body_low:
                raise Exception(f"GitHub login rejected: {body[:200]}")
            if i > 30:
                log(f"  ├─ [GR] ⚠️ Login form still present after {i}s")
                log(f"  ├─ [GR] [DEBUG] URL: {url}")
                log(f"  ├─ [GR] [DEBUG] Body: {body[:300]}")
                raise Exception("GitHub login form did not clear")
            continue

        # Device verification — read the code from the noov inbox
        if "verified-device" in url or "device verification" in body_low:
            if not (noov_cookie and noov_user_id):
                log(f"  ├─ [GR] [DEBUG] Body: {body[:300]}")
                raise Exception("GitHub device verification required but no noov mailbox provided")

            if device_verified:
                if i > 45:
                    raise Exception("Device verification code was rejected")
                continue

            log("  ├─ [GR] Device verification required, fetching code from noov...")
            code = wait_for_device_code(noov_cookie, noov_user_id)
            log(f"  ├─ [GR] Device code: {code}")

            try:
                filled = page.evaluate("""(c) => {
                    const inputs = Array.from(document.querySelectorAll('input'))
                        .filter(x => x.type !== 'hidden' && x.offsetParent !== null);
                    if (!inputs.length) return 'no-input';
                    const t = inputs[0];
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    setter.call(t, c);
                    t.dispatchEvent(new Event('input', { bubbles: true }));
                    t.dispatchEvent(new Event('change', { bubbles: true }));
                    return 'filled';
                }""", code)
                log(f"  ├─ [GR] Code fill: {filled}")
                time.sleep(1)

                res = page.evaluate("""() => {
                    const btn = Array.from(document.querySelectorAll('button, input[type=submit]'))
                        .find(b => /verify|continue|submit/i.test(b.textContent || b.value || ''));
                    if (btn) {
                        btn.disabled = false;
                        btn.removeAttribute('disabled');
                        btn.click();
                        return 'clicked';
                    }
                    const form = document.querySelector('form');
                    if (form) {
                        if (typeof form.requestSubmit === 'function') form.requestSubmit();
                        else form.submit();
                        return 'form-submitted';
                    }
                    return 'nothing';
                }""")
                log(f"  ├─ [GR] Verify submit: {res}")
                device_verified = True
                time.sleep(6)
            except Exception as e:
                log(f"  ├─ [GR] Device verify error: {str(e)[:80]}")
            continue

        if i % 10 == 9:
            log(f"  ├─ [GR] Still waiting... ({i+1}s) | URL: {url}")

    raise Exception(f"GoRouter OAuth did not complete. Last URL: {page.url}")


def generate_gorouter_api_key(page, key_name=None):
    """
    Navigate to /keys and create a new API key. Returns the key string.
    """
    key_name = key_name or generate_key_name()

    # Record API endpoint URLs only (reading bodies in a sync handler deadlocks Playwright)
    captured = {"endpoints": []}

    def _on_response(resp):
        try:
            u = resp.url
            if "/api/" in u:
                captured["endpoints"].append(f"{resp.request.method} {u.split('?')[0]} [{resp.status}]")
        except Exception:
            pass

    page.on("response", _on_response)

    log(f"\n  ├─ [API] Navigating to {GR_KEYS_URL}...")

    def safe_url():
        try:
            return page.url
        except Exception:
            return ""

    def open_keys_page():
        """Open /keys and make sure we are not bounced to sign-in."""
        for attempt in range(1, 6):
            try:
                page.goto(GR_KEYS_URL, timeout=60000)
            except Exception as e:
                log(f"  ├─ [API] goto error: {str(e)[:70]}")

            # give the SPA time to run its auth check / client redirect
            settled = ""
            for _ in range(10):
                time.sleep(1)
                settled = safe_url()
                if "sign-in" in settled or "sign-up" in settled:
                    break
                if "/keys" in settled:
                    # confirm it stays on /keys
                    time.sleep(2)
                    settled = safe_url()
                    break

            if "/keys" in settled and "sign-in" not in settled:
                log(f"  ├─ [API] ✅ On keys page (attempt {attempt})")
                return True

            log(f"  ├─ [API] ⚠️ Bounced to {settled} (attempt {attempt}/5)")

            # session not ready yet — warm it up via dashboard, else re-auth with GitHub
            if attempt <= 2:
                log("  ├─ [API] Warming session via dashboard...")
                try:
                    page.goto(f"{GR_BASE_URL}/dashboard/overview", timeout=60000)
                except Exception:
                    pass
                time.sleep(5)
            else:
                log("  ├─ [API] Re-authenticating via 'Continue with GitHub'...")
                try:
                    res = page.evaluate("""() => {
                        const b = Array.from(document.querySelectorAll('button, a'))
                            .find(x => /continue with github/i.test(x.textContent || ''));
                        if (!b) return 'not-found';
                        b.click();
                        return 'clicked';
                    }""")
                    log(f"  ├─ [API] GitHub re-auth: {res}")
                except Exception as e:
                    log(f"  ├─ [API] Re-auth error: {str(e)[:70]}")

                # GitHub session is already active, so this normally bounces straight back
                for _ in range(25):
                    time.sleep(1)
                    u = safe_url()
                    if "gorouter.app" in u and "sign-in" not in u and "sign-up" not in u:
                        break
                    if "/login/oauth/authorize" in u:
                        try:
                            page.evaluate("""() => {
                                const btn = document.querySelector('button[name="authorize"][value="1"]');
                                if (btn) { btn.disabled = false; btn.removeAttribute('disabled'); btn.click(); }
                            }""")
                        except Exception:
                            pass
                        time.sleep(4)
                time.sleep(3)

        return False

    if not open_keys_page():
        log(f"  ├─ [API] [DEBUG] URL: {safe_url()}")
        try:
            log(f"  ├─ [API] [DEBUG] Body: {page.inner_text('body')[:400]}")
        except Exception:
            pass
        raise Exception("Could not reach /keys — GoRouter session not established")

    log(f"  ├─ [API] URL: {safe_url()}")

    # Click "Create API Key" and WAIT for the modal to actually open
    log("  ├─ [API] Opening 'Create API Key' modal...")
    kill_overlays(page)

    dialog_open = False

    for open_try in range(3):
        log(f"  ├─ [API] Open attempt {open_try+1}/3")

        # Click the create button (JS first, then Playwright)
        clicked = False
        try:
            res = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                const btn = btns.find(b => {
                    const t = (b.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return t === 'create api key' || t === '+ create api key' || t.endsWith('create api key');
                });
                if (!btn) return 'not-found';
                btn.scrollIntoView({ block: 'center' });
                btn.click();
                return 'clicked';
            }""")
            clicked = (res == 'clicked')
            log(f"  ├─ [API] JS click: {res}")
        except Exception as e:
            log(f"  ├─ [API] JS click error: {str(e)[:80]}")

        if not clicked:
            try:
                btn = page.query_selector('button:has-text("Create API Key")')
                if btn:
                    btn.scroll_into_view_if_needed()
                    btn.click(force=True, timeout=8000, no_wait_after=True)
                    clicked = True
                    log("  ├─ [API] Clicked via Playwright")
            except Exception as e:
                log(f"  ├─ [API] Playwright click error: {str(e)[:80]}")

        # Wait for dialog
        for _ in range(10):
            time.sleep(1)
            state = page.evaluate("""() => {
                const dlg = document.querySelector('[role="dialog"], dialog[open], .modal.show, [data-state="open"]');
                if (!dlg) return null;
                return {
                    text: (dlg.innerText || '').slice(0, 300),
                    inputs: Array.from(dlg.querySelectorAll('input, textarea')).map(i => ({
                        type: i.type, name: i.name, ph: i.placeholder, id: i.id
                    }))
                };
            }""")
            if state:
                dialog_open = True
                log(f"  ├─ [API] ✅ Modal opened")
                log(f"  ├─ [API] Modal inputs: {state['inputs']}")
                break

        if dialog_open:
            break

        log("  ├─ [API] ⚠️ Modal did not open, retrying...")
        time.sleep(2)

    if not dialog_open:
        log(f"  ├─ [API] [DEBUG] URL: {page.url}")
        log(f"  ├─ [API] [DEBUG] Body: {page.inner_text('body')[:600]}")
        raise Exception("Create API Key modal did not open")

    # Fill the name input INSIDE the modal only
    log(f"  ├─ [API] Filling key name inside modal: {key_name}")
    try:
        filled = page.evaluate("""(name) => {
            const dlg = document.querySelector('[role="dialog"], dialog[open], .modal.show, [data-state="open"]');
            if (!dlg) return 'no-dialog';
            const inputs = Array.from(dlg.querySelectorAll('input[type="text"], input:not([type]), textarea'));
            if (!inputs.length) return 'no-input';
            const target = inputs[0];
            const setter = Object.getOwnPropertyDescriptor(
                target.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype,
                'value'
            ).set;
            setter.call(target, name);
            target.dispatchEvent(new Event('input', { bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            return 'filled';
        }""", key_name)
        log(f"  ├─ [API] Name fill: {filled}")
    except Exception as e:
        log(f"  ├─ [API] Name fill error: {str(e)[:80]}")

    time.sleep(1)

    # Submit inside the modal only
    log("  ├─ [API] Submitting modal...")
    try:
        res = page.evaluate("""() => {
            const dlg = document.querySelector('[role="dialog"], dialog[open], .modal.show, [data-state="open"]');
            if (!dlg) return 'no-dialog';
            const btns = Array.from(dlg.querySelectorAll('button'));
            // prefer submit-type or confirm-looking buttons, avoid cancel/close
            const btn = btns.find(b => {
                const t = (b.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                if (!t) return false;
                if (/cancel|close|batal/.test(t)) return false;
                return /create|submit|confirm|save|ok|generate/.test(t);
            }) || btns.find(b => b.type === 'submit');
            if (!btn) return 'no-button:' + btns.map(b => (b.textContent||'').trim()).join('|');
            btn.disabled = false;
            btn.removeAttribute('disabled');
            btn.click();
            return 'clicked:' + (btn.textContent || '').trim();
        }""")
        log(f"  ├─ [API] Submit: {res}")
    except Exception as e:
        log(f"  ├─ [API] Submit error: {str(e)[:80]}")

    time.sleep(4)

    # Extract the API key.
    # UI only shows a masked key, so ask the backend directly using the page session.
    log("  ├─ [API] Extracting API key via backend API...")
    api_key = None

    def looks_full(v):
        return isinstance(v, str) and v.startswith("sk-") and "*" not in v and len(v) > 20

    # Give the create request time to finish
    time.sleep(2)

    try:
        result = page.evaluate("""async (keyName) => {
            const out = { tried: [], key: null, tokenId: null, sample: null };

            const listPaths = [
                '/api/token/?p=1&size=20',
                '/api/token/?p=1&page_size=20',
                '/api/token/',
                '/api/gateway/token/?p=1&page_size=20',
                '/api/keys?page=1&pageSize=20',
                '/api/api-keys?page=1&pageSize=20',
                '/api/user/token',
            ];

            const getJson = async (path) => {
                try {
                    const r = await fetch(path, { credentials: 'include', headers: { accept: 'application/json' } });
                    out.tried.push(path + ' -> ' + r.status);
                    if (!r.ok) return null;
                    const t = await r.text();
                    try { return JSON.parse(t); } catch (_) { return null; }
                } catch (e) {
                    out.tried.push(path + ' -> ERR');
                    return null;
                }
            };

            const deepFind = (obj, pred, depth = 0) => {
                if (obj == null || depth > 6) return null;
                if (typeof obj === 'string') return pred(obj) ? obj : null;
                if (Array.isArray(obj)) {
                    for (const v of obj) { const f = deepFind(v, pred, depth + 1); if (f) return f; }
                    return null;
                }
                if (typeof obj === 'object') {
                    for (const k of Object.keys(obj)) {
                        const f = deepFind(obj[k], pred, depth + 1);
                        if (f) return f;
                    }
                }
                return null;
            };

            const isFullKey = (s) => typeof s === 'string' && s.startsWith('sk-') && !s.includes('*') && s.length > 20;

            // 1) look for a full key anywhere in the list responses
            let listData = null;
            for (const p of listPaths) {
                const d = await getJson(p);
                if (!d) continue;
                listData = listData || d;
                const full = deepFind(d, isFullKey);
                if (full) { out.key = full; return out; }
            }

            if (listData) out.sample = JSON.stringify(listData).slice(0, 700);

            // 2) find the token id, then hit the reveal endpoint
            const findItems = (d) => {
                const cands = [d?.data?.items, d?.data?.records, d?.data?.list, d?.data, d?.items, d?.records, d?.list, d];
                for (const c of cands) if (Array.isArray(c)) return c;
                return [];
            };

            for (const p of listPaths) {
                const d = await getJson(p);
                if (!d) continue;
                const items = findItems(d);
                if (!items.length) continue;

                let item = items.find(x => x && (x.name === keyName || x.key_name === keyName));
                if (!item) item = items[0];
                const id = item?.id ?? item?.token_id ?? item?.ID;
                if (id == null) continue;
                out.tokenId = id;

                const revealPaths = [
                    ['POST', `/api/token/${id}/key`],
                    ['GET',  `/api/token/${id}/key`],
                    ['POST', `/api/gateway/token/${id}/key`],
                    ['GET',  `/api/token/${id}`],
                    ['POST', `/api/keys/${id}/reveal`],
                    ['GET',  `/api/keys/${id}`],
                ];

                for (const [method, rp] of revealPaths) {
                    try {
                        const r = await fetch(rp, {
                            method,
                            credentials: 'include',
                            headers: { accept: 'application/json', 'content-type': 'application/json' },
                            body: method === 'POST' ? '' : undefined,
                        });
                        out.tried.push(method + ' ' + rp + ' -> ' + r.status);
                        if (!r.ok) continue;
                        const t = await r.text();
                        let d2 = null;
                        try { d2 = JSON.parse(t); } catch (_) { d2 = t; }
                        const full = deepFind(d2, isFullKey);
                        if (full) { out.key = full; return out; }
                    } catch (e) {
                        out.tried.push(method + ' ' + rp + ' -> ERR');
                    }
                }
                break;
            }

            return out;
        }""", key_name)

        for t in (result.get("tried") or [])[:30]:
            log(f"  │    {t}")
        if result.get("tokenId") is not None:
            log(f"  ├─ [API] token id: {result['tokenId']}")
        if looks_full(result.get("key")):
            api_key = result["key"]
            log("  ├─ [API] ✅ Key retrieved from backend")
        elif result.get("sample"):
            log(f"  ├─ [API] [DEBUG] list sample: {result['sample']}")
    except Exception as e:
        log(f"  ├─ [API] Backend fetch failed: {str(e)[:150]}")

    # Fallback: full key sometimes visible in the DOM right after creation
    if not api_key:
        log("  ├─ [API] Falling back to DOM scan...")
        for _ in range(4):
            time.sleep(1)
            try:
                found = page.evaluate("""() => {
                    for (const inp of document.querySelectorAll('input, textarea')) {
                        const v = inp.value || '';
                        if (v.startsWith('sk-') && !v.includes('*')) return v;
                    }
                    for (const el of document.querySelectorAll('[data-clipboard-text], [data-copy-value]')) {
                        const v = el.getAttribute('data-clipboard-text') || el.getAttribute('data-copy-value') || '';
                        if (v.startsWith('sk-') && !v.includes('*')) return v;
                    }
                    const m = document.body.innerText.match(/sk-[A-Za-z0-9_\\-]{20,}/);
                    return m ? m[0] : null;
                }""")
                if looks_full(found):
                    api_key = found
                    log("  ├─ [API] ✅ Full key found in DOM")
                    break
            except Exception as e:
                log(f"  ├─ [API] DOM scan error: {str(e)[:70]}")

    # Fallback: intercept clipboard when clicking the copy icon (no real clipboard read — it hangs)
    if not api_key:
        log("  ├─ [API] Falling back to copy-button intercept...")
        try:
            page.evaluate("""() => {
                window.__copied = null;
                if (navigator.clipboard) {
                    navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); };
                }
                const origExec = document.execCommand ? document.execCommand.bind(document) : null;
                document.execCommand = function (cmd, ...rest) {
                    if (String(cmd).toLowerCase() === 'copy') {
                        const ae = document.activeElement;
                        if (ae && ae.value) window.__copied = ae.value;
                        const sel = window.getSelection();
                        if (sel && sel.toString()) window.__copied = sel.toString();
                    }
                    return origExec ? origExec(cmd, ...rest) : false;
                };
                document.addEventListener('copy', (e) => {
                    try {
                        const cd = e.clipboardData || window.clipboardData;
                        const t = cd && cd.getData ? cd.getData('text') : '';
                        if (t) window.__copied = t;
                    } catch (_) {}
                }, true);
            }""")

            total = page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr, [role="row"]'));
                const row = rows.find(r => /sk-[A-Za-z0-9_*\\-]{6,}/.test(r.innerText || ''));
                return (row || document.body).querySelectorAll('button, [role="button"]').length;
            }""")
            log(f"  ├─ [API] {total} buttons in key row")

            for idx in range(min(int(total or 0), 6)):
                page.evaluate("""(i) => {
                    window.__copied = null;
                    const rows = Array.from(document.querySelectorAll('tr, [role="row"]'));
                    const row = rows.find(r => /sk-[A-Za-z0-9_*\\-]{6,}/.test(r.innerText || ''));
                    const btns = Array.from((row || document.body).querySelectorAll('button, [role="button"]'));
                    if (btns[i]) btns[i].click();
                }""", idx)
                time.sleep(1.2)
                cap = page.evaluate("() => window.__copied")
                if looks_full(cap):
                    api_key = cap
                    log(f"  ├─ [API] ✅ Key captured from button #{idx}")
                    break
        except Exception as e:
            log(f"  ├─ [API] Copy intercept failed: {str(e)[:100]}")

    if not api_key:
        try:
            masked = page.evaluate("""() => {
                const m = document.body.innerText.match(/sk-[A-Za-z0-9_*\\-]{8,}/);
                return m ? m[0] : null;
            }""")
            log(f"  ├─ [API] ⚠️ Masked key only: {masked}")
        except Exception:
            pass
        log(f"  ├─ [API] [DEBUG] URL: {page.url}")
        log("  ├─ [API] [DEBUG] API endpoints seen:")
        for ep in captured["endpoints"][-25:]:
            log(f"  │    {ep}")
        raise Exception("Could not extract full API key")

    log(f"  ├─ [API] ✅ Key: {api_key[:12]}...{api_key[-4:]}")

    return {"name": key_name, "key": api_key}
