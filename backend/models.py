"""
SQLAlchemy models — Users, Resumes, ResumeAnalysis.
Matches the entity list in the Technical Architecture document (a subset,
scoped to what Sprint 1 actually needs: auth + resume persistence).
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=True)  # null for Google-only accounts
    auth_provider = Column(String, nullable=False, default="password")  # "password" | "google"
    google_sub = Column(String, unique=True, nullable=True, index=True)  # Google's stable user id
    created_at = Column(DateTime, default=datetime.utcnow)

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    original_filename = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    parsed_json = Column(JSON, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="resumes")
    analyses = relationship("ResumeAnalysis", back_populates="resume", cascade="all, delete-orphan")


class ResumeAnalysis(Base):
    __tablename__ = "resume_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id"), nullable=False)
    target_role = Column(String, nullable=True)
    skill_gap_json = Column(JSON, nullable=True)
    job_readiness_score = Column(String, nullable=True)  # stored as-is from model output
    created_at = Column(DateTime, default=datetime.utcnow)

    resume = relationship("Resume", back_populates="analyses")


class MockInterview(Base):
    __tablename__ = "mock_interviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    target_role = Column(String, nullable=False)
    transcript = Column(JSON, nullable=False, default=list)  # list of {role, content}
    question_number = Column(Integer, nullable=False, default=0)
    status = Column(String, nullable=False, default="in_progress")  # in_progress | completed
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    report = relationship("InterviewReport", back_populates="interview", uselist=False, cascade="all, delete-orphan")


class InterviewReport(Base):
    __tablename__ = "interview_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interview_id = Column(UUID(as_uuid=True), ForeignKey("mock_interviews.id"), nullable=False, unique=True)
    score = Column(Integer, nullable=True)
    strengths = Column(JSON, nullable=True)          # list of strings
    improvement_points = Column(JSON, nullable=True)  # list of strings
    created_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("MockInterview", back_populates="report")
