"""
AI Interview Coach — the platform's core differentiator beyond resume
parsing and skill gaps. Runs a real multi-turn mock interview (mixing
behavioral, technical, and problem-solving questions), gives feedback
after each answer, and produces a persisted final report with a score.

Mount in main.py:
    from interview_routes import router as interview_router
    app.include_router(interview_router, prefix="/api/interview", tags=["interview"])
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models
import auth
from mesh_client import client, SONNET

router = APIRouter()

TOTAL_QUESTIONS = 4  # 1 behavioral, 2 technical/conceptual, 1 problem-solving


def _validate_uuid_or_404(id_str: str, what: str = "resource") -> str:
    """Confirms id_str is a syntactically valid UUID before it ever reaches
    a database query. Without this check, a malformed (but non-UUID-shaped)
    ID string causes PostgreSQL itself to raise an error when comparing it
    against a UUID column — surfacing as a raw 500 Internal Server Error
    instead of a clean 404. From the outside, "malformed ID" and "ID that
    doesn't exist" should look identical: both just 404."""
    try:
        uuid.UUID(id_str)
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail=f"{what.capitalize()} not found.")
    return id_str

SYSTEM_PROMPT_TEMPLATE = """You are an AI interview coach conducting a mock interview for a
"{role}" role. Ask exactly {total} questions total, one at a time: question 1 is
behavioral, questions 2-3 are technical/conceptual for this role, question 4 is a
problem-solving question. After each candidate answer (except the final one), give
brief constructive feedback (2-3 sentences) then ask the next question. Keep questions
and feedback concise and realistic, as a real interviewer would."""

FINAL_SUMMARY_PROMPT = """The candidate has now answered all {total} questions. Give brief
feedback (2-3 sentences) on their final answer, then provide an overall summary.
Return ONLY valid JSON with this exact structure, no extra commentary, no markdown fences:

{{
  "final_feedback": "",
  "score": 0,
  "strengths": ["", ""],
  "improvement_points": ["", "", ""]
}}

Score is out of 10. Base it on the full conversation above, not just the last answer.
"""


def _parse_json_response(raw: str) -> dict:
    """Same tolerant JSON parsing approach used elsewhere in the app —
    strips stray markdown fences some models add around JSON output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail=f"Model did not return valid JSON for the interview summary. Raw output: {raw[:500]}",
        )


def _call_interview_model(messages: list, max_tokens: int):
    response = client.chat.completions.create(
        model=SONNET,
        messages=messages,
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    usage = {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }
    return content, usage


@router.post("/start")
def start_interview(
    target_role: str = Form(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Starts a new mock interview session and returns the first question."""
    target_role = target_role.strip()
    if not target_role:
        raise HTTPException(status_code=400, detail="Target role must not be empty.")
    if len(target_role) > 200:
        raise HTTPException(status_code=400, detail="Target role text too long (max 200 characters).")

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(role=target_role, total=TOTAL_QUESTIONS)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I'm ready to start the interview."},
    ]

    content, usage = _call_interview_model(messages, max_tokens=300)

    transcript = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "I'm ready to start the interview."},
        {"role": "assistant", "content": content},
    ]

    interview = models.MockInterview(
        user_id=current_user.id,
        target_role=target_role,
        transcript=transcript,
        question_number=1,
        status="in_progress",
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    return {
        "interview_id": str(interview.id),
        "question_number": 1,
        "total_questions": TOTAL_QUESTIONS,
        "message": content,
        "is_final": False,
        "usage": usage,
    }


@router.post("/answer")
def answer_interview(
    interview_id: str = Form(...),
    answer: str = Form(...),
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Submits the candidate's answer to the current question. Returns
    feedback + the next question, or — if this was the final question —
    a persisted final report with a score."""
    answer = answer.strip()
    if not answer:
        raise HTTPException(status_code=400, detail="Answer must not be empty.")
    if len(answer) > 5000:
        raise HTTPException(status_code=400, detail="Answer is too long (max 5000 characters).")

    interview = (
        db.query(models.MockInterview)
        .filter(
            models.MockInterview.id == _validate_uuid_or_404(interview_id, "interview session"),
            models.MockInterview.user_id == current_user.id,
        )
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    if interview.status == "completed":
        raise HTTPException(status_code=400, detail="This interview session is already completed.")

    transcript = list(interview.transcript)
    transcript.append({"role": "user", "content": answer})

    is_last_question = interview.question_number >= TOTAL_QUESTIONS

    if is_last_question:
        transcript.append({"role": "user", "content": FINAL_SUMMARY_PROMPT})
        content, usage = _call_interview_model(transcript, max_tokens=500)

        summary = _parse_json_response(content)

        transcript.append({"role": "assistant", "content": content})
        interview.transcript = transcript
        interview.status = "completed"
        interview.completed_at = datetime.now(timezone.utc)
        db.add(interview)

        report = models.InterviewReport(
            interview_id=interview.id,
            score=summary.get("score"),
            strengths=summary.get("strengths", []),
            improvement_points=summary.get("improvement_points", []),
        )
        db.add(report)
        db.commit()
        db.refresh(report)

        return {
            "interview_id": str(interview.id),
            "is_final": True,
            "final_feedback": summary.get("final_feedback", ""),
            "score": report.score,
            "strengths": report.strengths,
            "improvement_points": report.improvement_points,
            "usage": usage,
        }

    else:
        content, usage = _call_interview_model(transcript, max_tokens=300)
        transcript.append({"role": "assistant", "content": content})

        interview.transcript = transcript
        interview.question_number += 1
        db.add(interview)
        db.commit()
        db.refresh(interview)

        return {
            "interview_id": str(interview.id),
            "question_number": interview.question_number,
            "total_questions": TOTAL_QUESTIONS,
            "message": content,
            "is_final": False,
            "usage": usage,
        }


@router.get("/{interview_id}/report")
def get_interview_report(
    interview_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Fetches the final report for a completed interview."""
    interview = (
        db.query(models.MockInterview)
        .filter(
            models.MockInterview.id == _validate_uuid_or_404(interview_id, "interview session"),
            models.MockInterview.user_id == current_user.id,
        )
        .first()
    )
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    if interview.status != "completed" or interview.report is None:
        raise HTTPException(status_code=400, detail="This interview is not yet completed.")

    return {
        "interview_id": str(interview.id),
        "target_role": interview.target_role,
        "score": interview.report.score,
        "strengths": interview.report.strengths,
        "improvement_points": interview.report.improvement_points,
        "completed_at": interview.completed_at.isoformat() if interview.completed_at else None,
    }
