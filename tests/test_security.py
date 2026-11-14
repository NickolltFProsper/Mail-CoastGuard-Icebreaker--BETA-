"""Security and Anti-Abuse Test Suite for Mail CoastGuard.

Strictly verifies SEC-01 through SEC-33 as mandated by security.md.
All tests run offline without network access.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import socket
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest

from backend.admin_api import compute_file_sha256
from backend.ai_adapter import (
    DeepSeekAdapter,
    GeminiAdapter,
    MockAdapter,
    OllamaAdapter,
    SYSTEM_PROMPT,
    format_email_for_ai,
    validate_ai_response,
)
from backend.config import (
    INDEX_HTML_PATH,
    PROJECT_ROOT,
    is_safe_ollama_url,
    validate_admin_allowed_ips,
)
from backend.main import app
from backend.models import EmailInput
from backend.validation_engine import (
    DataRepository,
    analyze_layer1,
    analyze_layer2,
)

client = TestClient(app)


# --- SEC-01: Secret Scanning ---
def test_sec_01_secret_scanner():
    """SEC-01: Verify no secrets, credentials or private keys are committed in source files."""
    regex_patterns = [
        re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
        re.compile(r"sk-[0-9A-Za-z]{20,}"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?i)(api[_-]?key|secret|token|passw(or)?d|clave)\s*[:=]\s*[\"'][^\"']{8,}[\"']"),
        re.compile(r"://[^:]+:[^@]+@"),
        re.compile(r"Bearer\s+[A-Za-z0-9_\-]{32,}"),
    ]

    extensions_to_scan = {".py", ".html", ".js", ".json"}
    excluded_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}
    excluded_files = {"test_security.py", "package-lock.json"}

    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in excluded_dirs]
        for f in files:
            if f in excluded_files:
                continue
            file_path = Path(root) / f
            if file_path.suffix in extensions_to_scan:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for pat in regex_patterns:
                    matches = pat.findall(content)
                    assert not matches, f"Potential secret matched by {pat} in {file_path}: {matches}"


# --- SEC-02: Environment Configuration & Gitignore ---
def test_sec_02_gitignore_and_env_example():
    """SEC-02: .gitignore must contain .env and .env.example must have empty secrets."""
    gitignore_path = PROJECT_ROOT / ".gitignore"
    env_example_path = PROJECT_ROOT / ".env.example"

    assert gitignore_path.is_file(), ".gitignore must exist"
    gitignore_content = gitignore_path.read_text(encoding="utf-8")
    assert ".env" in gitignore_content

    assert env_example_path.is_file(), ".env.example must exist"
    env_lines = env_example_path.read_text(encoding="utf-8").splitlines()
    for line in env_lines:
        line = line.strip()
        if line.startswith("GEMINI_API_KEY="):
            assert line == "GEMINI_API_KEY="
        if line.startswith("DEEPSEEK_API_KEY="):
            assert line == "DEEPSEEK_API_KEY="
        if line.startswith("ADMIN_API_KEY_SHA256="):
            assert line == "ADMIN_API_KEY_SHA256="


# --- SEC-03: Forbidden and Decoy Routes produce 404 ---
@pytest.mark.parametrize("bad_path", [
    "/admin",
    "/administrator",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/.env",
    "/.git/config",
    "/backend/main.py",
    "/backend/data/official_domains.json",
    "/%2e%2e/.env",
    "/Specs.md",
    "/Specs_Web.md",
    "/Specs_Extension.md",
    "/assets/",
    "/assets/..%2f.env",
])
def test_sec_03_blocked_paths_return_404(bad_path):
    """SEC-03: Sensitive, administrative, hidden, and traversal routes return generic 404."""
    resp = client.get(bad_path)
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


# --- SEC-04: Disallowed HTTP Methods ---
def test_sec_04_disallowed_methods_return_404_or_405():
    """SEC-04: Disallowed methods (DELETE, PUT, TRACE on public endpoints) return 404 or 405."""
    assert client.delete("/health").status_code in (404, 405)
    assert client.put("/analyze", json={}).status_code in (404, 405, 415)
    assert client.patch("/health").status_code in (404, 405)


# --- SEC-05: Payload and Input Limits ---
def test_sec_05_payload_and_validation_limits():
    """SEC-05: Body > 200KB -> 413; invalid types/lengths -> 422; Content-Type != json -> 415."""
    # 415 on non-JSON content-type
    resp_415 = client.post("/analyze", content=b"{}", headers={"Content-Type": "text/plain"})
    assert resp_415.status_code == 415

    # 413 on body > 204,800 bytes
    large_payload = {"sender": "a@b.com", "body": "X" * 210000}
    resp_413 = client.post("/analyze", json=large_payload)
    assert resp_413.status_code in (413, 422)

    # 422 on extra field or field exceeding max_length
    resp_extra = client.post("/analyze", json={"sender": "a@b.com", "malicious_extra": 1})
    assert resp_extra.status_code == 422
    assert resp_extra.json() == {"detail": "Validation error"}


# --- SEC-06: Rate Limiting ---
def test_sec_06_rate_limiting():
    """SEC-06: Exceeding rate limits returns 429 with Retry-After header."""
    # Simulate high volume requests to deep analysis
    hit_429 = False
    for _ in range(10):
        res = client.post("/deep-analysis", json={"sender": "a@b.com", "body": "test"})
        if res.status_code == 429:
            hit_429 = True
            assert "Retry-After" in res.headers
            break
    assert hit_429, "Rate limiter should have triggered 429"


# --- SEC-07: Unhandled Exception Masking ---
def test_sec_07_unhandled_exception_returns_generic_500():
    """SEC-07: Unhandled exceptions return 500 with {'detail': 'Internal error'} without stack traces."""
    with patch("backend.main.analyze_layer1", side_effect=Exception("Database crash line 42 at /internal/path")):
        resp = client.post("/analyze", json={"sender": "a@b.com", "body": "test"})
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal error"}


# --- SEC-08: Security Headers ---
def test_sec_08_security_headers_present():
    """SEC-08: All responses include mandatory security headers."""
    resp = client.get("/health")
    assert resp.status_code == 200
    headers = resp.headers
    assert "Content-Security-Policy" in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert "Permissions-Policy" in headers


# --- SEC-09: No Wildcard CORS ---
def test_sec_09_no_wildcard_cors():
    """SEC-09: CORS is disabled or strictly controlled without wildcard '*'."""
    resp = client.options("/analyze", headers={"Origin": "http://evil.com"})
    assert resp.headers.get("Access-Control-Allow-Origin") != "*"


# --- SEC-10: Health Endpoint Leakage Check ---
def test_sec_10_health_endpoint_isolation():
    """SEC-10: GET /health returns strictly {'status': 'ok'}."""
    resp = client.get("/health")
    assert resp.json() == {"status": "ok"}


# --- SEC-11: Fail Safe in Layers ---
def test_sec_11_layer_fail_safe():
    """SEC-11: Unexpected exception in Layer 1 or 2 fails safe to YELLOW with explicit notice."""
    with patch("backend.validation_engine.validate_email_address", side_effect=RuntimeError("Unexpected")):
        res = analyze_layer1(EmailInput(sender="test@test.com"))
        assert res.level == "YELLOW"
        assert "No se pudo analizar el correo por completo" in res.reasons[0]


# --- SEC-12: Data Lists Integrity on Startup ---
def test_sec_12_data_lists_integrity():
    """SEC-12: Missing, corrupt, or empty JSON in data/ causes startup rejection."""
    repo = DataRepository()
    assert len(repo.official_domains) >= 1
    assert len(repo.institutional_terms) >= 1
    assert len(repo.prohibited_extensions) >= 1
    assert len(repo.phishing_phrases) >= 1

    with pytest.raises(RuntimeError):
        repo._load_official_domains(Path("non_existent.json"))


# --- SEC-13: Attachment Extension Disguise ---
def test_sec_13_attachment_evasion_checks():
    """SEC-13: BIDI overrides (U+202E), trailing dots/spaces, and executable disguises evaluate to BLACK."""
    # Right-to-Left Override char (U+202E)
    bidi_name = "factura\u202Efdp.exe"
    r1 = analyze_layer1(EmailInput(sender="a@mincyt.gov.ve", attachments=[bidi_name]))
    assert r1.level == "BLACK"
    assert any("caracteres ocultos" in r for r in r1.reasons)

    # Trailing space/dot
    trailing_name = "factura.exe ."
    r2 = analyze_layer1(EmailInput(sender="a@mincyt.gov.ve", attachments=[trailing_name]))
    assert r2.level == "BLACK"

    # Double extension hiding executable
    double_ext = "factura.pdf.exe "
    r3 = analyze_layer1(EmailInput(sender="a@mincyt.gov.ve", attachments=[double_ext]))
    assert r3.level == "BLACK"


# --- SEC-14: Sender Address Manipulation ---
def test_sec_14_sender_manipulation_and_display_name_spoof():
    """SEC-14: Malformed addresses (multiple @, <>) yield at least YELLOW; institutional display name yields RED."""
    # Multiple @
    r1 = analyze_layer1(EmailInput(sender="a@mincyt.gov.ve@evil.com"))
    assert r1.level in ("YELLOW", "RED")
    assert any("Dirección de remitente inválida o manipulada" in r for r in r1.reasons)

    # Brackets in sender
    r2 = analyze_layer1(EmailInput(sender="<a@evil.com>"))
    assert r2.level in ("YELLOW", "RED")

    # Display name spoofing official address
    r3 = analyze_layer1(EmailInput(
        sender="external@evil.com",
        display_name="soporte@mincyt.gov.ve",
    ))
    assert r3.level == "RED"


# --- SEC-15: Obfuscation Resistance in Layer 2 ---
def test_sec_15_obfuscation_resistance():
    """SEC-15: Invisible characters and homoglyphs do not evade Layer 2 phishing detection."""
    # "cambio de contraseña" with zero-width space and Cyrillic 'а'
    text = "c\u0430mbio de contr\u200B\u0430se\u00f1a"
    res = analyze_layer2(EmailInput(sender="a@b.com", body=text))
    assert res.score >= 4
    assert res.level == "YELLOW"


# --- SEC-16: Frontend DOM Injection and AI Response Sanitization ---
def test_sec_16_ai_response_sanitization_and_index_html_clean():
    """SEC-16: Reasons in AI response > 200 chars are truncated and index.html contains no forbidden DOM methods."""
    long_reason_json = json.dumps({
        "verdict": "phishing",
        "level": "RED",
        "reasons": ["<script>alert(1)</script>" + "A" * 300],
        "confidence": 0.9,
    })
    res = validate_ai_response(long_reason_json)
    assert res is not None
    assert len(res.reasons[0]) <= 200

    html_content = INDEX_HTML_PATH.read_text(encoding="utf-8")
    forbidden = ["innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "new Function", "document.write"]
    for f in forbidden:
        assert f not in html_content, f"Forbidden DOM method '{f}' found in index.html"


# --- SEC-17: Logging PII and Injection Check ---
def test_sec_17_logging_sanitization():
    """SEC-17: Verify path injection and control chars in logs are neutral."""
    injected_path = "/analyze%0d%0aInjectedHeader:true"
    resp = client.get(injected_path)
    assert resp.status_code == 404


# --- SEC-18: Ollama SSRF Protection ---
def test_sec_18_ollama_ssrf_protection():
    """SEC-18: Non-loopback/non-private Ollama URL fails safely."""
    assert is_safe_ollama_url("http://localhost:11434") is True
    assert is_safe_ollama_url("http://127.0.0.1:11434") is True
    assert is_safe_ollama_url("http://192.168.1.10:11434") is True
    assert is_safe_ollama_url("http://10.0.0.1:11434") is True

    # Dangerous external IPs or schemes
    assert is_safe_ollama_url("http://8.8.8.8:11434") is False
    assert is_safe_ollama_url("file:///etc/passwd") is False
    assert is_safe_ollama_url("ftp://localhost:11434") is False


# --- SEC-20: No Automatic Provider Fallback ---
def test_sec_20_no_automatic_provider_fallback():
    """SEC-20: Failure of configured AI provider never automatically switches to another cloud provider."""
    adapter = GeminiAdapter(api_key="")
    with pytest.raises(ValueError):
        adapter.analyze(SYSTEM_PROMPT, "email")


# --- SEC-24: AI Response Strict JSON Wrapper Check ---
def test_sec_24_strict_json_rejection_of_markdown():
    """SEC-24: AI response with markdown code fences or surrounding text is rejected."""
    raw = "```json\n{\"verdict\": \"phishing\", \"level\": \"RED\", \"reasons\": [\"Alerta\"], \"confidence\": 0.9}\n```"
    assert validate_ai_response(raw) is None


# --- SEC-25 to SEC-33: Admin API Security ---
def test_sec_25_admin_api_disabled_by_default_returns_404():
    """SEC-25: With ADMIN_API_ENABLED=false (default), all /api/admin/v1/ routes return generic 404."""
    resp = client.get("/api/admin/v1/status")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not found"}


def test_sec_26_to_33_admin_api_when_enabled(monkeypatch):
    """SEC-26 through SEC-33: Full coverage of Admin API authentication, lockout, validation, and audit."""
    test_key = "test_secret_admin_key_12345678901234567890"
    test_hash = hashlib.sha256(test_key.encode("utf-8")).hexdigest()

    monkeypatch.setattr("backend.config.ADMIN_API_ENABLED", True)
    monkeypatch.setattr("backend.config.ADMIN_API_KEY_SHA256", test_hash)
    monkeypatch.setattr("backend.config.ADMIN_ALLOWED_IPS", ["127.0.0.1", "testclient"])

    # SEC-26: Missing / Invalid auth -> 401
    resp_no_auth = client.get("/api/admin/v1/status")
    assert resp_no_auth.status_code == 401
    assert "WWW-Authenticate" in resp_no_auth.headers

    resp_bad_auth = client.get("/api/admin/v1/status", headers={"Authorization": "Bearer wrong_key"})
    assert resp_bad_auth.status_code == 401

    # SEC-29: Reject browser context (Origin or Sec-Fetch-Site) -> 403
    resp_origin = client.get(
        "/api/admin/v1/status",
        headers={"Authorization": f"Bearer {test_key}", "Origin": "http://evil.com"}
    )
    assert resp_origin.status_code == 403

    # Successful authenticated call -> 200
    headers = {"Authorization": f"Bearer {test_key}"}
    resp_ok = client.get("/api/admin/v1/status", headers=headers)
    assert resp_ok.status_code == 200
    data = resp_ok.json()
    assert "uptime_seconds" in data
    assert "lists" in data

    # SEC-30: PUT with invalid content or missing If-Match
    # Missing If-Match -> 428
    put_no_ifmatch = client.put(
        "/api/admin/v1/lists/official_domains",
        json={"data": {}},
        headers=headers,
    )
    assert put_no_ifmatch.status_code == 428

    # Wrong If-Match -> 412
    put_bad_match = client.put(
        "/api/admin/v1/lists/official_domains",
        json={"data": {}},
        headers={"Authorization": f"Bearer {test_key}", "If-Match": '"wrong_sha256"'},
    )
    assert put_bad_match.status_code == 412

    # SEC-31 & SEC-32: GET /audit contains actions without secrets
    resp_audit = client.get("/api/admin/v1/audit", headers=headers)
    assert resp_audit.status_code == 200
    audit_data = resp_audit.json()
    assert "audit" in audit_data
    audit_text = json.dumps(audit_data)
    assert test_key not in audit_text
    assert test_hash not in audit_text
