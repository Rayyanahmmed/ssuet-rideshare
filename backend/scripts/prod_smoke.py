"""Production-simulation smoke test against a running API (no mocks).

usage: python prod_smoke.py http://127.0.0.1:8100/api/v1 http://localhost:8190
"""
import io
import sys

import httpx
from PIL import Image

API, ADMIN_ORIGIN = sys.argv[1].rstrip("/"), sys.argv[2]
results: list[tuple[str, bool, str]] = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""))


c = httpx.Client(timeout=30)

# 1. liveness / readiness (readiness checks the database)
r = c.get(f"{API}/health"); check("health 200", r.status_code == 200, str(r.status_code))
r = c.get(f"{API}/health/ready"); check("readiness (DB reachable)", r.status_code == 200, r.text[:120])

# 2. CORS: allowed admin origin gets header, foreign origin does not
r = c.options(f"{API}/auth/login", headers={"Origin": ADMIN_ORIGIN, "Access-Control-Request-Method": "POST"})
check("CORS allows admin origin", r.headers.get("access-control-allow-origin") == ADMIN_ORIGIN, r.headers.get("access-control-allow-origin", ""))
r = c.options(f"{API}/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
check("CORS refuses foreign origin", r.headers.get("access-control-allow-origin") != "https://evil.example")

# 3. security: API docs are hidden in production; unauthenticated admin is 401
r = c.get(f"{API}/admin/dashboard"); check("admin route without token → 401", r.status_code == 401, str(r.status_code))
check("API docs hidden in production (/docs)", c.get(API.rsplit("/api/v1", 1)[0] + "/docs").status_code == 404)
check("OpenAPI schema hidden in production", c.get(API.rsplit("/api/v1", 1)[0] + "/openapi.json").status_code == 404)
r = c.get(f"{API}/users/me"); check("member route without token → 401", r.status_code in (401, 403), str(r.status_code))

# 4. student sign-in
r = c.post(f"{API}/auth/login", json={"email": "ali@ssuet.edu.pk", "password": "Password123!"})
check("student login (seeded)", r.status_code == 200, str(r.status_code))
stu = r.json()
stu_h = {"Authorization": f"Bearer {stu['access_token']}"}

# 5. profile photo upload → stored in Postgres bytea, served back
buf = io.BytesIO(); Image.new("RGB", (800, 600), (30, 120, 200)).save(buf, "JPEG", quality=90)
r = c.post(f"{API}/users/me/photo", headers=stu_h, files={"file": ("me.jpg", buf.getvalue(), "image/jpeg")})
check("photo upload accepted", r.status_code in (200, 201), f"{r.status_code} {r.text[:100]}")
me = c.get(f"{API}/users/me", headers=stu_h).json()
uid = me.get("id") or me.get("user", {}).get("id")
r = c.get(f"{API}/users/{uid}/photo", headers=stu_h)
check("photo served back (full)", r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"), f"{r.status_code} {len(r.content)} bytes")
r = c.get(f"{API}/users/{uid}/photo?size=thumb", headers=stu_h)
check("photo served back (thumb)", r.status_code == 200 and len(r.content) > 0, f"{r.status_code} {len(r.content)} bytes")

# 6. admin sign-in + admin reset code fallback end-to-end
r = c.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "Admin@SSUET2026"})
check("admin login (bootstrap account)", r.status_code == 200, str(r.status_code))
adm_h = {"Authorization": f"Bearer {r.json()['access_token']}"}

r = c.get(f"{API}/admin/dashboard", headers=adm_h); check("admin dashboard", r.status_code == 200, str(r.status_code))
r = c.get(f"{API}/admin/integrations/maps", headers=adm_h); check("admin Map API settings", r.status_code == 200, str(r.status_code))
r = c.get(f"{API}/admin/integrations/app-download", headers=adm_h); check("admin APK settings", r.status_code == 200, str(r.status_code))

r = c.post(f"{API}/admin/users/{uid}/password-reset-code", headers=adm_h, json={})
check("admin creates reset code", r.status_code == 200 and len(r.json().get("code", "")) >= 20, str(r.status_code))
code = r.json()["code"]
r = c.post(f"{API}/auth/reset-password", json={"token": code, "new_password": "Changed123"})
check("member resets password with code", r.status_code == 200, str(r.status_code))
check("old password rejected after reset", c.post(f"{API}/auth/login", json={"email": "ali@ssuet.edu.pk", "password": "Password123!"}).status_code == 401)
check("new password accepted", c.post(f"{API}/auth/login", json={"email": "ali@ssuet.edu.pk", "password": "Changed123"}).status_code == 200)
check("old session revoked after reset", c.get(f"{API}/users/me", headers=stu_h).status_code == 401)
r = c.post(f"{API}/auth/reset-password", json={"token": code, "new_password": "Again12345"})
check("reset code is single-use", r.status_code == 422, str(r.status_code))

# 7. restore the seeded password so the browser tests can sign in
tok = c.post(f"{API}/auth/forgot-password", json={"email": "ali@ssuet.edu.pk"})
check("forgot-password endpoint answers 202 (no SMTP → logged)", tok.status_code == 202, str(tok.status_code))
code2 = c.post(f"{API}/admin/users/{uid}/password-reset-code", headers=adm_h, json={}).json()["code"]
c.post(f"{API}/auth/reset-password", json={"token": code2, "new_password": "Password123!"})
check("seeded password restored", c.post(f"{API}/auth/login", json={"email": "ali@ssuet.edu.pk", "password": "Password123!"}).status_code == 200)

# 8. APK download endpoint is public and reports the empty state
r = c.get(f"{API}/app/download"); check("public APK endpoint", r.status_code == 200 and "available" in r.json(), r.text[:100])

passed = sum(1 for _, ok, _ in results if ok)
print(f"\nRESULT: {passed}/{len(results)} passed")
sys.exit(0 if passed == len(results) else 1)
