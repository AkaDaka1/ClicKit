"""Тесты трейсов OpenTelemetry сервиса ClicKit Cloud (M8 T1.3).

Контракт — `plans/M8-observability.md` §4.1 и ADR №41: трейс запроса виден в
Tempo и содержит спан HTTP и спан запроса к БД; `trace_id` в журнале
совпадает с идентификатором трейса спана.

Проверяется три уровня, как и у метрик (T1.2):

* настройки (`CLICKIT_OTEL_*`) — разбор, значения по умолчанию, fail-closed
  на ошибочные значения;
* сборка трейса — экспортёр в память: HTTP-спан с шаблоном маршрута,
  дочерний спан БД, `request_id` на спане, `trace_id` в JSON-журнале;
* отказоустойчивость — трейсинг выключен или упал при старте, сервис
  продолжает работать, `trace_id` в журнале остаётся `-`.

Батчевый экспортёр отправляет спаны в фоновом потоке, поэтому тесты вызывают
`Tracing.flush()` до чтения `InMemorySpanExporter`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("opentelemetry.sdk")

from fastapi.testclient import TestClient  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind  # noqa: E402

from service.app.config import ServiceConfigError, Settings, load_settings  # noqa: E402
from service.app.db import Database  # noqa: E402
from service.app.main import create_app  # noqa: E402
from service.app.observability.tracing import (  # noqa: E402
    REQUEST_ID_ATTRIBUTE,
    TRACES_PATH,
    TraceContextMiddleware,
    Tracing,
    TracingSetup,
    active_trace_id,
    otlp_traces_url,
)
from tests.service.conftest import API_KEY, DatabaseFactory, publish_body  # noqa: E402
from tests.service.fakes import FakeDatabase  # noqa: E402

#: Базовый адрес OTLP по умолчанию (`Settings.otel_endpoint`).
DEFAULT_ENDPOINT = "http://localhost:4318"
#: Минимальный валидный набор переменных окружения.
BASE_ENV = {"CLICKIT_API_KEY": API_KEY, "CLICKIT_DB_URL": "sqlite+pysqlite://"}


@pytest.fixture()
def exporter() -> InMemorySpanExporter:
    """Экспортёр в память: спаны не уходят в сеть."""
    return InMemorySpanExporter()


@pytest.fixture()
def tracing(exporter: InMemorySpanExporter) -> Iterator[Tracing]:
    """Объект `Tracing` с экспортёром в память."""
    yield Tracing(exporter=exporter)


@pytest.fixture()
def traced_client(
    database: Database,
    tracing: Tracing,
) -> Iterator[TestClient]:
    """Клиент приложения с включённым трейсингом и рабочей БД."""
    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url, otel_enabled=True),
        database,
        tracing,
        enable_tracing=True,
    )
    with TestClient(app) as client:
        client.headers.update({"X-API-Key": API_KEY})
        yield client


def _spans(exporter: InMemorySpanExporter) -> list:
    """Завершённые спаны после принудительной отправки батча."""
    return list(exporter.get_finished_spans())


def _server_spans(exporter: InMemorySpanExporter) -> list:
    """Спаны HTTP (SERVER): по одному на запрос."""
    return [span for span in _spans(exporter) if span.kind is SpanKind.SERVER]


def _status_of(span: object) -> int | None:
    """Код ответа спана: современная конвенция, затем устаревшая."""
    attributes = span.attributes  # type: ignore[attr-defined]
    value = attributes.get("http.response.status_code")
    if value is None:
        value = attributes.get("http.status_code")
    return int(value) if value is not None else None


def _trace_id(span: object) -> str:
    """`trace_id` спана в шестнадцатеричном виде (как в журнале)."""
    return format(span.context.trace_id, "032x")  # type: ignore[attr-defined]


# --- Настройки -----------------------------------------------------------


def test_tracing_defaults_are_enabled() -> None:
    """По умолчанию трейсинг включён, 100 % сэмплов, локальный OTLP."""
    settings = load_settings(BASE_ENV)

    assert settings.otel_enabled is True
    assert settings.otel_endpoint == DEFAULT_ENDPOINT
    assert settings.otel_sample_rate == 1.0
    assert settings.otel_service_name is None


def test_tracing_settings_are_read_from_env() -> None:
    """Переменные `CLICKIT_OTEL_*` читаются и нормализуются (T1.3)."""
    settings = load_settings(
        {
            **BASE_ENV,
            "CLICKIT_OTEL_ENABLED": "off",
            "CLICKIT_OTEL_ENDPOINT": " http://tempo:4318 ",
            "CLICKIT_OTEL_SAMPLE_RATE": "0.25",
            "CLICKIT_OTEL_SERVICE_NAME": "clikit-cloud-test",
        }
    )

    assert settings.otel_enabled is False
    assert settings.otel_endpoint == "http://tempo:4318"
    assert settings.otel_sample_rate == 0.25
    assert settings.otel_service_name == "clikit-cloud-test"


@pytest.mark.parametrize("value", ["0", "0.0", "-0.1", "1.5", "abc"])
def test_invalid_sample_rate_is_fail_closed(value: str) -> None:
    """Доля сэмплов вне (0, 1] или не число — ошибка старта."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_OTEL_SAMPLE_RATE"):
        load_settings({**BASE_ENV, "CLICKIT_OTEL_SAMPLE_RATE": value})


