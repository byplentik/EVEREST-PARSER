"""Инициализация и инспекция схемы базы данных."""

from __future__ import annotations

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from everest_parser.db.base import Base
from everest_parser.db.session import get_engine

# Импорт моделей нужен для регистрации таблиц в metadata.
from everest_parser.db import models as _models  # noqa: F401


def get_declared_table_names() -> list[str]:
    """Вернуть список таблиц, объявленных в ORM-метаданных."""

    return sorted(Base.metadata.tables.keys())


def create_database_schema(engine: Engine | None = None) -> list[str]:
    """Создать таблицы, которых еще нет в базе данных."""

    active_engine = engine or get_engine()
    Base.metadata.create_all(bind=active_engine)
    return sorted(inspect(active_engine).get_table_names())
