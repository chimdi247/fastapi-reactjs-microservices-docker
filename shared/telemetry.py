"""
Unified OpenTelemetry setup shared by every service.

Each service calls `setup_telemetry(service_name, app=...)` once at startup.
All three signals (traces, metrics, logs) are sent via OTLP/gRPC to the
OpenTelemetry Collector, which fans them out to Jaeger, Prometheus, and
Loki respectively. See /observability/otel-collector/otel-collector-config.yaml.
"""

import logging
import os

from opentelemetry import trace, metrics
from opentelemetry.sdk.resources import Resource

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter

# Every service in this project talks to the same collector. Overridable per
# service via the OTEL_EXPORTER_OTLP_ENDPOINT env var if ever needed.
OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")


def setup_telemetry(service_name: str, app=None):
    """
    Wires up traces, metrics, and logs for `service_name`, all exported to
    the OTel Collector. If `app` (a FastAPI instance) is passed, it is
    auto-instrumented for HTTP request tracing + metrics.

    Returns (tracer_provider, meter_provider, logger_provider) in case a
    service needs to create custom spans/metrics beyond the automatic ones.
    """
    resource = Resource.create({"service.name": service_name})

    # ---- Traces ----
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=OTEL_ENDPOINT, insecure=True))
    )
    trace.set_tracer_provider(tracer_provider)

    # ---- Metrics ----
    metric_exporter = OTLPMetricExporter(endpoint=OTEL_ENDPOINT, insecure=True)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(metric_exporter, export_interval_millis=10000)
        ],
    )
    metrics.set_meter_provider(meter_provider)

    # ---- Logs ----
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTEL_ENDPOINT, insecure=True))
    )
    otel_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    root_logger = logging.getLogger()
    root_logger.addHandler(otel_handler)
    root_logger.setLevel(logging.INFO)

    # ---- Auto-instrumentation ----
    if app is not None:
        # Imported lazily so services that don't use FastAPI (product-service,
        # which is gRPC-only) don't need this dependency.
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app, tracer_provider=tracer_provider, meter_provider=meter_provider
        )

    return tracer_provider, meter_provider, logger_provider


def instrument_grpc_server():
    """
    For gRPC-only services (product-service). Auto-instruments the gRPC
    server so every RPC gets a trace span. Call this once, before
    `server.start()`, after `setup_telemetry()`.
    """
    from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer

    GrpcInstrumentorServer().instrument()


def instrument_grpc_client():
    """
    For services that call product-service over gRPC (user-service).
    Auto-instruments the gRPC client channel so calls show up as child spans
    of the request that triggered them.
    """
    from opentelemetry.instrumentation.grpc import GrpcInstrumentorClient

    GrpcInstrumentorClient().instrument()
