"""CLI приложения."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from everest_parser import __version__
from everest_parser.config import get_settings
from everest_parser.db import create_database_schema
from everest_parser.db import get_declared_table_names
from everest_parser.db import ParserType
from everest_parser.services import JobImportError
from everest_parser.services import create_job_from_xlsx


def build_cli() -> argparse.ArgumentParser:
    """Создать CLI-парсер приложения."""

    parser = argparse.ArgumentParser(prog="everest-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    about_parser = subparsers.add_parser(
        "about",
        help="Показать сводку конфигурации приложения.",
    )
    about_parser.set_defaults(command="about")

    db_parser = subparsers.add_parser(
        "db",
        help="Команды для работы со схемой базы данных.",
    )
    db_subparsers = db_parser.add_subparsers(dest="db_command", required=True)

    db_init_parser = db_subparsers.add_parser(
        "init",
        help="Создать таблицы приложения в целевой базе данных.",
    )
    db_init_parser.set_defaults(command="db", db_command="init")

    job_parser = subparsers.add_parser(
        "job",
        help="Команды для загрузки входного файла в очередь задач.",
    )
    job_subparsers = job_parser.add_subparsers(dest="job_command", required=True)

    job_create_parser = job_subparsers.add_parser(
        "create",
        help="Создать batch-job и задачи из входного .xlsx файла.",
    )
    job_create_parser.add_argument(
        "--parser",
        dest="parser_type",
        required=True,
        choices=[parser_type.value for parser_type in ParserType],
        help="Тип парсера, для которого подготавливаются задачи.",
    )
    job_create_parser.add_argument(
        "--input",
        dest="input_path",
        required=True,
        help="Путь к входному .xlsx файлу.",
    )
    job_create_parser.set_defaults(command="job", job_command="create")

    return parser


def print_payload(payload: dict[str, object], *, stream: object | None = None) -> None:
    """Напечатать структурированный JSON-ответ CLI."""

    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def handle_about() -> None:
    """Вывести сводку конфигурации приложения."""

    settings = get_settings()
    payload = {
        "name": settings.app_name,
        "version": __version__,
        "status": "ready",
        "declared_tables": get_declared_table_names(),
        "settings": settings.public_summary(),
    }
    print_payload(payload)


def handle_db_init() -> None:
    """Создать схему базы данных и вывести результат операции."""

    settings = get_settings()

    try:
        created_tables = create_database_schema()
    except SQLAlchemyError as error:
        payload = {
            "status": "error",
            "database_url": settings.masked_database_url(),
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print_payload(payload, stream=sys.stderr)
        raise SystemExit(1) from error

    payload = {
        "status": "ready",
        "database_url": settings.masked_database_url(),
        "tables": created_tables,
    }
    print_payload(payload)


def handle_job_create(parser_type: str, input_path: str) -> None:
    """Импортировать входной `.xlsx` в job и очередь задач."""

    try:
        summary = create_job_from_xlsx(
            parser_type=ParserType(parser_type),
            input_path=Path(input_path),
        )
    except JobImportError as error:
        payload = {
            "status": "error",
            "parser_type": parser_type,
            "input_path": input_path,
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print_payload(payload, stream=sys.stderr)
        raise SystemExit(1) from error
    except SQLAlchemyError as error:
        payload = {
            "status": "error",
            "parser_type": parser_type,
            "input_path": input_path,
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print_payload(payload, stream=sys.stderr)
        raise SystemExit(1) from error

    payload = {
        "status": "ready",
        **summary.as_payload(),
    }
    print_payload(payload)


def main() -> None:
    """Точка входа для CLI приложения."""

    parser = build_cli()
    args = parser.parse_args()

    if args.command == "about":
        handle_about()
        return

    if args.command == "db" and args.db_command == "init":
        handle_db_init()
        return

    if args.command == "job" and args.job_command == "create":
        handle_job_create(parser_type=args.parser_type, input_path=args.input_path)
        return

    parser.error("Неизвестная команда CLI.")
