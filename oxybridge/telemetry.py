import json
import logging

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider

from oxybridge.config import settings
from oxybridge.db import now

configured = False


def configure(service):
    global configured
    if configured:
        return
    configured = True
    provider = TracerProvider(resource=Resource.create({"service.name": "oxybridge-" + service}))
    endpoint = settings().otel_exporter_otlp_endpoint
    if endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip("/") + "/v1/traces"))
        )
    trace.set_tracer_provider(provider)
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log(event, **fields):
    logging.getLogger("oxybridge").info(
        json.dumps({"timestamp": now().isoformat(), "level": "INFO", "event": event, **fields})
    )


tracer = trace.get_tracer("oxybridge")
