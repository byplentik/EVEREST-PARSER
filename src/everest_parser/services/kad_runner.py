"""Запуск batch-задач для `kad.arbitr.ru`."""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone

from sqlalchemy import Select
from sqlalchemy import func
from sqlalchemy import select

from everest_parser.browser.kad_bootstrap import KadBootstrapError
from everest_parser.clients.errors import BlockedResponseError
from everest_parser.clients.errors import TransportError
from everest_parser.clients.transports import KadTransport
from everest_parser.db import JobStatus
from everest_parser.db import KadResult
from everest_parser.db import ParseJob
from everest_parser.db import ParseTask
from everest_parser.db import ParserType
from everest_parser.db import TaskStatus
from everest_parser.db import session_scope
from everest_parser.parsers.kad import KadArbitrParser
from everest_parser.parsers.kad import KadParseResult
from everest_parser.utils import print_project_log


FAILED_TASK_STATUSES = (TaskStatus.NOT_FOUND, TaskStatus.BLOCKED, TaskStatus.ERROR)


class KadJobRunnerError(Exception):
    """Ошибка выполнения batch-job для `kad.arbitr.ru`."""


@dataclass(slots=True)
class KadJobRunSummary:
    """Сводка по результату одного запуска `kad`-job."""

    job_id: int
    job_status: str
    tasks_selected: int
    processed_now: int
    success_now: int
    not_found_now: int
    blocked_now: int
    error_now: int
    processed_total: int
    success_total: int
    failed_total: int
    remaining_pending: int

    def as_payload(self) -> dict[str, object]:
        """Вернуть JSON-совместимую сводку для CLI."""

        return asdict(self)


def run_kad_job(job_id: int, limit: int | None = None) -> KadJobRunSummary:
    """Выполнить `pending`-задачи `kad` для одного job."""

    if limit is not None and limit <= 0:
        raise KadJobRunnerError("Параметр `limit` должен быть больше нуля.")

    selected_task_ids = prepare_kad_job(job_id=job_id, limit=limit)
    log_kad_event(
        f"Старт job {job_id}. Выбрано pending-задач: {len(selected_task_ids)}."
    )

    transport = KadTransport()
    parser = KadArbitrParser(transport=transport)
    success_now = 0
    not_found_now = 0
    blocked_now = 0
    error_now = 0

    try:
        for task_id in selected_task_ids:
            task = mark_task_running(task_id)
            log_kad_task_event(job_id, task.id, task.normalized_value, "Старт обработки.")

            try:
                parse_result = parser.parse_case(task.normalized_value)
            except (BlockedResponseError, KadBootstrapError) as error:
                finish_task_with_error(task_id, TaskStatus.BLOCKED, str(error))
                log_kad_task_event(
                    job_id,
                    task.id,
                    task.normalized_value,
                    f"BLOCKED: {error}",
                )
                blocked_now += 1
                continue
            except TransportError as error:
                finish_task_with_error(task_id, TaskStatus.ERROR, str(error))
                log_kad_task_event(
                    job_id,
                    task.id,
                    task.normalized_value,
                    f"ERROR: {error}",
                )
                error_now += 1
                continue
            except Exception as error:
                finish_task_with_error(task_id, TaskStatus.ERROR, str(error))
                log_kad_task_event(
                    job_id,
                    task.id,
                    task.normalized_value,
                    f"ERROR: {error}",
                )
                error_now += 1
                continue

            if parse_result is None:
                finish_task_with_error(
                    task_id,
                    TaskStatus.NOT_FOUND,
                    "Дело не найдено в SearchInstances.",
                )
                log_kad_task_event(
                    job_id,
                    task.id,
                    task.normalized_value,
                    "NOT_FOUND: дело не найдено.",
                )
                not_found_now += 1
                continue

            finish_task_with_success(task_id, parse_result)
            log_kad_task_event(
                job_id,
                task.id,
                parse_result.case_number,
                f"SUCCESS: дата={format_document_date(parse_result.document_date)}, документ={parse_result.document_name}",
            )
            success_now += 1
    except Exception as error:
        mark_job_failed(job_id, str(error))
        raise
    finally:
        parser.close()

    summary = finalize_kad_job(
        job_id=job_id,
        tasks_selected=len(selected_task_ids),
        success_now=success_now,
        not_found_now=not_found_now,
        blocked_now=blocked_now,
        error_now=error_now,
    )
    log_kad_event(
        f"Завершение job {job_id}. status={summary.job_status}, "
        f"success={summary.success_now}, not_found={summary.not_found_now}, "
        f"blocked={summary.blocked_now}, error={summary.error_now}."
    )
    return summary


def prepare_kad_job(job_id: int, limit: int | None) -> list[int]:
    """Проверить job, перевести его в `running` и вернуть список `pending` task id."""

    with session_scope() as session:
        job = session.get(ParseJob, job_id)
        if job is None:
            raise KadJobRunnerError(f"Job не найден: {job_id}")

        if job.parser_type is not ParserType.KAD:
            raise KadJobRunnerError(
                f"Job {job_id} относится к parser_type={job.parser_type.value}, а не к kad."
            )

        if job.started_at is None:
            job.started_at = now_utc()

        job.status = JobStatus.RUNNING

        pending_query = build_pending_task_query(job_id)
        if limit is not None:
            pending_query = pending_query.limit(limit)

        return list(session.scalars(pending_query))


def build_pending_task_query(job_id: int) -> Select[int]:
    """Построить запрос на выбор `pending`-задач job."""

    return (
        select(ParseTask.id)
        .where(ParseTask.job_id == job_id, ParseTask.status == TaskStatus.PENDING)
        .order_by(ParseTask.id.asc())
    )


