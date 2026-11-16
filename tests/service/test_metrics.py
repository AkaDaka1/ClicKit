"""Тесты метрик Prometheus ClicKit Cloud (M8 T1.2).

Контракт — `docs/sre/slo.md` §8: имена, типы и метки метрик стабильны,
кардинальность ограничена (`method`, `route`, `status`), `/metrics`
разбирается парсером Prometheus и не шумит в журнале.

Проверяется три уровня:

* коллекторы (`ServiceMetrics`) — форма серий и кардинальность;
* middleware — сквозной учёт запросов приложения, включая ошибки и 413;
* `GET /metrics` — текст со всеми пятью метриками контракта, включая
  `clikit_db_pool_connections` на настоящем пуле SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("prometheus_client")

from fastapi.testclient import TestClient  # noqa: E402
from prometheus_client import CollectorRegistry  # noqa: E402
from prometheus_client.parser import text_string_to_metric_families  # noqa: E402

from service.app.config import Settings  # noqa: E402
from service.app.db import Database  # noqa: E402
from service.app.main import create_app  # noqa: E402
from service.app.observability.metrics import (  # noqa: E402
    BUILD_INFO,
    DB_POOL_CONNECTIONS,
    DURATION_BUCKETS,
    REQUEST_DURATION_SECONDS,
    REQUESTS_IN_FLIGHT,
    REQUESTS_TOTAL,
    ServiceMetrics,
    labels_are_allowed,
)
from service.app.version import SERVICE_VERSION  # noqa: E402
from tests.service.conftest import API_KEY, DatabaseFactory, publish_body  # noqa: E402
from tests.service.fakes import FakeDatabase  # noqa: E402

#: URL БД-заглушки: соединение в этих тестах не устанавливается.
DB_URL = "postgresql+psycopg://clikit:clikit@localhost:5432/clikit"
#: Коммит «сборки» в тестах.
GIT_SHA = "abc1234"
#: Разрешённые метки контракта (правила кардинальности, `docs/sre/slo.md` §8).
ALLOWED_LABELS: frozenset[str] = frozenset({"method", "route", "status"})

#: Разбор `/metrics`: (имя серии, метки) → значение. Гистограмма лежит
#: отдельными сериями `_bucket`/`_count`/`_sum`.
Samples = dict[tuple[str, tuple[tuple[str, str], ...]], float]


def _key(name: str, labels: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Ключ серии: имя и отсортированные метки (одно имя — много серий)."""
    return name, tuple(sorted(labels.items()))


@pytest.fixture()
def collector() -> ServiceMetrics:
    """Отдельный реестр метрик на тест (не глобальный `REGISTRY`)."""
    return ServiceMetrics(registry=CollectorRegistry())


@pytest.fixture()
def app_client() -> Iterator[TestClient]:
    """Клиент с собственным экземпляром метрик (БД — заглушка)."""
    app = create_app(
        Settings(api_key=API_KEY, db_url=DB_URL, git_sha=GIT_SHA),
        database=FakeDatabase(),
    )
    with TestClient(app) as test_client:
        yield test_client


def _value(collector: ServiceMetrics, name: str, labels: dict[str, str]) -> float:
    """Значение серии из реестра; отсутствие серии — ошибка теста."""
    value = collector.registry.get_sample_value(name, labels)
    assert value is not None, f"серии {name}{labels} нет в реестре"
    return value


def _scrape(client: TestClient) -> Samples:
    """Запросить `/metrics` и разобрать ответ парсером Prometheus."""
    response = client.get("/metrics")
    assert response.status_code == 200
    return {
        _key(sample.name, dict(sample.labels)): sample.value
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    }


def _series(client: TestClient) -> list[tuple[str, dict[str, str], float]]:
    """Все серии `/metrics` списком (одно имя может встречаться несколько раз)."""
    response = client.get("/metrics")
    assert response.status_code == 200
    return [
        (sample.name, dict(sample.labels), sample.value)
        for family in text_string_to_metric_families(response.text)
        for sample in family.samples
    ]


def _count(samples: Samples, name: str, labels: dict[str, str]) -> float:
    """Значение конкретной серии в разобранном ответе."""
    return samples[_key(name, labels)]


def _routes(samples: Samples, metric: str = REQUESTS_TOTAL) -> set[str]:
    """Значения метки `route` у указанной серии."""
    return {dict(key[1])["route"] for key in samples if key[0] == metric}


# --- Коллекторы -----------------------------------------------------------


def test_contract_metric_names_are_stable() -> None:
    """Имена метрик совпадают с контрактом `docs/sre/slo.md` §8."""
    assert REQUESTS_TOTAL == "clikit_http_requests_total"
    assert REQUEST_DURATION_SECONDS == "clikit_http_request_duration_seconds"
    assert REQUESTS_IN_FLIGHT == "clikit_http_requests_in_flight"
    assert DB_POOL_CONNECTIONS == "clikit_db_pool_connections"
    assert BUILD_INFO == "clikit_build_info"


