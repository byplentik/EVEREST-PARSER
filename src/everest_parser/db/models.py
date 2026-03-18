"""ORM-модели для batch-обработки и результатов парсинга."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import func
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship

from everest_parser.db.base import Base
from everest_parser.db.enums import JobStatus
from everest_parser.db.enums import ParserType
from everest_parser.db.enums import TaskStatus


def enum_values(enum_cls: type[object]) -> list[str]:
    """Вернуть список строковых значений enum для SQLAlchemy."""

    return [item.value for item in enum_cls]

PARSER_TYPE_ENUM = SqlEnum(
    ParserType,
    name="parser_type_enum",
    native_enum=False,
    values_callable=enum_values,
)
JOB_STATUS_ENUM = SqlEnum(
    JobStatus,
    name="job_status_enum",
    native_enum=False,
    values_callable=enum_values,
)
TASK_STATUS_ENUM = SqlEnum(
    TaskStatus,
    name="task_status_enum",
    native_enum=False,
    values_callable=enum_values,
)


class ParseJob(Base):
    """Batch-job с набором задач для одного типа парсера."""

    __tablename__ = "parse_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parser_type: Mapped[ParserType] = mapped_column(PARSER_TYPE_ENUM, nullable=False)
    source_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        JOB_STATUS_ENUM,
        nullable=False,
        default=JobStatus.PENDING,
        server_default=JobStatus.PENDING.value,
    )
    total_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    processed_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    success_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    failed_items: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list["ParseTask"]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("total_items >= 0", name="total_items_non_negative"),
        CheckConstraint("processed_items >= 0", name="processed_items_non_negative"),
        CheckConstraint("success_items >= 0", name="success_items_non_negative"),
        CheckConstraint("failed_items >= 0", name="failed_items_non_negative"),
    )


class ParseTask(Base):
    """Отдельная задача внутри batch-job."""

    __tablename__ = "parse_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("parse_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        TASK_STATUS_ENUM,
        nullable=False,
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    job: Mapped[ParseJob] = relationship(back_populates="tasks")
    fedresurs_result: Mapped["FedresursResult | None"] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    kad_result: Mapped["KadResult | None"] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )

    __table_args__ = (
        UniqueConstraint("job_id", "normalized_value", name="uq_parse_tasks_job_normalized_value"),
        CheckConstraint("attempts >= 0", name="attempts_non_negative"),
    )


class FedresursResult(Base):
    """Результат выполнения задачи по `fedresurs.ru`."""

    __tablename__ = "fedresurs_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("parse_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    inn: Mapped[str] = mapped_column(String(12), nullable=False)
    case_number: Mapped[str] = mapped_column(String(64), nullable=False)
    last_publication_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped[ParseTask] = relationship(back_populates="fedresurs_result")


class KadResult(Base):
    """Результат выполнения задачи по `kad.arbitr.ru`."""

    __tablename__ = "kad_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("parse_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    case_number: Mapped[str] = mapped_column(String(64), nullable=False)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_name: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    task: Mapped[ParseTask] = relationship(back_populates="kad_result")
