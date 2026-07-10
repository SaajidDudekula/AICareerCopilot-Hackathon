"""
Core authentication logic: password hashing, JWT creation/verification,
and a basic in-memory login-attempt rate limiter.

Security choices, explained:
- Passwords are hashed with bcrypt (via passlib) — never stored or logged
  in plain text, anywhere.
- Two-token pattern: short-lived access tokens (used on every request) and
  longer-lived refresh tokens (used only to get a new access token). If an
  access token leaks, the exposure window is short.
- JWTs are signed with HS256 using a secret from .env — never hardcoded.
- Login attempts are rate-limited per email to slow down brute-force
  guessing. This is in-memory only (resets on server restart, not shared
  across multiple server instances) — fine for a single-instance MVP;
  swap for Redis-backed limiting before running multiple backend instances.
"""

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database import get_db
import models

# --- Config (from .env — never hardcode secrets) ---
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "change_this_to_a_long_random_string":
    raise RuntimeError(
        "JWT_SECRET_KEY is not set to a real secret. Generate one (e.g. "
        "`python -c \"import secrets; print(secrets.token_urlsafe(64))\"`) "
        "and put it in your .env file."
    )

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

pwd_context = None  # no longer used — kept as None so any stray reference fails loudly
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# --- Password hashing ---
# Using the `bcrypt` library directly rather than passlib: passlib is
# effectively unmaintained and has a known incompatibility with bcrypt
# 4.x/5.x (it can't read the version string it expects, and mis-detects
# bcrypt's 72-byte input limit as a crash instead of a clean truncation).
# Calling bcrypt directly avoids this entirely and is one less dependency.

def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


# --- JWT creation ---

def _create_token(data: dict, expires_delta: timedelta, token_type: str) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire, "type": token_type})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        "refresh",
    )


def decode_token(token: str, expected_type: str) -> str:
    """Returns the user_id (sub claim) if the token is valid and of the
    expected type. Raises HTTPException(401) otherwise."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        if user_id is None or token_type != expected_type:
            raise credentials_exception
        return user_id
    except JWTError:
        raise credentials_exception


# --- FastAPI dependency: get the current logged-in user ---

def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = decode_token(token, expected_type="access")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )
    return user


# --- Basic in-memory login rate limiter ---
# NOTE: in-memory only — resets on restart, not shared across multiple
# server processes/instances. Adequate for a single-instance MVP; replace
# with Redis-backed limiting before scaling horizontally.

_failed_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60  # 15 minutes


def check_rate_limit(email: str):
    now = time.time()
    attempts = _failed_attempts.get(email, [])
    # Drop attempts older than the lockout window
    attempts = [t for t in attempts if now - t < LOCKOUT_WINDOW_SECONDS]
    _failed_attempts[email] = attempts

    if len(attempts) >= MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in "
                   f"{LOCKOUT_WINDOW_SECONDS // 60} minutes.",
        )


def record_failed_attempt(email: str):
    now = time.time()
    _failed_attempts.setdefault(email, []).append(now)


def clear_failed_attempts(email: str):
    _failed_attempts.pop(email, None)
