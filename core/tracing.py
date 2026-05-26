"""
Optional OpenTelemetry tracing (no-op when OTEL is disabled or packages are missing).

Enable by setting ``OTEL_EXPORTER_OTLP_ENDPOINT`` (and optionally ``OTEL_SERVICE_NAME``).
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

_TRACER: Any = None
_INITIALIZED = False


def _otel_enabled() -> bool:
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if not endpoint:
        return False
    disabled = os.environ.get("OTEL_SDK_DISABLED", "").strip().lower()
    return disabled not in {"true", "1", "yes", "on"}


def init_tracing(service_name: str | None = None) -> bool:
    """Configure OTLP exporter once per process. Returns True when a tracer is active."""
    global _TRACER, _INITIALIZED
    if _INITIALIZED:
        return _TRACER is not None
    _INITIALIZED = True

    if not _otel_enabled():
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info("OpenTelemetry packages not installed; tracing disabled")
        return False

    name = service_name or os.environ.get("OTEL_SERVICE_NAME", "aicom")
    resource = Resource.create({"service.name": name})
    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TRACER = trace.get_tracer(name)
    logger.info("OpenTelemetry tracing enabled (service=%s)", name)
    return True


def get_tracer():
    init_tracing()
    return _TRACER


@contextmanager
def span(
    name: str,
    *,
    attributes: Optional[dict[str, Any]] = None,
) -> Iterator[Any]:
    """Start a span when tracing is configured; otherwise no-op.

    Yields the underlying OTel span (or ``None`` when tracing is disabled) so
    callers can set additional attributes once results are known — e.g. token
    counts that aren't available at span start.
    """
    tracer = get_tracer()
    if tracer is None:
        yield None
        return
    with tracer.start_as_current_span(name) as current:
        if attributes and current is not None:
            for key, value in attributes.items():
                if value is not None:
                    current.set_attribute(str(key), value)
        yield current


def current_trace_id_hex() -> Optional[str]:
    """Return the active OTel trace id as a 32-char lowercase hex string, or None.

    Used to stamp business artifacts (e.g. UNI receipts) with a trace pointer so
    a buyer can later follow the receipt back to the LLM trace in LangSmith,
    Phoenix, Jaeger, etc.
    """
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    sp = trace.get_current_span()
    ctx = sp.get_span_context() if sp is not None else None
    if ctx is None or not getattr(ctx, "is_valid", False):
        return None
    tid = getattr(ctx, "trace_id", 0)
    if not tid:
        return None
    return format(tid, "032x")


def trace_url_for(trace_id: Optional[str]) -> Optional[str]:
    """Render a trace URL from ``OTEL_TRACE_URL_TEMPLATE`` (``{trace_id}`` placeholder).

    Example: ``https://smith.langchain.com/o/<org>/projects/p/<proj>/r/{trace_id}``.
    Returns ``None`` when the template is unset or the id is missing.
    """
    if not trace_id:
        return None
    tpl = os.environ.get("OTEL_TRACE_URL_TEMPLATE", "").strip()
    if not tpl or "{trace_id}" not in tpl:
        return None
    return tpl.replace("{trace_id}", trace_id)
