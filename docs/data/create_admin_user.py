#!/usr/bin/env python3
"""Create or update a sign-in account for the Admin review page (docs/review.html). DEMO ONLY.

Accounts live in docs/data/admin_users.json as a salted PBKDF2-SHA256 hash (the password itself is never stored).
GitHub Pages has no server, so the page checks the hash in the browser: this keeps casual visitors out of the review
page during a demo, but it is NOT real security (anyone who reads the code can bypass it). Don't reuse a real password.

    python3 docs/data/create_admin_user.py --username analyst --name "Risk analyst"      # asks for the password
    python3 docs/data/create_admin_user.py --username analyst --remove
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import secrets
from pathlib import Path

USERS = Path(__file__).resolve().parent / "admin_users.json"
ITERATIONS = 150_000


def hash_password(password: str, salt_hex: str, iterations: int = ITERATIONS) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations).hex()


def load(path=USERS) -> dict:
    return json.loads(path.read_text()) if path.exists() else {
        "_note": "Demo sign-in for docs/review.html. Salted PBKDF2-SHA256 hashes only; checked in the browser, so this is "
                 "not real security. Manage with docs/data/create_admin_user.py.", "users": []}


def upsert(data: dict, username: str, password: str, name: str = "", role: str = "analyst") -> dict:
    salt = secrets.token_hex(16)
    user = {"username": username.strip().lower(), "name": name or username, "role": role, "salt": salt,
            "iterations": ITERATIONS, "hash": hash_password(password, salt)}
    data["users"] = [u for u in data["users"] if u["username"] != user["username"]] + [user]
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--username", required=True)
    ap.add_argument("--name", default="")
    ap.add_argument("--role", default="analyst")
    ap.add_argument("--remove", action="store_true")
    ap.add_argument("--file", type=Path, default=USERS)
    a = ap.parse_args(argv)
    data = load(a.file)
    if a.remove:
        data["users"] = [u for u in data["users"] if u["username"] != a.username.strip().lower()]
        print(f"removed {a.username}")
    else:
        pw = getpass.getpass("Password: ")
        if len(pw) < 8 or pw != getpass.getpass("Again: "):
            raise SystemExit("Passwords must match and be at least 8 characters.")
        upsert(data, a.username, pw, a.name, a.role)
        print(f"saved {a.username}")
    a.file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
