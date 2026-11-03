"""Тестовые двойники сервисного слоя.

Подделки позволяют проверять `/readyz` без запущенной PostgreSQL: сам сервис
в тестах не должен зависеть от локальной инфраструктуры.
"""

from __future__ import annotations


class FakeDatabase:
    """Подделка `DatabaseProtocol`: заданный результат `check` и учёт `dispose`."""

    def __init__(self, ready: bool = True) -> None:
        """Создать подделку с фиксированным ответом проверки.

        Args:
            ready: Что возвращать из `check` (`True` — БД доступна).
        """
        self.ready = ready
        self.checks = 0
        self.disposed = False

    def check(self) -> bool:
        """Вернуть заранее заданный результат и посчитать вызовы."""
        self.checks += 1
        return self.ready

    def dispose(self) -> None:
        """Запомнить, что сервис освободил соединения при остановке."""
        self.disposed = True
