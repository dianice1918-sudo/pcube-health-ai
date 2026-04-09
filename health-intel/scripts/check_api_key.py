import sys
import hashlib
from pathlib import Path

# Ensure project root is on sys.path so `app` package is importable when run from different CWDs
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from app.database import SessionLocal
from app.models import ApiKey


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def check_key(raw_key: str):
    key_hash = hash_api_key(raw_key.strip())
    db = SessionLocal()
    try:
        api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash).first()
        if not api_key:
            print("API key not found or invalid.")
            return 2
        print(f"API key found: id={api_key.id}, name={api_key.name}, tenant_id={api_key.tenant_id}")
        print(f"  key_prefix: {api_key.key_prefix}")
        print(f"  is_active: {api_key.is_active}")
        print(f"  created_at: {api_key.created_at}")
        print(f"  last_used_at: {api_key.last_used_at}")
        if not api_key.is_active:
            print("Status: INACTIVE (revoked)")
            return 3
        print("Status: ACTIVE")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_api_key.py <API_KEY>")
        sys.exit(1)
    raw = sys.argv[1]
    sys.exit(check_key(raw))
