"""
============================================================
RATIOS CANONICAL ORDERING ENGINE
============================================================

STRUCTURAL DIFFERENCE FROM IS / BS / CFS:
The Ratios statement is NOT a reconcilable financial statement.
Every row is a standalone COMPUTED METRIC (PE Ratio, ROE,
Debt/Equity, Dividend Yield, etc.). Consequently there are:

    - NO additive chains
    - NO anchors / subtotals
    - NO sign conventions
    - NO reconciliation identities
    - NO zone boundaries

Therefore the canonical engine reduces to its PURE POSITIONAL
CORE: we treat the entire statement as ONE FLAT ZONE and derive
canonical order solely from cross-ticker positional voting.

Because nothing is reconcilable, EVERY line item is auto-trusted
and NOTHING is filtered out. The full scraped universe becomes
the canonical template — which is exactly the goal for a
comprehensive ratios keymap (503-company superset).

Reuses StyledStatementClient, parse_numeric, and
resolve_canonical_positions from income_statement_canonical_order.py.
============================================================
"""

import csv
import sys
import time
from tqdm import tqdm

from line_item_scraper import load_tickers_from_file
from income_statement_canonical_order import (
    StyledStatementClient,
    parse_numeric,
    resolve_canonical_positions,
)


# ==================================================================
# SINGLE FLAT ZONE (no anchors — ratios are non-additive)
# ==================================================================

SENTINEL_TOP = "__TOP_OF_RATIOS__"
SENTINEL_BOTTOM = "__BOTTOM_OF_RATIOS__"

RATIOS_ZONE_KEY = (SENTINEL_TOP, SENTINEL_BOTTOM)


# ==================================================================
# STEP 1 — Cross-ticker positional voting
# ==================================================================
# Every row votes for the single flat zone. Its relative position
# is idx / n_rows. resolve_canonical_positions then averages the
# positions across all tickers to produce the canonical order.
# ==================================================================

def build_master_order_ratios(tickers, client, request_delay=0.3):
    item_zone_votes = {}
    item_zone_positions = {}

    value_columns_priority = ["LFY", "LFY-1", "LFY-2", "LFY-3", "TTM"]

    progress_bar = tqdm(
        tickers, desc="Building Ratios canonical order", unit="ticker",
        file=sys.stdout, dynamic_ncols=True, mininterval=0.3, ascii=True,
    )

    for ticker in progress_bar:
        try:
            df = client.fetch_statement(ticker, "Ratios")
            if df is None or df.empty:
                continue

            df = df.reset_index(drop=True)
            n_rows = len(df)
            if n_rows == 0:
                continue

            # available_cols only used to confirm the row carries data;
            # not required for positional voting, but we keep the same
            # shape as the other engines for consistency.
            _available = [c for c in value_columns_priority if c in df.columns]

            for idx, row in df.iterrows():
                label = str(row["Line Item"]).strip()
                if not label:
                    continue

                item_zone_votes.setdefault(label, {})
                item_zone_votes[label][RATIOS_ZONE_KEY] = (
                    item_zone_votes[label].get(RATIOS_ZONE_KEY, 0) + 1
                )

                rel_pos = idx / n_rows
                item_zone_positions.setdefault(label, {}).setdefault(
                    RATIOS_ZONE_KEY, []
                ).append(rel_pos)

        except Exception:
            continue

        finally:
            if request_delay:
                time.sleep(request_delay)

    return item_zone_votes, item_zone_positions


# ==================================================================
# STEP 2a — Master DRAFT statement
# ==================================================================
# Single flat zone → one ordered list, no section headers.
# ==================================================================

def build_master_draft_statement_ratios(canonical):
    rows = [{"Line Item": f"--- Ratios ---", "Type": "SECTION",
             "Confidence": None}]

    zone_items = [(l, i) for l, i in canonical.items()
                  if i["zone"] == RATIOS_ZONE_KEY]
    zone_items.sort(key=lambda x: x[1]["avg_position"])

    for label, info in zone_items:
        rows.append({"Line Item": label, "Type": "metric",
                     "Confidence": round(info["confidence"], 2)})

    return rows


# ==================================================================
# STEP 2b — Subject-company-specific template
# ==================================================================
# For each canonical item missing from the subject, insert it at
# its average positional index. No anchors to check — the single
# flat zone always exists, so nothing is ever skipped.
# ==================================================================

def build_subject_company_template_ratios(subject_ticker, client, canonical):
    df = client.fetch_statement(subject_ticker, "Ratios")
    if df is None or df.empty:
        raise ValueError(f"Could not fetch Ratios for {subject_ticker}")

    df = df.reset_index(drop=True)
    subject_labels = [str(x).strip() for x in df["Line Item"].tolist()]
    subject_label_set = set(subject_labels)
    n_rows = len(subject_labels)

    rows = [
        {"sort_key": float(idx), "Line Item": label,
         "Source": "subject", "Confidence": None}
        for idx, label in enumerate(subject_labels)
    ]

    for label, info in canonical.items():
        if label in subject_label_set:
            continue

        # Single flat zone spans the whole statement:
        # start_idx = -1, end_idx = n_rows, span = n_rows + 1
        start_idx = -1
        span = n_rows + 1
        target_key = start_idx + info["avg_position"] * span

        rows.append({
            "sort_key": target_key, "Line Item": label,
            "Source": "inserted", "Confidence": round(info["confidence"], 2),
        })

    rows.sort(key=lambda r: r["sort_key"])
    return rows


