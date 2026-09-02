from Canneberge.Sources.stockanalysis import StockAnalysisClient
from Canneberge.Sources.marketscreener import MarketScreenerClient
from Canneberge.Sources.fred import FREDClient
from Canneberge.Sources.beta_vol import BetaVolClient
from Canneberge import config
from Canneberge.Sources.yfinance_live import YFinanceLiveClient


class SourceDataService:
    def __init__(self, project_inputs, progress_callback=None):
        self.project_inputs = project_inputs
        self.progress = progress_callback or (lambda message: None)

    def refresh_stockanalysis(self):
        tickers = self.project_inputs.active_public_tickers
        statements = ["IS", "BS", "CFS", "Ratios"]

        client = StockAnalysisClient()
        all_results = {stmt: [] for stmt in statements}

        for idx, ticker in enumerate(tickers):
            self.progress(f"StockAnalysis: {ticker} ({idx + 1}/{len(tickers)})")
            for stmt in statements:
                try:
                    df = client.fetch_statement(ticker, stmt)
                    if df is not None and not df.empty:
                        records = df.to_dict("records")
                        all_results[stmt].extend(records)
                        self.progress(f"  {ticker} {stmt}: {len(records)} rows")
                    else:
                        self.progress(f"  {ticker} {stmt}: No data")
                except Exception as e:
                    self.progress(f"  {ticker} {stmt}: Error - {str(e)}")

        return all_results

    def refresh_marketscreener(self):
        tickers = self.project_inputs.active_public_tickers
        nfy = self.project_inputs.next_fiscal_year_year
        client = MarketScreenerClient()

        line_items = {
            "Revenue": ["Net Sales", "Revenue"],
            "EBITDA": ["EBITDA"],
            "EBIT": None,  # handled separately, avoid EBITDA substring collision
            "Net Income": ["Net Income"],
        }

        results = []

        for idx, ticker in enumerate(tickers):
            self.progress(f"MarketScreener: {ticker} ({idx + 1}/{len(tickers)})")
            try:
                slug = client.resolve_slug(ticker)
                if not slug:
                    self.progress(f"  {ticker}: slug not found")
                    continue

                html = client.get_finance_html(slug)
                if not html:
                    self.progress(f"  {ticker}: finance page not found")
                    continue

                all_years = client.get_all_year_headers(html)
                nfy_str = str(nfy)
                if nfy_str not in all_years:
                    self.progress(f"  {ticker}: NFY {nfy_str} not in headers {all_years}")
                    continue

                nfy_index = all_years.index(nfy_str)
                target_years = all_years[nfy_index:nfy_index + 3]
                if len(target_years) < 3:
                    self.progress(f"  {ticker}: not enough forward years")
                    continue

                for output_label, search_labels in line_items.items():
                    if output_label == "EBIT":
                        values = client.get_row_values_ebit(html, len(all_years))
                    else:
                        values = None
                        for label in search_labels:
                            values = client.get_row_values(html, label, len(all_years))
                            if values:
                                break

                    if values and len(values) >= nfy_index + 3:
                        nfy_values = values[nfy_index:nfy_index + 3]
                        results.append({
                            "Ticker": ticker.lower(),
                            "Line Item": output_label,
                            "Key": f"{ticker.lower()}|{output_label.lower()}",
                            "NFY": nfy_values[0],
                            "NFY+1": nfy_values[1],
                            "NFY+2": nfy_values[2],
                        })
                        self.progress(f"    {output_label}: {nfy_values}")
                    else:
                        self.progress(f"    {output_label}: not found")

            except Exception as e:
                self.progress(f"  {ticker}: Error - {str(e)}")

        return results

    def refresh_fred(self):
        try:
            api_key = config.get_fred_api_key()
        except RuntimeError as e:
            self.progress(str(e))
            return []

        series_map = config.get_fred_series()
        client = FREDClient(api_key=api_key, label_map=series_map)

        results = []
        for idx, series_id in enumerate(series_map.keys()):
            self.progress(f"FRED: {series_id} ({idx + 1}/{len(series_map)})")
            try:
                result = client.fetch_series(series_id)
                if result:
                    results.append(result)
                    self.progress(f"  {series_id}: {result['LatestValue']}")
                else:
                    self.progress(f"  {series_id}: no data")
            except Exception as e:
                self.progress(f"  {series_id}: Error - {str(e)}")

        return results

    def refresh_beta_vol(self, index_ticker="^GSPC", beta_history=5.0, vol_term=3.0):
        tickers = self.project_inputs.active_public_tickers
        valuation_date = self.project_inputs.valuation_date

        self.progress(f"Beta/Vol: pulling price history for {len(tickers)} tickers + index")
        try:
            client = BetaVolClient(
                tickers=tickers,
                index_ticker=index_ticker,
                valuation_date=valuation_date,
                beta_history=beta_history,
                vol_term=vol_term,
            )
            results = client.pull_and_calculate()
            self.progress(f"Beta/Vol: computed {len(results)} tickers")
            return results
        except Exception as e:
            self.progress(f"Beta/Vol: Error - {str(e)}")
            return []

    def _get_scale_divisor(self) -> float:
        """
        Parses ProjectInputs.numeric_scale ('Millions', 'Thousands', 'Actual')
        into a clean float divisor (1000000.0, 1000.0, or 1.0).
        """
        scale_str = str(getattr(self.project_inputs, "numeric_scale", "Millions")).strip().lower()
        if "million" in scale_str:
            return 1_000_000.0
        elif "thousand" in scale_str:
            return 1_000.0
        return 1.0

    def refresh_live_marks(self, existing_sa_results: dict = None):
        """
        Fast refresh (~2 seconds): pulls live market marks from yfinance.
        Scales Market Cap, EV, and Shares Outstanding to match the Home Page numeric scale.
        """
        tickers = self.project_inputs.active_public_tickers
        scale_divisor = self._get_scale_divisor()

        self.progress(f"Live Marks: Fetching live prices & caps for {len(tickers)} tickers via yfinance...")

        yf_client = YFinanceLiveClient(tickers)
        live_marks = yf_client.fetch_live_marks()

        sa_results = existing_sa_results if isinstance(existing_sa_results, dict) else {}
        if "Ratios" not in sa_results:
            sa_results["Ratios"] = []

        ratios = sa_results["Ratios"]

        # Map existing (ticker, line_item) -> list index in Ratios array
        existing_map = {
            (str(r.get("Ticker", "")).strip().lower(), str(r.get("Line Item", "")).strip().lower()): idx
            for idx, r in enumerate(ratios)
        }

        # Items that need scaling (everything except per-share price)
        ITEMS_TO_SCALE = {"market capitalization", "enterprise value", "shares outstanding"}

        patched_count = 0
        for ticker_lower, marks in live_marks.items():
            for line_item, val in marks.items():
                if val is None:
                    continue

                # Scale currency caps and shares count; leave stock price in actual dollars
                if line_item in ITEMS_TO_SCALE:
                    scaled_val = val / scale_divisor
                else:
                    scaled_val = val

                key = f"{ticker_lower}|{line_item}"
                idx = existing_map.get((ticker_lower, line_item))

                if idx is not None:
                    ratios[idx]["TTM"] = scaled_val
                else:
                    new_row = {
                        "Ticker": ticker_lower,
                        "Line Item": line_item,
                        "TTM": scaled_val,
                        "Key": key,
                    }
                    ratios.append(new_row)
                    existing_map[(ticker_lower, line_item)] = len(ratios) - 1
                patched_count += 1

        self.progress(f"Live Marks: Updated {patched_count} entries (scale divisor: {scale_divisor:,.0f}).")
        
        fred_results = self.refresh_fred()
        return {
            "stockanalysis": sa_results,
            "fred": fred_results,
        }