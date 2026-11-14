"""FastAPI main application entrypoint for Mail CoastGuard.

Strict whitelist routing, hardened security headers, rate limiting, and zero-PII logging.
"""

from __future__ import annotations

import asyncio
import collections
from contextlib import asynccontextmanager
import logging
import os
import re
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError

from backend.admin_api import record_ai_call, router as admin_router
from backend.ai_adapter import (
    SYSTEM_PROMPT,
    format_email_for_ai,
    get_ai_adapter,
    validate_ai_response,
)
from backend.config import (
    ADMIN_API_ENABLED,
    AI_MAX_CALLS_PER_HOUR,
    AI_MAX_CONCURRENT,
    AI_PROVIDER,
    AI_TIMEOUT_SECONDS,
    AI_UNAVAILABLE_NOTICE,
    CORS_ORIGINS,
    DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE,
    EMAIL_TEMPLATES_PATH,
    INBOX_EMAILS_PATH,
    INDEX_HTML_PATH,
    MAX_REQUEST_SIZE_BYTES,
    RATE_LIMIT_PER_MINUTE,
    UNETI_LOGO_PATH,
)
from backend.models import (
    AIResult,
    AnalyzeResponse,
    DeepAnalysisResponse,
    EmailInput,
)
from backend.validation_engine import (
    analyze_layer1,
    analyze_layer2,
    combine_levels,
    repo,
)

# Configure zero-PII logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("mail_coastguard")

# Global sliding window rate limiter
class RateLimiter:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.general_requests: dict[str, list[float]] = collections.defaultdict(list)
        self.deep_requests: dict[str, list[float]] = collections.defaultdict(list)
        self.ai_call_timestamps: collections.deque[float] = collections.deque()

    async def check_general(self, ip: str) -> tuple[bool, int]:
        async with self.lock:
            now = time.time()
            valid = [t for t in self.general_requests[ip] if now - t < 60]
            if len(valid) >= RATE_LIMIT_PER_MINUTE:
                retry_after = max(1, int(60 - (now - valid[0])))
                return False, retry_after
            valid.append(now)
            self.general_requests[ip] = valid
            return True, 0

    async def check_deep_analysis(self, ip: str) -> tuple[bool, int]:
        async with self.lock:
            now = time.time()
            valid = [t for t in self.deep_requests[ip] if now - t < 60]
            if len(valid) >= DEEP_ANALYSIS_RATE_LIMIT_PER_MINUTE:
                retry_after = max(1, int(60 - (now - valid[0])))
                return False, retry_after
            valid.append(now)
            self.deep_requests[ip] = valid
            return True, 0

    async def check_and_record_hourly_ai(self) -> bool:
        async with self.lock:
            now = time.time()
            cutoff = now - 3600
            while self.ai_call_timestamps and self.ai_call_timestamps[0] < cutoff:
                self.ai_call_timestamps.popleft()
            if len(self.ai_call_timestamps) >= AI_MAX_CALLS_PER_HOUR:
                return False
            self.ai_call_timestamps.append(now)
            return True


rate_limiter = RateLimiter()
ai_concurrency_semaphore = asyncio.Semaphore(AI_MAX_CONCURRENT)

# Public whitelist routes exactly allowed
PUBLIC_WHITELIST_PATHS = {
    "/",
    "/inbox_emails.json",
    "/email_templates.json",
    "/assets/uneti_logo.png",
    "/health",
    "/analyze",
    "/deep-analysis",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: strictly validate detection lists
    try:
        repo.load_all()
    except Exception as exc:
        logger.critical("Failed to load required data lists on startup: %s", exc)
        raise RuntimeError("Startup aborted: data lists invalid or missing") from exc

    # Warm-up AI if Ollama is selected
    if AI_PROVIDER == "ollama":
        try:
            get_ai_adapter("ollama")
        except Exception:
            logger.warning("AI warm-up failed")

    yield


app = FastAPI(
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    debug=False,
    lifespan=lifespan,
)

# Optional CORS setup
if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "HEAD", "OPTIONS"],
        allow_headers=["*"],
    )