def test_duration_buckets_include_slo_threshold(
    collector: ServiceMetrics,
) -> None:
    """Корзина 0.3 с — порог задержки SLO — обязана быть в гистограмме."""
    assert sorted(DURATION_BUCKETS) == list(DURATION_BUCKETS)
    assert 0.3 in DURATION_BUCKETS

    collector.observe_request(
        method="GET", route="/v1/scenarios", status=200, duration=0.2
    )

    labels = {"method": "GET", "route": "/v1/scenarios", "status": "200"}
    bucket = f"{REQUEST_DURATION_SECONDS}_bucket"
    assert _value(collector, bucket, {**labels, "le": "0.3"}) == 1
    assert _value(collector, bucket, {**labels, "le": "0.1"}) == 0
    assert _value(collector, bucket, {**labels, "le": "+Inf"}) == 1


def test_labels_stay_low_cardinality(collector: ServiceMetrics) -> None:
    """В метках только `method`, `route`, `status`; у gauge меток нет."""
    assert labels_are_allowed(collector.requests_total._labelnames, ALLOWED_LABELS)
    assert labels_are_allowed(collector.request_duration._labelnames, ALLOWED_LABELS)
    assert collector.requests_in_flight._labelnames == ()


def test_observe_request_updates_counter_and_sum(
    collector: ServiceMetrics,
) -> None:
    """Запрос увеличивает счётчик, корзины и сумму длительностей."""
    collector.observe_request(
        method="GET", route="/v1/scenarios/{id}", status=200, duration=0.2
    )

    labels = {"method": "GET", "route": "/v1/scenarios/{id}", "status": "200"}
    assert _value(collector, REQUESTS_TOTAL, labels) == 1
    assert _value(collector, f"{REQUEST_DURATION_SECONDS}_count", labels) == 1
    assert _value(
        collector, f"{REQUEST_DURATION_SECONDS}_sum", labels
    ) == pytest.approx(0.2)


def test_negative_duration_is_clamped(collector: ServiceMetrics) -> None:
    """Отрицательная длительность (прыжок часов) не портит сумму."""
    collector.observe_request(method="GET", route="/healthz", status=200, duration=-1)

    labels = {"method": "GET", "route": "/healthz", "status": "200"}
    assert _value(collector, f"{REQUEST_DURATION_SECONDS}_sum", labels) == 0


def test_instances_are_isolated() -> None:
    """Экземпляры метрик не конфликтуют: у каждого свой реестр."""
    first = ServiceMetrics()
    second = ServiceMetrics()

    first.observe_request(method="GET", route="/healthz", status=200, duration=0.01)

    labels = {"method": "GET", "route": "/healthz", "status": "200"}
    assert first.registry.get_sample_value(REQUESTS_TOTAL, labels) == 1
    assert second.registry.get_sample_value(REQUESTS_TOTAL, labels) is None


# --- Сквозной учёт через приложение --------------------------------------


def test_route_label_is_a_template(app_client: TestClient) -> None:
    """`route` — шаблон FastAPI, id сценария в метки не попадает."""
    app_client.get("/healthz")
    app_client.get("/v1/scenarios/00000000-0000-0000-0000-000000000000")

    samples = _scrape(app_client)

    assert (
        _count(
            samples,
            REQUESTS_TOTAL,
            {"method": "GET", "route": "/healthz", "status": "200"},
        )
        == 1.0
    )
    assert _routes(samples) <= {"/healthz", "/v1/scenarios/{scenario_id}"}
    assert all("00000000" not in route for route in _routes(samples))


def test_error_responses_are_counted_by_status(client: TestClient) -> None:
    """401 и 422 попадают в метрики своим кодом: без них SLO не посчитать."""
    unauthorized = client.post(
        "/v1/scenarios", headers={"X-API-Key": ""}, json=publish_body()
    )
    invalid = client.post(
        "/v1/scenarios",
        headers={"X-API-Key": API_KEY},
        json={"scenario": {"version": 1, "name": "x", "nodes": [{"type": "nope"}]}},
    )

    assert (unauthorized.status_code, invalid.status_code) == (401, 422)
    samples = _scrape(client)
    for status in ("401", "422"):
        assert (
            _count(
                samples,
                REQUESTS_TOTAL,
                {"method": "POST", "route": "/v1/scenarios", "status": status},
            )
            == 1.0
        )


def test_unhandled_error_keeps_route_template(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """500 учитывается с шаблоном маршрута, а не `unmatched`.

    Ответ 500 формирует `ServerErrorMiddleware` — слой **выше** метрик,
    поэтому `http.response.start` через них не проходит. Маршрут берётся из
    `scope` в `finally`: иначе 5xx выпадали бы из SLI доступности
    (`route=~"/v1/.*"`).
    """
    from service.app.api.v1 import scenarios as scenarios_module

    def boom(self: object, **kwargs: object) -> tuple[list[object], int]:
        raise RuntimeError("сбой для теста метрик")

    monkeypatch.setattr(scenarios_module.SqlScenarioRepository, "list_page", boom)
    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url),
        database=database,
    )

    with TestClient(app, raise_server_exceptions=False) as failing:
        assert failing.get("/v1/scenarios").status_code == 500
        samples = _scrape(failing)

    assert (
        _count(
            samples,
            REQUESTS_TOTAL,
            {"method": "GET", "route": "/v1/scenarios", "status": "500"},
        )
        == 1.0
    )


