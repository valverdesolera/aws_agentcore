"""
Domain entities for stock price data.
See docs/CleanArchitecture.md — Phase 2 for the architectural rationale.
Zero external dependencies — pure Python dataclasses only.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StockPrice:
    symbol: str
    current_price: Optional[float]
    previous_close: Optional[float]
    open: Optional[float]
    day_high: Optional[float]
    day_low: Optional[float]
    volume: Optional[int]
    currency: str
    market_state: str


@dataclass(frozen=True)
class HistoricalRecord:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class HistoricalPrices:
    symbol: str
    period: str
    interval: str
    records: list[HistoricalRecord]
