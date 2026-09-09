import csv
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm


class StockAnalysisClient:
    """Unmodified from your existing scraper - handles fetching + parsing."""

    def __init__(self):
        self.statements = ["IS", "BS", "CFS", "Ratios"]

    def fetch_statement(self, ticker: str, statement_type: str):
        ticker_lower = ticker.lower()

        if statement_type == "IS":
            url = f"https://stockanalysis.com/stocks/{ticker_lower}/financials/income-statement/"
        elif statement_type == "BS":
            url = f"https://stockanalysis.com/stocks/{ticker_lower}/financials/balance-sheet/"
        elif statement_type == "CFS":
            url = f"https://stockanalysis.com/stocks/{ticker_lower}/financials/cash-flow-statement/"
        elif statement_type == "Ratios":
            url = f"https://stockanalysis.com/stocks/{ticker_lower}/financials/ratios/"
        else:
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        tables = soup.find_all("table")

        if not tables:
            return None

        raw_table = None
        header_signature = None

        for table in tables:
            rows = table.find_all("tr")
            cols = table.find_all("th")

            if len(rows) > 5 and len(cols) > 2:
                raw_table = table
                header_signature = self._table_header(table)
                break

        if raw_table is None:
            return None

        matching_tables = [
            t for t in tables
            if self._table_header(t) == header_signature
        ]

        dfs = []
        for t in matching_tables:
            df_part = self._parse_table_to_dataframe(t)
            if not df_part.empty:
                dfs.append(df_part)

        if not dfs:
            return None

        df = pd.concat(dfs, ignore_index=True)

        if df.empty:
            return None

        df = self._clean_financial_table(df)

        first_col = df.columns[0]
        df.rename(columns={first_col: "Line Item"}, inplace=True)

        df = self._map_columns(df)

        df["Ticker"] = ticker_lower
        df["Key"] = df["Ticker"] + "|" + df["Line Item"].str.lower()

        return df

    def _table_header(self, table):
        tr = table.find("tr")
        if not tr:
            return None
        cells = tr.find_all(["th", "td"])
        return tuple(c.get_text(strip=True) for c in cells)

    def _parse_table_to_dataframe(self, table):
        html_rows = table.find_all("tr")

        if not html_rows:
            return pd.DataFrame()

        header_cells = html_rows[0].find_all(["th", "td"])
        headers = [cell.get_text(strip=True) for cell in header_cells]

        if len(headers) < 2:
            return pd.DataFrame()

        data = []

        for tr in html_rows[1:]:
            cells = tr.find_all(["th", "td"])
            row = [cell.get_text(strip=True) for cell in cells]

            if not row:
                continue

            first = row[0].strip().lower()

            if first in {"fiscal year", "period ending"}:
                continue

            if len(row) < len(headers):
                row.extend([None] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[:len(headers)]

            data.append(row)

        if not data:
            return pd.DataFrame()

        return pd.DataFrame(data, columns=headers)

    def _clean_financial_table(self, df):
        junk_values = ["-", "N/A", "NA", "", "—", None]

        for col in df.columns:
            df[col] = df[col].replace(junk_values, None)

            if df[col].dtype == "object":
                df[col] = df[col].apply(
                    lambda x: x.strip() if isinstance(x, str) else x
                )

        return df

    def _map_columns(self, df):
        rename_map = {}
        fy_cols = {}

        for col in df.columns[1:]:
            header = str(col).strip()
            upper_hdr = header.upper()

            if upper_hdr in ("TTM", "LTM", "CURRENT"):
                rename_map[col] = "TTM"

            elif header.startswith("FY"):
                try:
                    year = int(header.replace("FY", "").strip())
                    fy_cols[year] = col
                except ValueError:
                    pass

        for idx, year in enumerate(sorted(fy_cols.keys(), reverse=True)):
            col = fy_cols[year]

            if idx == 0:
                rename_map[col] = "LFY"
            else:
                rename_map[col] = f"LFY-{idx}"

        if rename_map:
            df.rename(columns=rename_map, inplace=True)

        return df


def load_tickers_from_file(filepath, column="Symbol"):
    """
    Reads a ticker list from a CSV or Excel file.
    Expects a column (default 'Symbol') containing ticker strings,
    matching the format of the S&P 500 constituents file
    (Symbol, Security, GICS Sector, ...).

    Returns a deduplicated list of uppercase ticker strings,
    preserving original file order.
    """
    if filepath.lower().endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found in {filepath}. "
            f"Available columns: {list(df.columns)}"
        )

    tickers = (
        df[column]
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
        .tolist()
    )

    # Dedupe while preserving order (in case of accidental duplicates)
    seen = set()
    deduped = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            deduped.append(t)

    return deduped


