"""
Tests for the AI Career Copilot hackathon demo backend.

Every call to Mesh API is mocked (via unittest.mock.patch) — these tests
never make real network calls, never cost real money, and never require a
real API key. This lets you run the full suite offline, in CI, or right
before a demo without worrying about spend.

Run:
    pip install pytest httpx
    pytest
"""

import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def make_fake_response(content_str: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    """Builds an object shaped like Mesh/OpenAI's chat completion response,
    just enough for main.call_model() to read .choices[0].message.content
    and .usage.prompt_tokens / .usage.completion_tokens."""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content_str))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


# --- Health check ---

def test_health_check():
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# --- Resume parsing: happy path ---

def test_parse_resume_txt_success():
    fake_json = json.dumps({
        "name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "",
        "education": [],
        "skills": ["Python", "SQL"],
        "experience": [],
        "projects": [],
        "certifications": [],
    })
    fake_response = make_fake_response(fake_json)

    with patch.object(main.client.chat.completions, "create", return_value=fake_response):
        resp = client.post(
            "/api/parse-resume",
            files={"file": ("resume.txt", b"Jane Doe\nSkills: Python, SQL", "text/plain")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["name"] == "Jane Doe"
    assert "Python" in body["data"]["skills"]
    assert body["usage"]["input_tokens"] == 10
    assert body["usage"]["output_tokens"] == 20


def test_parse_resume_docx_success(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Jane Doe")
    doc.add_paragraph("Skills: Python, SQL")
    docx_path = tmp_path / "resume.docx"
    doc.save(docx_path)
    docx_bytes = docx_path.read_bytes()

    fake_json = json.dumps({
        "name": "Jane Doe", "email": "", "phone": "",
        "education": [], "skills": ["Python", "SQL"],
        "experience": [], "projects": [], "certifications": [],
    })
    fake_response = make_fake_response(fake_json)

    with patch.object(main.client.chat.completions, "create", return_value=fake_response):
        resp = client.post(
            "/api/parse-resume",
            files={"file": (
                "resume.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )},
        )

    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Jane Doe"


# --- Resume parsing: validation / error handling ---

def test_parse_resume_rejects_unsupported_file_type():
    resp = client.post(
        "/api/parse-resume",
        files={"file": ("resume.xyz", b"some content", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]


def test_parse_resume_rejects_empty_file():
    resp = client.post(
        "/api/parse-resume",
        files={"file": ("resume.txt", b"", "text/plain")},
    )
    assert resp.status_code == 400


def test_parse_resume_rejects_oversized_file():
    big_content = b"a" * (main.MAX_FILE_SIZE_BYTES + 1)
    resp = client.post(
        "/api/parse-resume",
        files={"file": ("resume.txt", big_content, "text/plain")},
    )
    assert resp.status_code == 413


def test_parse_resume_handles_invalid_json_from_model():
    # Simulates the model returning something that isn't valid JSON —
    # the endpoint should fail cleanly (502) instead of crashing or
    # passing garbage back to the frontend.
    fake_response = make_fake_response("Sorry, I can't help with that.")

    with patch.object(main.client.chat.completions, "create", return_value=fake_response):
        resp = client.post(
            "/api/parse-resume",
            files={"file": ("resume.txt", b"Some resume text", "text/plain")},
        )

    assert resp.status_code == 502


# --- Skill gap: happy path ---

def test_skill_gap_success():
    fake_json = json.dumps({
        "missing_skills": [
            {"skill": "DSA", "priority": "high", "why_it_matters": "Interviews"}
        ],
        "roadmap": [
            {"step": 1, "title": "Learn DSA", "description": "...", "estimated_weeks": 4, "resources": ["LeetCode"]}
        ],
        "recommended_projects": [
            {"title": "Project X", "description": "...", "skills_practiced": ["Python"]}
        ],
        "job_readiness_score": 42,
    })
    fake_response = make_fake_response(fake_json)

    with patch.object(main.client.chat.completions, "create", return_value=fake_response):
        resp = client.post(
            "/api/skill-gap",
            data={"role": "SDE", "skills": "Python, SQL"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["job_readiness_score"] == 42
    assert body["data"]["missing_skills"][0]["skill"] == "DSA"


# --- Skill gap: validation ---

def test_skill_gap_rejects_empty_role():
    resp = client.post("/api/skill-gap", data={"role": "   ", "skills": "Python"})
    assert resp.status_code == 400


def test_skill_gap_rejects_oversized_role():
    resp = client.post(
        "/api/skill-gap",
        data={"role": "x" * (main.MAX_ROLE_LENGTH + 1), "skills": "Python"},
    )
    assert resp.status_code == 400


def test_skill_gap_rejects_oversized_skills():
    resp = client.post(
        "/api/skill-gap",
        data={"role": "SDE", "skills": "x" * (main.MAX_SKILLS_LENGTH + 1)},
    )
    assert resp.status_code == 400


# --- Security-relevant behavior ---

def test_parse_resume_does_not_leak_raw_exception_details():
    # A corrupted "PDF" (just random bytes with a .pdf name) should trigger
    # our sanitized error message, not raise a raw internal traceback/string
    # back to the client.
    resp = client.post(
        "/api/parse-resume",
        files={"file": ("resume.pdf", b"not a real pdf file", "application/pdf")},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "Traceback" not in detail
    assert "Failed to read this PDF" in detail
