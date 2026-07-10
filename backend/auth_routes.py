"""
Authentication endpoints: register, login (email/password), Google OAuth
login, token refresh, and a protected "who am I" endpoint.

Mount this router in main.py:
    from auth_routes import router as auth_router
    app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
"""

import os
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from database import get_db
import models
import schemas
import auth

router = APIRouter()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


@router.post("/register", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == payload.email).first()
    if existing:
        # Deliberately generic — don't confirm/deny which emails exist in
        # the system to an unauthenticated caller.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not register with these details.",
        )

    user = models.User(
        name=payload.name,
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        auth_provider="password",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token = auth.create_access_token(str(user.id))
    refresh_token = auth.create_refresh_token(str(user.id))

    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    auth.check_rate_limit(payload.email)

    user = db.query(models.User).filter(models.User.email == payload.email).first()

    # Same generic error whether the email doesn't exist or the password
    # is wrong — don't leak which one it was.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password.",
    )

    if user is None or user.auth_provider != "password" or user.password_hash is None:
        auth.record_failed_attempt(payload.email)
        raise invalid_credentials

    if not auth.verify_password(payload.password, user.password_hash):
        auth.record_failed_attempt(payload.email)
        raise invalid_credentials

    auth.clear_failed_attempts(payload.email)

    access_token = auth.create_access_token(str(user.id))
    refresh_token = auth.create_refresh_token(str(user.id))

    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/google", response_model=schemas.TokenResponse)
def google_login(payload: schemas.GoogleAuthRequest, db: Session = Depends(get_db)):
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google login is not configured on this server.",
        )

    try:
        # This call verifies the token's signature against Google's public
        # keys AND checks it was issued for our specific client ID — this
        # is what stops someone from forging a token or reusing one meant
        # for a different app.
        idinfo = google_id_token.verify_oauth2_token(
            payload.id_token,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token.",
        )

    google_sub = idinfo["sub"]  # Google's stable, unique user id
    email = idinfo.get("email")
    name = idinfo.get("name", email or "Google User")

    if not idinfo.get("email_verified", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google account email is not verified.",
        )

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()

    if user is None:
        # Also check if an account with this email already exists via
        # password signup — link accounts rather than creating a duplicate.
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is not None:
            user.google_sub = google_sub
            if user.auth_provider == "password":
                # Keep their existing password login working too; just
                # also allow Google going forward.
                pass
        else:
            user = models.User(
                name=name,
                email=email,
                password_hash=None,
                auth_provider="google",
                google_sub=google_sub,
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    access_token = auth.create_access_token(str(user.id))
    refresh_token = auth.create_refresh_token(str(user.id))

    return schemas.TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=schemas.TokenResponse)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)):
    user_id = auth.decode_token(payload.refresh_token, expected_type="refresh")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
        )

    new_access_token = auth.create_access_token(str(user.id))
    new_refresh_token = auth.create_refresh_token(str(user.id))

    return schemas.TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user=schemas.UserResponse.model_validate(user),
    )


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user: models.User = Depends(auth.get_current_user)):
    """Protected route — proves the JWT dependency works. Also handy for
    the frontend to fetch the logged-in user's profile."""
    return schemas.UserResponse.model_validate(current_user)