# Mount Admin API conditionally
if ADMIN_API_ENABLED:
    app.include_router(admin_router)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    raw_path = request.url.path

    # Sanitize path for logging
    clean_path = "".join(c for c in raw_path if ord(c) >= 32 and ord(c) != 127)[:100]

    # Block path traversal, decoys, hidden files, and unauthorized segments
    is_admin_path = ADMIN_API_ENABLED and raw_path.startswith("/api/admin/v1/")
    forbidden_markers = [
        "..", "%2e", "%2f", "\\",
        "/admin", "/administrator", "/wp-admin", "/phpmyadmin",
        "/console", "/debug", "/config", "/actuator", "/server-status",
        "/docs", "/redoc", "/openapi.json",
        "/backend", "/data", "/tests", "/evaluation", "/extension",
    ]
    lower_path = raw_path.lower()
    if any(marker in lower_path for marker in forbidden_markers):
        logger.warning("Blocked sensitive path attempt: %s", clean_path)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
        )

    # Check for hidden files (segments starting with '.')
    segments = [s for s in raw_path.split("/") if s]
    if any(s.startswith(".") for s in segments):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
        )

    # Check against whitelist
    if not is_admin_path and raw_path not in PUBLIC_WHITELIST_PATHS:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
        )

    # Check method
    allowed_methods = {"GET", "POST", "HEAD", "OPTIONS"}
    if request.method not in allowed_methods and not is_admin_path:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
        )

    # Enforce request body size limits
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_SIZE_BYTES:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Payload too large"},
                )
        except ValueError:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid Content-Length"},
            )

    # Enforce Content-Type for POST requests
    if request.method == "POST":
        ctype = request.headers.get("content-type", "")
        if "application/json" not in ctype.lower():
            return JSONResponse(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                content={"detail": "Unsupported media type: expected application/json"},
            )

    # Enforce Rate Limiting for public endpoints
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not is_admin_path:
        gen_allowed, gen_retry = await rate_limiter.check_general(client_ip)
        if not gen_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(gen_retry)},
            )

        if raw_path == "/deep-analysis":
            deep_allowed, deep_retry = await rate_limiter.check_deep_analysis(client_ip)
            if not deep_allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Too many requests for deep analysis"},
                    headers={"Retry-After": str(deep_retry)},
                )

    try:
        response: Response = await call_next(request)
    except Exception as exc:
        logger.error("Unhandled server exception: %s", type(exc).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal error"},
        )

    # Inject mandatory security headers
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "base-uri 'none'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"

    # Safe log of request outcome
    logger.info("Path=%s Status=%d", clean_path, response.status_code)
    return response


@app.exception_handler(RequestValidationError)
@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: Exception):
    """Generic 422 error handler without echoing input payload."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation error"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Generic 500 error handler hiding stack trace and internal details."""
    logger.error("Global exception caught: %s", type(exc).__name__)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal error"},
    )


# --- Public Static Routes ---

@app.get("/", include_in_schema=False)
@app.head("/", include_in_schema=False)
async def get_index():
    if not INDEX_HTML_PATH.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(INDEX_HTML_PATH, media_type="text/html; charset=utf-8")


@app.get("/inbox_emails.json", include_in_schema=False)
async def get_inbox_emails():
    if not INBOX_EMAILS_PATH.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(INBOX_EMAILS_PATH, media_type="application/json")


@app.get("/email_templates.json", include_in_schema=False)
async def get_email_templates():
    if not EMAIL_TEMPLATES_PATH.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(EMAIL_TEMPLATES_PATH, media_type="application/json")


@app.get("/assets/uneti_logo.png", include_in_schema=False)
async def get_uneti_logo():
    if not UNETI_LOGO_PATH.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return FileResponse(UNETI_LOGO_PATH, media_type="image/png")


# --- Public API Routes ---

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_email(email: EmailInput):
    layer1 = analyze_layer1(email)
    layer2 = analyze_layer2(email)
    final_level, message = combine_levels(layer1, layer2)

    logger.info("Analyze completed: final_level=%s", final_level)
    return AnalyzeResponse(
        final_level=final_level,
        message=message,
        layers=[layer1, layer2],
    )


@app.post("/deep-analysis", response_model=DeepAnalysisResponse)
async def deep_analyze_email(email: EmailInput):
    # Layers 1 and 2 run again (stateless server)
    layer1 = analyze_layer1(email)
    layer2 = analyze_layer2(email)
    base_level, base_message = combine_levels(layer1, layer2)

    # Check global hourly quota
    can_call_ai = await rate_limiter.check_and_record_hourly_ai()
    if not can_call_ai:
        logger.warning("AI hourly rate limit reached: falling back to local layers")
        return DeepAnalysisResponse(
            status="unavailable",
            notice=AI_UNAVAILABLE_NOTICE,
            final_level=base_level,
            message=base_message,
            layers=[layer1, layer2],
            layer3=None,
        )

    # Execute Layer 3 via AI Adapter
    ai_result: AIResult | None = None
    try:
        async with ai_concurrency_semaphore:
            adapter = get_ai_adapter()
            formatted_email = format_email_for_ai(email)

            # Run synchronous adapter in thread pool with strict timeout
            raw_text = await asyncio.wait_for(
                asyncio.to_thread(adapter.analyze, SYSTEM_PROMPT, formatted_email),
                timeout=AI_TIMEOUT_SECONDS,
            )
            record_ai_call()
            ai_result = validate_ai_response(raw_text)
    except Exception as exc:
        logger.warning("AI Layer 3 execution failed: %s", type(exc).__name__)
        ai_result = None

    if ai_result is None:
        # Controlled degradation
        logger.info("Deep analysis unavailable: returning local layers. Level=%s", base_level)
        return DeepAnalysisResponse(
            status="unavailable",
            notice=AI_UNAVAILABLE_NOTICE,
            final_level=base_level,
            message=base_message,
            layers=[layer1, layer2],
            layer3=None,
        )

    # Combine with asymmetry rule: AI can only increase risk
    final_level, message = combine_levels(layer1, layer2, layer3=ai_result)
    logger.info("Deep analysis completed: final_level=%s", final_level)

    return DeepAnalysisResponse(
        status="ok",
        notice=None,
        final_level=final_level,
        message=message,
        layers=[layer1, layer2],
        layer3=ai_result,
    )
