"""
Pytest configuration. Sets a dummy MESH_API_KEY before any test module
imports main.py — main.py raises at import time if the key is missing,
and tests must never require (or accidentally use) a real key since every
API call in the test suite is mocked.

Also explicitly adds the backend/ directory (the parent of this tests/
folder) to sys.path, so `import main` resolves regardless of which OS or
directory pytest is invoked from. Without this, some pytest/OS
combinations fail with `ModuleNotFoundError: No module named 'main'`.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ.setdefault("MESH_API_KEY", "mesh_sk_test_dummy_key_do_not_use_for_real_calls")
