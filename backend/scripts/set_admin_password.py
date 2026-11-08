"""Create an administrator account, or reset the password of an existing one.

    python -m scripts.set_admin_password --email admin@example.com --password 'Admin@SSUET2026'
    python -m scripts.set_admin_password --list

Why this exists: the startup bootstrap (`ADMIN_BOOTSTRAP_ENABLED=true`) creates the admin
**only once** — if the account already exists it logs "password untouched", so editing
ADMIN_PASSWORD in `backend/.env` afterwards changes nothing. This script is the supported way
to change the password of a running installation (§3, §22).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.models import AccountStatus, Base, User, UserRole, VerificationStatus  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.schemas.auth import _validate_password_strength  # noqa: E402


def list_admins() -> int:
    with SessionLocal() as db:
        admins = db.scalars(select(User).where(User.role == UserRole.ADMIN)).all()
        if not admins:
            print("No administrator accounts exist yet.")
            return 1
        print(f"{len(admins)} administrator account(s):")
        for admin in admins:
            state = "active" if admin.account_status is AccountStatus.ACTIVE else admin.account_status.value
            print(f"  {admin.email:<32} {state:<10} {admin.full_name}")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Create or re-password an administrator account.")
    parser.add_argument("--email", help="admin email (defaults to ADMIN_EMAIL from .env)")
    parser.add_argument("--password", help="new password (8-64 chars, not a common one)")
    parser.add_argument("--name", default="System Administrator")
    parser.add_argument("--list", action="store_true", help="show existing administrator accounts")
    args = parser.parse_args(argv)

    if args.list:
        return list_admins()

    from app.core.config import settings

    email = (args.email or settings.ADMIN_EMAIL or "").strip().lower()
    password = args.password or ""
    if not email or not password:
        parser.error("both --email and --password are required (or set ADMIN_EMAIL in .env)")

    try:
        _validate_password_strength(password)
    except ValueError as exc:
        print(f"Rejected: {exc}")
        return 1

    Base.metadata.create_all(bind=engine)  # a fresh SQLite file must exist before the insert

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                email=email,
                password_hash=hash_password(password),
                phone=f"03{abs(hash(email)) % 10**9:09d}",
                full_name=args.name,
                role=UserRole.ADMIN,
                department="University Administration",
                university_id="SSUET-ADMIN-0001",
                is_university_email=True,
                verification_status=VerificationStatus.VERIFIED,
                account_status=AccountStatus.ACTIVE,
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(password)
            user.role = UserRole.ADMIN
            user.account_status = AccountStatus.ACTIVE
            user.verification_status = VerificationStatus.VERIFIED
            action = "password updated"

        db.commit()

    print(f"Admin {action}: {email}")
    print("Sign in at http://localhost:5173 with this email and the password you just set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
