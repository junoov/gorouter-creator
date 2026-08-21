"""
Noov email (mail.noov.app) — create mailbox and read inbox
"""
import os
import random
import string
import requests


NOOV_API_BASE = "https://mail.noov.app"


def _random_string(length=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def create_noov_mailbox(cookie: str, api_base: str = None) -> dict:
    """
    Create a new mailbox on mail.noov.app
    Returns: {"email": "xxx@noov.app", "user_id": "uuid"}
    """
    api_base = api_base or os.environ.get("NOOV_API_BASE", NOOV_API_BASE)
    cookie_header = cookie if cookie.startswith("mailflare_session=") else f"mailflare_session={cookie}"

    username = _random_string(8 + random.randint(0, 4))

    res = requests.post(
        f"{api_base}/api/users",
        json={"username": username},
        headers={
            "Content-Type": "application/json",
            "cookie": cookie_header,
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "origin": api_base,
            "referer": f"{api_base}/users",
        },
        timeout=15,
    )
    res.raise_for_status()
    data = res.json()

    if not data.get("ok") or not data.get("user"):
        raise Exception(f"noov create mailbox failed: {str(data)[:200]}")

    return {
        "email": data["user"]["email"],
        "user_id": data["user"]["id"],
    }


def read_noov_inbox(cookie: str, user_id: str, api_base: str = None) -> list:
    """
    Read inbox for a noov mailbox
    Returns list of {"from", "subject", "body"}
    """
    api_base = api_base or os.environ.get("NOOV_API_BASE", NOOV_API_BASE)
    cookie_header = cookie if cookie.startswith("mailflare_session=") else f"mailflare_session={cookie}"

    headers = {
        "accept": "application/json",
        "cookie": cookie_header,
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "origin": api_base,
        "referer": f"{api_base}/users",
    }

    res = requests.get(
        f"{api_base}/api/users/{user_id}/inbox",
        headers=headers,
        timeout=10,
    )
    res.raise_for_status()

    emails = res.json().get("emails", [])
    results = []

    for msg in emails:
        sender = msg.get("sender", "")
        subject = msg.get("subject", "")
        body = msg.get("snippet", "")

        msg_id = msg.get("id")
        if msg_id:
            try:
                full_res = requests.get(
                    f"{api_base}/api/users/{user_id}/emails/{msg_id}",
                    headers=headers,
                    timeout=10,
                )
                full = full_res.json().get("email", {})
                body = full.get("bodyText", "") or full.get("bodyHtml", "") or body
            except Exception:
                pass

        results.append({"from": sender, "subject": subject, "body": body})

    return results


def find_noov_user_id(cookie: str, email: str, api_base: str = None):
    """Look up an existing mailbox id by its email address."""
    api_base = api_base or os.environ.get("NOOV_API_BASE", NOOV_API_BASE)
    cookie_header = cookie if cookie.startswith("mailflare_session=") else f"mailflare_session={cookie}"

    res = requests.get(
        f"{api_base}/api/users",
        headers={
            "accept": "application/json",
            "cookie": cookie_header,
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "origin": api_base,
            "referer": f"{api_base}/users",
        },
        timeout=15,
    )
    res.raise_for_status()

    for u in res.json().get("users", []):
        if (u.get("email") or "").lower() == email.lower():
            return u.get("id")
    return None
