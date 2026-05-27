"""
Structured logging + OpenTelemetry tracing (Task 28)

Features:
  - structlog with JSON output (each log line is valid JSON)
  - Correlation request_id propagated through the full chain
  - OpenTelemetry tracer exported to Jaeger (OTLP gRPC)
  - Flame-graph traceable: Telegram → bot → MCP → Ollama → response

Usage:
    from utils.logging_setup import setup_logging, get_logger, create_span

    setup_logging()  # call once at startup

    log = get_logger("my_module")
    log.info("processing", user_id=123, action="text_message")

    with create_span("llm_request") as span:
        span.set_attribute("model", "llama-3.1-8b-instant")
        ...
"""

import logging
import os
import uuid
from contextlib import contextmanager
from typing import Any

import structlog
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

JAEGER_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "telegram-ai-bot")

_tracer: trace.Tracer | None = None


def setup_logging(json_logs: bool = True, log_file: str = "bot.log"):
    """Initialize structlog with JSON output and OpenTelemetry tracing."""
    _setup_structlog(json_logs=json_logs)
    _setup_otel()
    # Redirect standard logging to structlog
    logging.basicConfig(
        format="%(message)s",
        level=logging.INFO,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _setup_structlog(json_logs: bool = True):
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]
    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _setup_otel():
    global _tracer
    resource = Resource.create({"service.name": SERVICE_NAME})
    provider = TracerProvider(resource=resource)

    # Try OTLP (Jaeger) first, fall back to console
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=JAEGER_ENDPOINT, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    except Exception:
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(SERVICE_NAME)


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def bind_request_context(request_id: str, **kwargs: Any):
    """Bind request_id to structlog context (all subsequent logs include it)."""
    structlog.contextvars.bind_contextvars(request_id=request_id, **kwargs)


def clear_request_context():
    structlog.contextvars.clear_contextvars()


@contextmanager
def create_span(name: str, **attributes):
    """Context manager for creating an OTel span with optional attributes."""
    tracer = _tracer or trace.get_tracer(SERVICE_NAME)
    with tracer.start_as_current_span(name) as span:
        for k, v in attributes.items():
            span.set_attribute(k, str(v))
        yield span


def get_current_trace_id() -> str:
    """Return current OTel trace ID for correlation logging."""
    ctx = trace.get_current_span().get_span_context()
    if ctx.trace_id:
        return format(ctx.trace_id, "032x")
    return ""
