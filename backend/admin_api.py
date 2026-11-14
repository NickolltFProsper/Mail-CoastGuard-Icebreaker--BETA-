"""Admin API for securely managing detection lists.

Optional component activated only when ADMIN_API_ENABLED=true and ADMIN_API_KEY_SHA256 is set.
"""

from __future__ import annotations

import collections
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from backend.config import (
    ADMIN_ALLOWED_IPS,
    ADMIN_API_ENABLED,
    ADMIN_API_KEY_SHA256,
    ADMIN_LOCKOUT_MINUTES,
    ADMIN_MAX_FAILED_ATTEMPTS,
    ADMIN_RATE_LIMIT_PER_MINUTE,
    AI_MODEL,
    AI_PROVIDER,
    DANGEROUS_EXTENSIONS_PATH,
    DATA_DIR,
    OFFICIAL_DOMAINS_PATH,
    PHISHING_PHRASES_PATH,
)
from backend.validation_engine import normalize_text_layer2, repo

admin_logger = logging.getLogger("mail_coastguard.admin")

router = APIRouter(prefix="/api/admin/v1")

# Fixed mappings for detection lists
LIST_PATHS: dict[str, Path] = {
    "official_domains": OFFICIAL_DOMAINS_PATH,
    "dangerous_extensions": DANGEROUS_EXTENSIONS_PATH,
    "phishing_phrases": PHISHING_PHRASES_PATH,
}

# Regex patterns for strict validation
DOMAIN_REGEX = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$")
EXT_REGEX = re.compile(r"^\.[a-z0-9]{1,10}$")

# Thread safety lock for atomic file updates
_write_lock = threading.Lock()

# Server start time for uptime calculation
START_TIME = time.time()

# AI call tracker (timestamp list)
_ai_calls: collections.deque[float] = collections.deque()

def record_ai_call() -> None:
    now = time.time()
    _ai_calls.append(now)
    cutoff = now - 3600
    while _ai_calls and _ai_calls[0] < cutoff:
        _ai_calls.popleft()

def get_ai_calls_last_hour() -> int:
    now = time.time()
    cutoff = now - 3600
    while _ai_calls and _ai_calls[0] < cutoff:
        _ai_calls.popleft()
    return len(_ai_calls)

# Rate limiter & brute-force tracker for admin API
class AdminSecurityTracker:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.failed_attempts: dict[str, list[float]] = collections.defaultdict(list)
        self.lockouts: dict[str, float] = {}
        self.request_timestamps: dict[str, list[float]] = collections.defaultdict(list)
        self.audit_log: collections.deque[dict[str, Any]] = collections.deque(maxlen=200)

    def is_locked_out(self, ip: str) -> tuple[bool, int]:
        now = time.time()
        with self.lock:
            unlock_time = self.lockouts.get(ip, 0)
            if now < unlock_time:
                remaining = int(unlock_time - now) + 1
                return True, remaining
            elif ip in self.lockouts:
                del self.lockouts[ip]
                self.failed_attempts[ip] = []
            return False, 0

    def record_failure(self, ip: str) -> bool:
        now = time.time()
        with self.lock:
            attempts = [t for t in self.failed_attempts[ip] if now - t < ADMIN_LOCKOUT_MINUTES * 60]
            attempts.append(now)
            self.failed_attempts[ip] = attempts
            if len(attempts) >= ADMIN_MAX_FAILED_ATTEMPTS:
                self.lockouts[ip] = now + (ADMIN_LOCKOUT_MINUTES * 60)
                return True
            return False

    def check_rate_limit(self, ip: str) -> tuple[bool, int]:
        now = time.time()
        with self.lock:
            times = [t for t in self.request_timestamps[ip] if now - t < 60]
            if len(times) >= ADMIN_RATE_LIMIT_PER_MINUTE:
                oldest = times[0]
                retry_after = max(1, int(60 - (now - oldest)))
                return False, retry_after
            times.append(now)
            self.request_timestamps[ip] = times
            return True, 0

    def log_audit(self, action: str, list_name: str | None, status_code: int, client_ip: str) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "list_name": list_name,
            "status_code": status_code,
            "client_ip": client_ip,
        }
        with self.lock:
            self.audit_log.append(entry)
        admin_logger.info(
            "Admin action: action=%s list=%s status=%d ip=%s",
            action, list_name or "none", status_code, client_ip
        )


admin_tracker = AdminSecurityTracker()


