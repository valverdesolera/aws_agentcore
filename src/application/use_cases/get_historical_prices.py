"""
Use-case: retrieve historical OHLCV stock prices for a given symbol.
See docs/CleanArchitecture.md — Phase 2 for the architectural rationale.
Depends only on Domain ports and entities — no infrastructure imports.
"""

from typing import Optional

from src.domain.entities.stock_price import HistoricalPrices
from src.domain.ports.stock_data_port import IStockDataProvider


class GetHistoricalStockPricesUseCase:
    def __init__(self, provider: IStockDataProvider) -> None:
        self._provider = provider

    def execute(
        self,
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> HistoricalPrices:
        """Fetch historical prices for *symbol*.

        Args:
            symbol:     Ticker symbol (case-insensitive).
            period:     yfinance period string (e.g. '3mo', '1y'). Ignored when
                        *start_date* is provided.
            interval:   Data frequency (e.g. '1d', '1wk').
            start_date: ISO-8601 start date (YYYY-MM-DD). Overrides *period*.
            end_date:   ISO-8601 end date (YYYY-MM-DD). Defaults to today.

        Raises:
            ValueError: if *symbol* is blank.
            Any exception propagated from IStockDataProvider on API failure.
        """
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        return self._provider.get_historical_prices(
            symbol.upper().strip(),
            period=period,
            interval=interval,
            start_date=start_date,
            end_date=end_date,
        )
