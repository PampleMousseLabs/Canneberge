import requests
from bs4 import BeautifulSoup
import pandas as pd


class StockAnalysisClient:
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

        for table in tables:
            rows = table.find_all("tr")
            cols = table.find_all("th")

            if len(rows) > 5 and len(cols) > 2:
                raw_table = table
                break

        if raw_table is None:
            return None

        df = self._parse_table_to_dataframe(raw_table)

        if df.empty:
            return None

        df = self._clean_financial_table(df)

        first_col = df.columns[0]
        df.rename(columns={first_col: "Line Item"}, inplace=True)

        df = self._map_columns(df)

        df["Ticker"] = ticker_lower
        df["Key"] = df["Ticker"] + "|" + df["Line Item"].str.lower()

        return df

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
        """
        Header-driven mapping:
        TTM/LTM/Current -> TTM
        Highest FY year -> LFY
        Next highest -> LFY-1, etc.
        """
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