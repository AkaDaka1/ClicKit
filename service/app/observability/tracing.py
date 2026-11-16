"""Трейсы OpenTelemetry сервиса ClicKit Cloud (M8 T1.3).

Контракт — `plans/M8-observability.md` §3–4.1 и ADR №41: один идентификатор
связывает запись журнала и трейс. Здесь живёт включение OTel SDK:

* **HTTP-спан** создаёт `opentelemetry-instrumentation-fastapi`
  (`FastAPIInstrumentor.instrument_app`): имя вида
  `GET /v1/scenarios/{scenario_id}` с шаблоном маршрута (кардинальность
  не растёт с числом сценариев), атрибуты метода, схемы URL и кода ответа;
* **спан запроса к БД** создаёт `SqlTracingListener` на событии
  `before_cursor_execute`: официальная
  `opentelemetry-instrumentation-sqlalchemy` 0.66b2 ограничена
  `sqlalchemy < 2.1`, а проект идёт на 2.x, поэтому вместо тихого «ничего
  не инструментировано» спан строится на стабильном событии SQLAlchemy.
  Текст SQL (`db.statement`) намеренно не пишется: в нём данные сценария;
* **экспорт** — OTLP/HTTP в Tempo (`/v1/traces`), батчевый и в фоновом
  потоке: недоступный коллектор не задерживает ответы сервиса.

`trace_id` попадает в журнал через `CorrelationFilter` (T1.1): слой
`TraceContextMiddleware` стоит **внутри** HTTP-спана, поэтому каждая запись
обработки запроса, включая access-строку из `finally`, берёт идентификатор
трейса из текущего спана (ADR №41). Атрибут `clikit.request_id` на
HTTP-спане связывает `request_id` из ответа с трейсом в Tempo.

`TracerProvider` — на каждое приложение (`create_app`), как и реестр метрик
(ADR №62): тесты не делят глобальное состояние, а повторная сборка
приложения не падает на «уже инструментировано». SDK включается **только**
в `Tracing.start` из `lifespan`, поэтому импорт модуля не требует ни сети,
ни окружения — тот же принцип, что у настроек (ADR №51).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, ParentBased, TraceIdRatioBased
from opentelemetry.trace import Tracer
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from starlette.datastructures import State  # noqa: F401 — тип `app.state`
from starlette.middleware import Middleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from service.app.config import DEFAULT_SPAN_EXPORT_TIMEOUT_SECONDS, Settings
from service.app.observability.logging import current_trace_id
from service.app.request_id import request_id_of_scope
from service.app.version import SERVICE_NAME, SERVICE_VERSION

logger = logging.getLogger(__name__)

#: Путь OTLP/HTTP для трейсов: экспортёр добавляет его к базовому адресу.
TRACES_PATH = "/v1/traces"
#: Атрибут спана с идентификатором запроса: связывает ответ API с трейсом.
REQUEST_ID_ATTRIBUTE = "clikit.request_id"
#: Ключ `app.state`: признак, что трейсинг приложения включён.
TRACING_ENABLED_KEY = "tracing_enabled"
#: Атрибут `app.state` с провайдером трейсинга приложения (тесты, отладка).
TRACE_PROVIDER_ATTR = "tracer_provider"
#: Ключ `Connection.info`: активные спаны запросов на этом соединении.
_SPAN_KEY = "clikit_otel_sql_spans"


class TracingSetup(Protocol):
    """Минимальный интерфейс настройки трейсинга, нужный приложению (тесты)."""

    def start(self, app: FastAPI, *, settings: Settings) -> None:
        """Включить трейсинг для приложения."""
        ...

    def shutdown(self) -> None:
        """Остановить экспорт и освободить ресурсы."""
        ...


def otlp_traces_url(endpoint: str) -> str:
    """Полный адрес OTLP/HTTP для трейсов.

    Args:
        endpoint: Базовый адрес (`http://tempo:4318`); допускается уже
            полный путь (`http://localhost:4318/v1/traces`).

    Returns:
        Адрес вида `http://tempo:4318/v1/traces`.
    """
    base = endpoint.rstrip("/")
    if base.endswith(TRACES_PATH):
        return base
    return f"{base}{TRACES_PATH}"


def active_trace_id() -> str | None:
    """`trace_id` текущего спана (`None` — трейсинга нет или он выключен).

    Используется фильтром журнала: OTel хранит активный спан в `ContextVar`,
    поэтому значение согласовано с тем же `trace_id`, что виден в Tempo,
    без ручной передачи контекста через все обработчики.
    """
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return None
    return format(context.trace_id, "032x")


class TraceContextMiddleware:
    """Футер запроса: `trace_id` спана — в журнальный контекст и в атрибуты.

    Слой добавляется в приложение **до** `Tracing.start`: инструментация
    FastAPI оборачивает приложение снаружи, поэтому к моменту входа в слой
    HTTP-спан уже создан. Своего спана слой не создаёт — у запроса остаётся
    один корневой спан и его дочерние спаны БД.

    Признак включённого трейсинга читается из `scope["app"].state` на каждом
    запросе: `lifespan` выставляет его уже после постройки стека middleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Обернуть ASGI-приложение.

        Args:
            app: Следующий слой стека Starlette.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Привязать `trace_id` к контексту запроса на время обработки."""
        if scope["type"] != "http" or not _tracing_enabled(scope):
            await self.app(scope, receive, send)
            return

        span = trace.get_current_span()
        context = span.get_span_context()
        if not context.is_valid:
            # Запрос исключён из трейсинга или SDK не стартовал — не мешаем.
            await self.app(scope, receive, send)
            return

        request_id = request_id_of_scope(scope)
        if span.is_recording():
            span.set_attribute(REQUEST_ID_ATTRIBUTE, request_id)
        token = current_trace_id.set(format(context.trace_id, "032x"))

        async def send_with_request_id(message: Message) -> None:
            # HTTP-спан OTel завершается на `http.response.start`, то есть
            # раньше, чем сработал бы `finally` этого слоя. Поэтому атрибут
            # ставится здесь: к этому моменту `RequestContextMiddleware`
            # (он внутри) уже записал в `scope["state"]` тот же
            # `request_id`, что уходит клиенту в `X-Request-ID`.
            if message["type"] == "http.response.start" and span.is_recording():
                span.set_attribute(REQUEST_ID_ATTRIBUTE, request_id_of_scope(scope))
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            current_trace_id.reset(token)


def install_tracer_provider(provider: TracerProvider) -> None:
    """Назначить провайдер трейсинга на процесс.

    Публичный `set_tracer_provider` срабатывает однократно, а повторный
    вызов молча игнорируется (и отменить его нельзя), из-за чего второй
    экземпляр приложения в процессе остался бы без спанов. Здесь
    сбрасывается сохранённый экземпляр, и провайдер назначается заново:
    в бою процесс один (uvicorn), а тестам нужен свой `TracerProvider` на
    каждый экземпляр — как реестр метрик (ADR №62).

    Args:
        provider: Провайдер SDK, который станет глобальным.
    """
    trace._TRACER_PROVIDER = None  # type: ignore[attr-defined]
    trace._TRACER_PROVIDER_SET_ONCE._done = False  # type: ignore[attr-defined]
    trace.set_tracer_provider(provider)


def _tracing_enabled(scope: Scope) -> bool:
    """Включён ли трейсинг у приложения из ASGI-scope.

    `app.state` — `starlette.datastructures.State`: отсутствующий ключ
    поднимает `AttributeError`, поэтому проверяется словарь состояния.
    """
    state = getattr(scope.get("app"), "state", None)
    values = getattr(state, "_state", None)
    return bool(values.get(TRACING_ENABLED_KEY)) if isinstance(values, dict) else False


def _insert_trace_middleware(app: FastAPI) -> None:
    """Вставить `TraceContextMiddleware` внутрь уже построенного стека.

    `TraceContextMiddleware` сам HTTP-спан не создаёт: спан принадлежит
    `OpenTelemetryMiddleware`, поэтому слой обязан оказаться внутри него.
    `add_middleware` в этот момент может быть запрещён (стек уже построен),
    а стек Starlette пересобирается из `app.user_middleware` при каждом
    запуске приложения, поэтому слой добавляется в список слоёв и стек
    пересобирается: первый запуск увидит его сразу, повторный — тем более.

    Args:
        app: Приложение FastAPI.
    """
    app.user_middleware.insert(0, Middleware(TraceContextMiddleware))
    app.middleware_stack = app.build_middleware_stack()


class SqlTracingListener:
    """Спаны вокруг SQL-запросов SQLAlchemy.

    Подписывается на `before_cursor_execute`/`after_cursor_execute` движка
    приложения: первый создаёт спан и подвешивает его в `Connection.info`,
    второй — завершает. Спан создаётся дочерним текущему (HTTP-спану), но
    активным контекстом не становится: иначе вложенный запрос внутри
    транзакции ломал бы связь с родителем.

    Атрибуты — по семантическим конвенциям БД: `db.system`, `db.namespace`,
    `db.operation`, `db.query.summary`. Текст запроса не пишется никогда:
    в SQL попадают данные сценария (описание, имя), а трейс не место для
    пользовательских данных (ADR №41, §9 плана M8 — приватность).
    """

    def __init__(self, tracer: Tracer) -> None:
        """Подготовить слушатель.

        Args:
            tracer: Трейсер приложения.
        """
        self._tracer = tracer
        self._engine: Engine | None = None

    def start(self, database: object) -> None:
        """Подписать слушатель на движок подключения приложения.

        Args:
            database: Подключение с атрибутом `engine` (`service.app.db.Database`).
        """
        engine = getattr(database, "engine", None)
        if not isinstance(engine, Engine):
            logger.warning("Спаны БД не включены: у подключения нет engine")
            return
        self._engine = engine
        event.listen(engine, "before_cursor_execute", self._before_execute)
        event.listen(engine, "after_cursor_execute", self._after_execute)

    def stop(self) -> None:
        """Снять слушатель с движка (идемпотентно)."""
        engine = self._engine
        if engine is not None:
            event.remove(engine, "before_cursor_execute", self._before_execute)
            event.remove(engine, "after_cursor_execute", self._after_execute)
        self._engine = None

    def _before_execute(
        self,
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """Начать спан запроса."""
        engine = conn.engine
        dialect = engine.dialect.name
        operation = _sql_operation(statement)
        span = self._tracer.start_span(
            f"{dialect} {operation}",
            kind=trace.SpanKind.CLIENT,
            attributes={
                "db.system": dialect,
                "db.namespace": engine.url.database or "",
                "db.operation": operation,
                "db.query.summary": f"{dialect} {operation}",
            },
        )
        conn.info.setdefault(_SPAN_KEY, []).append(span)

    def _after_execute(
        self,
        conn: Connection,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        """Завершить спан запроса."""
        spans: list[trace.Span] = conn.info.get(_SPAN_KEY) or []
        if spans:
            spans.pop().end()


#: Первое слово запроса → операция для имени спана и `db.operation`.
_SQL_OPERATIONS: tuple[str, ...] = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "COMMIT",
    "ROLLBACK",
    "CREATE",
    "ALTER",
    "DROP",
    "PRAGMA",
)


def _sql_operation(statement: str) -> str:
    """Определить операцию SQL по первому слову запроса."""
    upper = statement.lstrip(" \t\r\n(")[:12].upper()
    for word in _SQL_OPERATIONS:
        if upper.startswith(word):
            return word
    return "OTHER"


class Tracing:
    """Создать `TracerProvider` приложения и управлять его жизненным циклом.

    Attributes:
        provider: Провайдер трейсинга; `None` до `start` или при выключенном
            трейсинге.
        endpoint: Адрес OTLP-экспорта; `None` — свой экспортёр (тесты).
        instrumented: `True`, если инструментации включены.
    """

    def __init__(
        self,
        *,
        exporter: SpanExporter | None = None,
        service_name: str | None = None,
        version: str = SERVICE_VERSION,
        enabled: bool = True,
    ) -> None:
        """Подготовить ресурс провайдера (SDK при этом не включается).

        Args:
            exporter: Готовый экспортёр (тесты — `InMemorySpanExporter`);
                `None` — OTLP HTTP по адресу из настроек.
            service_name: `service.name` ресурса; `None` — имя сервиса.
            version: `service.version` ресурса.
            enabled: Включать ли трейсинг при старте приложения (`False` —
                тесты без трейсинга, `CLICKIT_OTEL_ENABLED=0`).
        """
        self._exporter = exporter
        self.enabled = enabled
        self._resource = Resource.create(
            {
                "service.name": service_name or SERVICE_NAME,
                "service.version": version,
            }
        )
        self.provider: TracerProvider | None = None
        self.endpoint: str | None = None
        self.instrumented = False
        self._sql_listener: SqlTracingListener | None = None

    def start(self, app: FastAPI, *, settings: Settings) -> None:
        """Включить провайдер, HTTP-инструментацию и спаны БД.

        Повторный вызов для другого приложения в том же процессе безопасен и
        ничего не делает: провайдер SDK глобальный, а второй
        `set_tracer_provider` молча игнорируется — иначе спаны второго
        приложения уходили бы в невидимый сборщик.

        Args:
            app: Приложение FastAPI; к его стеку добавляется инструментация
                HTTP, а к `app.state.database` — слушатель SQLAlchemy.
            settings: Настройки трейсинга: адрес коллектора и доля сэмплов.
        """
        if self.instrumented:
            logger.debug("Трейсинг для этого объекта уже включён")
            return
        exporter = self._exporter
        export_to = self.endpoint
        if exporter is None:
            self.endpoint = otlp_traces_url(settings.otel_endpoint)
            export_to = self.endpoint
            exporter = OTLPSpanExporter(
                endpoint=self.endpoint,
                timeout=DEFAULT_SPAN_EXPORT_TIMEOUT_SECONDS,
            )
        rate = settings.otel_sample_rate
        sampler = ALWAYS_ON if rate >= 1.0 else ParentBased(TraceIdRatioBased(rate))
        provider = TracerProvider(resource=self._resource, sampler=sampler)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        install_tracer_provider(provider)
        setattr(app.state, TRACE_PROVIDER_ATTR, provider)
        # Слой `TraceContextMiddleware` кладёт `trace_id` спана в контекст
        # журнала и связывает ответ с трейсом. Инструментация FastAPI
        # оборачивает приложение снаружи, поэтому слой вставляется в список
        # слоёв и стек пересобирается — иначе спан ещё не создан и
        # `trace_id` в журнале остался бы `-`.
        _insert_trace_middleware(app)
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)  # type: ignore[arg-type]
        listener = SqlTracingListener(
            provider.get_tracer(SERVICE_NAME, SERVICE_VERSION)
        )
        listener.start(getattr(app.state, "database", None))
        self._sql_listener = listener
        self.provider = provider
        self.instrumented = True
        logger.info(
            "Трейсинг включён: %s (сэмплирование %s)",
            export_to or "встроенный экспортёр",
            rate,
        )

    def shutdown(self) -> None:
        """Снять спаны БД, отправить накопленные трейсы и закрыть provider."""
        if not self.instrumented:
            return
        if self._sql_listener is not None:
            self._sql_listener.stop()
        if self.provider is not None:
            # `shutdown` дожидается отправки батча: трейсы последних запросов
            # не теряются при SIGTERM (graceful shutdown uvicorn).
            self.provider.shutdown()
        self.instrumented = False
        logger.info("Трейсинг остановлен")

    def flush(self) -> None:
        """Немедленно отправить накопленный батч (тесты, диагностика)."""
        if self.provider is not None:
            self.provider.force_flush()

    def tracer(self) -> Tracer:
        """Трейсер приложения: прикладные спаны идут в тот же провайдер."""
        if self.provider is None:
            return trace.get_tracer(SERVICE_NAME, SERVICE_VERSION)
        return self.provider.get_tracer(SERVICE_NAME, SERVICE_VERSION)
