"""Перечисления доменных типов для слоя базы данных."""

from __future__ import annotations

from enum import Enum


class ParserType(str, Enum):
    """Типы поддерживаемых парсеров."""

    FEDRESURS = "fedresurs"
    KAD = "kad"


class JobStatus(str, Enum):
    """Статусы batch-job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"


class TaskStatus(str, Enum):
    """Статусы отдельных задач в рамках job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    BLOCKED = "blocked"
    ERROR = "error"
