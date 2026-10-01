from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
import sys
from datetime import datetime, timezone


def pbkdf2(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 240_000
    ).hex()


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: seed_test_account.py <sqlite-db>")

    db_path = sys.argv[1]
    email = os.getenv("TMI_SEED_TEST_EMAIL", "").strip().lower()
    password = os.getenv("TMI_SEED_TEST_PASSWORD", "")
    display_name = os.getenv("TMI_SEED_TEST_DISPLAY_NAME", "TMI Test User").strip()
    user_id = os.getenv("TMI_SEED_TEST_USER_ID", "tmi-test-user-2026").strip()
    profile_slug = os.getenv("TMI_SEED_TEST_PROFILE_SLUG", "tmi-test-user").strip()

    if not email or not password:
        print("[seed-test-account] env not configured; skipping")
        return 0

    now = datetime.now(timezone.utc).isoformat()
    salt = hashlib.sha256(("tmi-test-salt:" + email).encode("utf-8")).hexdigest()[:32]
    pwd_hash = pbkdf2(password, salt)
    admin_secret = os.getenv("AUDIOID_ADMIN_API_TOKEN", "").strip()
    if admin_secret:
        stable_token = base64.urlsafe_b64encode(
            hmac.new(
                admin_secret.encode("utf-8"),
                f"tmi-seed-session:{user_id}".encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("ascii").rstrip("=")
        bootstrap_token_hash = hashlib.sha256(stable_token.encode("utf-8")).hexdigest()
    else:
        bootstrap_token_hash = hashlib.sha256(("bootstrap:" + user_id).encode("utf-8")).hexdigest()

    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS tmi_accounts (
                user_id VARCHAR PRIMARY KEY,
                email VARCHAR NOT NULL UNIQUE,
                password_salt VARCHAR(64) NOT NULL,
                password_hash VARCHAR(128) NOT NULL,
                profile_slug VARCHAR NOT NULL UNIQUE,
                language VARCHAR NOT NULL DEFAULT 'vi',
                full_listens_remaining INTEGER NOT NULL DEFAULT 5,
                created_at VARCHAR NOT NULL
            )"""
        )

        existing_user = cur.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if existing_user is None:
            cur.execute(
                """INSERT INTO users(
                    id, display_name, role, api_token_sha256, created_at, disabled
                ) VALUES (?, ?, 'user', ?, ?, 0)""",
                (user_id, display_name, bootstrap_token_hash, now),
            )
        else:
            cur.execute(
                """UPDATE users
                   SET display_name = ?, role = 'user', disabled = 0,
                       api_token_sha256 = ?
                   WHERE id = ?""",
                (display_name, bootstrap_token_hash, user_id),
            )

        existing_account = cur.execute(
            "SELECT user_id FROM tmi_accounts WHERE user_id = ? OR email = ?",
            (user_id, email),
        ).fetchone()

        if existing_account is None:
            cur.execute(
                """INSERT INTO tmi_accounts(
                    user_id, email, password_salt, password_hash, profile_slug,
                    language, full_listens_remaining, created_at
                ) VALUES (?, ?, ?, ?, ?, 'vi', 5, ?)""",
                (user_id, email, salt, pwd_hash, profile_slug, now),
            )
        else:
            cur.execute(
                """UPDATE tmi_accounts
                   SET email = ?, password_salt = ?, password_hash = ?,
                       profile_slug = ?, language = 'vi'
                   WHERE user_id = ?""",
                (email, salt, pwd_hash, profile_slug, user_id),
            )

        con.commit()
        print(f"[seed-test-account] ready: {email}")
    finally:
        con.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
