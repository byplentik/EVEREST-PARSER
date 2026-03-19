"""CLI приложения."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from everest_parser.browser.kad_bootstrap import KadBootstrapError
from everest_parser.clients.errors import TransportConfigError
from everest_parser.clients.errors import TransportError
from everest_parser.db import ParserType
from everest_parser.db import create_database_schema
from everest_parser.services import FedresursJobRunnerError
from everest_parser.services import JobImportError
from everest_parser.services import KadJobRunnerError
from everest_parser.services import create_job_from_xlsx
from everest_parser.services import run_fedresurs_job
from everest_parser.services import run_kad_job


SUPPORTED_PARSERS = (ParserType.KAD, ParserType.FEDRESURS)


def build_cli() -> argparse.ArgumentParser:
    """Создать CLI для инициализации БД и запуска парсеров."""

    parser = argparse.ArgumentParser(prog="everest-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

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

    parse_parser = subparsers.add_parser(
        "parse",
        help="Импортировать `.xlsx` и сразу запустить парсер.",
    )
    parse_parser.add_argument(
        "--parser",
        dest="parser_type",
        required=True,
        choices=[parser_type.value for parser_type in SUPPORTED_PARSERS],
        help="Тип парсера для обработки входного файла.",
    )
    parse_parser.add_argument(
        "--input",
        dest="input_path",
        required=True,
        help="Путь к входному `.xlsx` файлу.",
    )
    parse_parser.set_defaults(command="parse")

    return parser


def print_payload(payload: dict[str, object], *, stream: object | None = None) -> None:
    """Напечатать структурированный JSON-ответ CLI."""

    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream or sys.stdout)


def handle_db_init() -> None:
    """Создать схему базы данных и вывести результат операции."""

    try:
        created_tables = create_database_schema()
    except SQLAlchemyError as error:
        payload = {
            "status": "error",
            "error_type": type(error).__name__,
            "error": str(error),
        }
        print_payload(payload, stream=sys.stderr)
        raise SystemExit(1) from error

    payload = {
        "status": "ready",
        "tables": created_tables,
    }
    print_payload(payload)


def handle_parse(parser_type: str, input_path: str) -> None:
    """Импортировать `.xlsx` и выполнить выбранный парсер."""

    try:
        parser_enum = ParserType(parser_type)
        import_summary = create_job_from_xlsx(
            parser_type=parser_enum,
            input_path=Path(input_path),
        )

        if parser_enum is ParserType.KAD:
            run_summary = run_kad_job(job_id=import_summary.job_id)
        elif parser_enum is ParserType.FEDRESURS:
            run_summary = run_fedresurs_job(job_id=import_summary.job_id)
        else:
            raise ValueError(
                f"Реализация runner пока недоступна для parser={parser_enum.value}."
            )
    except (
        FedresursJobRunnerError,
        JobImportError,
        KadJobRunnerError,
        SQLAlchemyError,
        TransportError,
        KadBootstrapError,
        TransportConfigError,
        ValueError,
    ) as error:
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
        **import_summary.as_payload(),
        **run_summary.as_payload(),
    }
    print_payload(payload)


def main() -> None:
    """Точка входа для CLI приложения."""

    parser = build_cli()
    args = parser.parse_args()

    if args.command == "db" and args.db_command == "init":
        handle_db_init()
        return

    if args.command == "parse":
        handle_parse(parser_type=args.parser_type, input_path=args.input_path)
        return

    parser.error("Неизвестная команда CLI.")
