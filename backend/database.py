"""
Database connection setup for AI Career Copilot.

Uses SQLAlchemy with a PostgreSQL connection (Neon). Reads DATABASE_URL
from environment variables (.env) — never hardcode credentials here.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to your .env file — "
        "get the connection string from your Neon project dashboard."
    )

# Neon (and most managed Postgres providers) require SSL, which is already
# encoded in the connection string via sslmode=require, so no extra
# connect_args needed here.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a database session and ensures it's
    closed after the request, even if an error occurs."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
