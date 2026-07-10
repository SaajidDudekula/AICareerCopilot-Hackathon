"""
AI Career Copilot - Full Security Test Suite (single-run)

Runs a battery of real security checks against your ACTUAL LIVE backend
(not mocks) — rate limiting, JWT tampering, cross-user data access, and
input validation across auth, resume, skill-gap, and interview endpoints.

This makes a small number of real Mesh API calls (one resume parse, one
skill-gap generation, one interview start) as part of testing the live
flow — expect roughly Rs 3-5 of real Mesh API cost for one full run.

Requirements:
    pip install requests

Usage:
    1. Make sure your backend is running: uvicorn main:app --reload --port 8000
    2. Run: python security_test.py
"""

import time
import sys
import requests

API_BASE = "http://localhost:8000"

PASS = "PASS"
FAIL = "FAIL"

results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    marker = "[PASS]" if condition else "[FAIL]"
    line = f"{marker} {name}"
    if detail and not condition:
        line += f"  -> {detail}"
    print(line, flush=True)


def register(email, password, name="Security Test User"):
    return requests.post(
        f"{API_BASE}/api/auth/register",
        json={"name": name, "email": email, "password": password},
    )


def login(email, password):
    return requests.post(
        f"{API_BASE}/api/auth/login",
        json={"email": email, "password": password},
    )


