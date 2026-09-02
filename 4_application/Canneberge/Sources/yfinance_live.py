"""
yfinance_live.py
Canneberge — Sources

Fast batch fetcher for live market marks via yfinance API.
Pulls Market Cap, Enterprise Value, Last Sale Price, and Shares Outstanding.
"""

from typing import List, Dict, Any
import yfinance as yf


class YFinanceLiveClient:
    def __init__(self, tickers: List[str]):
        self.tickers = [t.strip().upper() for t in tickers if t and t.strip()]

    def fetch_live_marks(self) -> Dict[str, Dict[str, Any]]:
        if not self.tickers:
            return {}

        results = {}
        try:
            ticker_str = " ".join(self.tickers)
            batch = yf.Tickers(ticker_str)

            for ticker in self.tickers:
                t_obj = batch.tickers.get(ticker)
                info = getattr(t_obj, "info", {}) or {} if t_obj else {}

                price = (
                    info.get("currentPrice") or
                    info.get("regularMarketPrice") or
                    info.get("previousClose")
                )
                mcap = info.get("marketCap")
                ev = info.get("enterpriseValue")
                shares = info.get("sharesOutstanding")

                results[ticker.lower()] = {
                    "market capitalization": mcap,
                    "enterprise value": ev,
                    "last close price": price,
                    "shares outstanding": shares,
                }
        except Exception as e:
            print(f"YFinanceLiveClient fetch error: {e}")

        return results