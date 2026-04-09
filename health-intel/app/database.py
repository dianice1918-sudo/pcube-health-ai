import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.env import load_app_env

load_app_env()

def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def _build_database_url() -> str:
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")
    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")

    if db_host and db_name and db_user is not None and db_password is not None:
        db_port = os.getenv("DB_PORT", "5432")
        db_driver = os.getenv("DB_DRIVER", "postgresql+psycopg2")
        user_part = quote_plus(db_user)
        password_part = quote_plus(db_password)
        return f"{db_driver}://{user_part}:{password_part}@{db_host}:{db_port}/{db_name}"

    direct_url = os.getenv("DATABASE_URL")
    if direct_url:
        return _normalize_database_url(direct_url)

    return "sqlite:///./health_intel.db"


DATABASE_URL = _build_database_url()
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
ALLOW_SQLITE_IN_PRODUCTION = os.getenv("ALLOW_SQLITE_IN_PRODUCTION", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if APP_ENV == "production" and DATABASE_URL.startswith("sqlite") and not ALLOW_SQLITE_IN_PRODUCTION:
    raise ValueError(
        "SQLite is disabled in production. Configure a PostgreSQL DATABASE_URL or set DB_* variables."
    )

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    """Dependency that yields a SessionLocal session and closes it in a finally block."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
