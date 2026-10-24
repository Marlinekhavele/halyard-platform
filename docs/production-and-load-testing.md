# Hosting readiness and load testing

**Owner: Sharad Nanda**

This change set adds an opt-in production Compose overlay and a repeatable Locust
suite. The existing local-development stack and demo workflow are unchanged.

## Production-oriented Compose overlay

The overlay is a starting point for a single-host MVP deployment, not a claim
that the application is fully production-ready. It requires Docker Compose
v2.24.4 or later because it uses the `!override` and `!reset` merge tags.

1. Point `API_HOST` at the deployment host and point `PUBLIC_URL` at the hosted
   frontend. Ensure the frontend origin is included exactly in `CORS_ORIGINS`.
2. Copy `deploy/production/.env.production.example` to `.env.production` and
   replace every example value. Generate independent random secrets; for
   example, run `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   multiple times. Do not reuse the example passwords or commit the real env file.
3. Configure valid SMTP credentials, and verify DNS for `API_HOST`. Public TCP
   ports 80 and 443 must reach the gateway for HTTP-to-HTTPS redirection and
   ACME certificate issuance. Configure the provider firewall accordingly.
4. Review the provider's privacy, backup, restore and retention settings before
   putting customer documents or personal data on the host.

Validate the merged configuration before starting containers:

```bash
docker compose version
# Copy the example, then edit all values before using it:
cp deploy/production/.env.production.example .env.production
# This must pass before Compose is allowed to start production containers.
python scripts/check_production_env.py .env.production
docker compose --env-file .env.production \
  -f docker-compose.yml \
  -f deploy/production/compose.production.yml config

docker compose --env-file .env.production \
  -f docker-compose.yml \
  -f deploy/production/compose.production.yml up --build -d
```

The preflight check rejects missing, short or known placeholder secrets and
example hostnames. The overlay disables demo seeding, switches all services to
the guarded `production` environment, requires explicit secrets, scopes API
routers to `API_HOST`, redirects HTTP to HTTPS, disables the insecure Traefik dashboard,
removes published management ports, and puts Traefik behind a restricted Docker
socket proxy. The ACME storage volume persists certificates across restarts.

This overlay configures the backend API only. The frontend is in the separate
`halyard-web` repository and needs its own production deployment settings, HTTPS
origin and smoke checks.

This remains a single-host starting point. Before accepting real shipments,
verify database and document-volume backups with restore tests, host patching,
monitoring and alerting, SMTP deliverability, incident recovery, and legal/data
protection requirements. Local document storage, seeded rates, carrier booking
and tracking adapters, and invoice/VAT/accounting workflows still require
product-specific decisions or integrations.

## Load tests

The Locust dependency is intentionally separate from production dependencies.
Use a dedicated load-test account and never use personal or customer data.

```bash
python -m venv .venv-load
# macOS/Linux:
. .venv-load/bin/activate
pip install -r requirements-load.txt

export HALYARD_API_URL=http://127.0.0.1:8080
export HALYARD_LOAD_LOGIN_EMAIL=load-test@example.invalid
export HALYARD_LOAD_LOGIN_PASSWORD='use-a-dedicated-test-account-password'
locust -f tests/load/locustfile.py --host "$HALYARD_API_URL"
```

This opens the Locust UI on port 8089. Start with a small number of users and a
slow ramp-up; increase only after confirming the baseline works. For a repeatable
headless run, create a local results directory and use the same user count and
ramp rate for every comparison:

```bash
mkdir -p artifacts
locust -f tests/load/locustfile.py \
  --headless -u 20 -r 2 --run-time 10m --stop-timeout 30 \
  --host "$HALYARD_API_URL" \
  --csv artifacts/halyard-baseline
```

The default workload is read-heavy and covers login, quote listing, price
estimation, shipment listing, invoices, notifications, company profile and
ports. The default 20DV DEHAM-to-USNYC route matches the repository's seeded
route example. Override the route and container type only when the staging data
contains matching active rates. It does not create quotes or bookings by default.

### Remote staging guard

For remote hosts, both of these must be set explicitly:

```bash
export HALYARD_LOAD_TARGET=staging
export HALYARD_LOAD_ALLOW_REMOTE=true
```

Remote targets must use HTTPS. The test suite intentionally refuses a remote
load run without this explicit staging acknowledgement. Do not run these tests
against production or a carrier/provider endpoint without the owner's approval.

### Opt-in write workflow

The write task creates a new quote and books its first returned option. It
produces persistent records and downstream events. Use it only in an isolated
staging environment with a dedicated test account and known seeded route data:

```bash
export HALYARD_LOAD_INCLUDE_WRITES=true
export HALYARD_LOAD_POL=DEHAM
export HALYARD_LOAD_POD=USNYC
export HALYARD_LOAD_CONTAINER_TYPE=20DV
locust -f tests/load/locustfile.py --host "$HALYARD_API_URL"
```

If quote estimation or booking fails, check that the configured port pair has
active rates and bookable options before interpreting results as a capacity
problem.

### What to record

For each run, retain the Git commit, deployment size, user count, ramp rate,
run duration and target environment alongside Locust's CSV output. Review:

- p50, p95 and p99 response latency per endpoint;
- request rate, failure rate and HTTP status mix;
- host/container CPU and memory, and restarts/OOM events;
- PostgreSQL connection pressure, slow queries and lock waits;
- RabbitMQ ready/unacknowledged queue depth and consumer processing delay;
- outbox age, logs, request IDs and traces for slow or failed workflows.

Run in stages: smoke test, expected pilot concurrency, approximately twice the
expected pilot concurrency, then a controlled soak test. Agree on latency and
error-rate thresholds with the product owner before treating any result as a
release gate. Diagnose the first measured bottleneck before adding replicas or
new infrastructure.
