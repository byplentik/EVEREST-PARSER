"""Минимальный CLI для каркаса проекта на первом этапе."""

from __future__ import annotations

import argparse
import json

from everest_parser import __version__
from everest_parser.config import get_settings


def build_cli() -> argparse.ArgumentParser:
    """Создать CLI-парсер приложения."""

    parser = argparse.ArgumentParser(prog="everest-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    about_parser = subparsers.add_parser(
        "about",
        help="Показать статус каркаса проекта и сводку конфигурации.",
    )
    about_parser.set_defaults(command="about")

    return parser


def main() -> None:
    """Точка входа для CLI первого этапа."""

    parser = build_cli()
    args = parser.parse_args()

    if args.command == "about":
        settings = get_settings()
        payload = {
            "name": settings.app_name,
            "version": __version__,
            "stage": "stage-1-scaffold",
            "status": "ready",
            "message": "Каркас проекта инициализирован. Бизнес-логика пока не реализована.",
            "settings": settings.public_summary(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
