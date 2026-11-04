"""Тесты liveness-проверки контейнера (M7 T3.2)."""

from __future__ import annotations

import pytest

from service.app import healthcheck


class _Response:
    """Минимальный ответ urllib для проверки статуса."""

    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def test_check_returns_zero_for_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Успешный /healthz даёт код выхода 0 и передаёт url/timeout как есть."""
    calls: list[tuple[str, float]] = []

    def fake_urlopen(url: str, timeout: float) -> _Response:
        calls.append((url, timeout))
        return _Response(200)

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", fake_urlopen)

    assert healthcheck.check("http://example/healthz", timeout=1) == 0
    assert calls == [("http://example/healthz", 1)]


def test_check_returns_one_for_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Любой статус кроме 200 — провал проверки."""
    monkeypatch.setattr(
        healthcheck.urllib.request,
        "urlopen",
        lambda url, timeout: _Response(503),
    )

    assert healthcheck.check("http://example/healthz") == 1


def test_main_uses_env_url(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """URL берётся из CLICKIT_HEALTHCHECK_URL; ошибка печатается без traceback."""
    url = "http://example:9000/healthz"
    monkeypatch.setenv("CLICKIT_HEALTHCHECK_URL", url)
    seen: list[str] = []

    def failing_urlopen(url: str, timeout: float) -> _Response:
        seen.append(url)
        raise OSError("connection refused")

    monkeypatch.setattr(healthcheck.urllib.request, "urlopen", failing_urlopen)

    assert healthcheck.main() == 1
    assert seen == [url]
    captured = capsys.readouterr()
    assert "connection refused" in captured.err
    assert "Traceback" not in captured.err
