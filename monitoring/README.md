# Мониторинг PostgreSQL

Стек: **postgres_exporter** → **Prometheus** → **Grafana**. База снаружи не открывается — только контейнеры в одной сети; наружу торчит только веб-интерфейс Grafana (логин/пароль).

## Запуск

1. В `.env` задай пароль для входа в Grafana:
   ```env
   GRAFANA_ADMIN_PASSWORD=твой_надёжный_пароль
   ```
2. Подними стек (вместе с мониторингом):
   ```bash
   docker compose up -d
   ```
3. Открой Grafana: **http://localhost:3000** (или хост:порт из `GRAFANA_PORT`). Логин: `admin` (или `GRAFANA_ADMIN_USER`), пароль — из `GRAFANA_ADMIN_PASSWORD`.

## Поддомен (reverse proxy)

Если бэкенд доступен по домену, а Grafana хочешь по поддомену (например `https://monitor.weekend.example`):

1. В `.env`:
   ```env
   GRAFANA_ROOT_URL=https://monitor.weekend.example/
   ```
2. В nginx/traefik/caddy настрой проксирование поддомена на контейнер `grafana:3000` (порт наружу можно не пробрасывать, если прокси на той же машине ходит в Docker-сеть).

Дополнительная защита (Basic Auth, IP-ограничение) — в конфиге прокси по желанию.

## Дашборды в Grafana

После входа: **Dashboards** → **New** → **Import** → введи ID → **Load** → выбери источник **Prometheus** → **Import**.

| ID    | Назначение |
|-------|------------|
| **14114** | PostgreSQL Overview — нагрузка БД, QPS, соединения, cache hit ratio. |
| **1860**  | Node Exporter Full — нагрузка хоста: CPU, память (сколько осталось), диск, сеть, load average. |

На Windows (Docker Desktop) при ошибке монтирования `/proc` у `node_exporter` метрики хоста могут быть недоступны — тогда дашборд 1860 покажет метрики контейнера или VM Docker.

**Если в дашборде Node Exporter (1860) «No data» и в фильтре Instance только «None»:** Prometheus скрапит node_exporter только после перезагрузки конфига. Выполни `docker compose restart prometheus`, подожди 15–30 секунд, обнови страницу дашборда в Grafana — в выпадающем списке **Instance** должно появиться значение (например `node_exporter:9100`), выбери его и сохрани.

## Что снаружи, что внутри

| Сервис            | Порт наружу | Назначение        |
|-------------------|-------------|-------------------|
| postgres          | нет         | —                 |
| node_exporter     | нет         | метрики хоста     |
| postgres_exporter | нет         | метрики БД        |
| prometheus        | нет         | сбор метрик       |
| grafana           | 3000 (опц.) | UI дашбордов      |

База доступна только контейнерам по имени `postgres:5432`. С хоста без `docker-compose.override.yml` к ней не подключиться.