def mark_task_running(task_id: int) -> ParseTask:
    """Зафиксировать начало обработки одной задачи и вернуть ее слепок."""

    with session_scope() as session:
        task = session.get(ParseTask, task_id)
        if task is None:
            raise KadJobRunnerError(f"Task не найдена: {task_id}")

        task.status = TaskStatus.RUNNING
        task.attempts += 1
        task.started_at = now_utc()
        task.last_error = None
        session.flush()
        session.expunge(task)
        return task


def finish_task_with_success(task_id: int, result: KadParseResult) -> None:
    """Сохранить успешный результат обработки задачи `kad`."""

    with session_scope() as session:
        task = session.get(ParseTask, task_id)
        if task is None:
            raise KadJobRunnerError(f"Task не найдена: {task_id}")

        task.status = TaskStatus.SUCCESS
        task.finished_at = now_utc()
        task.last_error = None

        current_task_result = task.kad_result
        existing_results = (
            session.execute(
                select(KadResult)
                .where(KadResult.case_number == result.case_number)
                .order_by(KadResult.id.asc())
            )
            .scalars()
            .all()
        )

        if current_task_result is not None and current_task_result.case_number == result.case_number:
            canonical_result = current_task_result
        elif existing_results:
            canonical_result = existing_results[0]
        else:
            canonical_result = KadResult()
            session.add(canonical_result)

        if current_task_result is not None and current_task_result is not canonical_result:
            session.delete(current_task_result)
            session.flush()

        if canonical_result.task is not task:
            task.kad_result = canonical_result

        canonical_result.case_number = result.case_number
        canonical_result.document_date = result.document_date
        canonical_result.document_name = result.document_name
        canonical_result.raw_payload = result.raw_payload

        duplicate_results = [
            existing_result
            for existing_result in existing_results
            if existing_result is not canonical_result
        ]
        for duplicate_result in duplicate_results:
            session.delete(duplicate_result)


def finish_task_with_error(task_id: int, status: TaskStatus, error_message: str) -> None:
    """Зафиксировать итог ошибки для одной задачи."""

    with session_scope() as session:
        task = session.get(ParseTask, task_id)
        if task is None:
            raise KadJobRunnerError(f"Task не найдена: {task_id}")

        task.status = status
        task.finished_at = now_utc()
        task.last_error = error_message


def finalize_kad_job(
    job_id: int,
    *,
    tasks_selected: int,
    success_now: int,
    not_found_now: int,
    blocked_now: int,
    error_now: int,
) -> KadJobRunSummary:
    """Пересчитать итоговые счетчики job и вернуть сводку запуска."""

    with session_scope() as session:
        job = session.get(ParseJob, job_id)
        if job is None:
            raise KadJobRunnerError(f"Job не найден: {job_id}")

        stats = load_job_task_stats(session, job_id)
        remaining_pending = stats.get(TaskStatus.PENDING, 0)
        running_count = stats.get(TaskStatus.RUNNING, 0)
        success_total = stats.get(TaskStatus.SUCCESS, 0)
        failed_total = sum(stats.get(status, 0) for status in FAILED_TASK_STATUSES)
        processed_total = success_total + failed_total

        job.processed_items = processed_total
        job.success_items = success_total
        job.failed_items = failed_total

        if remaining_pending or running_count:
            job.status = JobStatus.RUNNING
            job.finished_at = None
        elif failed_total > 0:
            job.status = JobStatus.COMPLETED_WITH_ERRORS
            job.finished_at = now_utc()
        else:
            job.status = JobStatus.COMPLETED
            job.finished_at = now_utc()

        return KadJobRunSummary(
            job_id=job.id,
            job_status=job.status.value,
            tasks_selected=tasks_selected,
            processed_now=success_now + not_found_now + blocked_now + error_now,
            success_now=success_now,
            not_found_now=not_found_now,
            blocked_now=blocked_now,
            error_now=error_now,
            processed_total=processed_total,
            success_total=success_total,
            failed_total=failed_total,
            remaining_pending=remaining_pending,
        )


def mark_job_failed(job_id: int, error_message: str) -> None:
    """Перевести job в `failed`, если произошел внеплановый сбой на уровне runner."""

    with session_scope() as session:
        job = session.get(ParseJob, job_id)
        if job is None:
            return

        job.status = JobStatus.FAILED
        job.finished_at = now_utc()

        failed_task = (
            session.execute(
                select(ParseTask)
                .where(ParseTask.job_id == job_id, ParseTask.status == TaskStatus.RUNNING)
                .order_by(ParseTask.id.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )
        if failed_task is not None:
            failed_task.status = TaskStatus.ERROR
            failed_task.finished_at = now_utc()
            failed_task.last_error = error_message


def load_job_task_stats(session, job_id: int) -> dict[TaskStatus, int]:
    """Загрузить агрегированные счетчики задач job по статусам."""

    rows = session.execute(
        select(ParseTask.status, func.count(ParseTask.id))
        .where(ParseTask.job_id == job_id)
        .group_by(ParseTask.status)
    ).all()
    return {status: count for status, count in rows}


def now_utc() -> datetime:
    """Вернуть текущее время в UTC."""

    return datetime.now(timezone.utc)


def log_kad_event(message: str) -> None:
    """Вывести служебный лог runner в поток ошибок."""

    print_project_log("kad", message)


def log_kad_task_event(job_id: int, task_id: int, case_number: str, message: str) -> None:
    """Вывести лог по конкретной задаче и номеру дела."""

    log_kad_event(f"job={job_id} task={task_id} case_number={case_number} {message}")


def format_document_date(value) -> str:
    """Преобразовать дату документа в строку для лога."""

    if value is None:
        return "-"
    return value.isoformat()
