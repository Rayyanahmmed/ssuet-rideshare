"""Web check: a member's profile photo renders (fetched with the token, shown from a blob URL).

usage: python e2e_photo_web.py http://localhost:8181
"""
import re
import sys

from playwright.sync_api import expect, sync_playwright

WEB = sys.argv[1]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(f"{WEB}/login")
    page.locator('input').first.fill("ali@ssuet.edu.pk")
    page.locator('input[type="password"]').first.fill("Password123!")
    page.get_by_role("button", name=re.compile("Sign in|Log in", re.I)).first.click()
    page.wait_for_timeout(3000)
    page.goto(f"{WEB}/profile")
    try:
        expect(page.locator('img[src^="blob:"]').first).to_be_visible(timeout=15000)
        ok = True
    except AssertionError:
        ok = False
    print(("PASS" if ok else "FAIL"), "profile photo renders on web (blob URL, token-authenticated)")
    browser.close()
sys.exit(0 if ok else 1)
