"""Метрики Prometheus сервиса ClicKit Cloud (M8 T1.2).

Контракт метрик — `docs/sre/slo.md` §8: имена и метки стабильны, меняются
только через ADR. Здесь живут три вещи:

* `ServiceMetrics` — коллекторы, привязанные к **собственному**
  `CollectorRegistry`. Свой реестр, а не глобальный
  `prometheus_client.REGISTRY`, нужен потому, что экземпляр создаёт
  приложение (и каждый тест): второй `Counter` с тем же именем в глобальном
  реестре падал бы с `Duplicated timeseries`.
* `HttpMetricsMiddleware` — единственная точка учёта HTTP-запросов: счётчик,
  гистограмма и gauge «в обработке». Запись выполняется ровно один раз — на
  `http.response.start` (до отправки заголовков, чтобы скрейп не видел сам
  себя) или в `finally`, если ответ сформировал слой выше (500) либо
  соединение оборвалось. Поэтому учитываются и ответы ошибок (401/404/422/500),
  и 413 лимита тела, и оборванные запросы.
* `render_metrics` — текст для `GET /metrics`.

Правила кардинальности (`docs/sre/slo.md` §8): в метках только `method`,
`route` (шаблон FastAPI, например `/v1/scenarios/{id}`) и `status`; id
сценариев, query-параметры, IP и ключи в метки не попадают. Запрос, не
совпавший ни с одним маршрутом, получает `route="unmatched"`: иначе каждый
мусорный путь создавал бы новую серию.

`clikit_db_pool_connections` и `clikit_build_info` не регистрируются как
коллекторы: состояние пула и метки сборки вычисляются на момент скрейпа
(см. `Database.pool_samples`, `render_metrics`).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Имя счётчика запросов (контракт, `docs/sre/slo.md` §8).
REQUESTS_TOTAL = "clikit_http_requests_total"
#: Имя гистограммы длительности запросов.
REQUEST_DURATION_SECONDS = "clikit_http_request_duration_seconds"
#: Имя gauge запросов, находящихся в обработке.
REQUESTS_IN_FLIGHT = "clikit_http_requests_in_flight"
#: Имя gauge соединений пула БД (значение вычисляется при скрейпе).
DB_POOL_CONNECTIONS = "clikit_db_pool_connections"
#: Имя gauge сведений о сборке (вычисляется при скрейпе).
BUILD_INFO = "clikit_build_info"
#: Content-Type ответа `/metrics`: формат Prometheus 1.0, читается и
#: Prometheus >= 2.40, и curl (в заголовке есть `charset=utf-8`).
METRICS_CONTENT_TYPE = CONTENT_TYPE_LATEST

#: Служебные маршруты, запись журнала о которых не нужна: `/metrics`
#: скрейпится каждые 15 с (`plans/M8-observability.md` §3), иначе журнал
#: состоял бы из шума одного эндпоинта.
QUIET_ROUTES: frozenset[str] = frozenset({"/metrics"})
#: Метка `route`, если запрос не совпал ни с одним маршрутом.
UNMATCHED_ROUTE = "unmatched"
#: Путь скрейпа: запрос `/metrics` сам себя в `in_flight` не считает, иначе
#: gauge в теле ответа всегда показывал бы минимум 1 «активный» запрос — сам
#: скрейп. Счётчик и гистограмма при этом учитывают `/metrics` как обычно.
SCRAPE_PATHS: frozenset[str] = QUIET_ROUTES
#: Ключ `scope["state"]`: access-запись журнала этого запроса подавляется.
QUIET_LOG_KEY = "quiet_log"

#: Корзины длительности, секунды. `0.3` — порог задержки SLO
#: (`docs/sre/slo.md` §4.2), и он обязан быть в списке: без корзины
#: `le="0.3"` запись `clikit:sli_latency:ratio_rate5m` посчитать нельзя.
#: Остальные — стандартный набор для веб-сервиса.
DURATION_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.3,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


class ServiceMetrics:
    """Коллекторы метрик ClicKit Cloud в собственном реестре.

    Attributes:
        registry: Приватный реестр коллекторов.
        requests_total: Счётчик HTTP-запросов (`method`, `route`, `status`).
        request_duration: Гистограмма длительности (`method`, `route`,
            `status` + автоматическая `le`).
        requests_in_flight: Gauge активных запросов.
    """

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        """Создать коллекторы.

        Args:
            registry: Реестр (тесты); `None` — новый приватный реестр.
        """
        self.registry = registry if registry is not None else CollectorRegistry()
        self.requests_total = Counter(
            REQUESTS_TOTAL,
            "HTTP-запросы ClicKit Cloud: метод, шаблон маршрута, код ответа.",
            labelnames=("method", "route", "status"),
            registry=self.registry,
        )
        self.request_duration = Histogram(
            REQUEST_DURATION_SECONDS,
            "Длительность HTTP-запросов ClicKit Cloud, секунды.",
            labelnames=("method", "route", "status"),
            buckets=DURATION_BUCKETS,
            registry=self.registry,
        )
        self.requests_in_flight = Gauge(
            REQUESTS_IN_FLIGHT,
            "HTTP-запросы, находящиеся в обработке прямо сейчас.",
            registry=self.registry,
        )

    def observe_request(
        self,
        *,
        method: str,
        route: str,
        status: int,
        duration: float,
    ) -> None:
        """Учесть завершённый HTTP-запрос.

        Args:
            method: HTTP-метод (`GET`, `POST`, …).
            route: Шаблон маршрута FastAPI или `unmatched`.
            status: HTTP-код ответа.
            duration: Длительность обработки в секундах.
        """
        status_label = str(status)
        self.requests_total.labels(
            method=method, route=route, status=status_label
        ).inc()
        self.request_duration.labels(
            method=method, route=route, status=status_label
        ).observe(max(duration, 0.0))


class HttpMetricsMiddleware:
    """Учитывать каждый HTTP-запрос: счётчик, гистограмму и in-flight.

    Слой ставится внутри лимита тела и внутри `RequestContextMiddleware`:
    идентификатор запроса уже в `scope["state"]`, а ответ 413 лимита тела
    попадает в метрики.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Обернуть ASGI-приложение.

        Args:
            app: Следующий слой стека Starlette.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Измерить запрос и передать его дальше."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        metrics = _metrics_of_scope(scope)
        if metrics is None:  # pragma: no cover — приложению метрики обязательны
            await self.app(scope, receive, send)
            return

        status_code = 500
        recorded = False
        route = UNMATCHED_ROUTE
        # Скрейп `/metrics` не считается «в обработке»: иначе gauge в теле
        # ответа всегда был бы ≥ 1 из-за самого скрейпа.
        counts_in_flight = scope.get("path") not in SCRAPE_PATHS

        def record() -> None:
            nonlocal recorded, route
            if recorded:
                return
            recorded = True
            elapsed = time.perf_counter() - started
            if counts_in_flight:
                metrics.requests_in_flight.dec()
            if route == UNMATCHED_ROUTE:
                # Ответ мог сформировать слой выше (500 от ServerErrorMiddleware):
                # `http.response.start` через нас не прошёл, но маршрут уже
                # записан роутером в scope. Без этого 5xx попадали бы в
                # `unmatched` и выпадали из SLI доступности.
                route = _route_of_scope(scope)
            metrics.observe_request(
                method=scope.get("method", "-"),
                route=route,
                status=status_code,
                duration=elapsed,
            )
            if route in QUIET_ROUTES:
                _mark_quiet(scope)

        async def send_with_metrics(message: Message) -> None:
            nonlocal status_code, route
            if message["type"] == "http.response.start":
                # Шаблон маршрута появляется в scope только после маршрутизации,
                # поэтому берётся здесь, а не до вызова слоя. Запись — до
                # отправки заголовков: иначе скрейп `/metrics` видит себя же
                # «в обработке» (gauge ещё не уменьшен).
                status_code = int(message["status"])
                route = _route_of_scope(scope)
                record()
            await send(message)

        started = time.perf_counter()
        if counts_in_flight:
            metrics.requests_in_flight.inc()
        try:
            await self.app(scope, receive, send_with_metrics)
        finally:
            # Слои выше могут ответить мимо этого `send`, соединение может
            # оборваться — учёт всё равно обязан состояться ровно один раз.
            record()


