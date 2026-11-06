import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

from .runtime import runtime_directory


def password_hash(password):
    salt = secrets.token_hex(16)
    return salt + ":" + hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()


def verify_password(password, stored):
    try:
        salt, digest = stored.split(":")
        if len(salt) != 32 or len(digest) != 128:
            return False
        computed = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1, dklen=64).hex()
        return hmac.compare_digest(digest, computed)
    except (ValueError, TypeError):
        return False


def session_key():
    if os.getenv("SESSION_SECRET"):
        if len(os.environ["SESSION_SECRET"]) < 32:
            raise ValueError("SESSION_SECRET must contain at least 32 characters")
        return os.environ["SESSION_SECRET"]
    path = runtime_directory() / "session.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    return path.read_text().strip()


def sign(payload, key):
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return raw + "." + hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest()


def unsign(value, key):
    try:
        raw, signature = value.rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(key.encode(), raw.encode(), hashlib.sha256).hexdigest(), signature):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        return payload if payload.get("exp", 0) > time.time() else None
    except (ValueError, TypeError, AttributeError):
        return None


if __name__ == "__main__" and sys.argv[1:] == ["hash-password"]:
    password = getpass.getpass("Studio password (12+ characters): ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters")
    print(password_hash(password))
