"""
Run this once to create all tables in your Neon database, and to verify
the connection actually works before building anything on top of it.

Usage:
    python init_db.py
"""

from database import engine, Base
import models  # noqa: F401 — importing registers the models with Base


def main():
    print("Attempting to connect to the database...", flush=True)
    try:
        with engine.connect() as conn:
            print("Connection successful.", flush=True)
    except Exception as e:
        print(f"\n!!! CONNECTION FAILED !!!\n{type(e).__name__}: {e}", flush=True)
        return

    print("Creating tables (if they don't already exist)...", flush=True)
    Base.metadata.create_all(bind=engine)
    print("Done. Tables created: users, resumes, resume_analyses", flush=True)


if __name__ == "__main__":
    main()
