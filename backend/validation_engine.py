"""Mail CoastGuard validation engine.

Implements pure Layers 1 and 2, level combination, Levenshtein distance,
homoglyph normalization, and fail-safe error handling.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from backend.config import (
    DANGEROUS_EXTENSIONS_PATH,
    EXTERNAL_SENDER_LEVEL,
    LAYER_FALLBACK_REASON,
    LAYER2_RED_MIN,
    LAYER2_YELLOW_MIN,
    LEVEL_BLACK,
    LEVEL_GREEN,
    LEVEL_RANKS,
    LEVEL_RED,
    LEVEL_YELLOW,
    OFFICIAL_DOMAINS_PATH,
    PHISHING_PHRASES_PATH,
    USER_MESSAGES,
)
from backend.models import EmailInput, LayerResult

# Bidirectional text override characters (U+202A to U+202E, U+2066 to U+2069)
BIDI_CHARS = set(
    chr(cp) for cp in (
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069,
    )
)

# Invisible unicode characters (U+200B to U+200F, U+2060, U+FEFF)
INVISIBLE_CHARS = set(
    chr(cp) for cp in (
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F,
        0x2060, 0xFEFF,
    )
)

# Confusable Cyrillic and Greek characters to Latin mapping
HOMOGLYPH_MAP = {
    # Cyrillic lowercase
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "і": "i",
    # Cyrillic uppercase
    "А": "a", "Е": "e", "О": "o", "Р": "p", "С": "c", "Х": "x", "І": "i",
    # Greek lowercase
    "α": "a", "ε": "e", "ο": "o", "ρ": "p", "с": "c", "χ": "x", "ι": "i",
    # Greek uppercase
    "Α": "a", "Ε": "e", "Ο": "o", "Ρ": "p", "Τ": "t", "Χ": "x",
}


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings without external dependencies."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    # Optimization: ensure s1 is shorter
    if len(s1) > len(s2):
        s1, s2 = s2, s1

    previous_row = list(range(len(s1) + 1))
    for i, c2 in enumerate(s2):
        current_row = [i + 1] + [0] * len(s1)
        for j, c1 in enumerate(s1):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row[j + 1] = min(insertions, deletions, substitutions)
        previous_row = current_row

    return previous_row[-1]


class DataRepository:
    """Loads and caches in-memory threat detection lists."""

    def __init__(self) -> None:
        self.official_domains: list[str] = []
        self.institutional_terms: list[str] = []
        self.prohibited_extensions: list[str] = []
        self.suspicious_extensions: list[str] = []
        self.common_documents: list[str] = []
        self.phishing_phrases: list[dict[str, Any]] = []
        self.load_all()

    def load_all(self) -> None:
        """Load and validate all JSON files from backend/data."""
        self._load_official_domains(OFFICIAL_DOMAINS_PATH)
        self._load_dangerous_extensions(DANGEROUS_EXTENSIONS_PATH)
        self._load_phishing_phrases(PHISHING_PHRASES_PATH)

    def _load_official_domains(self, path: Path) -> None:
        if not path.is_file():
            raise RuntimeError(f"Missing required data file: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid format in {path}: expected dict")
        domains = data.get("domains")
        terms = data.get("institutional_terms")
        if not domains or not isinstance(domains, list) or len(domains) == 0:
            raise RuntimeError(f"Empty or missing 'domains' in {path}")
        if not terms or not isinstance(terms, list) or len(terms) == 0:
            raise RuntimeError(f"Empty or missing 'institutional_terms' in {path}")
        self.official_domains = [d.strip().lower() for d in domains if isinstance(d, str)]
        self.institutional_terms = [t.strip().lower() for t in terms if isinstance(t, str)]

    def _load_dangerous_extensions(self, path: Path) -> None:
        if not path.is_file():
            raise RuntimeError(f"Missing required data file: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid format in {path}: expected dict")
        proh = data.get("prohibited")
        susp = data.get("suspicious")
        common = data.get("common_documents")
        if not proh or not susp or not common:
            raise RuntimeError(f"Missing required extension lists in {path}")
        self.prohibited_extensions = [e.strip().lower() for e in proh if isinstance(e, str)]
        self.suspicious_extensions = [e.strip().lower() for e in susp if isinstance(e, str)]
        self.common_documents = [e.strip().lower() for e in common if isinstance(e, str)]

    def _load_phishing_phrases(self, path: Path) -> None:
        if not path.is_file():
            raise RuntimeError(f"Missing required data file: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or len(data) == 0:
            raise RuntimeError(f"Empty or invalid 'phishing_phrases' in {path}")
        for item in data:
            if not isinstance(item, dict) or "phrase" not in item or "weight" not in item:
                raise RuntimeError(f"Invalid phrase item in {path}: {item}")
        self.phishing_phrases = data


# Global singleton repository
repo = DataRepository()


def strip_accents(text: str) -> str:
    """Decompose Unicode and strip combining diacritical marks."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_text_layer2(text: str) -> str:
    """Normalize text according to Layer 2 specifications (Section 8.1):

    NFKC -> remove invisibles -> Cyrillic/Greek homoglyphs -> lowercase -> NFD strip accents -> collapse spaces.
    """
    # 1. Unicode NFKC
    res = unicodedata.normalize("NFKC", text)

    # 2. Remove invisible characters
    res = "".join(c for c in res if c not in INVISIBLE_CHARS)

    # 3. Confusable Cyrillic and Greek homoglyphs to Latin
    res = "".join(HOMOGLYPH_MAP.get(c, c) for c in res)

    # 4. Lowercase
    res = res.lower()

    # 5. Remove accents/diacritics
    res = strip_accents(res)

    # 6. Collapse whitespace and linebreaks into single space
    res = re.sub(r"\s+", " ", res).strip()
    return res


