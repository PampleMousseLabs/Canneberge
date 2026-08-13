import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from scipy import stats

# =========================================================
# INPUT PARAMETERS
# =========================================================
ticker = "AAPL"
index_ticker = "^GSPC"  # S&P 500
valuation_date = datetime.today()
beta_history_years = 5
volatility_term_years = 3

print(f"=== BETA & VOLATILITY CALCULATION ===")
print(f"Ticker: {ticker}")
print(f"Index: {index_ticker}")
print(f"Valuation Date: {valuation_date.strftime('%m/%d/%Y')}")
print(f"Beta History: {beta_history_years} years")
print(f"Volatility Term: {volatility_term_years} years")
print()

# =========================================================
# 1. FETCH OHLCV DATA
# =========================================================
print("Fetching price data from Yahoo Finance...")

# Date windows (mirrors Excel: =EDATE(ValuationDate, -BetaHistory*12)-30)
end_date = valuation_date
start_date = end_date - relativedelta(months=int(beta_history_years * 12)) - timedelta(days=30)

# Download data
ticker_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
index_data = yf.download(index_ticker, start=start_date, end=end_date, progress=False)

print(f"  {ticker}: {len(ticker_data)} trading days")
print(f"  {index_ticker}: {len(index_data)} trading days")
print()

# Use Close prices (yfinance returns MultiIndex)
ticker_prices = ticker_data[('Close', ticker)].sort_index(ascending=True)
index_prices = index_data[('Close', index_ticker)].sort_index(ascending=True)

# =========================================================
# 2. CALCULATE YEARS AVAILABLE
# =========================================================
years_available = (ticker_prices.index[-1] - ticker_prices.index[0]).days / 365.25
print(f"Years of data available: {years_available:.2f}")
print()

# =========================================================
# 3. EXTRACT ALIGNED SERIES (for beta)
# =========================================================
# Find dates where both ticker and index have data
aligned_dates = ticker_prices.index.intersection(index_prices.index)
ticker_aligned = ticker_prices[aligned_dates].values
index_aligned = index_prices[aligned_dates].values

print(f"Aligned trading days (both have data): {len(aligned_dates)}")
print()

# =========================================================
# 4. CALENDAR-ANCHORED BETA CALCULATION
# =========================================================
def find_closest_trading_date(target_date, available_dates, direction='<='):
    """Find the closest trading date to target, in specified direction"""
    if direction == '<=':
        valid = available_dates[available_dates <= target_date]
        if len(valid) > 0:
            return valid[-1]
    else:
        valid = available_dates[available_dates >= target_date]
        if len(valid) > 0:
            return valid[0]
    return None

def calculate_beta(ticker_prices, index_prices, aligned_dates, lookback_years, frequency='weekly'):
    """
    Calculate beta using calendar-anchored sampling.
    frequency: 'weekly' (2-year, 5yr obs) or 'monthly' (5-year, 60 obs)
    """
    
    if frequency == 'weekly':
        step_days = 7
        observations_needed = 104  # 2 years * 52 weeks
        # Snap to most recent Friday
        anchor = valuation_date - timedelta(days=(valuation_date.weekday() - 4) % 7)
    else:  # monthly
        step_days = 30  # Approximate; we'll use actual month-ends
        observations_needed = 60  # 5 years * 12 months
        # Snap to most recent month-end
        anchor = datetime(valuation_date.year, valuation_date.month, 1) - timedelta(days=1)
    
    # Build calendar-anchored sample dates (going backwards from anchor)
    sample_dates = []
    for i in range(observations_needed + 1):  # +1 for the return calculation (new/old - 1)
        if frequency == 'weekly':
            target = anchor - timedelta(days=7 * i)
        else:
            # Go back i months
            month_offset = i
            year = anchor.year
            month = anchor.month - month_offset
            while month <= 0:
                month += 12
                year -= 1
            # Get the last day of that month
            next_month = datetime(year, month, 1) + timedelta(days=32)
            target = datetime(next_month.year, next_month.month, 1) - timedelta(days=1)
        
        sample_dates.append(target)
    
    # Reverse to ascending order for return calculations
    sample_dates.reverse()
    
    # Find actual trading dates for each sample date
    ticker_sample = []
    index_sample = []
    
    for target in sample_dates:
        t_date = find_closest_trading_date(target, pd.DatetimeIndex(ticker_prices.index))
        i_date = find_closest_trading_date(target, pd.DatetimeIndex(index_prices.index))
        
        if t_date is None or i_date is None:
            return None
        
        ticker_sample.append(ticker_prices[t_date])
        index_sample.append(index_prices[i_date])
    
    # Calculate simple returns
    ticker_returns = np.diff(ticker_sample) / ticker_sample[:-1]
    index_returns = np.diff(index_sample) / index_sample[:-1]
    
    # Calculate beta via regression
    if len(ticker_returns) < 2:
        return None
    
    slope, intercept, r_value, p_value, std_err = stats.linregress(index_returns, ticker_returns)
    
    return slope