# ==================================================================
# DEBUGGER
# ==================================================================
# No reconciliation to run — ratios are non-additive. The debugger
# simply dumps the raw rows and the positional footprint so you can
# eyeball ordering consistency across tickers.
# ==================================================================

def debug_ticker_ratios(ticker, client, value_column="LFY"):
    df = client.fetch_statement(ticker, "Ratios")
    if df is None or df.empty:
        print(f"!! No data for {ticker}")
        return
    df = df.reset_index(drop=True)

    if value_column not in df.columns:
        print(f"!! Column '{value_column}' not found. "
              f"Available: {list(df.columns)}")
        return

    print(f"\n{'=' * 74}\n{ticker} — raw rows (column: {value_column})"
          f"\n{'=' * 74}")
    print(f"{'idx':>4} {'rel_pos':>8} {'value':>14}  Line Item")
    n_rows = len(df)
    for idx, row in df.iterrows():
        rel_pos = idx / n_rows
        print(f"{idx:>4} {rel_pos:>8.3f} "
              f"{str(row[value_column]):>14}  {row['Line Item']}")

    print(f"\n{'=' * 74}\nNOTE: Ratios are non-reconcilable (standalone "
          f"computed metrics).\nOrdering is positional only — no zone "
          f"reconciliation or identity check.\n{'=' * 74}")


# ==================================================================
# CSV EXPORTS
# ==================================================================

def export_canonical_order_ratios(canonical,
                                  filepath="canonical_order_Ratios.csv"):
    rows = sorted(canonical.items(), key=lambda kv: kv[1]["avg_position"])
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Avg Position", "Confidence",
                    "Observations"])
        for label, info in rows:
            w.writerow([label, round(info["avg_position"], 3),
                        round(info["confidence"], 3),
                        info["total_observations"]])
    print(f"Wrote {len(rows)} canonical items -> {filepath}")


def export_ambiguous_items_ratios(ambiguous,
                                  filepath="ambiguous_items_Ratios.csv"):
    # Ratios have a single flat zone, so ambiguity is effectively
    # impossible — this file will normally be empty. Written for
    # parity with the other engines.
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Zone Votes (start->end : count)"])
        for label, zone_votes in ambiguous.items():
            vote_str = "; ".join(
                f"{s}->{e}: {c}" for (s, e), c in zone_votes.items()
            )
            w.writerow([label, vote_str])
    print(f"Wrote {len(ambiguous)} ambiguous items -> {filepath}")


def export_master_draft_ratios(rows, filepath="master_draft_Ratios.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Type", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Type"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


def export_subject_template_ratios(rows,
                                   filepath="subject_template_Ratios.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Source", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Source"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


# ==================================================================
# MAIN
# ==================================================================

MODE = "full"

TICKER_FILE = "constituents.csv"
SUBJECT_TICKER = "MMM"
DEBUG_TICKERS = ["MMM", "ABBV", "AMD", "AES", "AFL", "ARE", "LNT",
                 "ALL", "GOOGL", "AXP", "AIG", "AMT", "AWK", "APP"]
DEBUG_COLUMN = "LFY"


if __name__ == "__main__":
    client = StyledStatementClient()

    if MODE == "debug":
        for t in DEBUG_TICKERS:
            debug_ticker_ratios(t, client, value_column=DEBUG_COLUMN)
            time.sleep(0.3)

    elif MODE == "full":
        tickers = load_tickers_from_file(TICKER_FILE, column="Symbol")
        print(f"Loaded {len(tickers)} tickers from {TICKER_FILE}")

        item_zone_votes, item_zone_positions = build_master_order_ratios(
            tickers, client, request_delay=0.3
        )

        canonical, ambiguous = resolve_canonical_positions(
            item_zone_votes, item_zone_positions, ambiguous_threshold=0.9
        )

        export_canonical_order_ratios(canonical)
        export_ambiguous_items_ratios(ambiguous)

        draft_rows = build_master_draft_statement_ratios(canonical)
        export_master_draft_ratios(draft_rows)

        subject_rows = build_subject_company_template_ratios(
            SUBJECT_TICKER, client, canonical
        )
        export_subject_template_ratios(
            subject_rows,
            f"subject_template_Ratios_{SUBJECT_TICKER}.csv"
        )

    else:
        raise ValueError(
            f"Unknown MODE: {MODE!r} (expected 'debug' or 'full')"
        )