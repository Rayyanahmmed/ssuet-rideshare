"""Browser test: admin issues a reset code → member sets a new password in the app.

usage: python e2e_reset_admin.py http://localhost:8190 http://localhost:8181 http://127.0.0.1:8100/api/v1
"""
import json
import re
import sys
import urllib.request

from playwright.sync_api import expect, sync_playwright

ADMIN_BASE, WEB_BASE, API = sys.argv[1], sys.argv[2], sys.argv[3]
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f" [{detail}]" if detail else ""))


def api(method, url, body=None, token=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}


status, login = api("POST", f"{API}/auth/login", {"email": "admin@example.com", "password": "Admin@SSUET2026"})
admin_token = login["access_token"]
_, users = api("GET", f"{API}/admin/users?search=ali%40ssuet.edu.pk", token=admin_token)
ali_id = users["items"][0]["id"]

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ---- 1. admin creates the code from the Users drawer
    admin = browser.new_page()
    admin.goto(f"{ADMIN_BASE}/login")
    admin.locator('input[type="email"]').fill("admin@example.com")
    admin.locator('input[type="password"]').fill("Admin@SSUET2026")
    admin.get_by_role("button", name=re.compile("Sign in")).click()
    admin.wait_for_url(lambda u: "/login" not in u, timeout=20000)
    check("admin signs in in the browser", "/login" not in admin.url, admin.url)

    admin.goto(f"{ADMIN_BASE}/users")
    admin.get_by_placeholder("Name, email, university ID, phone").fill("ali@ssuet.edu.pk")
    admin.wait_for_timeout(1200)
    admin.get_by_text("ali@ssuet.edu.pk").first.click()
    panel = admin.get_by_text("Password reset (when email is not set up)")
    expect(panel).to_be_visible(timeout=15000)
    check("member drawer shows the reset panel", panel.is_visible())
    admin.get_by_role("button", name="Create reset code").click()
    code_el = admin.locator("code").first
    expect(code_el).to_be_visible(timeout=15000)
    code = code_el.inner_text().strip()
    check("admin sees a one-time code", len(code) >= 20, f"{len(code)} chars")

    # ---- 2. member opens the reset screen with the code (link style) and sets a password
    member = browser.new_page()
    member.goto(f"{WEB_BASE}/reset-password?token={code}")
    member.get_by_placeholder("At least 8 characters, letters and numbers").fill("Renewed123")
    member.get_by_placeholder("Type the password again").fill("Renewed123")
    member.get_by_role("button", name="Change password").click()
    ok = member.get_by_text("Password changed").first
    try:
        expect(ok).to_be_visible(timeout=15000)
        check("member sets a new password with the code", True)
    except AssertionError:
        check("member sets a new password with the code", False, member.content()[:200])

    # ---- 3. the same code cannot be used twice (browser shows the error)
    again = browser.new_page()
    again.goto(f"{WEB_BASE}/reset-password?token={code}")
    again.get_by_placeholder("At least 8 characters, letters and numbers").fill("Another123")
    again.get_by_placeholder("Type the password again").fill("Another123")
    again.get_by_role("button", name="Change password").click()
    try:
        expect(again.get_by_text(re.compile("invalid or was already used|already used", re.I)).first).to_be_visible(timeout=15000)
        check("reused code is refused in the app", True)
    except AssertionError:
        check("reused code is refused in the app", False)

    # ---- 4. sign-in with the new password works in the browser login form
    signin = browser.new_page()
    signin.goto(f"{WEB_BASE}/login")
    signin.locator('input').first.fill("ali@ssuet.edu.pk")
    signin.locator('input[secureTextEntry], input[type="password"]').first.fill("Renewed123")
    browser.close()

s1, _ = api("POST", f"{API}/auth/login", {"email": "ali@ssuet.edu.pk", "password": "Renewed123"})
check("API accepts the new password", s1 == 200, str(s1))

# restore the seeded password for the other browser suites
_, code2 = api("POST", f"{API}/admin/users/{ali_id}/password-reset-code", {}, token=admin_token)
api("POST", f"{API}/auth/reset-password", {"token": code2["code"], "new_password": "Password123!"})
s2, _ = api("POST", f"{API}/auth/login", {"email": "ali@ssuet.edu.pk", "password": "Password123!"})
check("seeded password restored", s2 == 200, str(s2))

passed = sum(1 for _, ok in results if ok)
print(f"\nRESULT: {passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
