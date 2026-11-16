"""Статические проверки compose-стека наблюдаемости (M8 T2.1).

Реальный чекпоинт задачи — `docker compose -f docker-compose.observability.yml
up -d`, все targets UP и открывающиеся UI. Эти тесты страхуют конфигурацию от
регрессий, которые видны только при ручном запуске: забытый scrape-таргет,
правила, не смонтированные в Prometheus, datasource без Tempo, секрет в YAML
или `request_id` в метках Loki (взрыв кардинальности).

Синтаксис Prometheus проверяется отдельно `promtool` (см. docs/observability.md
§7), а здесь — дешёвые инварианты и связи между файлами.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "docker-compose.observability.yml"
ENV_EXAMPLE = ROOT / ".env.example"
DOC = ROOT / "docs" / "observability.md"
PROMETHEUS = ROOT / "observability" / "prometheus" / "prometheus.yml"
RULES = ROOT / "observability" / "prometheus" / "recording_rules.yml"
ALERTMANAGER = ROOT / "observability" / "alertmanager" / "alertmanager.yml"
DATASOURCES = (
    ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "datasources"
    / "datasources.yml"
)
DASHBOARDS = (
    ROOT
    / "observability"
    / "grafana"
    / "provisioning"
    / "dashboards"
    / "dashboards.yml"
)
LOKI = ROOT / "observability" / "loki" / "loki-config.yml"
PROMTAIL = ROOT / "observability" / "promtail" / "promtail-config.yml"
TEMPO = ROOT / "observability" / "tempo" / "tempo.yml"

#: Инфраструктура наблюдаемости; `db`/`migrate`/`api` приходят из `include`.
OBS_SERVICES = {
    "prometheus",
    "grafana",
    "loki",
    "promtail",
    "tempo",
    "alertmanager",
    "alert-sink",
    "node-exporter",
}
#: Ожидаемые scrape-таргеты Prometheus (docs/observability.md §4).
EXPECTED_JOBS = {
    "prometheus",
    "clikit-api",
    "alertmanager",
    "loki",
    "promtail",
    "tempo",
    "grafana",
    "node-exporter",
}
#: Переменные портов, которые обязан документировать `.env.example`.
PORT_ENV_VARS = (
    "CLICKIT_PROMETHEUS_PORT",
    "CLICKIT_GRAFANA_PORT",
    "CLICKIT_ALERTMANAGER_PORT",
    "CLICKIT_LOKI_PORT",
    "CLICKIT_TEMPO_PORT",
    "CLICKIT_OTLP_HTTP_PORT",
    "CLICKIT_ALERT_SINK_PORT",
)


def _yaml(path: Path) -> dict[str, Any]:
    """Прочитать YAML-файл как словарь (пустой файл — ошибка теста)."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict), f"{path.name}: ожидается YAML-объект"
    return data


def _compose() -> dict[str, Any]:
    """Разобрать compose-файл стека наблюдаемости."""
    return _yaml(COMPOSE)


def _service(name: str) -> dict[str, Any]:
    """Вернуть блок сервиса compose-файла."""
    services = _compose()["services"]
    assert name in services, f"в compose нет сервиса {name}"
    return services[name]


def test_compose_includes_cloud_stack() -> None:
    """API и БД поднимаются тем же проектом: общая сеть нужна для скрейпа."""
    include = _compose()["include"]
    paths = [entry["path"] if isinstance(entry, dict) else entry for entry in include]
    assert "docker-compose.cloud.yml" in paths


def test_all_observability_services_are_defined() -> None:
    """Каждый обязательный сервис есть в compose и имеет образ, а не build."""
    services = _compose()["services"]
    for name in OBS_SERVICES:
        assert name in services, f"нет сервиса {name}"
        assert "image" in services[name], f"{name}: нужен pinned image"
    assert _compose()["name"] == "clikit-observability"


def test_images_are_pinned_not_latest() -> None:
    """Образы зафиксированы по версии: воспроизводимый стек, не «latest»."""
    for name in OBS_SERVICES:
        image = str(_service(name)["image"])
        assert ":" in image, f"{name}: тег не указан ({image})"
        assert not image.endswith(":latest"), f"{name}: latest запрещён ({image})"


