"""
Use-case: retrieve the current real-time stock price for a given symbol.
See docs/CleanArchitecture.md — Phase 2 for the architectural rationale.
Depends only on Domain ports and entities — no infrastructure imports.
"""

from src.domain.entities.stock_price import StockPrice
from src.domain.ports.stock_data_port import IStockDataProvider


class GetRealtimeStockPriceUseCase:
    def __init__(self, provider: IStockDataProvider) -> None:
        self._provider = provider

    def execute(self, symbol: str) -> StockPrice:
        """Fetch the current price for *symbol* (uppercased).

        Raises:
            ValueError: if *symbol* is blank.
            Any exception propagated from the IStockDataProvider on API failure.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        return self._provider.get_realtime_price(symbol.upper().strip())
