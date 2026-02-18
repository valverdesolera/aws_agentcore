"""
Port (interface) for stock data providers.
See docs/CleanArchitecture.md — Phase 2 for the architectural rationale.
Infrastructure adapters (e.g. YFinanceStockDataProvider) must implement this interface.
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.entities.stock_price import HistoricalPrices, StockPrice


class IStockDataProvider(ABC):
    @abstractmethod
    def get_realtime_price(self, symbol: str) -> StockPrice: ...

    @abstractmethod
    def get_historical_prices(
        self,
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> HistoricalPrices: ...