def test_unknown_paths_share_one_unmatched_series(
    app_client: TestClient,
) -> None:
    """Мусорные пути не создают серию каждый: все получают `unmatched`."""
    app_client.get("/no-such-page-1")
    app_client.get("/no-such-page-2")

    samples = _scrape(app_client)

    assert (
        _count(
            samples,
            REQUESTS_TOTAL,
            {"method": "GET", "route": "unmatched", "status": "404"},
        )
        == 2.0
    )


def test_body_limit_response_is_counted(client: TestClient) -> None:
    """413 лимита тела учитывается: метрики стоят внутри лимита.

    Ответ формирует слой лимита **до** маршрутизации, поэтому шаблона
    маршрута ещё нет и метка `route` — `unmatched`. Для SLO это не важно:
    413 — ошибка клиента (4xx) и в знаменатель доступности не входит.
    """
    response = client.post(
        "/v1/scenarios",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        content=b"{" + b"a" * (1024 * 1024 + 10),
    )

    assert response.status_code == 413
    samples = _scrape(client)
    assert (
        _count(
            samples,
            REQUESTS_TOTAL,
            {"method": "POST", "route": "unmatched", "status": "413"},
        )
        == 1.0
    )


def test_in_flight_returns_to_zero(client: TestClient) -> None:
    """После завершённых запросов gauge «в обработке» снова ноль."""
    client.get("/healthz")

    assert _count(_scrape(client), REQUESTS_IN_FLIGHT, {}) == 0.0


def test_metrics_scrape_is_not_logged(
    app_client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Скрейп `/metrics` не пишет access-запись, но учитывается в метриках."""
    capsys.readouterr()
    assert app_client.get("/metrics").status_code == 200

    assert "HTTP-запрос" not in capsys.readouterr().out
    # Скрейп не видит сам себя: в теле — только предыдущий запрос `/metrics`.
    assert (
        _count(
            _scrape(app_client),
            REQUESTS_TOTAL,
            {"method": "GET", "route": "/metrics", "status": "200"},
        )
        == 1.0
    )


def test_other_routes_are_still_logged(
    app_client: TestClient, capsys: pytest.CaptureFixture[str]
) -> None:
    """Подавление журнала касается только служебных маршрутов."""
    capsys.readouterr()
    app_client.get("/healthz")

    assert "HTTP-запрос" in capsys.readouterr().out


# --- Ответ `/metrics` -----------------------------------------------------


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    """`/metrics` — текст Prometheus 1.0, читаемый стандартным парсером."""
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "version=1.0.0" in response.headers["content-type"]
    names = {family.name for family in text_string_to_metric_families(response.text)}
    assert {
        "clikit_http_requests",
        "clikit_http_request_duration_seconds",
        "clikit_http_requests_in_flight",
        "clikit_build_info",
    } <= names


def test_metrics_body_is_utf8_with_trailing_newline(client: TestClient) -> None:
    """UTF-8 и перевод строки в конце — без них Prometheus ругается."""
    response = client.get("/metrics")

    assert response.content.endswith(b"\n")
    response.content.decode("utf-8")


def test_build_info_has_version_and_git_sha(app_client: TestClient) -> None:
    """`clikit_build_info` — метки сборки из настроек приложения."""
    assert (
        _count(
            _scrape(app_client),
            BUILD_INFO,
            {"version": SERVICE_VERSION, "git_sha": GIT_SHA},
        )
        == 1.0
    )


def test_db_pool_connections_are_reported(
    database_factory: DatabaseFactory,
) -> None:
    """Пул SQLAlchemy даёт `clikit_db_pool_connections{state}`, скрейп его не держит.

    SQLite в локальном прогоне соединения не считает, тогда тест пропускается;
    в CI (`CLICKIT_TEST_DB_URL` → PostgreSQL 16) проверяются все три состояния.
    """
    database = database_factory()
    try:
        expected = database.pool_samples()
        if not expected:
            pytest.skip("пул БД не считает соединения (SQLite в локальном прогоне)")
        assert set(expected) == {"in_use", "idle", "overflow"}

        app = create_app(
            Settings(api_key=API_KEY, db_url=database.url, git_sha=GIT_SHA),
            database=database,
        )
        with TestClient(app) as test_client:
            pool = {
                labels["state"]: value
                for name, labels, value in _series(test_client)
                if name == DB_POOL_CONNECTIONS
            }

        assert set(pool) == {"in_use", "idle", "overflow"}
        # Скрейп не держит соединение: после ответа ни одно не занято.
        assert pool["in_use"] == 0
    finally:
        database.dispose()
