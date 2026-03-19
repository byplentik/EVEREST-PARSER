"""Консольные helper-функции для информативных логов."""

from __future__ import annotations

from datetime import datetime
import sys


def print_project_log(scope: str, message: str) -> None:
    """Вывести лог в простом и стабильном формате."""

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{scope}] {message}", file=sys.stderr, flush=True)
