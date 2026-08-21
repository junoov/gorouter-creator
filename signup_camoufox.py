#!/usr/bin/env python3
"""
GitHub signup using Camoufox (anti-detect Firefox browser)
"""
import time
import random
import string
import re
import os
import json
from email.header import decode_header as mime_decode_header
from camoufox.sync_api import Camoufox
from noov_email import read_noov_inbox
from logger import log

WARM_COOKIES_FILE = "warm_cookies.json"


def generate_username():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=10))


def generate_password():
    base = "".join(random.choices(string.ascii_letters + string.digits, k=18))
    return f"GhP{base}!@#"


def human_type(page, selector, text, delay_min=0.03, delay_max=0.09):
    """Type text character by character with random delays"""
    el = page.query_selector(selector)
    if not el:
        raise Exception(f"Element not found: {selector}")
    el.click(force=True, timeout=10000)
    time.sleep(random.uniform(0.3, 0.7))
    for char in text:
        el.type(char, delay=0)
        time.sleep(random.uniform(delay_min, delay_max))
    return el


def kill_verifying_overlay(page):
    """Remove the 'Verifying...' tooltip that blocks clicks"""
    try:
        page.evaluate("""() => {
            // Find and hide any element containing "Verifying"
            const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
            const hits = [];
            while (walk.nextNode()) {
                const el = walk.currentNode;
                const txt = (el.textContent || '').trim();
                if (txt === 'Verifying...' || txt === 'Verifying') {
                    hits.push(el);
                }
            }
            for (const el of hits) {
                el.style.display = 'none';
                el.style.pointerEvents = 'none';
                el.style.visibility = 'hidden';
                if (el.parentElement) {
                    el.parentElement.style.pointerEvents = 'none';
                }
            }
            // Also kill any tooltip/popover elements
            document.querySelectorAll('[role="tooltip"], .tooltipped, [popover], tool-tip').forEach(t => {
                t.style.display = 'none';
                t.style.pointerEvents = 'none';
            });
            return hits.length;
        }""")
    except Exception:
        pass



def wait_for_otp_noov(noov_cookie, noov_user_id, max_attempts=40):
    """Poll noov inbox for GitHub OTP"""
    for attempt in range(1, max_attempts + 1):
        log(f"  ├─ [OTP] Polling noov inbox (attempt {attempt}/{max_attempts})...")
        try:
            messages = read_noov_inbox(noov_cookie, noov_user_id)
            for msg in messages:
                sender = msg.get("from", "")
                raw_subject = msg.get("subject", "")
                body = msg.get("body", "")

                # Decode MIME subject
                subject = raw_subject
                try:
                    parts = mime_decode_header(raw_subject)
                    subject = "".join(
                        p.decode(enc or "utf-8") if isinstance(p, bytes) else p
                        for p, enc in parts
                    )
                except Exception:
                    pass

                if "noreply@github.com" in sender and "launch code" in subject.lower():
                    # Extract 8-digit OTP
                    m = re.search(r"(\d{8})", body)
                    if m:
                        code = m.group(1)
                        log(f"  ├─ [OTP] ✅ Code received: {code}")
                        return code
        except Exception as e:
            log(f"  ├─ [OTP] Error: {e}")

        time.sleep(5)

    raise Exception("GitHub OTP not received within timeout")


