"""Configuration and constants for Mail CoastGuard backend.

All environment loading strictly occurs here via python-dotenv.
"""

from __future__ import annotations

import ipaddress
import os
from pathlib import Path
import socket
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

# --- Filesystem Paths ---
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

OFFICIAL_DOMAINS_PATH = DATA_DIR / "official_domains.json"
DANGEROUS_EXTENSIONS_PATH = DATA_DIR / "dangerous_extensions.json"
PHISHING_PHRASES_PATH = DATA_DIR / "phishing_phrases.json"

FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML_PATH = FRONTEND_DIR / "index.html"
INBOX_EMAILS_PATH = FRONTEND_DIR / "inbox_emails.json"
EMAIL_TEMPLATES_PATH = FRONTEND_DIR / "email_templates.json"
UNETI_LOGO_PATH = FRONTEND_DIR / "assets" / "uneti_logo.png"

# --- Fixed Cloud Provider URLs & Parameters ---
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
AI_MAX_OUTPUT_TOKENS = 300

# --- Severity Levels and User Notices (Spanish literals for public servants) ---
LEVEL_GREEN = "GREEN"
LEVEL_YELLOW = "YELLOW"
LEVEL_RED = "RED"
LEVEL_BLACK = "BLACK"

LEVEL_RANKS: dict[str, int] = {
    LEVEL_GREEN: 1,
    LEVEL_YELLOW: 2,
    LEVEL_RED: 3,
    LEVEL_BLACK: 4,
}

USER_MESSAGES: dict[str, str] = {
    LEVEL_BLACK: "Adjunto peligroso: no lo abra.",
    LEVEL_RED: "Posible phishing: no haga clic ni responda.",
    LEVEL_YELLOW: "Revise con cuidado antes de actuar.",
    LEVEL_GREEN: "Sin indicios detectados. Esto no garantiza que el correo sea seguro.",
}

AI_UNAVAILABLE_NOTICE = "Análisis profundo no disponible. Se muestra el resultado de las capas locales."
LAYER_FALLBACK_REASON = "No se pudo analizar el correo por completo. Revíselo con cuidado."

# Layer 1 Defaults
EXTERNAL_SENDER_LEVEL = "YELLOW"

# Layer 2 Thresholds
LAYER2_YELLOW_MIN = 3
LAYER2_RED_MIN = 7

# Content & Input Constraints
MAX_BODY_CHARS = 50_000
AI_BODY_TRUNCATE_CHARS = 8_000
MAX_SENDER_LEN = 320
MAX_DISPLAY_NAME_LEN = 200
MAX_REPLY_TO_LEN = 320
MAX_SUBJECT_LEN = 500
MAX_ATTACHMENTS_COUNT = 50
MAX_ATTACHMENT_NAME_LEN = 255


def _get_bool(env_var: str, default: bool = False) -> bool:
    val = os.getenv(env_var)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "on")


def _get_int(env_var: str, default: int) -> int:
    val = os.getenv(env_var)
    if val is None:
        return default
    try:
        return int(val.strip())
    except ValueError:
        return default


def _get_float(env_var: str, default: float) -> float:
    val = os.getenv(env_var)
    if val is None:
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


# --- Environment Settings ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
if AI_PROVIDER not in ("gemini", "deepseek", "ollama", "mock"):
    raise ValueError(f"Unknown AI_PROVIDER: '{AI_PROVIDER}'. Must be one of: gemini, deepseek, ollama, mock.")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b").strip()
OLLAMA_NUM_CTX = _get_int("OLLAMA_NUM_CTX", 6144)
OLLAMA_NUM_PREDICT = _get_int("OLLAMA_NUM_PREDICT", 300)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m").strip()

# Active AI model resolved by provider
if AI_PROVIDER == "gemini":
    AI_MODEL = GEMINI_MODEL
elif AI_PROVIDER == "deepseek":
    AI_MODEL = DEEPSEEK_MODEL
elif AI_PROVIDER == "ollama":
    AI_MODEL = OLLAMA_MODEL
else:
    AI_MODEL = "mock"


AI_TIMEOUT_SECONDS = _get_float("AI_TIMEOUT_SECONDS", 60.0)
AI_MAX_CONCURRENT = _get_int("AI_MAX_CONCURRENT", 1)
APP_HOST = os.getenv("APP_HOST", "127.0.0.1").strip()
APP_PORT = _get_int("APP_PORT", 8000)

_cors_raw = os.getenv("CORS_ORIGINS", "").strip()
CORS_ORIGINS: list[str] = [x.strip() for x in _cors_raw.split(",") if x.strip()]

MAX_REQUEST_SIZE_BYTES = _get_int("MAX_REQUEST_SIZE_BYTES", 204800)
RATE_LIMIT_PER_MINUTE = _get_int("RATE_LIMIT_PER_MINUTE", 30)
DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE = _get_int("DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE", 6)
AI_MAX_CALLS_PER_HOUR = _get_int("AI_MAX_CALLS_PER_HOUR", 100)

# --- Admin API Configuration ---
ADMIN_API_ENABLED = _get_bool("ADMIN_API_ENABLED", False)
ADMIN_API_KEY_SHA256 = os.getenv("ADMIN_API_KEY_SHA256", "").strip().lower()

_admin_ips_raw = os.getenv("ADMIN_ALLOWED_IPS", "127.0.0.1,::1").strip()
ADMIN_ALLOWED_IPS: list[str] = [x.strip() for x in _admin_ips_raw.split(",") if x.strip()]

ADMIN_RATE_LIMIT_PER_MINUTE = _get_int("ADMIN_RATE_LIMIT_PER_MINUTE", 20)
ADMIN_MAX_FAILED_ATTEMPTS = _get_int("ADMIN_MAX_FAILED_ATTEMPTS", 5)
ADMIN_LOCKOUT_MINUTES = _get_int("ADMIN_LOCKOUT_MINUTES", 15)


def is_safe_ollama_url(url: str) -> bool:
    """Validate Ollama URL against SSRF: only http/https to loopback or RFC 1918."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname
        if not host:
            return False
        if host.lower() == "localhost":
            return True
        # Check if host is direct IP address
        try:
            ip = ipaddress.ip_address(host)
            return ip.is_loopback or ip.is_private
        except ValueError:
            # Resolve hostname to verify all IPs
            addr_info = socket.getaddrinfo(host, None)
            for item in addr_info:
                resolved_ip_str = item[4][0]
                ip = ipaddress.ip_address(resolved_ip_str)
                if not (ip.is_loopback or ip.is_private):
                    return False
            return True
    except Exception:
        return False


def validate_admin_allowed_ips(allowed_ips: list[str]) -> bool:
    """Verify that all admin allowed IPs are private or loopback."""
    for ip_entry in allowed_ips:
        try:
            if "/" in ip_entry:
                net = ipaddress.ip_network(ip_entry, strict=False)
                if not (net.is_loopback or net.is_private):
                    return False
            else:
                ip = ipaddress.ip_address(ip_entry)
                if not (ip.is_loopback or ip.is_private):
                    return False
        except ValueError:
            return False
    return True


# Deactivate Admin API if configuration is invalid
if ADMIN_API_ENABLED:
    if not ADMIN_API_KEY_SHA256 or len(ADMIN_API_KEY_SHA256) != 64:
        ADMIN_API_ENABLED = False
    elif not validate_admin_allowed_ips(ADMIN_ALLOWED_IPS):
        ADMIN_API_ENABLED = False