def is_similar_domain(domain: str, official: str) -> bool:
    """Check if domain resembles an official domain according to Section 7.3."""
    if domain == official:
        return True

    # 1. Confusable character substitutions: rn->m, vv->w, 0->o, 1->l, 1->i, 5->s
    substitutions = [
        ("rn", "m"),
        ("vv", "w"),
        ("0", "o"),
        ("1", "l"),
        ("1", "i"),
        ("5", "s"),
    ]

    # Test each substitution applied alone
    for old, new in substitutions:
        if old in domain:
            variant = domain.replace(old, new)
            if variant == official:
                return True

    # Test all substitutions applied together
    simultaneous = domain
    for old, new in substitutions:
        simultaneous = simultaneous.replace(old, new)
    if simultaneous == official:
        return True

    # 2. Domain without hyphens equals official without hyphens
    if domain.replace("-", "") == official.replace("-", ""):
        return True

    # 3. Levenshtein distance check
    threshold = 1 if len(official) < 8 else 2
    if abs(len(domain) - len(official)) <= threshold:
        dist = levenshtein_distance(domain, official)
        if dist <= threshold:
            return True

    return False


def validate_email_address(addr: str) -> tuple[bool, str]:
    """Validate sender address: must have exactly one '@', no spaces, control chars, or '<' '>'."""
    if not addr:
        return False, ""

    # Check for invalid characters
    for c in addr:
        cp = ord(c)
        if cp < 32 or cp == 127 or c in (" ", "<", ">"):
            # Invalid address format
            last_at = addr.rfind("@")
            domain_part = addr[last_at + 1:].strip().lower().rstrip(".") if last_at != -1 else ""
            return False, domain_part

    if addr.count("@") != 1:
        last_at = addr.rfind("@")
        domain_part = addr[last_at + 1:].strip().lower().rstrip(".") if last_at != -1 else ""
        return False, domain_part

    domain = addr.split("@")[1].strip().lower().rstrip(".")
    if not domain or len(domain) > 253:
        return False, domain

    return True, domain