def compute_file_sha256(path: Path) -> str:
    """Compute canonical SHA-256 hash of a JSON file's normalized content."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compute_data_sha256(data: Any) -> str:
    """Compute SHA-256 hash of data in canonical JSON representation."""
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def is_ip_allowed(client_ip: str) -> bool:
    """Verify if the client IP is in ADMIN_ALLOWED_IPS."""
    try:
        ip = ipaddress.ip_address(client_ip)
        for allowed in ADMIN_ALLOWED_IPS:
            if "/" in allowed:
                if ip in ipaddress.ip_network(allowed, strict=False):
                    return True
            else:
                if ip == ipaddress.ip_address(allowed):
                    return True
    except Exception:
        return False
    return False


async def authenticate_admin_request(request: Request, action: str = "request", list_name: str | None = None) -> None:
    """Enforce strict authentication and authorization layers for Admin API."""
    if not ADMIN_API_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    client_ip = request.client.host if request.client else "unknown"

    # Layer 2: Network origin check
    if not is_ip_allowed(client_ip):
        admin_tracker.log_audit(action, list_name, 404, client_ip)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Layer 3: No browser context allowed
    if "origin" in request.headers or "sec-fetch-site" in request.headers:
        admin_tracker.log_audit(action, list_name, 403, client_ip)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Layer 6: Brute force lockout check
    is_locked, retry_after = admin_tracker.is_locked_out(client_ip)
    if is_locked:
        admin_tracker.log_audit(action, list_name, 429, client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed attempts",
            headers={"Retry-After": str(retry_after)},
        )

    # Layer 7: Rate limiting
    allowed, rate_retry = admin_tracker.check_rate_limit(client_ip)
    if not allowed:
        admin_tracker.log_audit(action, list_name, 429, client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(rate_retry)},
        )

    # Layer 4: Admin API key verification
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        admin_tracker.record_failure(client_ip)
        admin_tracker.log_audit(action, list_name, 401, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header[7:].strip()
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    if not hmac.compare_digest(token_hash, ADMIN_API_KEY_SHA256):
        admin_tracker.record_failure(client_ip)
        admin_tracker.log_audit(action, list_name, 401, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/status")
async def get_admin_status(request: Request) -> JSONResponse:
    await authenticate_admin_request(request, action="get_status")
    client_ip = request.client.host if request.client else "unknown"

    lists_info: dict[str, Any] = {}
    for name, path in LIST_PATHS.items():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        count = len(data) if isinstance(data, list) else len(data.get("domains", []))
        lists_info[name] = {
            "count": count,
            "version": compute_file_sha256(path),
        }

    admin_tracker.log_audit("get_status", None, 200, client_ip)
    return JSONResponse(
        content={
            "uptime_seconds": round(time.time() - START_TIME, 2),
            "ai_provider": AI_PROVIDER,
            "ai_model": AI_MODEL if AI_PROVIDER != "mock" else "mock",
            "ai_calls_last_hour": get_ai_calls_last_hour(),
            "lists": lists_info,
        },
        headers={"Cache-Control": "no-store"},
    )


@router.get("/lists/{list_name}")
async def get_list(list_name: str, request: Request) -> JSONResponse:
    if list_name not in LIST_PATHS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    await authenticate_admin_request(request, action="get_list", list_name=list_name)
    client_ip = request.client.host if request.client else "unknown"

    path = LIST_PATHS[list_name]
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    admin_tracker.log_audit("get_list", list_name, 200, client_ip)
    return JSONResponse(
        content={
            "name": list_name,
            "version": compute_file_sha256(path),
            "data": data,
        },
        headers={"Cache-Control": "no-store"},
    )


def validate_list_content(list_name: str, data: Any) -> None:
    """Strictly validate list data according to security specifications."""
    if list_name == "official_domains":
        if not isinstance(data, dict) or set(data.keys()) != {"domains", "institutional_terms"}:
            raise ValueError("Invalid structure for official_domains")
        domains = data.get("domains")
        terms = data.get("institutional_terms")
        if not isinstance(domains, list) or not (1 <= len(domains) <= 200):
            raise ValueError("Invalid domains count")
        if not isinstance(terms, list) or not (1 <= len(terms) <= 200):
            raise ValueError("Invalid institutional_terms count")

        for d in domains:
            if not isinstance(d, str) or len(d) > 253 or not DOMAIN_REGEX.match(d):
                raise ValueError("Invalid domain entry")
        for t in terms:
            if not isinstance(t, str) or len(t) > 100 or t != t.lower():
                raise ValueError("Invalid institutional term entry")

    elif list_name == "dangerous_extensions":
        if not isinstance(data, dict) or set(data.keys()) != {"prohibited", "suspicious", "common_documents"}:
            raise ValueError("Invalid structure for dangerous_extensions")
        proh = data.get("prohibited")
        susp = data.get("suspicious")
        common = data.get("common_documents")
        for lst in (proh, susp, common):
            if not isinstance(lst, list) or not (1 <= len(lst) <= 200):
                raise ValueError("Invalid extensions list count")
            for ext in lst:
                if not isinstance(ext, str) or not EXT_REGEX.match(ext):
                    raise ValueError("Invalid extension format")

        # Disallow prohibited in common_documents
        proh_set = set(proh)
        common_set = set(common)
        if proh_set.intersection(common_set):
            raise ValueError("Extension conflict between prohibited and common_documents")

    elif list_name == "phishing_phrases":
        if not isinstance(data, list) or not (1 <= len(data) <= 1000):
            raise ValueError("Invalid phrases count")
        seen_phrases: set[str] = set()
        for item in data:
            if not isinstance(item, dict) or set(item.keys()) != {"phrase", "weight", "type"}:
                raise ValueError("Invalid phrase object keys")
            phrase = item.get("phrase")
            weight = item.get("weight")
            ptype = item.get("type")
            if not isinstance(phrase, str) or not (1 <= len(phrase) <= 200):
                raise ValueError("Invalid phrase length")
            if any(ord(c) < 32 or ord(c) == 127 for c in phrase):
                raise ValueError("Control characters in phrase")
            # Verify phrase is already normalized
            normalized = normalize_text_layer2(phrase)
            if phrase != normalized:
                raise ValueError("Phrase is not pre-normalized")
            if not isinstance(weight, int) or not (1 <= weight <= 10):
                raise ValueError("Invalid phrase weight")
            if not isinstance(ptype, str) or not (1 <= len(ptype) <= 60):
                raise ValueError("Invalid phrase type length")
            if phrase in seen_phrases:
                raise ValueError("Duplicate phrase detected")
            seen_phrases.add(phrase)


@router.put("/lists/{list_name}")
async def update_list(list_name: str, request: Request) -> JSONResponse:
    if list_name not in LIST_PATHS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    await authenticate_admin_request(request, action="update_list", list_name=list_name)
    client_ip = request.client.host if request.client else "unknown"

    content_type = request.headers.get("content-type", "")
    if "application/json" not in content_type:
        admin_tracker.log_audit("update_list", list_name, 415, client_ip)
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported media type")

    body_bytes = await request.body()
    if len(body_bytes) > 262144:  # 256 KB
        admin_tracker.log_audit("update_list", list_name, 413, client_ip)
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    if_match = request.headers.get("if-match")
    if not if_match:
        admin_tracker.log_audit("update_list", list_name, 428, client_ip)
        raise HTTPException(status_code=status.HTTP_428_PRECONDITION_REQUIRED, detail="If-Match header required")

    path = LIST_PATHS[list_name]
    current_version = compute_file_sha256(path)
    clean_match = if_match.strip().strip('"')
    if clean_match != current_version:
        admin_tracker.log_audit("update_list", list_name, 412, client_ip)
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail="Precondition failed")

    try:
        payload = json.loads(body_bytes)
    except Exception:
        admin_tracker.log_audit("update_list", list_name, 422, client_ip)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON")

    if not isinstance(payload, dict) or set(payload.keys()) != {"data"}:
        admin_tracker.log_audit("update_list", list_name, 422, client_ip)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Validation error")

    new_data = payload["data"]
    try:
        validate_list_content(list_name, new_data)
    except ValueError:
        admin_tracker.log_audit("update_list", list_name, 422, client_ip)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Validation error")

    # Atomic write with backup
    with _write_lock:
        tmp_path = path.with_suffix(".tmp")
        bak_path = path.with_suffix(".bak")
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, indent=2, ensure_ascii=False)

            # Copy current version to .bak
            with open(path, "r", encoding="utf-8") as src, open(bak_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())

            os.replace(tmp_path, path)
            # Reload repository in memory
            repo.load_all()
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            admin_tracker.log_audit("update_list", list_name, 500, client_ip)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")

    new_version = compute_file_sha256(path)
    admin_tracker.log_audit("update_list", list_name, 200, client_ip)
    return JSONResponse(
        content={"status": "ok", "version": new_version},
        headers={"Cache-Control": "no-store"},
    )


@router.post("/lists/reload")
async def reload_lists(request: Request) -> JSONResponse:
    await authenticate_admin_request(request, action="reload_lists")
    client_ip = request.client.host if request.client else "unknown"

    with _write_lock:
        try:
            repo.load_all()
        except Exception:
            admin_tracker.log_audit("reload_lists", None, 500, client_ip)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal error")

    admin_tracker.log_audit("reload_lists", None, 200, client_ip)
    return JSONResponse(
        content={"status": "reloaded"},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/audit")
async def get_audit(request: Request) -> JSONResponse:
    await authenticate_admin_request(request, action="get_audit")
    client_ip = request.client.host if request.client else "unknown"

    with admin_tracker.lock:
        entries = list(admin_tracker.audit_log)

    admin_tracker.log_audit("get_audit", None, 200, client_ip)
    return JSONResponse(
        content={"audit": entries},
        headers={"Cache-Control": "no-store"},
    )
