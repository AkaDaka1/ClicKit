"""Liveness-проверка для Docker HEALTHCHECK (M7 T3.2).

Отдельный модуль вместо `python -c` нужен по двум причинам: HEALTHCHECK не
должен засорять журнал контейнера traceback'ом при старте, а сама проверка
должна быть тестируемой. Проверяется только `/healthz` (без БД): недоступность
PostgreSQL — это не повод перезапускать контейнер через Docker.

Запуск: `python -m service.app.healthcheck` (код выхода 0 — сервис жив,
1 — проверка не прошла). URL можно переопределить переменной
`CLICKIT_HEALTHCHECK_URL`, если порт сервиса изменён.
"""

from __future__ import annotations

import os
import sys
import urllib.request

#: Адрес liveness-проверки по умолчанию (порт uvicorn в образе).
DEFAULT_HEALTHCHECK_URL = "http://127.0.0.1:8000/healthz"
#: Таймаут HTTP-запроса, секунды: HEALTHCHECK не должен висеть.
DEFAULT_TIMEOUT_SECONDS = 2.0


def check(url: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> int:
    """Проверить, что сервис отвечает на `url` кодом 200.

    Args:
        url: Полный URL liveness-эндпоинта.
        timeout: Таймаут запроса в секундах.

    Returns:
        Код выхода: 0 — ответ 200, 1 — ошибка соединения или другой статус.
    """
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 0 if response.status == 200 else 1
    except OSError as exc:
        # URLError/HTTPError — наследники OSError; печатаем короткую причину,
        # без traceback: журнал healthcheck'а читают люди и Docker.
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        return 1


def main() -> int:
    """Точка входа HEALTHCHECK: URL из env или значение по умолчанию."""
    url = os.environ.get("CLICKIT_HEALTHCHECK_URL", DEFAULT_HEALTHCHECK_URL)
    return check(url)


if __name__ == "__main__":
    raise SystemExit(main())
