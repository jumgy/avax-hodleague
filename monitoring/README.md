# PostgreSQL Monitoring

Stack: **postgres_exporter** -> **Prometheus** -> **Grafana**. The database is not exposed externally; only containers in the same network. The Grafana web UI is exposed (login/password).

## Running

1. Set Grafana admin password in `.env`:
   ```env
   GRAFANA_ADMIN_PASSWORD=your_secure_password
   ```
2. Start the stack (with monitoring):
   ```bash
   docker compose up -d
   ```
3. Open Grafana at **http://localhost:3000** (or host:port from `GRAFANA_PORT`). Login: `admin` (or `GRAFANA_ADMIN_USER`), password from `GRAFANA_ADMIN_PASSWORD`.

## Subdomain (reverse proxy)

If the backend is on a domain and you want Grafana on a subdomain (e.g. `https://monitor.weekend.example`):

1. In `.env`:
   ```env
   GRAFANA_ROOT_URL=https://monitor.weekend.example/
   ```
2. In nginx/traefik/caddy configure proxying of the subdomain to the `grafana:3000` container (you may not need to expose the port if the proxy is on the same host).

Additional protection (Basic Auth, IP allowlist) can be configured in the proxy.

## Grafana dashboards

After login: **Dashboards** -> **New** -> **Import** -> enter ID -> **Load** -> select **Prometheus** as source -> **Import**.

| ID     | Purpose |
|--------|---------|
| **14114** | PostgreSQL Overview — DB load, QPS, connections, cache hit ratio. |
| **1860**  | Node Exporter Full — host load: CPU, memory, disk, network, load average. |

On Windows (Docker Desktop), if mounting `/proc` fails for `node_exporter`, host metrics may be unavailable — then dashboard 1860 will show container or Docker VM metrics.

**If Node Exporter dashboard (1860) shows "No data" and Instance filter only has "None":** Prometheus scrapes node_exporter only after config reload. Run `docker compose restart prometheus`, wait 15–30 seconds, refresh the dashboard in Grafana — the **Instance** dropdown should list a value (e.g. `node_exporter:9100`). Select it and save.

## What is exposed

| Service           | Port exposed | Purpose        |
|-------------------|-------------|----------------|
| postgres          | no          | —              |
| node_exporter     | no          | host metrics   |
| postgres_exporter | no          | DB metrics     |
| prometheus        | no          | metric scrape  |
| grafana           | 3000 (opt.) | dashboard UI   |

The database is only reachable by containers at `postgres:5432`. Without `docker-compose.override.yml` you cannot connect to it from the host.
