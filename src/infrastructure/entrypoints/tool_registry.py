"""
LangChain @tool wrappers — Infrastructure entrypoint / Composition Root.
See docs/CleanArchitecture.md — Phase 2 & 3 for the architectural rationale.

The @tool decorator is a LangChain/LangGraph infrastructure concern and must
NOT appear in the application or domain layers.  This module binds each
application use-case to a tool callable that can be passed to build_agent_graph().
"""

import dataclasses
from typing import Optional

from langchain_core.tools import tool

from src.application.use_cases.get_historical_prices import GetHistoricalStockPricesUseCase
from src.application.use_cases.get_realtime_price import GetRealtimeStockPriceUseCase
from src.application.use_cases.retrieve_documents import RetrieveFinancialDocumentsUseCase
from src.domain.ports.stock_data_port import IStockDataProvider
from src.domain.ports.vector_store_port import IVectorStore


def create_tools(
    stock_provider: IStockDataProvider,
    vector_store: IVectorStore,
) -> list:
    """Build and return the three LangChain tools with injected use-case dependencies.

    Args:
        stock_provider: IStockDataProvider implementation (e.g. YFinanceStockDataProvider).
        vector_store:   IVectorStore implementation, already loaded (e.g. FAISSVectorStore).

    Returns:
        List of three @tool callables ready to be passed to build_agent_graph().
    """
    realtime_uc = GetRealtimeStockPriceUseCase(stock_provider)
    historical_uc = GetHistoricalStockPricesUseCase(stock_provider)
    retrieval_uc = RetrieveFinancialDocumentsUseCase(vector_store)

    @tool
    def retrieve_realtime_stock_price(symbol: str) -> dict:
        """Retrieve the current real-time stock price for a given ticker symbol.

        Args:
            symbol: Stock ticker symbol (e.g. 'AMZN', 'AAPL', 'GOOGL').

        Returns:
            Dictionary with keys: symbol, current_price, previous_close, open,
            day_high, day_low, volume, currency, market_state.
            Returns {'error': '<message>'} if the symbol is invalid or data
            is unavailable.
        """
        try:
            result = realtime_uc.execute(symbol)
            return dataclasses.asdict(result)
        except Exception as exc:
            return {"error": str(exc)}

    @tool
    def retrieve_historical_stock_price(
        symbol: str,
        period: str = "3mo",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> dict:
        """Retrieve historical OHLCV stock prices for a given ticker symbol.

        Args:
            symbol:     Stock ticker symbol (e.g. 'AMZN').
            period:     Time period — valid values: 1d, 5d, 1mo, 3mo, 6mo, 1y,
                        2y, 5y, 10y, ytd, max. Ignored when start_date is set.
            interval:   Data frequency — valid values: 1m, 2m, 5m, 15m, 30m,
                        60m, 90m, 1h, 1d, 5d, 1wk, 1mo, 3mo.
            start_date: Start date in YYYY-MM-DD format (optional).
            end_date:   End date in YYYY-MM-DD format (optional, defaults to today).

        Returns:
            Dictionary with keys: symbol, period, interval, records (list of
            {date, open, high, low, close, volume} dicts).
            Returns {'error': '<message>'} if the symbol is invalid or data
            is unavailable.
        """
        try:
            result = historical_uc.execute(symbol, period, interval, start_date, end_date)
            return dataclasses.asdict(result)
        except Exception as exc:
            return {"error": str(exc)}

    @tool
    def retrieve_financial_documents(query: str) -> str:
        """Search Amazon's financial documents for information relevant to the query.

        Searches across the following documents:
          - Amazon 2024 Annual Report
          - Amazon Q2 2025 Earnings Release
          - Amazon Q3 2025 Earnings Release

        Use this tool for any question about Amazon's financials, business
        operations, earnings, revenue, AI investments, guidance, or any other
        topic covered in their official filings.

        Args:
            query: Natural-language search query.

        Returns:
            Relevant text passages with source file and page number, separated
            by '---'.  Returns an empty string if no relevant passages are found.
        """
        return retrieval_uc.execute(query)

    return [
        retrieve_realtime_stock_price,
        retrieve_historical_stock_price,
        retrieve_financial_documents,
    ]
