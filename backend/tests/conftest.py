"""
Pytest configuration. Sets dummy environment variables before any test
module imports main.py — main.py (via database.py and auth.py) raises at
import time if these are missing, and tests must never require real
credentials or a real database/API connection since every external call
in the test suite is mocked.

Note on DATABASE_URL: this dummy value lets SQLAlchemy's engine object be
created without error (engines connect lazily, not at creation time), but
any test that actually queries the database would fail against this fake
host. That's fine for the existing resume/skill-gap tests, which don't
touch the database. If you add tests for the auth endpoints, they'll need
either a real test database or mocking of the db session — flag this if
you get there and we'll set that up properly rather than pointing tests
at a throwaway fake connection string.

Also explicitly adds the backend/ directory (the parent of this tests/
folder) to sys.path, so `import main` resolves regardless of which OS or
directory pytest is invoked from.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("MESH_API_KEY", "mesh_sk_test_dummy_key_do_not_use_for_real_calls")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test_db_not_real")
os.environ.setdefault("JWT_SECRET_KEY", "test_only_secret_key_never_use_this_in_production_xyz123")
os.environ.setdefault("GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
