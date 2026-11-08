#!/usr/bin/env python3
"""End-to-end browser test of the WEB build of the app (Playwright + Chromium).

Prerequisites
  1. API running:        cd backend && uvicorn app.main:app --port 8000
  2. Web build served:   npx expo export -p web  (with EXPO_PUBLIC_API_URL=http://127.0.0.1:8000/api/v1)
                         python3 serve dist on http://localhost:8081 (SPA fallback)
  3. pip install playwright && playwright install chromium

Usage: python3 scripts/e2e-web.py [--base http://localhost:8081] [--api http://127.0.0.1:8000/api/v1]
Exit code 1 if any check fails. Screenshots go to ./e2e-shots/.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import Page, sync_playwright

ADMIN = ("admin@example.com", "Admin@SSUET2026")
STUDENT = ("ali@ssuet.edu.pk", "Password123!")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not ok else ""))


def api(method: str, url: str, body: dict | None = None, token: str | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def admin_token(api_base: str) -> str:
    return api("POST", f"{api_base}/auth/login", {"email": ADMIN[0], "password": ADMIN[1]})["access_token"]


def shot(page: Page, name: str) -> None:
    os.makedirs("e2e-shots", exist_ok=True)
    page.screenshot(path=f"e2e-shots/{name}.png", full_page=False)


def path_of(page: Page) -> str:
    return re.sub(r"^https?://[^/]+", "", page.url).split("?")[0] or "/"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8081")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    args = parser.parse_args()
    base, api_base = args.base.rstrip("/"), args.api.rstrip("/")

    console_errors: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 420, "height": 860})
        page = context.new_page()
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)

        # Start from a known state: withdraw any APK link published by an earlier run.
        token = admin_token(api_base)
        api("PUT", f"{api_base}/admin/integrations/app-download", {"url": "", "version": ""}, token)

        # ---- 1. protected deep link while signed out is redirected to Welcome
        page.goto(f"{base}/my-rides")
        page.wait_for_timeout(2500)
        check("signed-out deep link /my-rides → Welcome", path_of(page) in ("/welcome", "/(auth)/welcome"), path_of(page))
        shot(page, "01-welcome-redirect")

        # ---- 2. Welcome screen: no APK published yet → no download button
        dl_button = page.get_by_text("Download Android app")
        check("no APK published → no download button", dl_button.count() == 0)

        # ---- 3. Admin publishes an APK link (no redeploy) → button appears on reload
        api(
            "PUT",
            f"{api_base}/admin/integrations/app-download",
            {"url": "https://expo.dev/artifacts/eas/ssuet-test.apk", "version": "1.0.4"},
            token,
        )
        page.goto(f"{base}/welcome")
        page.wait_for_timeout(2500)
        dl_button = page.get_by_text("Download Android app")
        check("published APK → download button shows version", dl_button.count() > 0 and "1.0.4" in page.content())
        shot(page, "02-welcome-with-apk")

        # ---- 4. Onboarding navigation: Continue through slides, then Get started → signup
        for _ in range(4):
            cont = page.get_by_text("Continue", exact=True)
            if cont.count() == 0:
                break
            cont.first.click()
            page.wait_for_timeout(400)
        page.get_by_text("Get started", exact=True).first.click()
        page.wait_for_timeout(1500)
        check("Get started → signup screen", path_of(page).endswith("/signup"), path_of(page))
        shot(page, "03-signup")

        # ---- 5. Sign-in link → login screen (ghost link on welcome)
        page.goto(f"{base}/welcome")
        page.wait_for_timeout(2000)
        page.get_by_text("Sign in", exact=False).last.click()
        page.wait_for_timeout(1500)
        check("Welcome 'Sign in' link → login screen", path_of(page).endswith("/login"), path_of(page))

        # ---- 6. Login with a real student account → tabs (Home)
        page.get_by_placeholder("yourname@ssuet.edu.pk").fill(STUDENT[0])
        page.get_by_placeholder("Your password").fill(STUDENT[1])
        page.get_by_role("button", name="Sign in").first.click()
        page.wait_for_timeout(4000)
        check("login → Home tabs", path_of(page) in ("/", "/(tabs)", "/(tabs)/index"), path_of(page))
        shot(page, "04-home")

        # ---- 7. Every tab opens without an "unmatched route" error
        for tab in ("explore", "publish", "my-rides", "profile"):
            page.goto(f"{base}/{tab}")
            page.wait_for_timeout(2000)
            body = page.inner_text("body")
            check(f"tab /{tab} renders", "Unmatched Route" not in body and "Page could not be found" not in body)
        shot(page, "05-profile")

        # ---- 8. Stack screen with history: open Chats from Home, Back returns
        page.goto(f"{base}/")
        page.wait_for_timeout(2500)
        page.goto(f"{base}/chats")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="Go back").first.click()
        page.wait_for_timeout(1500)
        check("Chats back control leaves the screen (no dead end)", path_of(page) != "/chats", path_of(page))

        # ---- 9. Direct deep link to a stack screen (no history) → back falls back to Home
        page.goto(f"{base}/chats")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name="Go back").first.click()
        page.wait_for_timeout(1500)
        check("no history → back falls back to Home (not stuck)", path_of(page) in ("/", "/(tabs)"), path_of(page))

        # ---- 10. Publish wizard step 2 embeds the editable map (WebMap → MapSurface iframe on web)
        page.goto(f"{base}/publish")
        page.wait_for_timeout(4000)
        page.get_by_text("SSUET → Home", exact=True).first.click()
        page.get_by_text("Continue", exact=True).first.click()
        page.wait_for_timeout(3000)
        iframes = page.locator("iframe[title='Map']")
        check("publish step shows the map iframe", iframes.count() > 0)
        if iframes.count() > 0:
            frame = iframes.first.element_handle().content_frame()
            tiles_ok = False
            try:
                frame.wait_for_selector("img", timeout=15000)
                # wait until at least one tile has really decoded (not just been inserted)
                frame.wait_for_function(
                    "() => Array.from(document.images).some(i => i.complete && i.naturalWidth > 0)",
                    timeout=15000,
                )
                tiles_ok = True
            except Exception:
                tiles_ok = False
            check("map iframe loads tiles from the API proxy", tiles_ok)
        shot(page, "06-publish-map")

        browser.close()

    real_errors = [e for e in console_errors if "favicon" not in e.lower() and "Failed to load resource" not in e]
    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)} passed · {len(failed)} failed · {len(real_errors)} console errors")
    if real_errors[:5]:
        print("sample console errors:", *real_errors[:5], sep="\n  ")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
