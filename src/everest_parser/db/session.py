"""Создание engine и фабрики SQLAlchemy-сессий."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from everest_parser.config import Settings
from everest_parser.config import get_settings


def build_engine(settings: Settings | None = None) -> Engine:
    """Создать SQLAlchemy-engine по текущим настройкам приложения."""

    active_settings = settings or get_settings()
    return create_engine(
        active_settings.database_url,
        pool_pre_ping=True,
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Вернуть кэшированный engine приложения."""

    return build_engine()


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Вернуть кэшированную фабрику SQLAlchemy-сессий."""

    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def session_scope() -> Iterator[Session]:
    """Открыть транзакционную SQLAlchemy-сессию с автокоммитом и rollback."""

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
