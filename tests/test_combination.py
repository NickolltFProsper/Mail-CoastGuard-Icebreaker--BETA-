"""Tests for level combination and asymmetry rules.

Acceptance criteria: CA-11, CA-13, CA-14.
"""

from backend.models import AIResult, EmailInput, LayerResult
from backend.validation_engine import (
    analyze_layer1,
    analyze_layer2,
    combine_levels,
)


def test_ca11_official_domain_with_phishing_content_produces_red_or_yellow():
    """CA-11: An exact official domain with phishing phrases produces at least YELLOW or RED through Layer 2."""
    email = EmailInput(
        sender="rectorado@uneti.edu.ve",
        display_name="Rectorado",
        subject="Urgente cambio de clave",
        body="Por favor realice el cambio de contrasena hoy o su cuenta sera suspendida.",
    )
    l1 = analyze_layer1(email)
    assert l1.level == "GREEN"  # Layer 1 sees official domain and no bad attachments

    l2 = analyze_layer2(email)
    # Score: cambio de contrasena (4) + su cuenta sera suspendida (3) + urgente (1) = 8 -> RED
    assert l2.level == "RED"
    assert l2.score >= 7

    final_level, message = combine_levels(l1, l2)
    assert final_level == "RED"
    assert "Posible phishing" in message


def test_ca13_asymmetry_rule_ai_cannot_downgrade_risk():
    """CA-13: Local layers give RED and AI responds with GREEN -> final_level remains RED."""
    l1 = LayerResult(name="layer1", level="RED", reasons=["Dominio parecido."])
    l2 = LayerResult(name="layer2", level="GREEN", reasons=[], score=0)
    ai_green = AIResult(verdict="no_indicators", level="GREEN", reasons=["Safe"], confidence=0.99)

    final_level, message = combine_levels(l1, l2, layer3=ai_green)
    assert final_level == "RED"
    assert "Posible phishing" in message


def test_ca14_level_precedence_black_beats_all():
    """CA-14: Combination order strictly respects BLACK > RED > YELLOW > GREEN."""
    l_green = LayerResult(name="layer1", level="GREEN", reasons=[])
    l_yellow = LayerResult(name="layer2", level="YELLOW", reasons=["Alerta media."])
    l_red = LayerResult(name="layer1", level="RED", reasons=["Alerta alta."])
    l_black = LayerResult(name="layer1", level="BLACK", reasons=["Ejecutable peligroso."])

    # GREEN vs YELLOW -> YELLOW
    lvl, _ = combine_levels(l_green, l_yellow)
    assert lvl == "YELLOW"

    # YELLOW vs RED -> RED
    lvl, _ = combine_levels(l_yellow, l_red)
    assert lvl == "RED"

    # RED vs BLACK -> BLACK
    lvl, _ = combine_levels(l_red, l_black)
    assert lvl == "BLACK"

    # BLACK vs everything -> BLACK
    lvl, msg = combine_levels(l_black, l_green)
    assert lvl == "BLACK"
    assert "Adjunto peligroso: no lo abra." in msg
