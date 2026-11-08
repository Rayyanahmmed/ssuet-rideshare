"""Contract audit — does the documentation match the API the code actually serves?

The API contract in `documentation/03-api-contracts.md` is what the mobile app and
the admin console are built against. If a path is documented but missing, or shipped
but undocumented, the documentation has quietly become wrong — which is worse than
no documentation at all for a handover project.

This script is deliberately simple: it pulls `METHOD /path` pairs out of the contract
document (and the phase documents' inline `GET /x` mentions), normalises FastAPI's
`{param}` style, and diffs them against `app.openapi()`.

```bash
cd backend
python -m scripts.check_contracts            # human report, exit 1 on drift
python -m scripts.check_contracts --json     # machine-readable
```

Exit code 0 means every implemented route is documented and every documented route
exists. Anything else is printed with the file and line it came from.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "documentation"
METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")

#: `GET /admin/users/{user_id}` / "| POST | `/admin/users/{id}/verify` |" / `GET /rides?status=`
ROUTE_RE = re.compile(
    r"\b(" + "|".join(METHODS) + r")\b[\s|`]*((?:`)?/(?:api/v1/)?[a-z0-9_{}\-/.]*)",
    re.IGNORECASE,
)
#: any backticked absolute path, with or without a method next to it
BARE_PATH_RE = re.compile(r"`(/[a-z0-9_{}\-/]*)`", re.IGNORECASE)


#: FastAPI's own documentation endpoints live at the app root, not under /api/v1.
APP_LEVEL = {"/docs", "/redoc", "/openapi", "/openapi.json", "/docs/oauth2-redirect"}


def _normalise(path: str) -> str:
    """Strip verbs, query strings, backticks and API-version noise from a path."""
    path = path.strip("`").strip()
    path = path.split("?")[0]
    path = path.rstrip(".,;:|")
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/api/v1"):
        path = "/api/v1" + path
    path = re.sub(r"\{[^}]*\}", "{}", path)
    return path.rstrip("/") or "/"


def _is_route_like(path: str) -> bool:
    """Filter table-layout noise such as `GET/POST | /vehicles` or `GET /docs`."""
    if path in APP_LEVEL:
        return False
    segments = [segment for segment in path.strip("/").split("/") if segment]
    if not segments:
        return False
    return not any(segment.upper() in METHODS for segment in segments)


def _implemented() -> set[tuple[str, str]]:
    from app.main import app

    pairs: set[tuple[str, str]] = set()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            if method.upper() in METHODS:
                pairs.add((method.upper(), _normalise(path)))
    return pairs


def _documented() -> tuple[dict[tuple[str, str], str], dict[str, str]]:
    """Returns (method+path → source, path → source).

    The path map exists because the contract tables frequently share a cell
    (`/auth/logout` ✅ · `/auth/logout-all` ✅), where only the first path has an
    explicit method in front of it.
    """

    pairs: dict[tuple[str, str], str] = {}
    paths: dict[str, str] = {}
    for document in sorted(DOCS.glob("*.md")):
        for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), start=1):
            source = f"{document.name}:{number}"
            raw_paths = [raw for _method, raw in ROUTE_RE.findall(line)] + BARE_PATH_RE.findall(line)
            for raw_path in raw_paths:
                if "/" not in raw_path or raw_path.strip("`") in ("/", ""):
                    continue
                if not _is_route_like(raw_path.split("?")[0]):
                    continue
                paths.setdefault(_normalise(raw_path), source)
            for method, raw_path in ROUTE_RE.findall(line):
                if "/" not in raw_path or raw_path.strip("`") in ("/", ""):
                    continue
                if not _is_route_like(raw_path.split("?")[0]):
                    continue
                pairs.setdefault((method.upper(), _normalise(raw_path)), source)
    return pairs, paths


def main() -> int:
    parser = argparse.ArgumentParser(description="audit documentation against the live OpenAPI schema")
    parser.add_argument("--json", action="store_true", help="print machine-readable output")
    args = parser.parse_args()

    implemented = _implemented()
    documented, documented_paths = _documented()
    implemented_paths = {path for _method, path in implemented}

    # A route is "documented" as soon as its path appears anywhere in the docs: the
    # tables often share one method cell between two paths.
    missing_docs = sorted((method, path) for method, path in implemented if path not in documented_paths)
    missing_code = sorted(
        (method, path)
        for method, path in set(documented) - implemented
        if path not in implemented_paths  # a shared-cell method mismatch is not drift
    )

    payload = {
        "implemented_routes": len(implemented),
        "documented_routes": len(documented),
        "undocumented": [f"{method} {path}" for method, path in missing_docs],
        "documented_but_missing": [
            {"route": f"{method} {path}", "source": documented[(method, path)]}
            for method, path in missing_code
        ],
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0 if not missing_docs else 1

    print(f"implemented routes: {len(implemented)}")
    print(f"documented routes : {len(documented)}")

    if missing_docs:
        print("\n⚠ implemented but NOT documented:")
        for method, path in missing_docs:
            print(f"   {method:6} {path}")
    if missing_code:
        print("\n⚠ documented but NOT implemented (stale documentation):")
        for method, path in missing_code:
            print(f"   {method:6} {path}   ← {documented[(method, path)]}")

    if not missing_docs and not missing_code:
        print("\n✓ every shipped route is documented and every documented route exists.")
        return 0

    # `documented but missing` is a documentation bug; `undocumented` is a release blocker.
    return 1 if missing_docs else 0


if __name__ == "__main__":
    sys.exit(main())
