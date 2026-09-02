import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from scipy import stats


class BetaVolClient:
    def __init__(self, tickers, index_ticker, valuation_date, beta_history, vol_term):
        self.tickers = tickers
        self.index_ticker = index_ticker
        self.valuation_date = pd.Timestamp(valuation_date)
        self.beta_history = beta_history
        self.vol_term = vol_term

    def pull_and_calculate(self):
        end_date = self.valuation_date
        start_date = end_date - relativedelta(months=int(self.beta_history * 12)) - timedelta(days=30)

        index_data = yf.download(self.index_ticker, start=start_date, end=end_date, progress=False, threads=False)
        if len(index_data) == 0:
            return []

        index_prices = index_data[('Close', self.index_ticker)].sort_index(ascending=True)

        ticker_prices_dict = {}
        for ticker in self.tickers:
            ticker_data = yf.download(ticker, start=start_date, end=end_date, progress=False, threads=False)
            if len(ticker_data) > 0:
                ticker_prices_dict[ticker] = ticker_data[('Close', ticker)].sort_index(ascending=True)

        return self._calculate_all(ticker_prices_dict, index_prices)

    def _calculate_all(self, ticker_prices_dict, index_prices):
        results = []
        for ticker in self.tickers:
            if ticker not in ticker_prices_dict:
                results.append({
                    'Ticker': ticker,
                    '2yr Raw': None,
                    '2yr Adj': None,
                    '5yr Raw': None,
                    '5yr Adj': None,
                    'Volatility': None,
                    'YearsAvail': 0
                })
                continue

            ticker_prices = ticker_prices_dict[ticker]
            years_available = (ticker_prices.index[-1] - ticker_prices.index[0]).days / 365.25

            beta_2yr_raw = self._calculate_beta(ticker_prices, index_prices, frequency='weekly')
            beta_2yr_adj = beta_2yr_raw * (2/3) + (1/3) if beta_2yr_raw is not None else None

            beta_5yr_raw = self._calculate_beta(ticker_prices, index_prices, frequency='monthly')
            beta_5yr_adj = beta_5yr_raw * (2/3) + (1/3) if beta_5yr_raw is not None else None

            volatility = self._calculate_volatility(ticker_prices, years_available)

            results.append({
                'Ticker': ticker,
                '2yr Raw': beta_2yr_raw,
                '2yr Adj': beta_2yr_adj,
                '5yr Raw': beta_5yr_raw,
                '5yr Adj': beta_5yr_adj,
                'Volatility': volatility,
                'YearsAvail': years_available
            })
        return results

    def _calculate_beta(self, ticker_prices, index_prices, frequency='weekly'):
        if frequency == 'weekly':
            observations_needed = 104
            anchor = self.valuation_date - timedelta(days=(self.valuation_date.weekday() - 4) % 7)
        else:
            observations_needed = 60
            anchor = datetime(self.valuation_date.year, self.valuation_date.month, 1) - timedelta(days=1)

        sample_dates = []
        for i in range(observations_needed + 1):
            if frequency == 'weekly':
                target = anchor - timedelta(days=7 * i)
            else:
                month_offset = i
                year = anchor.year
                month = anchor.month - month_offset
                while month <= 0:
                    month += 12
                    year -= 1
                next_month = datetime(year, month, 1) + timedelta(days=32)
                target = datetime(next_month.year, next_month.month, 1) - timedelta(days=1)
            sample_dates.append(target)

        sample_dates.reverse()

        ticker_sample = []
        index_sample = []

        for target in sample_dates:
            t_date = self._find_closest_trading_date(target, pd.DatetimeIndex(ticker_prices.index))
            i_date = self._find_closest_trading_date(target, pd.DatetimeIndex(index_prices.index))
            if t_date is None or i_date is None:
                return None
            ticker_sample.append(ticker_prices[t_date])
            index_sample.append(index_prices[i_date])

        ticker_returns = np.diff(ticker_sample) / ticker_sample[:-1]
        index_returns = np.diff(index_sample) / index_sample[:-1]

        if len(ticker_returns) < 2:
            return None

        try:
            slope, _, _, _, _ = stats.linregress(index_returns, ticker_returns)
            return slope
        except:
            return None

    def _calculate_volatility(self, ticker_prices, years_available):
        vol_term_used = min(self.vol_term, years_available)
        if vol_term_used <= 0:
            return None
        n = len(ticker_prices)
        terms = []
        for d in ticker_prices.index:
            yearfrac = (self.valuation_date - pd.Timestamp(d)).days / 365.25
            term = round(yearfrac * 1000) / 1000
            terms.append(term)
        start_idx = 0
        for i in range(n):
            if terms[i] <= vol_term_used:
                start_idx = i
                break
        ret_count = n - start_idx
        if ret_count < 2:
            return None
        log_returns = np.log(ticker_prices.iloc[start_idx+1:].values / ticker_prices.iloc[start_idx:-1].values)
        vol = np.std(log_returns, ddof=0) * np.sqrt(252)
        return vol

    def _find_closest_trading_date(self, target_date, available_dates, direction='<='):
        if direction == '<=':
            valid = available_dates[available_dates <= target_date]
            if len(valid) > 0:
                return valid[-1]
        return None