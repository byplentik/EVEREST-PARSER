"""Публичный интерфейс site-specific парсеров."""

from everest_parser.parsers.fedresurs import FedresursParseResult
from everest_parser.parsers.fedresurs import FedresursParser
from everest_parser.parsers.kad import KadArbitrParser
from everest_parser.parsers.kad import KadParseResult
from everest_parser.parsers.kad import KadSearchMatch

__all__ = [
    "FedresursParseResult",
    "FedresursParser",
    "KadArbitrParser",
    "KadParseResult",
    "KadSearchMatch",
]
