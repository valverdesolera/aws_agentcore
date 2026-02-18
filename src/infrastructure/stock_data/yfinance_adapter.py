"""
Infrastructure adapter: yfinance → IStockDataProvider.
See docs/CleanArchitecture.md — Phase 2 for the architectural rationale.
All yfinance-specific details (ticker.info, fast_info, history()) are confined here;
the rest of the codebase depends only on IStockDataProvider.
"""

from typing import Optional

import yfinance as yf

from src.domain.entities.stock_price import HistoricalPrices, HistoricalRecord, StockPrice
from src.domain.ports.stock_data_port import IStockDataProvider


class YFinanceStockDataProvider(IStockDataProvider):
    """Fetches stock market data from Yahoo Finance via the yfinance library."""

    def get_realtime_price(self, symbol: str) -> StockPrice:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        fast_info = ticker.fast_info

        current_price = getattr(fast_info, "last_price", None) or info.get("currentPrice")
        if current_price is None:
            raise ValueError(f"No price data available for symbol: {symbol!r}")

        return StockPrice(
            symbol=symbol,
            current_price=round(float(current_price), 4),
            previous_close=(
                getattr(fast_info, "previous_close", None) or info.get("previousClose")
            ),
            open=info.get("open"),
            day_high=info.get("dayHigh"),
            day_low=info.get("dayLow"),
            volume=info.get("volume"),
            currency=info.get("currency", "USD"),
            market_state=info.get("marketState", "UNKNOWN"),
        )

    def get_historical_prices(
        self,
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> HistoricalPrices:
        ticker = yf.Ticker(symbol)
        history = (
            ticker.history(start=start_date, end=end_date, interval=interval)
            if start_date
            else ticker.history(period=period, interval=interval)
        )

        if history.empty:
            raise ValueError(f"No historical data available for symbol: {symbol!r}")

        records = [
            HistoricalRecord(
                date=date.strftime("%Y-%m-%d"),
                open=round(float(row["Open"]), 4),
                high=round(float(row["High"]), 4),
                low=round(float(row["Low"]), 4),
                close=round(float(row["Close"]), 4),
                volume=int(row["Volume"]),
            )
            for date, row in history.iterrows()
        ]

        period_label = (
            period if not start_date else f"{start_date} to {end_date or 'today'}"
        )
        return HistoricalPrices(
            symbol=symbol,
            period=period_label,
            interval=interval,
            records=records,
        )
