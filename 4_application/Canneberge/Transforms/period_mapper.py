def map_statement_headers(df: object) -> object:
    """
    Apply header-driven mapping to a scraped statement DataFrame.
    Expects columns: Line Item, then source headers (TTM, FY XXXX, Current, etc.)
    Returns DataFrame with normalized columns.
    """
    import pandas as pd

    rename_map = {}
    fy_cols = {}

    for col in df.columns:
        if col == 'Line Item' or col in ('Ticker', 'Key'):
            continue
        header = str(col).strip()
        upper_hdr = header.upper()

        if upper_hdr in ('TTM', 'LTM', 'CURRENT'):
            rename_map[col] = 'TTM'
        elif header.startswith('FY'):
            try:
                year = int(header.replace('FY', '').strip())
                fy_cols[year] = col
            except ValueError:
                pass

    for idx, year in enumerate(sorted(fy_cols.keys(), reverse=True)):
        col = fy_cols[year]
        rename_map[col] = 'LFY' if idx == 0 else f'LFY-{idx}'

    if rename_map:
        df = df.rename(columns=rename_map)

    return df