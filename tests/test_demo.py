"""Tests for demo emails in inbox_emails.json.

Acceptance criteria: CA-19.
Verifies that all 5 synthetic emails in the institutional inbox match their expected levels.
"""

import json
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient

from backend.ai_adapter import MockAdapter
from backend.config import INBOX_EMAILS_PATH
from backend.main import app

client = TestClient(app)


def test_ca19_demo_emails_expected_outcomes():
    """CA-19: The 5 demonstration emails produce the expected results specified in Specs_Web.md Section 9."""
    assert INBOX_EMAILS_PATH.is_file(), f"Missing inbox emails file: {INBOX_EMAILS_PATH}"

    with open(INBOX_EMAILS_PATH, "r", encoding="utf-8") as f:
        emails = json.load(f)

    assert len(emails) == 5, f"Expected 5 demo emails, found {len(emails)}"

    for email_data in emails:
        eid = email_data["id"]
        expected_auto = email_data["expected"]["automatic"]
        expected_deep = email_data["expected"]["deep_mock"]

        payload = {
            "sender": email_data["sender"],
            "display_name": email_data.get("display_name", ""),
            "reply_to": email_data.get("reply_to", ""),
            "subject": email_data.get("subject", ""),
            "body": email_data.get("body", ""),
            "attachments": email_data.get("attachments", []),
        }

        # 1. Automatic layers verification (POST /analyze)
        resp_auto = client.post("/analyze", json=payload)
        assert resp_auto.status_code == 200, f"Analyze failed for {eid}: {resp_auto.text}"
        data_auto = resp_auto.json()
        assert data_auto["final_level"] == expected_auto, (
            f"Email '{eid}' expected automatic level {expected_auto}, but got {data_auto['final_level']}"
        )

        # 2. Deep analysis verification if deep_mock is specified
        if expected_deep is not None:
            with patch("backend.ai_adapter.get_ai_adapter", return_value=MockAdapter()):
                resp_deep = client.post("/deep-analysis", json=payload)
                assert resp_deep.status_code == 200, f"Deep analysis failed for {eid}: {resp_deep.text}"
                data_deep = resp_deep.json()
                assert data_deep["final_level"] == expected_deep, (
                    f"Email '{eid}' expected deep mock level {expected_deep}, but got {data_deep['final_level']}"
                )