# Calculate 2-year weekly beta
beta_2yr_raw = calculate_beta(ticker_prices, index_prices, aligned_dates, 2, frequency='weekly')
beta_2yr_adj = beta_2yr_raw * (2/3) + (1/3) if beta_2yr_raw else None

# Calculate 5-year monthly beta
beta_5yr_raw = calculate_beta(ticker_prices, index_prices, aligned_dates, 5, frequency='monthly')
beta_5yr_adj = beta_5yr_raw * (2/3) + (1/3) if beta_5yr_raw else None

print(f"2-Year Weekly Beta (Raw): {beta_2yr_raw:.4f}" if beta_2yr_raw else "2-Year Weekly Beta (Raw): N/A")
print(f"2-Year Weekly Beta (Adj): {beta_2yr_adj:.4f}" if beta_2yr_adj else "2-Year Weekly Beta (Adj): N/A")
print(f"5-Year Monthly Beta (Raw): {beta_5yr_raw:.4f}" if beta_5yr_raw else "5-Year Monthly Beta (Raw): N/A")
print(f"5-Year Monthly Beta (Adj): {beta_5yr_adj:.4f}" if beta_5yr_adj else "5-Year Monthly Beta (Adj): N/A")
print()

# =========================================================
# 5. VOLATILITY CALCULATION (log returns, YEARFRAC-anchored)
# =========================================================
# Calculate years back from valuation date for each price point
years_back = np.array([(valuation_date - pd.Timestamp(d)).days / 365.25 for d in ticker_prices.index])

# Filter to only rows within volatility term
vol_window = ticker_prices[years_back <= volatility_term_years]

if len(vol_window) < 2:
    volatility = None
else:
    # Calculate log returns
    log_returns = np.log(vol_window.values[1:] / vol_window.values[:-1])
    
    # Annualized volatility (252 trading days per year)
    volatility = np.std(log_returns) * np.sqrt(252)

print(f"Volatility (annualized, {volatility_term_years}-year term): {volatility:.4f}" if volatility else "Volatility: N/A")
print()

# =========================================================
# 6. OUTPUT
# =========================================================
print("=== RESULTS ===")
print(f"{ticker:12} | 2yr Raw | 2yr Adj | 5yr Raw | 5yr Adj | Volatility | YearsAvail")
print("-" * 80)
row_data = [
    ticker,
    f"{beta_2yr_raw:.4f}" if beta_2yr_raw else "N/A",
    f"{beta_2yr_adj:.4f}" if beta_2yr_adj else "N/A",
    f"{beta_5yr_raw:.4f}" if beta_5yr_raw else "N/A",
    f"{beta_5yr_adj:.4f}" if beta_5yr_adj else "N/A",
    f"{volatility:.4f}" if volatility else "N/A",
    f"{years_available:.2f}"
]
print(f"{row_data[0]:12} | {row_data[1]:7} | {row_data[2]:7} | {row_data[3]:7} | {row_data[4]:7} | {row_data[5]:10} | {row_data[6]}")