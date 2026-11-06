import base64
import hashlib
import hmac
import secrets


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password: str) -> str:
    if not 12 <= len(password) <= 256:
        raise ValueError("operator password must contain 12..256 characters")
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt + derived).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        if not encoded.startswith("scrypt$") or len(password) > 256:
            return False
        raw = base64.b64decode(encoded.split("$", 1)[1], validate=True)
        if len(raw) != 48:
            return False
        derived = hashlib.scrypt(password.encode(), salt=raw[:16], n=16384, r=8, p=1, dklen=32)
        return hmac.compare_digest(derived, raw[16:])
    except (ValueError, TypeError):
        return False
