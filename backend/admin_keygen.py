"""CLI tool to generate a cryptographically secure admin key and its SHA-256 hash.

Usage:
    python -m backend.admin_keygen
"""

import hashlib
import secrets


def generate_admin_credentials() -> tuple[str, str]:
    """Generate a high-entropy URL-safe token and its hex-encoded SHA-256 digest."""
    plain_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(plain_key.encode("utf-8")).hexdigest()
    return plain_key, key_hash


def main() -> None:
    plain_key, key_hash = generate_admin_credentials()
    print("=" * 65)
    print("Mail CoastGuard — Admin Key Generator")
    print("=" * 65)
    print("\n[!] Keep the Plain Secret Key safe. It will NEVER be shown again:\n")
    print(f"    Secret Key:  {plain_key}\n")
    print("[!] Add the following hash to your .env file:\n")
    print(f"    ADMIN_API_KEY_SHA256={key_hash}")
    print("    ADMIN_API_ENABLED=true\n")
    print("=" * 65)


if __name__ == "__main__":
    main()