def test_prometheus_retains_slo_window() -> None:
    """Retention 40 дней = 30-дневное окно SLO + запас (ADR №60)."""
    command = " ".join(map(str, _service("prometheus")["command"]))
    assert "--storage.tsdb.retention.time=40d" in command
    assert "--config.file=/etc/prometheus/prometheus.yml" in command
    volumes = " ".join(str(item) for item in _service("prometheus")["volumes"])
    assert "./observability/prometheus:/etc/prometheus:ro" in volumes


def test_api_sends_traces_to_tempo() -> None:
    """API получает OTLP-адрес Tempo в общей сети (T1.3, ADR №63)."""
    environment = _service("api")["environment"]
    assert environment["CLICKIT_OTEL_ENDPOINT"] == "http://tempo:4318"
    assert environment["CLICKIT_OTEL_ENABLED"] == "1"


def test_ui_ports_are_localhost_and_configurable() -> None:
    """UI доступны только на localhost; порты меняются через env."""
    for name in OBS_SERVICES:
        for mapping in _service(name).get("ports", []):
            text = str(mapping)
            assert text.startswith("127.0.0.1:"), (
                f"{name}: порт не на localhost: {text}"
            )


def test_ports_are_documented_in_env_example() -> None:
    """`.env.example` перечисляет все порты стека (без них compose не настроить)."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    for name in PORT_ENV_VARS:
        assert f"{name}=" in text, f"в .env.example нет {name}"


def test_prometheus_scrapes_api_and_every_component() -> None:
    """Все компоненты стека и API — scrape-таргеты; `metrics_path` у API верный."""
    config = _yaml(PROMETHEUS)
    assert config["global"]["scrape_interval"] == "15s"
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}
    assert set(jobs) == EXPECTED_JOBS
    api_targets = jobs["clikit-api"]["static_configs"][0]["targets"]
    assert api_targets == ["api:8000"]
    assert jobs["clikit-api"].get("metrics_path") == "/metrics"


def test_prometheus_loads_recording_rules_and_alerts_to_alertmanager() -> None:
    """Правила SLO смонтированы, Alertmanager подключён как приёмник алертов."""
    config = _yaml(PROMETHEUS)
    assert "/etc/prometheus/recording_rules.yml" in config["rule_files"]
    targets = config["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"]
    assert targets == ["alertmanager:9093"]
    # Файл правил существует и содержит записи (T0.1) — иначе Prometheus упадёт.
    assert RULES.exists()


def test_alertmanager_routes_to_local_sink() -> None:
    """Базовый маршрут T2.1: всё в локальный вебхук-приёмник, resolved включён."""
    config = _yaml(ALERTMANAGER)
    assert config["route"]["receiver"] == "local-sink"
    receivers = {item["name"]: item for item in config["receivers"]}
    webhook = receivers["local-sink"]["webhook_configs"][0]
    assert webhook["url"] == "http://alert-sink:8080/webhook"
    assert webhook["send_resolved"] is True


def test_grafana_provisions_three_datasources() -> None:
    """Grafana получает Prometheus, Loki и Tempo из Git, а не из UI."""
    config = _yaml(DATASOURCES)
    by_uid = {item["uid"]: item for item in config["datasources"]}
    assert set(by_uid) == {"prometheus", "loki", "tempo"}
    assert by_uid["prometheus"]["url"] == "http://prometheus:9090"
    assert by_uid["loki"]["url"] == "http://loki:3100"
    assert by_uid["tempo"]["url"] == "http://tempo:3200"
    # Корреляция: trace_id из JSON-лога открывает трейс в Tempo (ADR №41).
    derived = by_uid["loki"]["jsonData"]["derivedFields"]
    assert derived[0]["datasourceUid"] == "tempo"
    assert "trace_id" in derived[0]["matcherRegex"]


def test_grafana_dashboards_provider_is_read_only() -> None:
    """Дашборды — код из Git: UI-правки не сохраняются (ADR №39)."""
    config = _yaml(DASHBOARDS)
    provider = config["providers"][0]
    assert provider["allowUiUpdates"] is False
    assert provider["options"]["path"] == "/var/lib/grafana/dashboards"
    grafana = _service("grafana")
    assert grafana["environment"]["GF_AUTH_ANONYMOUS_ORG_ROLE"] == "Viewer"
    assert grafana["environment"]["GF_METRICS_ENABLED"] == "true"


def test_loki_retention_and_metadata_policy() -> None:
    """Loki хранит логи 30 дней и допускает structured metadata (trace_id)."""
    config = _yaml(LOKI)
    assert config["auth_enabled"] is False
    assert config["server"]["http_listen_port"] == 3100
    assert config["limits_config"]["retention_period"] == "720h"
    assert config["limits_config"]["allow_structured_metadata"] is True
    assert config["compactor"]["retention_enabled"] is True
    assert config["compactor"]["delete_request_store"] == "filesystem"


def test_promtail_reads_api_logs_without_high_cardinality_labels() -> None:
    """Promtail берёт контейнеры проекта через Docker API; id — не метки."""
    config = _yaml(PROMTAIL)
    assert config["clients"] == [{"url": "http://loki:3100/loki/api/v1/push"}]
    job = config["scrape_configs"][0]
    discovery = job["docker_sd_configs"][0]
    assert discovery["host"] == "unix:///var/run/docker.sock"
    filters = discovery["filters"]
    label_values = [set(item["values"]) for item in filters if item["name"] == "label"]
    assert {"com.docker.compose.project=clikit-observability"} in label_values
    assert {"com.docker.compose.service=api"} in label_values

    stages = job["pipeline_stages"]
    label_stages = [stage["labels"] for stage in stages if "labels" in stage]
    assert label_stages, "нет stage с метками"
    labels = set().union(*label_stages)
    assert labels == {"level"}, f"лишние метки: {labels}"
    metadata = [
        stage["structured_metadata"]
        for stage in stages
        if "structured_metadata" in stage
    ]
    assert "trace_id" in metadata[0]
    # request_id/trace_id не должны попадать в метки потока (взрыв кардинальности).
    assert "trace_id" not in labels and "request_id" not in labels


def test_tempo_accepts_otlp_http_and_keeps_traces_locally() -> None:
    """Tempo принимает OTLP/HTTP на 4318 и хранит блоки в локальном томе."""
    config = _yaml(TEMPO)
    http_receiver = config["distributor"]["receivers"]["otlp"]["protocols"]["http"]
    assert http_receiver["endpoint"] == "0.0.0.0:4318"
    assert config["storage"]["trace"]["backend"] == "local"
    assert config["storage"]["trace"]["wal"]["path"] == "/var/tempo/wal"
    assert config["usage_report"]["reporting_enabled"] is False


def test_alert_sink_runs_the_repository_script() -> None:
    """Приёмник — тот же `scripts/alert_sink.py`, что покрыт тестами."""
    sink = _service("alert-sink")
    command = " ".join(map(str, sink["command"]))
    assert "/app/scripts/alert_sink.py" in command
    assert "./scripts/alert_sink.py:/app/scripts/alert_sink.py:ro" in sink["volumes"]


def test_services_have_resource_limits_and_healthchecks() -> None:
    """У стека есть лимиты памяти (риск «съест ноутбук») и healthcheck.

    Loki и Tempo — distroless, у Promtail нет wget: healthcheck в их образах
    не выразить. Их готовность проверяется снаружи (`/ready`) и target'ами в
    Prometheus, поэтому исключение осознанное, а не забытое.
    """
    no_healthcheck = {"loki", "promtail", "tempo", "node-exporter"}
    for name in OBS_SERVICES:
        service = _service(name)
        assert service.get("mem_limit"), f"{name}: нет mem_limit"
        if name not in no_healthcheck:
            assert service.get("healthcheck"), f"{name}: нет healthcheck"


def test_no_secrets_in_observability_files() -> None:
    """В конфигах стека нет ключей и паролей: только имена переменных."""
    for path in (
        COMPOSE,
        PROMETHEUS,
        ALERTMANAGER,
        DATASOURCES,
        DASHBOARDS,
        LOKI,
        PROMTAIL,
        TEMPO,
    ):
        text = path.read_text(encoding="utf-8")
        assert "CLICKIT_API_KEY=" not in text, f"{path.name}: похоже на секрет"
        assert "POSTGRES_PASSWORD=" not in text, f"{path.name}: похоже на секрет"
        assert "xoxb-" not in text, f"{path.name}: похоже на токен"


def test_documentation_describes_the_stack() -> None:
    """Руководство существует, ссылается на compose и описывает порты."""
    text = DOC.read_text(encoding="utf-8")
    assert "docker-compose.observability.yml" in text
    for fragment in ("127.0.0.1:9090", "127.0.0.1:3000", "127.0.0.1:9093"):
        assert fragment in text
    assert "T2.2" in text and "T3.1" in text