def create_github_account_on_page(page, email, noov_cookie, noov_user_id):
    """Create a GitHub account on an existing Camoufox page"""
    username = generate_username()
    password = generate_password()

    log(f"\n  Account: {email}")
    log(f"  Username: {username}")
    log(f"  Password: {password}")

    if True:
        # Warm-up dulu: buka github.com, baru ke /signup.
        # Langsung buka /signup dari sesi kosong = sinyal bot paling kuat.
        log("  ├─ Warm-up di github.com...")
        try:
            page.goto("https://github.com/", timeout=60000)
            time.sleep(random.uniform(2.5, 4.5))
            for _ in range(random.randint(2, 4)):
                page.mouse.move(random.randint(80, 1100), random.randint(80, 600))
                page.mouse.wheel(0, random.randint(250, 700))
                time.sleep(random.uniform(0.6, 1.6))
        except Exception as e:
            log(f"  ├─ warmup error: {str(e)[:70]}")

        log("  ├─ Navigating to github.com/signup...")
        page.goto("https://github.com/signup", timeout=60000)
        time.sleep(random.uniform(2.5, 4))

        # DataDome / rate-limit handling.
        # Reload saja jarang menolong karena cookie DataDome ikut terbawa.
        # Jadi tiap retry: hapus cookie -> warm-up di github.com -> baru ke /signup.
        max_block_tries = int(os.environ.get("DATADOME_RETRIES", "6"))

        def page_state():
            try:
                content = page.content().lower()
            except Exception:
                content = ""
            try:
                body = page.inner_text("body").lower()
            except Exception:
                body = ""
            return content, body

        def human_warmup():
            """Buka github.com dulu, gerak-gerak sedikit, biar tidak terlihat langsung nembak /signup."""
            try:
                page.goto("https://github.com/", timeout=60000)
                time.sleep(random.uniform(2.5, 4.5))
                for _ in range(random.randint(2, 4)):
                    page.mouse.move(random.randint(80, 1100), random.randint(80, 600))
                    page.mouse.wheel(0, random.randint(250, 700))
                    time.sleep(random.uniform(0.6, 1.6))
                time.sleep(random.uniform(1.5, 3.0))
            except Exception as e:
                log(f"  ├─ warmup error: {str(e)[:70]}")

        for attempt in range(1, max_block_tries + 1):
            content, body_text = page_state()

            blocked = (
                "captcha-delivery.com" in content
                or "access is temporarily restricted" in body_text
                or "unusual activity" in body_text
            )
            limited = "too many requests" in body_text or "rate limit" in body_text

            if not blocked and not limited:
                if attempt > 1:
                    log(f"  ├─ ✅ Block hilang setelah {attempt - 1} retry")
                break

            if attempt == max_block_tries:
                kind = "rate limit" if limited else "DataDome block"
                raise Exception(
                    f"GitHub {kind} tidak hilang setelah {max_block_tries} percobaan — "
                    "ganti IP (restart router / matikan VPN) atau tunggu 15-30 menit"
                )

            # backoff: 20s, 45s, 90s, 150s, 240s (capped)
            wait = min(20 * (2 ** (attempt - 1)), 240) + random.uniform(0, 10)
            if limited:
                wait = max(wait, 90)
                log(f"  ├─ ⚠️ Rate limited (try {attempt}/{max_block_tries}) — tunggu {int(wait)}s...")
            else:
                log(f"  ├─ ⚠️ DataDome block (try {attempt}/{max_block_tries}) — tunggu {int(wait)}s...")

            time.sleep(wait)

            # Buang cookie DataDome supaya dapat identitas baru
            try:
                page.context.clear_cookies()
                log("  ├─ cookie dibersihkan")
            except Exception as e:
                log(f"  ├─ clear cookie gagal: {str(e)[:60]}")

            human_warmup()

            try:
                page.goto("https://github.com/signup", timeout=60000)
            except Exception as e:
                log(f"  ├─ nav error: {str(e)[:70]}")

            time.sleep(random.uniform(4, 8))

        # Wait for email field
        log("  ├─ [EMAIL] Waiting for email field...")
        try:
            page.wait_for_selector(
                'input#email, input[name="user[email]"], input[type="email"]',
                timeout=30000,
            )
        except Exception:
            log(f"  ├─ [EMAIL] ❌ Field not found!")
            log(f"  ├─ [EMAIL] URL: {page.url}")
            log(f"  ├─ [EMAIL] Title: {page.title()}")
            log(f"  ├─ [EMAIL] Body: {page.inner_text('body')[:300]}")
            raise Exception("Email field not found on signup page")

        log(f"  ├─ [EMAIL] Typing: {email}")
        human_type(page, 'input#email, input[name="user[email]"], input[type="email"]', email)
        log("  ├─ [EMAIL] ✅ Done")
        time.sleep(random.uniform(1, 2))

        # Password
        log("  ├─ [PASSWORD] Typing...")
        human_type(page, 'input#password, input[type="password"]', password)
        log("  ├─ [PASSWORD] ✅ Done")
        time.sleep(random.uniform(1, 2))

        # Username — with availability check & retry
        max_username_tries = 5
        for try_num in range(max_username_tries):
            log(f"  ├─ [USERNAME] Typing: {username} (try {try_num+1}/{max_username_tries})")
            
            # Clear field first if retrying
            username_el = page.query_selector('input#login, input[name="user[login]"]')
            if username_el:
                username_el.click(force=True, timeout=8000)
                page.keyboard.press("Control+a")
                page.keyboard.press("Delete")
                time.sleep(0.3)
            
            human_type(page, 'input#login, input[name="user[login]"]', username)
            log("  ├─ [USERNAME] Waiting for availability check...")
            time.sleep(3)
            
            # Check for error message (username taken)
            body_text = page.inner_text("body").lower()
            username_taken = (
                "username is not available" in body_text or
                "already taken" in body_text or
                "unavailable" in body_text
            )
            
            if username_taken:
                log(f"  ├─ [USERNAME] ⚠️ '{username}' taken, generating new one...")
                username = generate_username()
                time.sleep(1)
                continue
            
            # Check for green checkmark / valid state
            log(f"  ├─ [USERNAME] ✅ '{username}' available")
            break
        else:
            raise Exception(f"Could not find available username after {max_username_tries} tries")
        
        time.sleep(random.uniform(1.5, 2.5))

        # Uncheck copilot
        try:
            copilot = page.query_selector('input[name="user[copilot_opt_in]"]')
            if copilot and copilot.is_checked():
                copilot.click(force=True, timeout=8000)
                log("  ├─ [CHECKBOX] Copilot unchecked")
        except Exception:
            pass

        # Uncheck marketing
        try:
            marketing = page.query_selector('input[name="user[marketing_consent]"]')
            if marketing and marketing.is_checked():
                marketing.click(force=True, timeout=8000)
                log("  ├─ [CHECKBOX] Marketing unchecked")
        except Exception:
            pass

        time.sleep(random.uniform(1, 2))

        # Kill the "Verifying..." tooltip that blocks clicks (it never disappears)
        log("  ├─ [SUBMIT] Removing 'Verifying...' overlay...")
        kill_verifying_overlay(page)
        time.sleep(0.5)

        # Submit — retry until form actually submits
        max_submit_tries = 3
        submitted = False

        for submit_try in range(max_submit_tries):
            log(f"  ├─ [SUBMIT] Clicking Create Account (try {submit_try+1}/{max_submit_tries})...")

            # Remove overlay again before each attempt
            kill_verifying_overlay(page)

            clicked = False

            # Method 1: Direct JS click (most reliable, bypasses all overlays)
            try:
                result = page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('button, input[type=submit]'));
                    const btn = btns.find(b => {
                        const t = (b.textContent || b.value || '').trim().toLowerCase();
                        return t.includes('create account');
                    });
                    if (!btn) return 'not-found';
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.scrollIntoView({ block: 'center' });
                    btn.click();
                    return 'clicked';
                }""")
                if result == 'clicked':
                    log("  ├─ [SUBMIT] ✅ Clicked via JS")
                    clicked = True
                else:
                    log(f"  ├─ [SUBMIT] JS click: {result}")
            except Exception as e:
                log(f"  ├─ [SUBMIT] JS click error: {str(e)[:80]}")

            # Method 2: Playwright force click
            if not clicked:
                for sel in ['button:has-text("Create account")', 'button[type="submit"]', 'input[type="submit"]']:
                    try:
                        btn = page.query_selector(sel)
                        if btn:
                            btn.scroll_into_view_if_needed()
                            time.sleep(0.3)
                            btn.click(force=True, timeout=8000, no_wait_after=True)
                            log(f"  ├─ [SUBMIT] ✅ Clicked via Playwright: {sel}")
                            clicked = True
                            break
                    except Exception as e:
                        log(f"  ├─ [SUBMIT] Click failed on {sel}: {str(e)[:60]}")
                        continue

            # Method 3: Submit form directly
            if not clicked:
                log("  ├─ [SUBMIT] Submitting form via requestSubmit()...")
                try:
                    page.evaluate("""() => {
                        const form = document.querySelector('form[action*="signup"]') || document.querySelector('form');
                        if (form) {
                            if (typeof form.requestSubmit === 'function') form.requestSubmit();
                            else form.submit();
                            return true;
                        }
                        return false;
                    }""")
                    clicked = True
                except Exception as e:
                    log(f"  ├─ [SUBMIT] Form submit failed: {str(e)[:80]}")

            # Verify submission actually happened
            log("  ├─ [SUBMIT] Verifying submission...")
            for i in range(15):
                time.sleep(1)
                current_url = page.url
                body_text = page.inner_text("body").lower()

                otp_field = page.query_selector('input[name="otp"], input#otp, input[autocomplete="one-time-code"]')
                if otp_field:
                    log(f"  ├─ [SUBMIT] ✅ OTP field appeared")
                    submitted = True
                    break

                if "signup" not in current_url:
                    log(f"  ├─ [SUBMIT] ✅ Redirected to: {current_url}")
                    submitted = True
                    break

                if "verify your email" in body_text or "launch code" in body_text or "enter the code" in body_text:
                    log(f"  ├─ [SUBMIT] ✅ Verification page detected")
                    submitted = True
                    break

                if "too many requests" in body_text or "rate limit" in body_text:
                    raise Exception("Rate limited after submit")

            if submitted:
                break

            log(f"  ├─ [SUBMIT] ⚠️ Form still on page, retrying...")
            time.sleep(2)

        if not submitted:
            log(f"  ├─ [SUBMIT] ❌ Could not submit after {max_submit_tries} tries")
            log(f"  ├─ [SUBMIT] [DEBUG] URL: {page.url}")
            log(f"  ├─ [SUBMIT] [DEBUG] Body: {page.inner_text('body')[:500]}")
            raise Exception("Form submission failed — button click did not register")

        log(f"  ├─ [SUBMIT] URL: {page.url}")

        # Wait for OTP
        log("  ├─ [OTP] Waiting for GitHub launch code...")
        otp = wait_for_otp_noov(noov_cookie, noov_user_id)

        # Enter OTP
        log(f"  ├─ [OTP] Entering code: {otp}")

        # Dump all inputs for debugging
        try:
            inputs_info = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id, name: i.name, type: i.type,
                    maxlength: i.getAttribute('maxlength'),
                    autocomplete: i.getAttribute('autocomplete'),
                    visible: i.offsetParent !== null
                }));
            }""")
            log(f"  ├─ [OTP] Inputs on page: {inputs_info}")
        except Exception:
            pass

        otp_entered = False

        # Method 1: single OTP field
        for sel in ['input[autocomplete="one-time-code"]', 'input[name="otp"]', 'input#otp',
                    'input[aria-label*="code" i]', 'input[placeholder*="code" i]']:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    log(f"  ├─ [OTP] Using selector: {sel}")
                    el.click(force=True, timeout=8000)
                    time.sleep(0.3)
                    el.fill("")
                    for d in otp:
                        page.keyboard.type(d, delay=random.randint(60, 140))
                    otp_entered = True
                    break
            except Exception as e:
                log(f"  ├─ [OTP] {sel} failed: {str(e)[:60]}")
                continue

        # Method 2: multiple digit boxes
        if not otp_entered:
            try:
                boxes = page.query_selector_all('input[maxlength="1"]')
                if len(boxes) >= len(otp):
                    log(f"  ├─ [OTP] Using {len(boxes)} digit boxes")
                    boxes[0].click(force=True, timeout=8000)
                    for d in otp:
                        page.keyboard.type(d, delay=random.randint(60, 140))
                    otp_entered = True
            except Exception as e:
                log(f"  ├─ [OTP] Digit boxes failed: {str(e)[:60]}")

        # Method 3: blind keyboard typing
        if not otp_entered:
            log("  ├─ [OTP] Fallback: blind keyboard typing")
            for d in otp:
                page.keyboard.type(d, delay=random.randint(60, 140))
            otp_entered = True

        # Verify the digits actually landed in the boxes
        try:
            entered = page.evaluate("""() => {
                const boxes = Array.from(document.querySelectorAll('input[name="launch_code[]"], input[maxlength="1"]'));
                return boxes.map(b => b.value || '').join('');
            }""")
            log(f"  ├─ [OTP] Digits in boxes: '{entered}'")

            # If digits missing, set them directly via JS
            if entered.replace(" ", "") != otp:
                log("  ├─ [OTP] Digits mismatch — setting via JS...")
                page.evaluate("""(code) => {
                    const boxes = Array.from(document.querySelectorAll('input[name="launch_code[]"], input[maxlength="1"]'));
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    boxes.forEach((b, i) => {
                        if (i < code.length) {
                            setter.call(b, code[i]);
                            b.dispatchEvent(new Event('input', { bubbles: true }));
                            b.dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    });
                }""", otp)
                time.sleep(1)
        except Exception as e:
            log(f"  ├─ [OTP] Digit check failed: {str(e)[:70]}")

        # Click Continue / submit the verification form
        log("  ├─ [OTP] Submitting verification form...")
        try:
            res = page.evaluate("""() => {
                const btns = Array.from(document.querySelectorAll('button, input[type=submit]'));
                const btn = btns.find(b => {
                    const t = (b.textContent || b.value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return t === 'continue' || t === 'verify' || t === 'submit';
                });
                if (btn) {
                    btn.disabled = false;
                    btn.removeAttribute('disabled');
                    btn.click();
                    return 'clicked:' + (btn.textContent || btn.value || '').trim();
                }
                const form = document.querySelector('form[action*="verification"], form');
                if (form) {
                    if (typeof form.requestSubmit === 'function') form.requestSubmit();
                    else form.submit();
                    return 'form-submitted';
                }
                return 'nothing-found';
            }""")
            log(f"  ├─ [OTP] Submit: {res}")
        except Exception as e:
            log(f"  ├─ [OTP] Submit error: {str(e)[:80]}")
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass

        # Wait for verification to complete
        log("  ├─ [OTP] Waiting for verification...")
        verified = False
        for i in range(45):
            time.sleep(1)
            try:
                url = page.url
            except Exception:
                continue
            try:
                body_low = page.inner_text("body").lower()
            except Exception:
                body_low = ""

            # Success = we are no longer sitting on the verification/signup screen
            if "account_verifications" not in url and "signup" not in url and "github.com" in url:
                log(f"  ├─ [OTP] ✅ Left verification page — {url}")
                verified = True
                break

            # Sometimes the URL stays but the code boxes disappear (SPA transition)
            try:
                boxes_left = page.evaluate(
                    "() => document.querySelectorAll('input[name=\"launch_code[]\"]').length"
                )
            except Exception:
                boxes_left = None
            if boxes_left == 0:
                log("  ├─ [OTP] ✅ Code boxes gone — verification accepted")
                verified = True
                break
            # Only trust a rejection if the error text is actually VISIBLE
            # (GitHub keeps hidden validation strings in the DOM at all times)
            if i >= 6:
                try:
                    err = page.evaluate("""() => {
                        const pats = [
                            'incorrect', 'invalid', 'expired',
                            'try again', 'does not match', "didn't match"
                        ];
                        const nodes = Array.from(document.querySelectorAll(
                            '.flash-error, .error, [role="alert"], .js-flash-alert, .color-fg-danger'
                        ));
                        for (const n of nodes) {
                            if (n.offsetParent === null) continue;
                            const t = (n.innerText || '').trim().toLowerCase();
                            if (!t) continue;
                            if (pats.some(p => t.includes(p))) return t.slice(0, 200);
                        }
                        return null;
                    }""")
                except Exception:
                    err = None

                if err:
                    log(f"  ├─ [OTP] ❌ Code rejected: {err}")
                    break

            if i % 10 == 9:
                log(f"  ├─ [OTP] Still waiting... ({i+1}s) | URL: {url}")
                if i == 19:
                    try:
                        log(f"  ├─ [OTP] [DEBUG] Body: {page.inner_text('body')[:400]}")
                        boxes_now = page.evaluate("""() => {
                            const b = Array.from(document.querySelectorAll('input[name="launch_code[]"], input[maxlength="1"]'));
                            return b.map(x => x.value || '_').join('');
                        }""")
                        log(f"  ├─ [OTP] [DEBUG] Boxes now: '{boxes_now}'")
                    except Exception:
                        pass

        final_url = page.url
        log(f"  ├─ [OTP] Final URL: {final_url}")

        if not verified:
            body = page.inner_text("body")[:500]
            log(f"  └─ ❌ Verification did not complete")
            log(f"       URL: {final_url}")
            log(f"       Body: {body}")
            raise Exception(f"GitHub OTP verification failed — stuck at {final_url}")

        log("  └─ ✅ GitHub account created & verified!")
        return {
            "success": True,
            "email": email,
            "password": password,
            "username": username,
        }
