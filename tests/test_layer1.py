"""Tests for Layer 1: Sender domain, headers, and attachments validation.

Acceptance criteria: CA-01, CA-02, CA-03, CA-04, CA-05, CA-06, CA-07.
"""

import pytest
from backend.models import EmailInput
from backend.validation_engine import analyze_layer1


def test_ca02_official_domain_exact_no_alert():
    """CA-02: Exact official domain generates no domain alert and evaluates to GREEN."""
    email = EmailInput(
        sender="usuario@mincyt.gov.ve",
        display_name="Usuario Mincyt",
        reply_to="",
        subject="Reunión de coordinación",
        body="Cuerpo normal sin adjuntos.",
        attachments=[],
    )
    res = analyze_layer1(email)
    assert res.level == "GREEN"
    assert len(res.reasons) == 0


def test_ca03_lookalike_domain_substitutions_produces_red():
    """CA-03: rnincyt.gov.ve vs mincyt.gov.ve produces RED."""
    email = EmailInput(
        sender="soporte@rnincyt.gov.ve",
        display_name="Soporte",
        subject="Aviso",
        body="Texto",
        attachments=[],
    )
    res = analyze_layer1(email)
    assert res.level == "RED"
    assert any("imita al dominio oficial" in r for r in res.reasons)


def test_ca04_lookalike_and_deceptive_subdomains_produce_red():
    """CA-04: mincyt-gov.ve, mincyt.gov.ve.sitio-falso.com and m1ncyt.gov.ve produce RED."""
    cases = [
        "alertas@mincyt-gov.ve",
        "seguridad@mincyt.gov.ve.sitio-falso.com",
        "soporte@m1ncyt.gov.ve",
        "admin@unetl.edu.ve",
    ]
    for sender in cases:
        email = EmailInput(sender=sender, subject="Test", body="Test")
        res = analyze_layer1(email)
        assert res.level == "RED", f"Failed for {sender}"


def test_ca05_external_domain_without_resemblance_produces_yellow():
    """CA-05: External domain without resemblance (gmail.com) produces YELLOW, never RED."""
    email = EmailInput(
        sender="contacto@gmail.com",
        display_name="Contacto Externo",
        subject="Cotización",
        body="Buenos días",
        attachments=["cotizacion.pdf"],
    )
    res = analyze_layer1(email)
    assert res.level == "YELLOW"
    assert any("Remitente fuera de la red institucional" in r for r in res.reasons)


def test_ca06_attachments_prohibited_suspicious_and_legitimate():
    """CA-06: .exe and factura.pdf.exe -> BLACK; .zip and .docm -> YELLOW; agenda.pdf -> no alert."""
    # Prohibited single extension
    e1 = EmailInput(sender="a@mincyt.gov.ve", attachments=["programa.exe"])
    assert analyze_layer1(e1).level == "BLACK"

    # Double extension hiding executable
    e2 = EmailInput(sender="a@mincyt.gov.ve", attachments=["factura.pdf.exe"])
    res2 = analyze_layer1(e2)
    assert res2.level == "BLACK"
    assert any("oculta un ejecutable" in r for r in res2.reasons)

    # Suspicious compressed or macro files
    e3 = EmailInput(sender="a@mincyt.gov.ve", attachments=["archivo.zip"])
    assert analyze_layer1(e3).level == "YELLOW"

    e4 = EmailInput(sender="a@mincyt.gov.ve", attachments=["informe.docm"])
    assert analyze_layer1(e4).level == "YELLOW"

    # Legitimate common document without alert
    e5 = EmailInput(sender="a@mincyt.gov.ve", attachments=["agenda.pdf"])
    assert analyze_layer1(e5).level == "GREEN"


def test_ca07_headers_display_name_and_reply_to_spoofing():
    """CA-07: Institutional display name on non-official sender or different reply-to produces at least YELLOW or RED."""
    # Institutional term in display_name with external sender
    e1 = EmailInput(
        sender="promocion@empresa-externa.com",
        display_name="Soporte Tecnico Ministerio",
        subject="Aviso",
        body="Hola",
    )
    res1 = analyze_layer1(e1)
    assert res1.level in ("YELLOW", "RED")
    assert any("El nombre mostrado parece institucional" in r for r in res1.reasons)

    # Reply-to domain different from sender
    e2 = EmailInput(
        sender="funcionario@mincyt.gov.ve",
        display_name="Funcionario",
        reply_to="atacante@evil-server.org",
        subject="Consulta",
        body="Hola",
    )
    res2 = analyze_layer1(e2)
    assert res2.level in ("YELLOW", "RED")
    assert any("Las respuestas se enviarían a una dirección distinta" in r for r in res2.reasons)

    # Display name contains an official email address while sender is external -> RED
    e3 = EmailInput(
        sender="malicious@correo-libre.com",
        display_name="soporte@mincyt.gov.ve",
        subject="Alerta",
        body="Hola",
    )
    res3 = analyze_layer1(e3)
    assert res3.level == "RED"
    assert any("incluye una dirección institucional que no es la del remitente" in r for r in res3.reasons)
