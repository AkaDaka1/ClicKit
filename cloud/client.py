"""HTTP-клиент ClicKit Cloud (`docs/api.md` §10, M7 T4.2).

Клиент — тонкая обёртка над `httpx`: он не валидирует IR (это делает сервис
через `core.ir.schema`, ADR №37) и не знает о GUI. Его обязанности строго
перечислены контрактом:

- собрать запрос по контракту (`/v1/scenarios`, `/v1/crash-reports`);
- повторить запрос только при 5xx, таймауте и сетевой ошибке — до трёх
  попыток с паузами `0.5, 1, 2` с и jitter ±25 %; 4xx **не** повторяются;
- превратить ответ или problem+json в объекты `PublishedScenario`,
  `ScenarioPage`, `CrashReceipt` либо в исключение из иерархии `CloudError`.

Модуль живёт отдельно от `core/` и `gui/`: desktop-приложение остаётся
работоспособным без сети (ADR №36). Время ожидания по умолчанию — 5 с на
попытку, чтобы CLI не «висел» на мёртвом сервере.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

#: Значение по умолчанию для `User-Agent` (сервер его не разбирает).
DEFAULT_USER_AGENT = "clikit-cloud-client/1.0"
#: Максимум записей в списке `errors` problem+json (`docs/api.md` §4).
MAX_ISSUES = 50
#: Паузы между попытками в секундах (до трёх попыток — две паузы).
DEFAULT_BACKOFF = (0.5, 1.0, 2.0)


@dataclass(frozen=True)
class PublishedScenario:
    """Метаданные опубликованного сценария (`docs/api.md` §5.5, §5.7).

    Attributes:
        id: UUIDv4 сценария.
        name: Имя сценария.
        sha256: Канонический хэш IR (он же `ETag`).
        created_at: Время создания (RFC 3339, UTC).
        updated_at: Время обновления (RFC 3339, UTC).
        url: Путь скачивания (`/v1/scenarios/<id>`) или `None` для списка.
        description: Описание сценария (в ответе 201 может отсутствовать).
    """

    id: str
    name: str
    sha256: str
    created_at: str
    updated_at: str
    url: str | None = None
    description: str = ""


@dataclass(frozen=True)
class ScenarioPage:
    """Страница списка сценариев (`docs/api.md` §5.7).

    Attributes:
        items: Сценарии страницы (без полного IR).
        total: Полное число сценариев.
        limit: Размер страницы.
        offset: Смещение.
    """

    items: list[PublishedScenario]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CrashReceipt:
    """Ответ 202 на приём crash-отчёта (`docs/api.md` §5.9).

    Attributes:
        id: UUIDv4 сохранённого отчёта.
        received_at: Время приёма (RFC 3339, UTC).
    """

    id: str
    received_at: str


class CloudError(Exception):
    """Базовая ошибка клиента ClicKit Cloud.

    Attributes:
        status: HTTP-код ответа (0 — сеть/таймаут без ответа).
        detail: Человекочитаемая деталь (из problem+json или текста ошибки).
        request_id: Значение `X-Request-ID` сервера, если пришло.
        type_urn: Стабильный URN типа ошибки (`urn:clikit:error:...`).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        detail: str = "",
        request_id: str | None = None,
        type_urn: str | None = None,
    ) -> None:
        """Создать ошибку клиента.

        Args:
            message: Краткое описание для пользователя.
            status: HTTP-код ответа или 0 для сетевых ошибок.
            detail: Подробность из problem+json (`detail`).
            request_id: Идентификатор корреляции сервера.
            type_urn: URN типа ошибки.
        """
        super().__init__(message)
        self.status = status
        self.detail = detail
        self.request_id = request_id
        self.type_urn = type_urn

    def __str__(self) -> str:
        """Собрать сообщение с корреляцией для консольного вывода."""
        text = super().__str__()
        if self.detail and self.detail != text:
            text = f"{text}: {self.detail}"
        if self.request_id:
            text = f"{text} (request_id={self.request_id})"
        return text


class CloudAuthError(CloudError):
    """401/403: ключ не передан, неверен или не даёт прав (`docs/api.md` §2)."""


class CloudNotFoundError(CloudError):
    """404: сценарий не найден."""


class CloudConflictError(CloudError):
    """409: `Idempotency-Key` повторён с другим телом (`docs/api.md` §7)."""


class CloudTooLargeError(CloudError):
    """413: тело запроса больше лимита (1 МБ)."""