def analyze_layer1(email: EmailInput) -> LayerResult:
    """Layer 1: Sender domain, headers, and attachment validation."""
    reasons: list[str] = []
    level = LEVEL_GREEN

    def raise_level(new_level: str, reason: str | None = None) -> None:
        nonlocal level
        if LEVEL_RANKS[new_level] > LEVEL_RANKS[level]:
            level = new_level
        if reason and reason not in reasons:
            reasons.append(reason)

    try:
        # --- 1. Sender Domain Evaluation ---
        valid_addr, domain = validate_email_address(email.sender)
        sender_is_official = False

        if not valid_addr or not domain or len(domain) > 253:
            raise_level(LEVEL_YELLOW, "Dirección de remitente inválida o manipulada.")

        domain_matched = False
        if domain:
            for off in repo.official_domains:
                # 2.1 Domain exact or subdomain
                if domain == off or domain.endswith("." + off):
                    sender_is_official = True
                    domain_matched = True
                    break
                # 2.2 Official domain appears inside domain but not as exact suffix
                elif off in domain:
                    raise_level(LEVEL_RED, f"El dominio del remitente intenta aparentar ser <{off}> (subdominio engañoso).")
                    domain_matched = True
                    break
                # 2.3 Resembles official domain
                elif is_similar_domain(domain, off):
                    raise_level(LEVEL_RED, f"El dominio del remitente ({domain}) imita al dominio oficial <{off}>.")
                    domain_matched = True
                    break

            if not domain_matched:
                # Non-ASCII or punycode check
                has_non_ascii = any(ord(c) > 127 for c in domain)
                has_punycode = any(part.startswith("xn--") for part in domain.split("."))
                if has_non_ascii or has_punycode:
                    raise_level(LEVEL_YELLOW, "El dominio usa caracteres internacionales que pueden imitar a otro.")
                else:
                    raise_level(EXTERNAL_SENDER_LEVEL, "Remitente fuera de la red institucional.")

        # --- 2. Headers Evaluation ---
        disp_name_clean = strip_accents(email.display_name).lower()

        # Institutional term in display_name when sender is not official
        if not sender_is_official:
            for term in repo.institutional_terms:
                term_clean = strip_accents(term).lower()
                if term_clean in disp_name_clean:
                    raise_level(LEVEL_YELLOW, "El nombre mostrado parece institucional, pero la dirección no lo es.")
                    break

        # Display name contains an official domain/address when sender is not official
        if not sender_is_official:
            for off in repo.official_domains:
                if off in disp_name_clean:
                    raise_level(LEVEL_RED, "El nombre mostrado incluye una dirección institucional que no es la del remitente real.")
                    break

        # Reply-To domain check
        if email.reply_to.strip():
            rt_addr = email.reply_to.strip()
            _, rt_domain = validate_email_address(rt_addr)
            if not rt_domain and "@" in rt_addr:
                rt_domain = rt_addr.split("@")[-1].strip().lower().rstrip(".")
            if rt_domain and rt_domain != domain:
                raise_level(LEVEL_YELLOW, "Las respuestas se enviarían a una dirección distinta del remitente.")

        # --- 3. Attachments Evaluation ---
        for raw_att in email.attachments:
            # Check for BIDI direction override characters
            if any(c in BIDI_CHARS for c in raw_att):
                raise_level(LEVEL_BLACK, f"El adjunto {raw_att} usa caracteres ocultos para disfrazar su extensión.")
                continue

            # Clean control chars, trailing spaces, and dots
            cleaned_name = "".join(c for c in raw_att if ord(c) >= 32 and ord(c) != 127).rstrip(" .")
            lower_name = cleaned_name.lower()

            parts = lower_name.split(".")
            if len(parts) >= 2:
                ext = "." + parts[-1].rstrip(" .")
                penultimate_ext = "." + parts[-2].rstrip(" .") if len(parts) >= 3 else None

                # Double extension check: penultimate in common_documents, last in prohibited
                if penultimate_ext and penultimate_ext in repo.common_documents and ext in repo.prohibited_extensions:
                    raise_level(LEVEL_BLACK, f"El adjunto {raw_att} oculta un ejecutable tras una extensión de documento.")
                elif ext in repo.prohibited_extensions:
                    raise_level(LEVEL_BLACK, f"El adjunto {raw_att} es un archivo ejecutable o de alto riesgo.")
                elif ext in repo.suspicious_extensions:
                    raise_level(LEVEL_YELLOW, f"El adjunto {raw_att} es un archivo comprimido o con macros: revíselo con cuidado.")

    except Exception:
        # Fail safe to YELLOW on any unexpected exception
        return LayerResult(
            name="layer1",
            level=LEVEL_YELLOW,
            reasons=[LAYER_FALLBACK_REASON],
            score=None,
        )

    return LayerResult(
        name="layer1",
        level=level,
        reasons=reasons,
        score=None,
    )


def analyze_layer2(email: EmailInput) -> LayerResult:
    """Layer 2: Content heuristic scoring and phishing phrases analysis."""
    try:
        combined_text = f"{email.subject} {email.body}"
        normalized = normalize_text_layer2(combined_text)

        score = 0
        reasons: list[str] = []

        for item in repo.phishing_phrases:
            phrase = item["phrase"]
            weight = item["weight"]
            phrase_type = item["type"]

            # Phishing phrases in JSON are already normalized
            if phrase in normalized:
                score += weight
                reasons.append(f"Frase sospechosa detectada: «{phrase}» ({phrase_type}).")

        if score < LAYER2_YELLOW_MIN:
            level = LEVEL_GREEN
        elif score < LAYER2_RED_MIN:
            level = LEVEL_YELLOW
        else:
            level = LEVEL_RED

        return LayerResult(
            name="layer2",
            level=level,
            reasons=reasons,
            score=score,
        )
    except Exception:
        # Fail safe to YELLOW on any unexpected exception
        return LayerResult(
            name="layer2",
            level=LEVEL_YELLOW,
            reasons=[LAYER_FALLBACK_REASON],
            score=None,
        )


def combine_levels(
    layer1: LayerResult,
    layer2: LayerResult,
    layer3: LayerResult | None = None,
) -> tuple[str, str]:
    """Combine results from layers: highest severity always prevails.

    Returns (final_level, user_message).
    """
    levels = [layer1.level, layer2.level]
    if layer3 is not None and layer3.level in LEVEL_RANKS:
        levels.append(layer3.level)

    final_level = max(levels, key=lambda lvl: LEVEL_RANKS[lvl])
    return final_level, USER_MESSAGES[final_level]