def main():
    print(f"Running security test suite against {API_BASE}\n", flush=True)

    # Quick reachability check before running anything else
    try:
        health = requests.get(f"{API_BASE}/", timeout=5)
        check("Backend is reachable", health.status_code == 200, f"got {health.status_code}")
        if health.status_code != 200:
            print("\nBackend not reachable correctly - stopping early.")
            sys.exit(1)
    except requests.exceptions.ConnectionError:
        print(f"[FAIL] Could not connect to {API_BASE} at all.")
        print("Is uvicorn actually running? (uvicorn main:app --reload --port 8000)")
        sys.exit(1)

    timestamp = int(time.time())
    user_a_email = f"sectest_a_{timestamp}@example.com"
    user_b_email = f"sectest_b_{timestamp}@example.com"
    password = "SecurePass123"  # meets the strength rules: upper/lower/digit/8+ chars

    print("\n=== Setup: creating two throwaway test users ===")
    resp_a = register(user_a_email, password)
    resp_b = register(user_b_email, password)
    check("Register user A succeeds", resp_a.status_code == 201, resp_a.text[:200])
    check("Register user B succeeds", resp_b.status_code == 201, resp_b.text[:200])

    token_a = resp_a.json().get("access_token") if resp_a.status_code == 201 else None
    token_b = resp_b.json().get("access_token") if resp_b.status_code == 201 else None
    headers_a = {"Authorization": f"Bearer {token_a}"} if token_a else {}
    headers_b = {"Authorization": f"Bearer {token_b}"} if token_b else {}

    if not token_a or not token_b:
        print("\nCould not create test users - stopping early, remaining tests need valid tokens.")
        print_summary()
        sys.exit(1)

    # --- Test 1: Login rate limiting ---
    print("\n=== Test 1: Login rate limiting (brute-force protection) ===")
    last_status = None
    for i in range(6):
        r = login(user_a_email, "DefinitelyWrongPassword1")
        last_status = r.status_code
    check(
        "6th consecutive wrong-password login attempt is rate-limited (429)",
        last_status == 429,
        f"got {last_status} on attempt 6",
    )

    # --- Test 2: JWT tampering ---
    print("\n=== Test 2: JWT tampering ===")
    tampered_token = token_a[:-5] + "abcde"
    r = requests.get(f"{API_BASE}/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    check("Tampered JWT is rejected (401)", r.status_code == 401, f"got {r.status_code}")

    # --- Test 3: No token at all ---
    print("\n=== Test 3: Protected routes reject missing auth ===")
    r = requests.post(f"{API_BASE}/api/parse-resume", files={"file": ("t.txt", b"test", "text/plain")})
    check("parse-resume with no auth header returns 401", r.status_code == 401, f"got {r.status_code}")

    r = requests.post(f"{API_BASE}/api/skill-gap", data={"role": "SDE", "skills": "Python"})
    check("skill-gap with no auth header returns 401", r.status_code == 401, f"got {r.status_code}")

    r = requests.post(f"{API_BASE}/api/interview/start", data={"target_role": "SDE"})
    check("interview/start with no auth header returns 401", r.status_code == 401, f"got {r.status_code}")

    # --- Test 4: Cross-user resume access ---
    print("\n=== Test 4: Cross-user data isolation (resumes) ===")
    r = requests.post(
        f"{API_BASE}/api/parse-resume",
        headers=headers_a,
        files={"file": ("resume.txt", b"Test User A\nSkills: Python, SQL", "text/plain")},
    )
    check("User A can parse their own resume", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    resume_id_a = r.json().get("resume_id") if r.status_code == 200 else None

    if resume_id_a:
        r2 = requests.post(
            f"{API_BASE}/api/skill-gap",
            headers=headers_b,
            data={"role": "SDE", "skills": "Python", "resume_id": resume_id_a},
        )
        check(
            "User B submitting User A's resume_id does not error or crash",
            r2.status_code == 200,
            f"got {r2.status_code}: {r2.text[:200]}",
        )
        print("    Note: the API response itself never includes another user's data by design.")
        print("    To fully confirm no cross-linked row was created, check the resume_analyses")
        print("    table in Neon manually and confirm no new row references User A's resume_id")
        print("    with User B as the analysis owner.")

    # --- Test 5: Input validation on resume upload ---
    print("\n=== Test 5: Input validation ===")
    r = requests.post(
        f"{API_BASE}/api/parse-resume",
        headers=headers_a,
        files={"file": ("resume.xyz", b"some content", "application/octet-stream")},
    )
    check("Unsupported file type rejected (400)", r.status_code == 400, f"got {r.status_code}")

    r = requests.post(
        f"{API_BASE}/api/parse-resume",
        headers=headers_a,
        files={"file": ("resume.txt", b"", "text/plain")},
    )
    check("Empty file rejected (400)", r.status_code == 400, f"got {r.status_code}")

    big_content = b"a" * (5 * 1024 * 1024 + 1)
    r = requests.post(
        f"{API_BASE}/api/parse-resume",
        headers=headers_a,
        files={"file": ("resume.txt", big_content, "text/plain")},
    )
    check("Oversized file (>5MB) rejected (413)", r.status_code == 413, f"got {r.status_code}")

    # --- Test 6: Interview Coach - validation and cross-user access ---
    print("\n=== Test 6: Interview Coach security ===")
    r = requests.post(f"{API_BASE}/api/interview/start", headers=headers_a, data={"target_role": "SDE - Entry Level"})
    check("User A can start an interview", r.status_code == 200, f"got {r.status_code}: {r.text[:200]}")
    interview_id = r.json().get("interview_id") if r.status_code == 200 else None

    if interview_id:
        r2 = requests.post(
            f"{API_BASE}/api/interview/answer",
            headers=headers_a,
            data={"interview_id": interview_id, "answer": "   "},
        )
        check("Empty interview answer rejected (400)", r2.status_code == 400, f"got {r2.status_code}")

        r3 = requests.post(
            f"{API_BASE}/api/interview/answer",
            headers=headers_a,
            data={"interview_id": interview_id, "answer": "x" * 6000},
        )
        check("Oversized interview answer (>5000 chars) rejected (400)", r3.status_code == 400, f"got {r3.status_code}")

        r4 = requests.post(
            f"{API_BASE}/api/interview/answer",
            headers=headers_b,
            data={"interview_id": interview_id, "answer": "User B trying to hijack User A's interview"},
        )
        check(
            "User B cannot answer User A's interview session (404)",
            r4.status_code == 404,
            f"got {r4.status_code}",
        )

    r5 = requests.get(f"{API_BASE}/api/interview/nonexistent-id-1234/report", headers=headers_a)
    check("Requesting a nonexistent interview report returns 404 (not 500)", r5.status_code == 404, f"got {r5.status_code}")

    # --- Test 7: Error messages don't leak internals ---
    print("\n=== Test 7: Error messages stay clean (no stack traces leaked) ===")
    r = requests.post(
        f"{API_BASE}/api/parse-resume",
        headers=headers_a,
        files={"file": ("resume.pdf", b"not a real pdf file", "application/pdf")},
    )
    detail = r.json().get("detail", "") if r.status_code == 400 else ""
    check(
        "Corrupted PDF error message has no raw traceback",
        r.status_code == 400 and "Traceback" not in detail and "File \"" not in detail,
        f"got {r.status_code}: {detail[:200]}",
    )

    print_summary()


def print_summary():
    print("\n" + "=" * 60)
    passed = sum(1 for _, s, _ in results if s == PASS)
    total = len(results)
    print(f"SUMMARY: {passed}/{total} checks passed")
    failed = [r for r in results if r[1] == FAIL]
    if failed:
        print("\nFAILED CHECKS:")
        for name, status, detail in failed:
            print(f"  - {name}")
            if detail:
                print(f"    {detail}")
    else:
        print("All checks passed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
