"""Tests for Layer 2: Content heuristic scoring and phishing phrase analysis.

Acceptance criteria: CA-08, CA-09, CA-10.
"""

from backend.models import EmailInput
from backend.validation_engine import analyze_layer2, normalize_text_layer2


def test_ca08_normalization_accents_and_case():
    """CA-08: URGENTE, urgente, and Urgénte score identically due to NFKC and NFD accent normalization."""
    assert normalize_text_layer2("URGENTE") == "urgente"
    assert normalize_text_layer2("urgente") == "urgente"
    assert normalize_text_layer2("Urgénte") == "urgente"

    e1 = EmailInput(sender="test@uneti.edu.ve", subject="URGENTE", body="")
    e2 = EmailInput(sender="test@uneti.edu.ve", subject="urgente", body="")
    e3 = EmailInput(sender="test@uneti.edu.ve", subject="Urgénte", body="")

    r1 = analyze_layer2(e1)
    r2 = analyze_layer2(e2)
    r3 = analyze_layer2(e3)

    assert r1.score == r2.score == r3.score == 1
    assert r1.level == r2.level == r3.level == "GREEN"


def test_ca09_threshold_scoring_green_yellow_red():
    """CA-09: Score < 3 -> GREEN; 3 <= Score <= 6 -> YELLOW; Score >= 7 -> RED."""
    # Single weight 1 phrase ("urgente") -> score 1 -> GREEN
    e_green = EmailInput(sender="a@b.com", subject="Asunto urgente", body="Mensaje normal sin otras frases.")
    r_green = analyze_layer2(e_green)
    assert r_green.score == 1
    assert r_green.level == "GREEN"

    # Weight 4 ("cambio de contrasena") -> score 4 -> YELLOW
    e_yellow = EmailInput(sender="a@b.com", subject="Aviso", body="Requiera cambio de contrasena de su cuenta.")
    r_yellow = analyze_layer2(e_yellow)
    assert r_yellow.score == 4
    assert r_yellow.level == "YELLOW"

    # Weight 4 + Weight 4 ("verifique su cuenta" + "ingrese sus datos") -> score 8 -> RED
    e_red = EmailInput(
        sender="a@b.com",
        subject="Urgente",
        body="Por favor verifique su cuenta e ingrese sus datos hoy.",
    )
    r_red = analyze_layer2(e_red)
    assert r_red.score >= 8
    assert r_red.level == "RED"


def test_ca10_repeated_phrases_count_only_once():
    """CA-10: Repeated phrase counts its weight only once."""
    e_single = EmailInput(sender="a@b.com", subject="urgente", body="nada mas")
    e_repeated = EmailInput(sender="a@b.com", subject="URGENTE urgente Urgénte", body="urgente urgente")

    r_single = analyze_layer2(e_single)
    r_repeated = analyze_layer2(e_repeated)

    assert r_single.score == r_repeated.score == 1


def test_layer2_homoglyphs_and_invisible_characters_detection():
    """Verify Cyrillic homoglyphs and invisible Unicode zero-width spaces are unmasked."""
    # "cambio de contrasena" with Cyrillic 'а' and invisible char U+200B
    obfuscated = "c\u0430mbio de contr\u200B\u0430se\u00f1a"
    e = EmailInput(sender="a@b.com", subject="Notificación", body=obfuscated)
    res = analyze_layer2(e)
    assert res.score == 4
    assert res.level == "YELLOW"
