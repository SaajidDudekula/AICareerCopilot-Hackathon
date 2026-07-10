"""
Pydantic schemas for authentication — request/response validation.
FastAPI validates these automatically; a malformed request never reaches
your business logic.
"""

import re
import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict, field_validator


class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty.")
        if len(v) > 100:
            raise ValueError("Name is too long (max 100 characters).")
        return v

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Deliberately strict, per "strict secure" requirement — adjust
        # if this is too aggressive for your actual user base.
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if len(v.encode("utf-8")) > 72:
            # bcrypt has a hard 72-byte limit — reject clearly here rather
            # than let it fail confusingly deeper in the hashing step.
            raise ValueError("Password must be at most 72 bytes long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"[0-9]", v):
            raise ValueError("Password must contain at least one digit.")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    id_token: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    auth_provider: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse
