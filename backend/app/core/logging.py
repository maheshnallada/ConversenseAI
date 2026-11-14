import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

trace_id_ctx: ContextVar[str] = ContextVar("trace_id", default="")
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_ctx: ContextVar[str] = ContextVar("tenant_id", default="")


class StructuredJsonFormatter(logging.Formatter):
    """
    Formats log records as single-line JSON objects with correlation IDs,
    timestamps, and execution metadata for observability and tracing.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_obj: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Tracing context
        trace_id = trace_id_ctx.get()
        request_id = request_id_ctx.get()
        tenant_id = tenant_id_ctx.get()

        if trace_id:
            log_obj["trace_id"] = trace_id
        if request_id:
            log_obj["request_id"] = request_id
        if tenant_id:
            log_obj["tenant_id"] = tenant_id

        # Attach extra attributes if present
        for key in ("method", "path", "status_code", "duration_ms", "client_ip", "interaction_id", "details"):
            if hasattr(record, key):
                log_obj[key] = getattr(record, key)

        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_obj)


def configure_logging(level: str = "INFO") -> None:
    """Configures the root and app loggers with the StructuredJsonFormatter."""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root_logger.addHandler(handler)

    # Ensure uvicorn access logs are not conflicting or overly verbose
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.error").handlers = [handler]


def get_logger(name: str = "conversense") -> logging.Logger:
    return logging.getLogger(name)


class TraceLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates/extracts X-Trace-ID and X-Request-ID,
    binds them to contextvars, logs structured metrics on request completion,
    and returns tracing headers to the client.
    """

    def __init__(self, app, logger_name: str = "conversense.api"):
        super().__init__(app)
        self.logger = logging.getLogger(logger_name)

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("x-trace-id") or str(uuid.uuid4())
        request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id") or str(uuid.uuid4())
        tenant_id = request.headers.get("X-Tenant-Id") or request.headers.get("x-tenant-id") or "health_campaign"

        token_trace = trace_id_ctx.set(trace_id)
        token_req = request_id_ctx.set(request_id)
        token_tenant = tenant_id_ctx.set(tenant_id)

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Request-ID"] = request_id

            # Avoid logging static assets on every refresh if needed, but log all API calls
            if request.url.path.startswith("/api/"):
                self.logger.info(
                    f"{request.method} {request.url.path} {response.status_code} in {duration_ms}ms",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "client_ip": client_ip,
                    },
                )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            self.logger.error(
                f"Unhandled error handling {request.method} {request.url.path}: {exc}",
                exc_info=True,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            raise
        finally:
            trace_id_ctx.reset(token_trace)
            request_id_ctx.reset(token_req)
            tenant_id_ctx.reset(token_tenant)