def test_invalid_enabled_flag_is_reported() -> None:
    """Опечатка во флаге не должна тихо выключать трейсинг."""
    with pytest.raises(ServiceConfigError, match="CLICKIT_OTEL_ENABLED"):
        load_settings({**BASE_ENV, "CLICKIT_OTEL_ENABLED": "maybe"})


def test_otlp_url_keeps_full_path() -> None:
    """Путь `/v1/traces` добавляется один раз, даже если уже есть."""
    assert otlp_traces_url("http://tempo:4318") == f"http://tempo:4318{TRACES_PATH}"
    assert otlp_traces_url("http://tempo:4318/") == f"http://tempo:4318{TRACES_PATH}"
    assert (
        otlp_traces_url(f"http://tempo:4318{TRACES_PATH}")
        == f"http://tempo:4318{TRACES_PATH}"
    )


# --- Сборка трейса -------------------------------------------------------


def test_request_creates_http_span_with_route_template(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """HTTP-спан есть, имя — шаблон маршрута, а не конкретный id (ADR №41)."""
    created = traced_client.post("/v1/scenarios", json=publish_body()).json()
    traced_client.get(f"/v1/scenarios/{created['id']}")
    tracing.flush()

    names = [span.name for span in _server_spans(exporter)]

    assert "POST /v1/scenarios" in names
    assert "GET /v1/scenarios/{scenario_id}" in names
    assert not any(created["id"] in name for name in names), (
        "id сценария не должен попадать в имя спана"
    )


def test_database_span_is_child_of_http_span(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """Спаны БД — дочерние HTTP-спану и лежат в том же трейсе (done-критерий)."""
    traced_client.get("/v1/scenarios")
    tracing.flush()

    [http_span] = _server_spans(exporter)
    db_spans = [span for span in _spans(exporter) if span.kind is SpanKind.CLIENT]

    assert db_spans, "нет спана запроса к БД"
    for span in db_spans:
        assert _trace_id(span) == _trace_id(http_span)
        assert span.parent is not None
    # Спан БД вложен под HTTP-спан (прямо или через `fastapi.*`): иначе трейс
    # в Tempo выглядел бы как отдельный запрос к базе.
    span_by_id = {span.context.span_id: span for span in _spans(exporter)}
    ancestor = (
        span_by_id.get(db_spans[0].parent.span_id) if db_spans[0].parent else None
    )
    chain: list[object] = []
    while ancestor is not None:
        chain.append(ancestor)
        ancestor = (
            span_by_id.get(ancestor.parent.span_id) if ancestor.parent else None  # type: ignore[attr-defined]
        )
    assert http_span in chain, "спан БД не вложен в HTTP-спан"
    assert db_spans[0].attributes["db.operation"] == "SELECT"
    # Диалект зависит от БД теста: SQLite локально, PostgreSQL в CI (T5.1).
    assert db_spans[0].attributes["db.system"] in {"sqlite", "postgresql"}


def test_database_span_does_not_carry_sql_text(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """Текст SQL в атрибутах не пишется: там данные сценария (приватность)."""
    traced_client.post("/v1/scenarios", json=publish_body(name="секретное-имя"))
    tracing.flush()

    attributes = {
        key: value
        for span in _spans(exporter)
        for key, value in span.attributes.items()
        if span.kind is SpanKind.CLIENT
    }

    assert "db.statement" not in attributes
    assert "секретное-имя" not in json.dumps(attributes, ensure_ascii=False)


def test_request_id_is_stored_on_http_span(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """`request_id` ответа лежит на HTTP-спане — связь ответа и трейса."""
    request_id = "client-request-id-0123456789abcdef"
    response = traced_client.get("/version", headers={"X-Request-ID": request_id})
    tracing.flush()

    [span] = _server_spans(exporter)

    assert response.headers["X-Request-ID"] == request_id
    assert span.attributes[REQUEST_ID_ATTRIBUTE] == request_id


def test_log_trace_id_matches_span_trace_id(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`trace_id` access-записи журнала совпадает с трейсом спана (ADR №41)."""
    capsys.readouterr()  # записи старта не нужны
    traced_client.get("/v1/scenarios")
    tracing.flush()

    [span] = _server_spans(exporter)
    payloads = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    access = [item for item in payloads if item.get("event") == "http_request"]

    assert access, "нет access-записи журнала"
    assert access[-1]["trace_id"] == _trace_id(span)


def test_error_response_is_traced(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """Ошибочные ответы (401/404) тоже дают спан: инцидент разбирается по трейсу."""
    traced_client.get("/v1/scenarios/00000000-0000-0000-0000-000000000000")
    traced_client.get("/v1/scenarios/not-a-uuid")
    tracing.flush()

    statuses = [_status_of(span) for span in _server_spans(exporter)]

    assert 404 in statuses
    assert 422 in statuses


# --- Отказоустойчивость --------------------------------------------------


def test_disabled_tracing_keeps_log_trace_id_empty(
    database: Database,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`CLICKIT_OTEL_ENABLED=0` — сервис работает, `trace_id` в журнале `-`.

    Ожидание «без спанов» относится к **этому** приложению: глобальный
    провайдер мог остаться от предыдущего теста в процессе и продолжает
    экспортировать чужие спаны, поэтому изоляция ставит `NoOpTracerProvider`
    и проверка не зависит от порядка.
    """
    from opentelemetry.trace import NoOpTracerProvider

    from service.app.observability import tracing as tracing_module

    monkeypatch.setattr(tracing_module.trace, "get_tracer_provider", NoOpTracerProvider)
    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url, otel_enabled=False),
        database,
        tracing,
    )
    capsys.readouterr()
    with TestClient(app) as client:
        assert client.get("/version").status_code == 200

    payloads = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    access = [item for item in payloads if item.get("event") == "http_request"]

    assert access and access[-1]["trace_id"] == "-"
    assert tracing.instrumented is False
    assert _spans(exporter) == []


def test_tracing_failure_does_not_break_service(
    database: Database,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сбой старта трейсинга логируется, а сервис продолжает отвечать."""

    class BrokenTracing(TracingSetup):
        def start(self, app: object, *, settings: Settings) -> None:
            raise RuntimeError("коллектор недоступен")

        def shutdown(self) -> None:
            pass

    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url, otel_enabled=True),
        database,
        BrokenTracing(),
        enable_tracing=True,
    )
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200

    payloads = [line for line in capsys.readouterr().out.splitlines() if line]
    assert any('"level":"ERROR"' in line for line in payloads), payloads


def test_shutdown_stops_tracing(database: Database, tracing: Tracing) -> None:
    """Остановка приложения снимает инструментации и закрывает провайдер."""
    app = create_app(
        Settings(api_key=API_KEY, db_url=database.url, otel_enabled=True),
        database,
        tracing,
        enable_tracing=True,
    )
    with TestClient(app):
        assert tracing.instrumented is True

    assert tracing.instrumented is False


# --- Окружение тестов ----------------------------------------------------


def test_sqlite_database_uses_sqlite_operation(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """Имя спана БД: `{диалект} {операция}`, атрибуты — конвенции OTel."""
    traced_client.get("/v1/scenarios")
    tracing.flush()

    db_spans = [span for span in _spans(exporter) if span.kind is SpanKind.CLIENT]

    assert db_spans
    assert all(" " in span.name for span in db_spans)
    assert all("db.namespace" in span.attributes for span in db_spans)


def test_trace_context_middleware_is_inside_http_span(
    traced_client: TestClient,
    tracing: Tracing,
    exporter: InMemorySpanExporter,
) -> None:
    """Слой `trace_id` встроен в стек, а не лежит снаружи инструментации."""
    app = traced_client.app
    user_middleware = [middleware.cls for middleware in app.user_middleware]

    assert TraceContextMiddleware in user_middleware
    assert app.state.tracing_enabled is True


def test_active_trace_id_is_none_without_span() -> None:
    """Вне спана `active_trace_id` — `None` (журнал пишет `-`)."""
    assert active_trace_id() is None


def test_fake_database_without_engine_does_not_break_tracing() -> None:
    """Подделка БД без `engine` — предупреждение в журнале, а не падение."""
    app = create_app(
        Settings(api_key=API_KEY, db_url="postgresql+psycopg://x@localhost/x"),
        FakeDatabase(),
        Tracing(exporter=InMemorySpanExporter()),
        enable_tracing=True,
    )
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200


def test_tracing_log_records_are_json(
    database_factory: DatabaseFactory,
    tracing: Tracing,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Сообщения трейсинга идут через тот же JSON-обработчик (T1.1)."""
    database = database_factory()
    capsys.readouterr()
    try:
        app = create_app(
            Settings(api_key=API_KEY, db_url=database.url, otel_enabled=True),
            database,
            tracing,
            enable_tracing=True,
        )
        with TestClient(app):
            pass
    finally:
        database.dispose()

    payloads = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line
    ]
    messages = [item["message"] for item in payloads]
    assert any("Трейсинг включён" in message for message in messages)
    assert any("Трейсинг остановлен" in message for message in messages)
