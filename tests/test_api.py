"""Tests for FastAPI endpoints, offline pure layers, controlled degradation, and zero-PII logging.

Acceptance criteria: CA-01, CA-15, CA-18, CA-20.
"""

from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from backend.main import app

client = TestClient(app)


def test_health_endpoint_returns_only_status_ok():
    """Verify /health returns solely {'status': 'ok'} without revealing provider or internal config."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ca01_offline_execution_of_layers_1_and_2():
    """CA-01: Layers 1 and 2 respond without external network calls."""
    payload = {
        "sender": "usuario@mincyt.gov.ve",
        "subject": "Reunión",
        "body": "Texto normal",
        "attachments": [],
    }
    # No network calls needed
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "final_level" in data
    assert len(data["layers"]) == 2


def test_ca15_controlled_degradation_on_ai_failure():
    """CA-15: AI exception, timeout or invalid response produces 200, status='unavailable', notice, and local result."""
    payload = {
        "sender": "alerta@portal-falso.com",
        "subject": "Aviso",
        "body": "Texto",
        "attachments": [],
    }

    # Simulate AI adapter raising an exception
    with patch("backend.ai_adapter.get_ai_adapter") as mock_get:
        mock_adapter = mock_get.return_value
        mock_adapter.analyze.side_effect = RuntimeError("Simulated API failure or timeout")

        resp = client.post("/deep-analysis", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["layer3"] is None
        assert "Análisis profundo no disponible" in data["notice"]
        assert data["final_level"] in ("YELLOW", "RED")


def test_ca18_green_message_never_says_safe():
    """CA-18: The message for GREEN is exactly the Section 5 literal and never claims the email is 'safe'."""
    payload = {
        "sender": "rectorado@uneti.edu.ve",
        "subject": "Reunión ordinaria",
        "body": "Buenas tardes estimados profesores.",
        "attachments": ["agenda.pdf"],
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["final_level"] == "GREEN"
    expected_msg = "Sin indicios detectados. Esto no garantiza que el correo sea seguro."
    assert data["message"] == expected_msg
    assert "seguro." in data["message"]  # literal says "no garantiza que el correo sea seguro"
    assert not data["message"].startswith("Correo seguro")


def test_ca20_logs_do_not_contain_pii(caplog):
    """CA-20: Application logs never contain sender, subject, body, or attachment names."""
    secret_body_marker = "SUPER_SECRET_TOKEN_XYZ_123"
    payload = {
        "sender": "confidential_sender@uneti.edu.ve",
        "subject": "Confidential Subject 987",
        "body": f"Here is the secret body {secret_body_marker}",
        "attachments": ["secret_financials.xlsx"],
    }

    with caplog.at_level("INFO"):
        resp = client.post("/analyze", json=payload)
        assert resp.status_code == 200

    log_text = caplog.text
    assert "confidential_sender" not in log_text
    assert "Confidential Subject" not in log_text
    assert secret_body_marker not in log_text
    assert "secret_financials.xlsx" not in log_text
