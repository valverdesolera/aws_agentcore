# Phase 2 — Finance Tools

> **Architecture reference:** Before writing or reviewing any code for this phase, consult
> [`docs/CleanArchitecture.md`](../CleanArchitecture.md).
> Key files for this phase:
> - **Domain:** `src/domain/entities/stock_price.py`, `src/domain/ports/stock_data_port.py`
> - **Application:** `src/application/use_cases/get_realtime_price.py`, `src/application/use_cases/get_historical_prices.py`
> - **Infrastructure:** `src/infrastructure/stock_data/yfinance_adapter.py`, `src/infrastructure/entrypoints/tool_registry.py`

## Summary

Build the two required finance tools (`retrieve_realtime_stock_price` and `retrieve_historical_stock_price`) using the `yfinance` library. These tools will later be registered with the LangGraph ReAct agent. They must be defined as LangChain-compatible tools using the `@tool` decorator so LangGraph can invoke them.

> **Note:** Unit tests are not part of this project scope. Validation is done manually by running the tools against the live yfinance API before wiring them into the agent.

---

## Dependencies

| Dependency | Version / Notes |
|---|---|
| Python | >= 3.10 |
| `yfinance` | Latest (`pip install yfinance`) |
| `langchain-core` | For the `@tool` decorator |
| `pandas` | Transitive dependency of yfinance |
| Phase 1 | Not strictly required — tools are developed locally |

---

## Setup

### 1. Install Dependencies

```bash
pip install yfinance langchain-core
```

### 2. Project File Structure

```
src/
├── tools/
│   ├── __init__.py
│   └── stock_tools.py        # Both finance tools
```

---

## Requirements

### A. `retrieve_realtime_stock_price`

Retrieves the current / most recent stock price for a given ticker symbol.

**yfinance API used:** `yf.Ticker(symbol).info` or `yf.Ticker(symbol).history(period="1d")`

```python
from langchain_core.tools import tool
import yfinance as yf


@tool
def retrieve_realtime_stock_price(symbol: str) -> dict:
    """Retrieve the current real-time stock price for a given ticker symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AMZN', 'AAPL', 'GOOGL')

    Returns:
        Dictionary containing current price data including:
        - symbol: The ticker symbol
        - current_price: Current market price
        - previous_close: Previous closing price
        - currency: Currency of the price
        - market_state: Whether market is open/closed
    """
    ticker = yf.Ticker(symbol)
    info = ticker.info

    # Get fast info for real-time price
    # Note: fast_info is a FastInfo object with attributes, NOT a dict.
    # Access via attribute syntax (fast_info.last_price), not .get().
    fast_info = ticker.fast_info

    return {
        "symbol": symbol.upper(),
        "current_price": getattr(fast_info, "last_price", None) or info.get("currentPrice"),
        "previous_close": getattr(fast_info, "previous_close", None) or info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "volume": info.get("volume"),
        "currency": info.get("currency", "USD"),
        "market_state": info.get("marketState", "UNKNOWN"),
    }
```

**Key yfinance patterns:**
- `yf.Ticker("AMZN")` creates a Ticker object for a single symbol
- `.info` returns a dict of company/price data (may be slower)
- `.fast_info` returns a `FastInfo` **object** (not a dict) with attributes like `last_price`, `previous_close`, etc. Use `fast_info.last_price` or `getattr(fast_info, "last_price", None)` — do NOT use `.get()`
- `.history(period="1d")` returns a DataFrame with OHLCV data

**Reference:** https://ranaroussi.github.io/yfinance/index

---

### B. `retrieve_historical_stock_price`

Retrieves historical stock prices over a date range or period.

**yfinance API used:** `yf.download()` or `yf.Ticker(symbol).history()`

```python
@tool
def retrieve_historical_stock_price(
    symbol: str,
    period: str = "3mo",
    interval: str = "1d",
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """Retrieve historical stock prices for a given ticker symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AMZN', 'AAPL', 'GOOGL')
        period: Time period to retrieve. Valid values: 1d, 5d, 1mo, 3mo, 6mo,
                1y, 2y, 5y, 10y, ytd, max. Ignored if start_date is provided.
        interval: Data interval. Valid values: 1m, 2m, 5m, 15m, 30m, 60m, 90m,
                  1h, 1d, 5d, 1wk, 1mo, 3mo.
        start_date: Start date in YYYY-MM-DD format (optional, overrides period)
        end_date: End date in YYYY-MM-DD format (optional, defaults to today)

    Returns:
        Dictionary containing historical price data with dates, open, high,
        low, close prices, and volume.
    """
    ticker = yf.Ticker(symbol)

    if start_date:
        history = ticker.history(start=start_date, end=end_date, interval=interval)
    else:
        history = ticker.history(period=period, interval=interval)

    if history.empty:
        return {"symbol": symbol.upper(), "error": "No data found", "records": []}

    records = []
    for date, row in history.iterrows():
        records.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(row["Open"], 2),
            "high": round(row["High"], 2),
            "low": round(row["Low"], 2),
            "close": round(row["Close"], 2),
            "volume": int(row["Volume"]),
        })

    return {
        "symbol": symbol.upper(),
        "period": period if not start_date else f"{start_date} to {end_date or 'today'}",
        "interval": interval,
        "record_count": len(records),
        "records": records,
    }
```

**Key yfinance patterns:**
- `yf.download(tickers="AMZN", period="1mo")` — batch download for multiple tickers
- `ticker.history(period="6mo", interval="1wk")` — single-ticker historical data
- `ticker.history(start="2024-10-01", end="2024-12-31")` — date-range query
- Results are returned as a `pandas.DataFrame` with columns: Open, High, Low, Close, Volume

**Reference:** https://ranaroussi.github.io/yfinance/reference/yfinance.functions

---

## Implementation Notes

1. **Tool docstrings are critical.** LangGraph and the LLM use the docstring to decide when to call each tool. Be explicit about what each parameter means and what the tool returns.

2. **Error handling.** Wrap yfinance calls in try/except to handle:
   - Invalid ticker symbols (yfinance may return empty DataFrames)
   - Network timeouts
   - API rate limiting

   ```python
   try:
       ticker = yf.Ticker(symbol)
       fast_info = ticker.fast_info
       price = getattr(fast_info, "last_price", None)
       if price is None:
           return {"error": f"No data found for symbol: {symbol}"}
   except Exception as e:
       return {"error": f"Failed to retrieve data: {str(e)}"}
   ```

3. **LangChain `@tool` decorator** ensures the function signature, docstring, and return type are exposed to the LLM when the tool is bound. This is the standard way to register tools in LangGraph.

4. **Q4 query handling.** For the UAT query "What were the stock prices for Amazon in Q4 last year?", the agent will need to translate "Q4 last year" into `start_date="2024-10-01"` and `end_date="2024-12-31"`. The LLM handles this reasoning; the tool just needs to accept date parameters.

5. **Return format.** Return dicts (not raw DataFrames) so the LLM can reason about the data in its context window.

---

## Verification Checklist

- [ ] `retrieve_realtime_stock_price("AMZN")` returns a dict with `current_price` > 0
- [ ] `retrieve_historical_stock_price("AMZN", period="1mo")` returns records with correct OHLCV fields
- [ ] `retrieve_historical_stock_price("AMZN", start_date="2024-10-01", end_date="2024-12-31")` returns Q4 2024 data
- [ ] Both tools handle invalid symbols gracefully (return error dict, no crash)
- [ ] Both tools are importable and can be passed to `llm.bind_tools([...])`

> Validation is done via manual spot-checks against the live yfinance API, not automated unit tests.