class LineItemUniverseBuilder:
    """
    Scrapes a ticker list and builds a master list of unique
    'Line Item' row labels per statement type (IS, BS, CFS, Ratios).

    For each unique label, tracks:
      - the first ticker where it was seen (example reference)
      - how many distinct tickers had that label (seen count)
    """

    def __init__(self, tickers, progress_callback=None, request_delay=0.3, show_progress_bar=True):
        self.tickers = tickers
        self.statements = ["IS", "BS", "CFS", "Ratios"]
        self.client = StockAnalysisClient()
        self.progress = progress_callback or (lambda msg: None)
        self.request_delay = request_delay
        self.show_progress_bar = show_progress_bar

    def build(self):
        """
        Returns:
            {
              "IS": {
                  line_item_str: {"example_ticker": str, "seen_count": int},
                  ...
              },
              "BS": {...},
              "CFS": {...},
              "Ratios": {...},
            }
        Insertion order = first-seen order.
        """
        results = {stmt: {} for stmt in self.statements}

        ticker_iterator = tqdm(
            self.tickers,
            desc="Scraping tickers",
            unit="ticker",
            disable=not self.show_progress_bar,
        )

        for ticker in ticker_iterator:
            ticker_iterator.set_postfix_str(ticker)
            self.progress(f"{ticker}")

            for stmt in self.statements:
                try:
                    df = self.client.fetch_statement(ticker, stmt)

                    if df is None or df.empty or "Line Item" not in df.columns:
                        self.progress(f"  {ticker} {stmt}: no data")
                        continue

                    labels = df["Line Item"].dropna().unique()
                    new_count = 0

                    for raw_label in labels:
                        label = str(raw_label).strip()
                        if not label:
                            continue

                        if label not in results[stmt]:
                            results[stmt][label] = {
                                "example_ticker": ticker.lower(),
                                "seen_count": 1,
                            }
                            new_count += 1
                        else:
                            results[stmt][label]["seen_count"] += 1

                    self.progress(
                        f"  {ticker} {stmt}: {new_count} new / {len(labels)} total"
                    )

                except Exception as e:
                    self.progress(f"  {ticker} {stmt}: Error - {str(e)}")

                if self.request_delay:
                    time.sleep(self.request_delay)

        return results

    def export_to_csv(self, results, output_dir="."):
        """
        Writes one CSV per statement type:
            line_items_IS.csv, line_items_BS.csv, etc.
        Columns: Line Item, Example Ticker, Seen Count
        """
        for stmt, mapping in results.items():
            filepath = f"{output_dir}/line_items_{stmt}.csv"
            with open(filepath, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Line Item", "Example Ticker", "Seen Count"])
                for label, info in mapping.items():
                    writer.writerow(
                        [label, info["example_ticker"], info["seen_count"]]
                    )

            self.progress(f"Wrote {len(mapping)} unique labels -> {filepath}")


if __name__ == "__main__":
    # Only input needed: path to your constituents file
    TICKER_FILE = "constituents.csv"  # or "constituents.xlsx"

    TICKERS = load_tickers_from_file(TICKER_FILE, column="Symbol")
    print(f"Loaded {len(TICKERS)} tickers from {TICKER_FILE}")

    def print_progress(msg):
        # Detailed log messages - could route to a file instead of print
        # if you want the console to just show the tqdm bar cleanly.
        pass  # set to `print(msg)` if you want verbose per-ticker logs too

    builder = LineItemUniverseBuilder(
        tickers=TICKERS,
        progress_callback=print_progress,
        request_delay=0.3,
        show_progress_bar=True,
    )

    results = builder.build()
    builder.export_to_csv(results, output_dir=".")