class CloudValidationError(CloudError):
    """422: схема запроса или IR невалидны.

    Attributes:
        issues: Список `{path, message}` из problem+json (до 50 записей).
    """

    def __init__(
        self,
        message: str,
        *,
        issues: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> None:
        """Создать ошибку валидации.

        Args:
            message: Краткое описание.
            issues: Ошибки полей с путями.
            **kwargs: Аргументы `CloudError` (status, detail, request_id, …).
        """
        super().__init__(message, **kwargs)
        self.issues = list(issues or [])[:MAX_ISSUES]


class CloudServerError(CloudError):
    """5xx или сеть/таймаут после исчерпания попыток."""


class _Retryable(Exception):
    """Внутренняя отметка «запрос можно повторить» (5xx, таймаут, сеть)."""


class CloudClient:
    """Клиент ClicKit Cloud по контракту `docs/api.md` §10.

    Экземпляр держит один `httpx.Client` с таймаутом на попытку и общим
    заголовком `User-Agent`. Его можно переиспользовать между вызовами и
    закрывать через `close()` (или как контекстный менеджер).
    """

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        timeout: float = 5.0,
        attempts: int = 3,
        backoff_base: float = 0.5,
        jitter: float = 0.25,
        transport: httpx.BaseTransport | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        """Настроить клиент.

        Args:
            base_url: Базовый URL сервиса, например `http://localhost:8000`.
            api_key: Ключ записи (`X-API-Key`); без него доступны только
                публичные методы.
            timeout: Таймаут одной попытки в секундах.
            attempts: Число попыток, 1–10 (по умолчанию 3).
            backoff_base: Базовая пауза между попытками в секундах.
            jitter: Доля случайного разброса паузы (0.25 → ±25 %).
            transport: Готовый `httpx`-transport (в тестах — `MockTransport`).
            user_agent: Заголовок `User-Agent`.

        Raises:
            ValueError: неверный `base_url`, `attempts` или отрицательные
                таймауты/паузы.
        """
        normalized = (base_url or "").strip()
        if not normalized.startswith(("http://", "https://")):
            raise ValueError("base_url должен начинаться с http:// или https://")
        if not 1 <= attempts <= 10:
            raise ValueError("attempts должен быть в диапазоне 1..10")
        if timeout <= 0:
            raise ValueError("timeout должен быть положительным")
        if backoff_base < 0 or not 0 <= jitter < 1:
            raise ValueError("backoff_base ≥ 0 и 0 ≤ jitter < 1")

        self._base_url = normalized.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._attempts = attempts
        self._backoff = [backoff_base * (2**index) for index in range(attempts - 1)]
        self._jitter = jitter
        self._sleep = time.sleep
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        if api_key:
            headers["X-API-Key"] = api_key
        self._http = httpx.Client(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
            headers=headers,
            transport=transport,
            follow_redirects=False,
        )

    # --- Публичный API -------------------------------------------------

    def publish(
        self,
        document: dict[str, Any],
        *,
        name: str | None = None,
        description: str | None = None,
        idempotency_key: str | None = None,
    ) -> PublishedScenario:
        """Опубликовать сценарий (`.acl.json`) — `POST /v1/scenarios`.

        Args:
            document: IR-сценарий (полный документ `.acl.json`).
            name: Имя публикации; если `None`, сервер берёт `document["name"]`.
            description: Описание; если `None`, поле не отправляется.
            idempotency_key: Значение `Idempotency-Key` для безопасного
                повтора запроса (`docs/api.md` §7).

        Returns:
            Метаданные созданного (или ранее созданного по тому же ключу)
            сценария.

        Raises:
            CloudError: иерархия ошибок по HTTP-коду ответа.
        """
        body: dict[str, Any] = {"scenario": document}
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        headers = {}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        payload = self._request(
            "POST",
            "/v1/scenarios",
            json=body,
            headers=headers,
            require_key=True,
        )
        return _scenario_from_payload(payload, with_url=True)

    def download(self, scenario_id: str) -> dict[str, Any]:
        """Скачать полный документ сценария — `GET /v1/scenarios/{id}`.

        Args:
            scenario_id: UUIDv4 сценария.

        Returns:
            Полный `.acl.json` (валидированный и нормализованный IR).

        Raises:
            CloudError: 404 для неизвестного id, 422 для неверного UUID.
        """
        payload = self._request("GET", f"/v1/scenarios/{_quote(scenario_id)}")
        if not isinstance(payload, dict):
            raise CloudServerError("Сервер вернул не JSON-объект сценария")
        return payload

    def list(self, *, limit: int = 20, offset: int = 0) -> ScenarioPage:
        """Отдать страницу списка сценариев — `GET /v1/scenarios`.

        Args:
            limit: Размер страницы, 1–100.
            offset: Смещение, ≥ 0.

        Returns:
            Страница метаданных (`items`, `total`, `limit`, `offset`).

        Raises:
            CloudError: 422 при неверных параметрах.
        """
        payload = self._request(
            "GET",
            "/v1/scenarios",
            params={"limit": str(limit), "offset": str(offset)},
        )
        if not isinstance(payload, dict):
            raise CloudServerError("Сервер вернул не JSON-объект списка")
        items = payload.get("items") or []
        if not isinstance(items, list):
            raise CloudServerError("Сервер вернул некорректный список сценариев")
        return ScenarioPage(
            items=[
                _scenario_from_payload(item) for item in items if isinstance(item, dict)
            ],
            total=int(payload.get("total") or 0),
            limit=int(payload.get("limit") or limit),
            offset=int(payload.get("offset") or offset),
        )

    def delete(self, scenario_id: str) -> None:
        """Удалить сценарий — `DELETE /v1/scenarios/{id}`.

        Args:
            scenario_id: UUIDv4 сценария.

        Raises:
            CloudError: 401/403 без прав, 404 для неизвестного id.
        """
        self._request(
            "DELETE",
            f"/v1/scenarios/{_quote(scenario_id)}",
            require_key=True,
        )

    def report_crash(
        self,
        *,
        app_version: str,
        os: str,
        error_hash: str,
        traceback: str | None = None,
    ) -> CrashReceipt:
        """Отправить crash-отчёт — `POST /v1/crash-reports`.

        Публичный эндпоинт: ключ не нужен. Санитизацию PII выполняет сервер,
        клиент отправляет текст как есть (`docs/api.md` §5.9).

        Args:
            app_version: Версия приложения (1–64 символа).
            os: Описание ОС (≤ 64 символа).
            error_hash: SHA-256 сигнатуры ошибки (64 hex).
            traceback: Текст трассировки или `None`.

        Returns:
            Идентификатор сохранённого отчёта и время приёма.

        Raises:
            CloudError: 413/422/5xx.
        """
        body: dict[str, Any] = {
            "app_version": app_version,
            "os": os,
            "error_hash": error_hash,
        }
        if traceback is not None:
            body["traceback"] = traceback
        payload = self._request("POST", "/v1/crash-reports", json=body)
        if not isinstance(payload, dict):
            raise CloudServerError("Сервер вернул не JSON-объект квитанции")
        return CrashReceipt(
            id=str(payload.get("id", "")),
            received_at=str(payload.get("received_at", "")),
        )

    def close(self) -> None:
        """Закрыть соединения `httpx`."""
        self._http.close()

    def __enter__(self) -> CloudClient:
        """Войти в контекстный менеджер."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Закрыть клиент при выходе из контекста."""
        self.close()

    # --- Внутренняя механика -------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        require_key: bool = False,
    ) -> Any:
        """Выполнить запрос с retry и разбором ответа.

        Args:
            method: HTTP-метод.
            path: Путь от базового URL (`/v1/...`).
            json: JSON-тело запроса.
            params: Query-параметры.
            headers: Дополнительные заголовки.
            require_key: Требовать настроенный ключ до отправки.

        Returns:
            Разобранное JSON-тело ответа (или `None` для пустого тела).

        Raises:
            CloudError: ошибка по коду ответа или после исчерпания попыток.
        """
        if require_key and not self._api_key:
            raise CloudAuthError(
                "Для этого действия нужен API-ключ (CLICKIT_API_KEY)",
                status=401,
            )

        last_error: _Retryable | None = None
        last_status = 0
        last_request_id: str | None = None
        for attempt in range(1, self._attempts + 1):
            if attempt > 1:
                self._sleep(self._pause(attempt - 2))
            try:
                response = self._http.request(
                    method,
                    path,
                    json=json,
                    params=params,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                last_error = _Retryable(f"таймаут запроса: {exc}")
                logger.warning(
                    "Попытка %s/%s: %s %s — таймаут",
                    attempt,
                    self._attempts,
                    method,
                    path,
                )
                continue
            except httpx.HTTPError as exc:
                last_error = _Retryable(f"сетевая ошибка: {exc}")
                logger.warning(
                    "Попытка %s/%s: %s %s — %s",
                    attempt,
                    self._attempts,
                    method,
                    path,
                    exc,
                )
                continue

            if response.status_code >= 500:
                last_status = response.status_code
                last_request_id = response.headers.get("X-Request-ID")
                last_error = _Retryable(
                    _detail_of(response) or f"HTTP {response.status_code}"
                )
                logger.warning(
                    "Попытка %s/%s: %s %s — HTTP %s",
                    attempt,
                    self._attempts,
                    method,
                    path,
                    response.status_code,
                )
                continue

            return _handle_response(response)

        if last_error is None:  # защита от пустого списка попыток (attempts ≥ 1)
            last_error = _Retryable("неизвестная ошибка")
        raise CloudServerError(
            f"Сервис недоступен после {self._attempts} попыток",
            status=last_status,
            detail=str(last_error),
            request_id=last_request_id,
        )

    def _pause(self, index: int) -> float:
        """Пауза перед попыткой с jitter (`docs/api.md` §10)."""
        if not self._backoff:
            return 0.0
        base = self._backoff[min(index, len(self._backoff) - 1)]
        if not self._jitter:
            return base
        spread = base * self._jitter
        return max(0.0, base + random.uniform(-spread, spread))


def _handle_response(response: httpx.Response) -> Any:
    """Разобрать ответ: успех → тело, ошибка → исключение иерархии.

    Args:
        response: Ответ `httpx`, кроме 5xx (они уже отработаны retry).

    Returns:
        Разобранное JSON-тело или `None`, если тело пустое.

    Raises:
        CloudError: соответствующее HTTP-коду исключение.
    """
    request_id = response.headers.get("X-Request-ID")
    status = response.status_code

    if 200 <= status < 300:
        if status == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise CloudServerError(
                "Сервер вернул некорректный JSON",
                status=status,
                request_id=request_id,
            ) from exc

    detail, type_urn, issues = _parse_problem(response)
    kwargs: dict[str, Any] = {
        "status": status,
        "detail": detail,
        "request_id": request_id,
        "type_urn": type_urn,
    }
    summary = detail or f"HTTP {status}"

    if status in (401, 403):
        raise CloudAuthError(
            "Доступ запрещён" if status == 403 else "Требуется API-ключ", **kwargs
        )
    if status == 404:
        raise CloudNotFoundError("Ресурс не найден", **kwargs)
    if status == 409:
        raise CloudConflictError("Конфликт идемпотентности", **kwargs)
    if status == 413:
        raise CloudTooLargeError("Тело запроса слишком большое", **kwargs)
    if status == 422:
        raise CloudValidationError("Запрос не прошёл проверку", issues=issues, **kwargs)
    raise CloudError(f"Ошибка сервиса: {summary}", **kwargs)


def _parse_problem(
    response: httpx.Response,
) -> tuple[str, str | None, list[dict[str, str]]]:
    """Извлечь из problem+json `detail`, `type` и список `errors`.

    Ответ, который не является problem+json, не считается ошибкой клиента:
    возвращается пустой `detail`, а вызывающий код формирует «HTTP N».

    Args:
        response: Ответ с кодом ≥ 400.

    Returns:
        Кортеж `(detail, type_urn, issues)`; `issues` — до `MAX_ISSUES`
        записей `{path, message}`.
    """
    try:
        payload = response.json()
    except ValueError:
        text = (response.text or "").strip()
        return (text[:500], None, [])
    if not isinstance(payload, dict):
        return ("", None, [])

    detail = payload.get("detail")
    type_urn = payload.get("type") if isinstance(payload.get("type"), str) else None
    raw_issues = payload.get("errors")
    issues: list[dict[str, str]] = []
    if isinstance(raw_issues, list):
        for item in raw_issues[:MAX_ISSUES]:
            if isinstance(item, dict):
                issues.append(
                    {
                        "path": str(item.get("path", "")),
                        "message": str(item.get("message", "")),
                    }
                )
    return (str(detail) if detail else "", type_urn, issues)


def _detail_of(response: httpx.Response) -> str:
    """Короткая деталь ошибки 5xx для журнала и итогового сообщения."""
    detail, _type, _issues = _parse_problem(response)
    return detail


def _scenario_from_payload(
    payload: Any,
    *,
    with_url: bool = False,
) -> PublishedScenario:
    """Собрать `PublishedScenario` из JSON ответа.

    Args:
        payload: Элемент ответа (`201` или элемент `items`).
        with_url: Читать ли поле `url` из ответа (только для `201`).

    Returns:
        Метаданные сценария с пустыми строками вместо отсутствующих полей.

    Raises:
        CloudServerError: элемент ответа — не JSON-объект.
    """
    if not isinstance(payload, dict):
        raise CloudServerError("Сервер вернул некорректные метаданные сценария")
    url = payload.get("url") if with_url else None
    return PublishedScenario(
        id=str(payload.get("id", "")),
        name=str(payload.get("name", "")),
        sha256=str(payload.get("sha256", "")),
        created_at=str(payload.get("created_at", "")),
        updated_at=str(payload.get("updated_at", "")),
        url=str(url) if isinstance(url, str) else None,
        description=str(payload.get("description", "")),
    )


def _quote(value: str) -> str:
    """Экранировать идентификатор для пути URL.

    Идентификатор приходит от пользователя (CLI), поэтому `quote` с безопасным
    набором символов не даёт «склеить» лишний сегмент пути.
    """
    return quote(value, safe="")
