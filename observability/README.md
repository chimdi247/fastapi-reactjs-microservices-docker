# Observability

## Pipeline

```
FastAPI/gRPC services (shared/telemetry.py, OTel auto-instrumentation)
        │  OTLP/gRPC (traces + metrics + logs)
        ▼
  OTel Collector  (observability/otel-collector/otel-collector-config.yaml)
        │
        ├──► Jaeger        (traces)
        ├──► :8889/metrics ──► Prometheus scrapes it (metrics)
        └──► Loki           (logs)

cAdvisor       ──► Prometheus scrapes it (per-container CPU/memory)
node-exporter  ──► Prometheus scrapes it (host CPU/memory)

Grafana ◄── datasources: Prometheus, Loki, Jaeger, Postgres (appdb)
```

Every service calls `shared.telemetry.setup_telemetry(service_name, app=...)`
once at startup (see each service's `main.py`). That single call wires up:

- **Traces** — a `TracerProvider` exporting via OTLP, plus
  `FastAPIInstrumentor.instrument_app()` for automatic HTTP request spans.
  product-service (gRPC-only) uses `instrument_grpc_server()` instead;
  user-service also calls `instrument_grpc_client()` so its calls to
  product-service show up as child spans of the request that triggered
  them — one trace, gateway to database.
- **Metrics** — a `MeterProvider` exporting via OTLP on a 10s interval.
  FastAPI auto-instrumentation includes HTTP request duration/count out of
  the box.
- **Logs** — Python's root logger gets an OTel `LoggingHandler`, so
  ordinary `logging`/`print`-adjacent calls (well, `logging` calls — plain
  `print()` still only goes to stdout, picked up separately by
  Promtail) flow to Loki with trace/span IDs attached automatically,
  which is what makes the "jump from a log line to its trace" link in
  Grafana's Loki datasource work.

Container logs are *also* scraped directly by Promtail
(`observability/promtail/`) straight from the Docker socket, independent of
the OTel logging path above — this was already the project's original
approach and still works as a simple, reliable fallback.

## The dashboard

`observability/grafana/dashboards/fast-store-overview.json`, auto-loaded via
`observability/grafana/provisioning/dashboards/dashboards.yaml`. Panels:

- **Service uptime** (4 panels, one per app service) — `time() -
  container_start_time_seconds{name="..."}` from cAdvisor. This is
  deliberately *not* derived from application-level metrics: with metrics
  routed through a single shared OTel Collector rather than one Prometheus
  scrape target per service, there's no `up{job="user-service"}` to query
  directly. cAdvisor already tracks exactly when each container started,
  which is a more direct "is this service up, and for how long" signal
  anyway.
- **HTTP 5xx error rate by service** — from each service's
  FastAPI-auto-instrumented request metrics, grouped by the `service_name`
  label (present because the collector's Prometheus exporter has
  `resource_to_telemetry_conversion` enabled, turning the OTel
  `service.name` resource attribute into a Prometheus label).
- **Container CPU / memory** — cAdvisor, as a percentage (memory is
  usage ÷ each container's own memory limit).
- **Node CPU / memory** — node-exporter, host-wide.
- **Total Users / Total Products / Total Orders / Total Stock On Hand** —
  raw SQL against the Postgres datasource (`SELECT COUNT(*) FROM "user"`,
  etc.) — the simplest, most direct way to answer "how many X exist" is
  just asking the database, not routing it through the metrics pipeline.

### One thing I could not verify, and how to fix it if it's wrong

The error-rate panel's query uses
`http_server_duration_milliseconds_count` — the metric name FastAPI's OTel
auto-instrumentation has historically exported. **I could not start the
full Docker stack in this environment to confirm that's the exact name
produced by the specific `opentelemetry-instrumentation-fastapi` version
this project resolved to** (metric naming has shifted between library
versions as HTTP semantic conventions were stabilized — a slightly newer
version might export `http_server_request_duration_seconds_count`
instead). If that panel comes up empty:

1. Open Prometheus directly (`http://localhost:9090/graph`).
2. Type `http_server` and let autocomplete show you what actually exists.
3. Swap the real name into the panel's query (Grafana → the panel → Edit).

Every other panel in the dashboard queries cAdvisor, node-exporter, or
Postgres directly — all well-established, unambiguous metric/table names
that don't have this version-dependent uncertainty.

## Alerting

CPU/memory alerting is implemented as **Grafana's own unified alerting**
(`observability/grafana/provisioning/alerting/`), not a separate
Prometheus Alertmanager deployment — a deliberate simplification, since
everything else here is already centered on Grafana as the single UI.
Four rules, all firing at >70% for 5 minutes straight:

- Container CPU usage > 70%
- Container memory usage > 70%
- Node CPU usage > 70%
- Node memory usage > 70%

A contact point (`ops-team`) and notification policy are provisioned so the
rules have somewhere to route to, but **no real SMTP server is
configured** — alerts will show as "firing" in Grafana's Alerting UI, but
no email actually sends until you configure `GF_SMTP_*` environment
variables on the `grafana` service in `docker-compose.yaml` and replace the
placeholder address in `contact-points.yaml`.

## Known limitations

- **RabbitMQ connectivity for order-service/inventory-service, and the
  full OTLP pipeline end-to-end, weren't verified by actually running the
  stack** — this environment can't run `docker compose up` itself. Every
  piece was validated as thoroughly as possible short of that: each
  service's business logic was exercised directly against a real database
  (see README.docker.md §6), and every YAML/JSON config file here was
  syntax-validated. The genuinely untested seam is "does the collector's
  `loki` exporter actually reach Loki, formatted the way Loki expects" —
  if log delivery seems off, `docker compose logs otel-collector` is the
  first place to look.
- **cAdvisor runs `privileged: true`** — required for it to read
  per-container cgroup stats. Fine for local/dev use; worth revisiting for
  a genuinely public deployment.
- No `/dev/kmsg` device mapping was added to cAdvisor (an optional
  performance enhancement in some setups) — left out deliberately, since
  that device doesn't exist on every host (e.g. some cloud VM kernels,
  WSL2), and cAdvisor works fine without it.