def _metrics_of_scope(scope: Scope) -> ServiceMetrics | None:
    """Объект метрик приложения из ASGI-scope (вне `lifespan` — `None`)."""
    app = scope.get("app")
    state = getattr(app, "state", None)
    metrics = getattr(state, "metrics", None)
    return metrics if isinstance(metrics, ServiceMetrics) else None


def _route_of_scope(scope: Scope) -> str:
    """Шаблон маршрута FastAPI из scope (`/v1/scenarios/{id}`) или `unmatched`."""
    path = getattr(scope.get("route"), "path", None)
    return path if isinstance(path, str) and path else UNMATCHED_ROUTE


def _mark_quiet(scope: Scope) -> None:
    """Пометить запрос как служебный: access-запись в журнале не нужна."""
    state = scope.get("state")
    if isinstance(state, dict):
        state[QUIET_LOG_KEY] = True


def render_metrics(
    metrics: ServiceMetrics,
    *,
    pool_samples: Callable[[], Mapping[str, float]] | None = None,
    build_labels: Callable[[], Mapping[str, str]] | None = None,
) -> bytes:
    """Собрать ответ `GET /metrics` в текстовом формате Prometheus.

    Args:
        metrics: Коллекторы приложения.
        pool_samples: Состояние пула БД на момент скрейпа
            (`clikit_db_pool_connections{state}`); `None` — метрики нет
            (например, БД — заглушка в тестах).
        build_labels: Метки `clikit_build_info` (`version`, `git_sha`).

    Returns:
        Текст в кодировке UTF-8, открытые метрики процессора и GC включены
        стандартной библиотекой `prometheus_client`, как принято для Python.
    """
    parts: list[str] = []
    if build_labels is not None:
        rendered = ",".join(
            f'{name}="{_escape_label(value)}"' for name, value in build_labels().items()
        )
        parts.extend(
            (
                f"# HELP {BUILD_INFO} Сведения о сборке ClicKit Cloud.",
                f"# TYPE {BUILD_INFO} gauge",
                f"{BUILD_INFO}{{{rendered}}} 1",
            )
        )
    if pool_samples is not None:
        parts.extend(
            (
                f"# HELP {DB_POOL_CONNECTIONS} Соединения пула БД по состоянию.",
                f"# TYPE {DB_POOL_CONNECTIONS} gauge",
            )
        )
        parts.extend(
            f'{DB_POOL_CONNECTIONS}{{state="{state}"}} {value}'
            for state, value in pool_samples().items()
        )
    body = "\n".join(parts)
    if body:
        body += "\n"
    return body.encode("utf-8") + generate_latest(metrics.registry)


def _escape_label(value: str) -> str:
    """Экранировать значение метки по правилам текстового формата Prometheus."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def labels_are_allowed(names: Iterable[str], allowed: frozenset[str]) -> bool:
    """Проверить, что все метки сбора входят в разрешённый набор.

    Используется статическим тестом кардинальности: новые метки (id, путь,
    IP) должны ломать тест, а не Prometheus.

    Args:
        names: Имена меток коллектора.
        allowed: Разрешённые имена.

    Returns:
        `True`, если лишних меток нет.
    """
    return set(names) <= set(allowed)
