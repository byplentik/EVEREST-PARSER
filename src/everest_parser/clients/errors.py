"""Исключения транспортного слоя и lifecycle сессии."""

from __future__ import annotations


class TransportError(Exception):
    """Базовая ошибка transport layer."""


class TransportConfigError(TransportError):
    """Ошибка конфигурации HTTP-транспорта или session lifecycle."""


class TransportRequestError(TransportError):
    """Ошибка выполнения HTTP-запроса."""


class BlockedResponseError(TransportError):
    """Сайт вернул ответ, похожий на блокировку или антибот-страницу."""
