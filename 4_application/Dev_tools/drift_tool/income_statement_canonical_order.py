"""
============================================================
INCOME STATEMENT CANONICAL ORDERING ENGINE
============================================================

PROBLEM:
Every company's Income Statement has a different length and a
different SET of line items, but they all share a small set of
universal "checkpoint" subtotals (Revenue, Gross Profit,
Operating Income, Pretax Income, Net Income, EPS) that appear in
the same relative order everywhere. Every other line item sits
somewhere BETWEEN two of these checkpoints.

By scanning hundreds of tickers we statistically learn where each
item "usually" sits, so when we build a model for a Subject
Company that's MISSING a line item another company has, we know
exactly where to insert it (as a 0/NA placeholder) so future data
lands in the correct row.

VALIDATION TRICK:
Anchors are also subtotals. Rather than trusting the vendor's
reported value, we independently RE-CALCULATE each anchor by
summing the line items assigned to that zone, then compare to the
reported delta between the two anchors.
  - Match   -> zone assignment trustworthy, counts toward the vote
  - Mismatch-> skip this ticker/zone rather than pollute the order

------------------------------------------------------------
REVISION HISTORY / FIXES
------------------------------------------------------------
FIX A: `IsBold` is force-cast to a real boolean dtype. Previously
       pd.concat across table fragments could leave it as
       object/NaN, which threw a Pandas4Warning and meant bold
       detection was silently misfiring on some rows.

FIX B: Bold detection alone proved INSUFFICIENT. Replacing the
       manual subtotal list with pure bold-detection tanked
       GP->OI to 0.3% and regressed OI->PI from 85.6% to 17.6%,
       because rollups like "Operating Expenses" and "EBT
       Excluding Unusual Items" are not reliably bold and got
       summed alongside their own children (double-counting).
       Now we exclude a row if it is bold OR in the manual list.

FIX C: Sign convention is now PER-ZONE, not a hardcoded item list.
       A hardcoded list can't scale to the dozens of expense-label
       variants across 503 companies, but the zone itself has a
       consistent convention (expense zones report positive
       magnitudes that must be subtracted; non-operating zones
       report pre-signed values). Per-item overrides still exist
       for the mixed PI->NI zone.

FIX D: Sentinel bookend zones so items ABOVE Revenue and BELOW
       EPS (EBITDA, EBIT, margins, Effective Tax Rate, etc.) get
       canonical positions. Previously they belonged to no zone
       and could never be inserted into another company's
       template.

FIX E: tqdm settings tuned for PowerShell / legacy Windows console
       (was printing a new line per update instead of refreshing
       in place).
============================================================
"""

import csv
import sys
import time
import requests
import pandas as pd
from bs4 import BeautifulSoup
from tqdm import tqdm

from line_item_scraper import load_tickers_from_file  # reuse as-is


# ==================================================================
# ANCHOR DEFINITIONS
# ==================================================================
# The fixed "checkpoint" subtotals, in canonical order, as they
# appear on stockanalysis.com's STANDARDIZED Income Statement view.
#
# HOW TO EDIT:
#   - `label` must EXACTLY match the scraped "Line Item" text.
#   - `formula` documents how we'd conceptually re-derive this
#     subtotal from the raw items preceding it.
#   - Order in this list IS the canonical anchor order. Adding an
#     anchor here splits an existing zone into two smaller ones;
#     removing one merges two zones together.
#   - If you add/remove an anchor, also review
#     ZONE_SIGN_CONVENTION and NON_RECONCILABLE_ZONES below, since
#     those are keyed on (start_label, end_label) pairs.
# ==================================================================

IS_ANCHORS = [
    {"label": "Revenue",
     "formula": "N/A - top of statement"},
    {"label": "Gross Profit",
     "formula": "Revenue - Cost of Revenue"},
    {"label": "Operating Income",
     "formula": "Gross Profit - SG&A - R&D - Other Operating Expenses"},
    {"label": "Pretax Income",
     "formula": "Operating Income +/- Interest Inc/Exp +/- Other "
                "Non-Operating Items (equity earnings, FX, gains/"
                "losses on sale, impairments, legal settlements)"},
    {"label": "Net Income",
     "formula": "Pretax Income - Income Tax Expense +/- Discontinued "
                "Ops +/- Minority Interest"},
    {"label": "EPS (Diluted)",
     "formula": "Net Income to Common / Diluted Shares Outstanding "
                "(NOT additive - excluded from $ reconciliation)"},
]

# ------------------------------------------------------------------
# FIX D — Sentinel bookend anchors.
# Virtual anchors representing "top of statement" and "bottom of
# statement" so that items outside the real anchor range still get
# a canonical slot. These are never dollar-reconciled.
# ------------------------------------------------------------------
SENTINEL_START = "__TOP_OF_STATEMENT__"
SENTINEL_END = "__BOTTOM_OF_STATEMENT__"

ANCHOR_LABELS = {a["label"] for a in IS_ANCHORS} | {SENTINEL_START, SENTINEL_END}


# ==================================================================
# NON-ADDITIVE ROWS
# ==================================================================
# Growth %, margin %, per-share metrics and share counts are never
# summed into a dollar reconciliation. Detected by keyword because
# new variants appear constantly (e.g. "<anything> Growth").
# ==================================================================

NON_ADDITIVE_KEYWORDS = [
    "growth", "margin", "per share",
    "shares outstanding", "shares change", "eps",
]


# ==================================================================
# FIX B — KNOWN INTRA-ZONE SUBTOTALS
# ==================================================================
# Rollup rows that are NOT reliably bold on the site. Summing these
# alongside their own components double-counts and guarantees a
# reconciliation failure.
#
# Two detection strategies:
#   1. EXACT MATCH for subtotals whose label varies too much to
#      generalize (e.g. "Operating Expenses").
#   2. PREFIX MATCH for subtotals that follow a site-wide naming
#      convention:
#        - "Total ___" (confirmed across IS AND CFS: "Total
#          Operating Expenses", "Total Interest Income", "Total
#          Interest Expense", "Total Non-Interest Income/Expense",
#          "Total Debt Repaid", "Total Legal Settlements", etc.)
#        - "Earnings From Continuing ___" (structurally ALWAYS
#          equals Pretax Income - Income Tax Expense, regardless of
#          exact suffix wording -- confirmed two variants in the
#          wild: "Earnings From Continuing Operations" (MMM, ABT,
#          BRK.B) vs "Earnings From Continuing Ops." (AES))
#
# HOW TO EDIT: if a zone's pass rate is suspiciously low, run
# MODE = "debug" on a sample failing ticker (see
# zone_failure_examples_IS.csv for real candidates). If you see a
# row whose value equals the sum/derivation of its neighbors, add
# its exact label to the set below, or a new prefix if it looks
# like a recurring naming pattern rather than a one-off.
# ==================================================================

KNOWN_INTRA_ZONE_SUBTOTALS = {
    "Operating Expenses",
    "EBT Excluding Unusual Items",
    "Earnings From Continuing Operations",
    "Net Income to Company",
    "Net Income to Common",
    "Net Interest Expense",   # rollup of Interest Expense + Interest Income
}

SUBTOTAL_PREFIXES = (
    "total ",                     # Total Operating Expenses, Total Interest
                                   # Income/Expense, Total Non-Interest
                                   # Income/Expense, etc.
    "earnings from continuing",   # catches both "...Operations" and
                                   # "...Ops." variants
)


def is_known_subtotal(label) -> bool:
    """True if `label` is a nested subtotal that should be excluded
    from zone summation, via either an exact match or a known
    naming-convention prefix. See KNOWN_INTRA_ZONE_SUBTOTALS /
    SUBTOTAL_PREFIXES above for the evidence behind each entry."""
    stripped = str(label).strip()
    if stripped in KNOWN_INTRA_ZONE_SUBTOTALS:
        return True
    lower = stripped.lower()
    return any(lower.startswith(p) for p in SUBTOTAL_PREFIXES)

# ==================================================================
# FIX C — SIGN CONVENTION
# ==================================================================
# stockanalysis.com uses TWO different sign conventions depending on
# where you are in the statement:
#
#   "SUBTRACT"    - components are reported as POSITIVE MAGNITUDES
#                   but represent a subtraction in the waterfall.
#                   Typical of expense-style zones.
#   "AS_REPORTED" - components already carry their own sign and
#                   should be summed as-is.
#
# Verified against MMM (FY2025):
#   Rev->GP : Cost of Revenue 14,990 positive -> must SUBTRACT
#             (24,948 - 14,990 = 9,958 = Gross Profit)  ✓
#   GP->OI  : SG&A 4,081 and R&D 1,169 positive -> must SUBTRACT
#   OI->PI  : Interest Expense already -946 -> AS_REPORTED
#   PI->NI  : MIXED. Income Tax Expense 1,003 is positive and must
#             be subtracted, but Minority Interest -12 is already
#             signed. Hence the per-item override lists below.
#
# HOW TO EDIT: change the zone default first; only add per-item
# overrides for genuine exceptions within a zone.
# ==================================================================

ZONE_SIGN_CONVENTION = {
    ("Revenue", "Gross Profit"): "SUBTRACT",
    ("Gross Profit", "Operating Income"): "SUBTRACT",
    ("Operating Income", "Pretax Income"): "AS_REPORTED",
    ("Pretax Income", "Net Income"): "AS_REPORTED",
    # Financial-sector companies (banks, utilities) often skip
    # straight from Revenue to Operating Income or Pretax Income
    # with no Gross Profit line. Their in-between items (Salaries,
    # Occupancy, SG&A, Operating Expenses) are positive magnitudes
    # needing subtraction, same convention as Revenue->Gross Profit.
    # Verified against AES (utility) and BAC (bank).
    ("Revenue", "Operating Income"): "SUBTRACT",
    ("Revenue", "Pretax Income"): "SUBTRACT",
}

# Per-item overrides. These BEAT the zone default, in both
# directions. Labels must match the scraped text exactly.
SUBTRACT_SIGN_ITEMS = {
    "Income Tax Expense",
}

AS_REPORTED_ITEMS = {
    # Add a label here if it lives in a "SUBTRACT" zone but is
    # genuinely pre-signed (e.g. an income item sitting among
    # expenses).
}


# ==================================================================
# NON-RECONCILABLE ZONES
# ==================================================================
# Zones where a dollar-based check is fundamentally invalid, so we
# auto-trust them instead of validating.
#
#   Net Income -> EPS (Diluted): bridges a $ figure to a per-share
#       ratio. There is no additive dollar path between them, so
#       this zone failed 100% of the time when validated.
#   Sentinel zones: contain informational metrics (EBITDA, EBIT,
#       margins, Effective Tax Rate) with no single defined bridge.
# ==================================================================

NON_RECONCILABLE_ZONES = {
    ("Net Income", "EPS (Diluted)"),
    (SENTINEL_START, "Revenue"),
    ("EPS (Diluted)", SENTINEL_END),
}


# ==================================================================
# HELPERS
# ==================================================================

def is_non_additive(label: str) -> bool:
    lower = str(label).lower()
    return any(kw in lower for kw in NON_ADDITIVE_KEYWORDS)


def parse_numeric(value):
    """Scraped value -> float. Missing/dash/NaN is treated as 0.0
    since a dash on this site means zero / not applicable. Returns
    None only if genuinely unparseable text, which causes the
    sample to be skipped.

    NOTE: NaN must be checked explicitly with pd.isna() BEFORE the
    isinstance(value, (int, float)) check below, because
    isinstance(float('nan'), float) is True in Python — without
    this check, NaN silently passes through unchanged and poisons
    any sum it's added to (nan + x = nan), which was causing
    false-negative zone reconciliation failures whenever a company
    was legitimately missing a line item (Impairment of Goodwill,
    Legal Settlements, Discontinued Ops, etc.) rather than an
    actual data/formula problem.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        if pd.isna(value):
            return 0.0
        return float(value)
    cleaned = str(value).replace(",", "").replace("$", "").strip()
    if cleaned in ("", "-", "\u2014"):
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return None


def compute_signed_value(label, raw_value, zone_key):
    """
    FIX C — single source of truth for sign handling.

    Used by BOTH validate_ticker_zones() and debug_ticker() so the
    debugger can never disagree with the real validator.

    Returns (signed_value, was_flipped) or (None, False) if the raw
    value couldn't be parsed.
    """
    val = parse_numeric(raw_value)
    if val is None:
        return None, False

    label = str(label).strip()
    zone_default = ZONE_SIGN_CONVENTION.get(zone_key, "AS_REPORTED")

    if label in SUBTRACT_SIGN_ITEMS:
        return -val, True
    if label in AS_REPORTED_ITEMS:
        return val, False
    if zone_default == "SUBTRACT":
        return -val, True
    return val, False


def get_additive_rows(zone_rows):
    """
    A row counts toward the zone sum only if it is:
      - NOT bold (auto-detected nested subtotal), AND
      - NOT a known subtotal by exact match or naming prefix
        (see is_known_subtotal), AND
      - NOT a non-additive metric (growth/margin/per-share)

    Each mask is explicitly cast to plain numpy bool before
    combining with `&` to avoid a pandas dtype deprecation warning
    that can occur after pd.concat() across table fragments leaves
    "Line Item" backed by a nullable string dtype.
    """
    mask_not_bold = (~zone_rows["IsBold"]).astype(bool)
    mask_not_subtotal = (~zone_rows["Line Item"].apply(
        is_known_subtotal)).astype(bool)
    mask_not_nonadditive = (~zone_rows["Line Item"].apply(
        is_non_additive)).astype(bool)

    return zone_rows[mask_not_bold & mask_not_subtotal & mask_not_nonadditive]


# ==================================================================
# SCRAPER (captures the `bolded` CSS class per row)
# ==================================================================

class StyledStatementClient:
    """
    Same fetch logic as StockAnalysisClient in line_item_scraper.py,
    but additionally returns an `IsBold` column, detected from
    class="bolded ..." on each row's first <td>. Confirmed via live
    inspection of the Gross Profit row's HTML.
    """

    def fetch_statement(self, ticker: str, statement_type: str):
        ticker_lower = ticker.lower()
        urls = {
            "IS": f"https://stockanalysis.com/stocks/{ticker_lower}/financials/income-statement/",
            "BS": f"https://stockanalysis.com/stocks/{ticker_lower}/financials/balance-sheet/",
            "CFS": f"https://stockanalysis.com/stocks/{ticker_lower}/financials/cash-flow-statement/",
            "Ratios": f"https://stockanalysis.com/stocks/{ticker_lower}/financials/ratios/",
        }
        url = urls.get(statement_type)
        if url is None:
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

        raw_table, header_signature = None, None
        for table in tables:
            if len(table.find_all("tr")) > 5 and len(table.find_all("th")) > 2:
                raw_table = table
                header_signature = self._table_header(table)
                break
        if raw_table is None:
            return None

        matching_tables = [
            t for t in tables if self._table_header(t) == header_signature
        ]

        dfs = []
        for t in matching_tables:
            df_part = self._parse_table_with_bold(t)
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

        # FIX A — force IsBold to a genuine boolean dtype. pd.concat
        # across table fragments can otherwise leave it as object or
        # NaN, which triggers Pandas4Warning on `~df["IsBold"]` and
        # makes bold detection silently unreliable.
        if "IsBold" in df.columns:
            df["IsBold"] = df["IsBold"].fillna(False).astype(bool)
        else:
            df["IsBold"] = False

        return df

    def _table_header(self, table):
        tr = table.find("tr")
        if not tr:
            return None
        return tuple(c.get_text(strip=True) for c in tr.find_all(["th", "td"]))

    def _parse_table_with_bold(self, table):
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
            if not cells:
                continue

            row = [cell.get_text(strip=True) for cell in cells]
            first = row[0].strip().lower()
            if first in {"fiscal year", "period ending"}:
                continue

            first_cell_classes = cells[0].get("class", [])
            is_bold = "bolded" in first_cell_classes

            if len(row) < len(headers):
                row.extend([None] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[:len(headers)]

            row.append(is_bold)
            data.append(row)

        if not data:
            return pd.DataFrame()

        result = pd.DataFrame(data, columns=headers + ["IsBold"])
        result["IsBold"] = result["IsBold"].fillna(False).astype(bool)  # FIX A
        return result

    def _clean_financial_table(self, df):
        junk_values = ["-", "N/A", "NA", "", "\u2014", None]
        for col in df.columns:
            if col == "IsBold":
                continue
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
            if col == "IsBold":
                continue
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
            rename_map[fy_cols[year]] = "LFY" if idx == 0 else f"LFY-{idx}"
        if rename_map:
            df.rename(columns=rename_map, inplace=True)
        return df


# ==================================================================
# STEP 1 — Locate anchors & build zones for a single ticker
# ==================================================================

def locate_anchor_positions(df, include_sentinels=True):
    """
    Returns {anchor_label: row_index}. Missing anchors are omitted.

    FIX D — sentinels are injected at index -1 (above the first row)
    and len(df) (below the last row) so that items outside the real
    anchor range still fall inside a zone.
    """
    positions = {}
    labels = [str(x).strip() for x in df["Line Item"].tolist()]

    for anchor in IS_ANCHORS:
        try:
            positions[anchor["label"]] = labels.index(anchor["label"])
        except ValueError:
            continue

    if include_sentinels:
        positions[SENTINEL_START] = -1
        positions[SENTINEL_END] = len(df)

    return positions


def build_zones(anchor_positions):
    """
    Returns [(start_label, start_idx, end_label, end_idx), ...] for
    consecutive found anchors. Returns None if the found anchors
    aren't in increasing row order (anomalous statement layout).
    """
    ordered_labels = (
        [SENTINEL_START]
        + [a["label"] for a in IS_ANCHORS]
        + [SENTINEL_END]
    )

    found = [
        (label, anchor_positions[label])
        for label in ordered_labels
        if label in anchor_positions
    ]

    indices = [idx for _, idx in found]
    if indices != sorted(indices):
        return None

    return [
        (found[i][0], found[i][1], found[i + 1][0], found[i + 1][1])
        for i in range(len(found) - 1)
    ]


# ==================================================================
# STEP 2 — Reconciliation validation
# ==================================================================

def validate_ticker_zones(df, zones, value_columns, ticker=None,
                           zone_failure_examples=None,
                           max_examples_per_zone=15):
    """
    ...
    If `zone_failure_examples` is provided, logs up to
    `max_examples_per_zone` UNIQUE TICKERS per zone (not rows) — a
    single ticker failing across all 5 fiscal-year columns should
    only cost one "slot" in the sample, not five, otherwise a
    handful of chronically-failing tickers crowd out the diversity
    needed to spot a real pattern.
    """
    results = {}

    for start_label, start_idx, end_label, end_idx in zones:
        zone_key = (start_label, end_label)
        if zone_key in NON_RECONCILABLE_ZONES:
            continue

        zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]
        additive_rows = get_additive_rows(zone_rows)

        for col in value_columns:
            if col not in df.columns:
                continue

            total = 0.0
            skip_column = False

            for _, row in additive_rows.iterrows():
                signed, _flipped = compute_signed_value(
                    row["Line Item"], row[col], zone_key
                )
                if signed is None:
                    skip_column = True
                    break
                total += signed

            if skip_column:
                continue

            start_val = parse_numeric(df.loc[start_idx, col])
            end_val = parse_numeric(df.loc[end_idx, col])
            if start_val is None or end_val is None:
                continue

            reported_delta = end_val - start_val
            tolerance = max(1.0, abs(reported_delta) * 0.02)
            diff = total - reported_delta
            is_valid = abs(diff) <= tolerance
            results[(start_label, end_label, col)] = is_valid

            if not is_valid and zone_failure_examples is not None:
                bucket = zone_failure_examples.setdefault(zone_key, [])
                tickers_already_logged = {ex["ticker"] for ex in bucket}
                if (ticker not in tickers_already_logged
                        and len(tickers_already_logged) < max_examples_per_zone):
                    bucket.append({
                        "ticker": ticker,
                        "column": col,
                        "calculated": round(total, 1),
                        "reported": round(reported_delta, 1),
                        "diff": round(diff, 1),
                    })

    return results


def zone_is_trustworthy(validation_results, start_label, end_label,
                         min_valid_fraction=0.5):
    """A ticker's zone is trusted if at least `min_valid_fraction` of
    its fiscal-year samples reconciled. Non-reconcilable zones are
    always trusted."""
    if (start_label, end_label) in NON_RECONCILABLE_ZONES:
        return True

    relevant = [
        v for (s, e, _), v in validation_results.items()
        if s == start_label and e == end_label
    ]
    if not relevant:
        return False
    return (sum(relevant) / len(relevant)) >= min_valid_fraction


# ==================================================================
# STEP 3 — Cross-ticker voting
# ==================================================================

def build_master_order(tickers, client, min_valid_fraction=0.5,
                        request_delay=0.3, max_examples_per_zone=5):
    """
    Scans every ticker's IS, keeps only zone assignments that pass
    reconciliation, and votes on each line item's canonical
    (zone, relative-position-within-zone).

    Also collects a handful of real failing-ticker examples per
    zone (see zone_failure_examples), for targeted debugging.
    """
    item_zone_votes = {}
    item_zone_positions = {}
    zone_recon_stats = {}
    zone_failure_examples = {}

    value_columns_priority = ["LFY", "LFY-1", "LFY-2", "LFY-3", "TTM"]

    progress_bar = tqdm(
        tickers,
        desc="Building IS canonical order",
        unit="ticker",
        file=sys.stdout,
        dynamic_ncols=True,
        mininterval=0.3,
        ascii=True,
    )

    for ticker in progress_bar:
        try:
            df = client.fetch_statement(ticker, "IS")
            if df is None or df.empty:
                continue

            df = df.reset_index(drop=True)
            anchor_positions = locate_anchor_positions(df)
            zones = build_zones(anchor_positions)
            if not zones:
                continue

            available_cols = [
                c for c in value_columns_priority if c in df.columns
            ]
            validation_results = validate_ticker_zones(
                df, zones, available_cols, ticker=ticker,
                zone_failure_examples=zone_failure_examples,
                max_examples_per_zone=max_examples_per_zone,
            )

            for (s, e, _col), is_valid in validation_results.items():
                zone_recon_stats.setdefault((s, e), {"pass": 0, "fail": 0})
                zone_recon_stats[(s, e)]["pass" if is_valid else "fail"] += 1

            for start_label, start_idx, end_label, end_idx in zones:
                if not zone_is_trustworthy(validation_results, start_label,
                                            end_label, min_valid_fraction):
                    continue

                zone_span = end_idx - start_idx
                if zone_span <= 0:
                    continue

                zone_key = (start_label, end_label)
                zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]

                for _, row in zone_rows.iterrows():
                    label = str(row["Line Item"]).strip()
                    if not label or label in ANCHOR_LABELS:
                        continue

                    item_zone_votes.setdefault(label, {})
                    item_zone_votes[label][zone_key] = (
                        item_zone_votes[label].get(zone_key, 0) + 1
                    )

                    rel_pos = (row.name - start_idx) / zone_span
                    item_zone_positions.setdefault(label, {}).setdefault(
                        zone_key, []
                    ).append(rel_pos)

        except Exception:
            continue

        finally:
            if request_delay:
                time.sleep(request_delay)

    return (item_zone_votes, item_zone_positions,
            zone_recon_stats, zone_failure_examples)


def resolve_canonical_positions(item_zone_votes, item_zone_positions,
                                 ambiguous_threshold=0.9):
    """Picks each item's modal zone + average relative position
    within it. Flags items below `ambiguous_threshold` confidence."""
    canonical, ambiguous = {}, {}

    for label, zone_votes in item_zone_votes.items():
        total_votes = sum(zone_votes.values())
        best_zone = max(zone_votes, key=zone_votes.get)
        confidence = zone_votes[best_zone] / total_votes

        positions = item_zone_positions[label][best_zone]
        avg_position = sum(positions) / len(positions)

        canonical[label] = {
            "zone": best_zone,
            "avg_position": avg_position,
            "confidence": confidence,
            "total_observations": total_votes,
        }
        if confidence < ambiguous_threshold:
            ambiguous[label] = zone_votes

    return canonical, ambiguous


# ==================================================================
# STEP 4a — Master DRAFT statement
# ==================================================================

def build_master_draft_statement(canonical):
    """
    Every unique universe line item plus the anchors, in full
    canonical top-to-bottom order — as if one hypothetical company
    reported EVERYTHING. This is the artifact to sanity-check by
    hand before trusting the ordering.
    """
    rows = []
    ordered_labels = (
        [SENTINEL_START]
        + [a["label"] for a in IS_ANCHORS]
        + [SENTINEL_END]
    )

    for i in range(len(ordered_labels) - 1):
        start_label = ordered_labels[i]
        end_label = ordered_labels[i + 1]

        if start_label not in (SENTINEL_START, SENTINEL_END):
            rows.append({
                "Line Item": start_label,
                "Type": "ANCHOR",
                "Confidence": None,
            })

        zone_items = [
            (label, info) for label, info in canonical.items()
            if info["zone"] == (start_label, end_label)
        ]
        zone_items.sort(key=lambda x: x[1]["avg_position"])

        for label, info in zone_items:
            rows.append({
                "Line Item": label,
                "Type": "component",
                "Confidence": round(info["confidence"], 2),
            })

    # Close out the final real anchor
    last_real = IS_ANCHORS[-1]["label"]
    if not any(r["Line Item"] == last_real and r["Type"] == "ANCHOR"
               for r in rows):
        rows.append({
            "Line Item": last_real,
            "Type": "ANCHOR",
            "Confidence": None,
        })

    return rows


# ==================================================================
# STEP 4b — Subject-company-specific template
# ==================================================================

def build_subject_company_template(subject_ticker, client, canonical):
    """
    1. Backbone = the Subject Company's OWN real line-item order.
    2. Any universe item NOT present gets spliced in at its
       statistically-learned position as a placeholder.
    """
    df = client.fetch_statement(subject_ticker, "IS")
    if df is None or df.empty:
        raise ValueError(f"Could not fetch IS for {subject_ticker}")

    df = df.reset_index(drop=True)
    subject_labels = [str(x).strip() for x in df["Line Item"].tolist()]
    subject_label_set = set(subject_labels)
    anchor_positions = locate_anchor_positions(df)

    rows = [
        {"sort_key": float(idx), "Line Item": label,
         "Source": "subject", "Confidence": None}
        for idx, label in enumerate(subject_labels)
    ]

    skipped = []
    for label, info in canonical.items():
        if label in subject_label_set:
            continue

        start_label, end_label = info["zone"]
        if (start_label not in anchor_positions
                or end_label not in anchor_positions):
            skipped.append(label)
            continue

        start_idx = anchor_positions[start_label]
        end_idx = anchor_positions[end_label]
        span = end_idx - start_idx
        if span <= 0:
            skipped.append(label)
            continue

        target_key = start_idx + info["avg_position"] * span

        rows.append({
            "sort_key": target_key,
            "Line Item": label,
            "Source": "inserted",
            "Confidence": round(info["confidence"], 2),
        })

    rows.sort(key=lambda r: r["sort_key"])

    if skipped:
        print(f"\nNOTE: {len(skipped)} universe items skipped for "
              f"{subject_ticker} — their zone anchors don't exist in "
              f"its own statement:\n  {skipped}")

    return rows


# ==================================================================
# DEBUGGER
# ==================================================================

def debug_ticker(ticker, client, value_column="LFY"):
    """
    Prints the full reconciliation math for ONE ticker: every row,
    its bold flag, its sign treatment, and calculated-vs-reported
    delta per zone.

    Run this BEFORE any full 503-ticker run when tuning
    KNOWN_INTRA_ZONE_SUBTOTALS or the sign lists — it turns a
    7-minute feedback loop into about one second.

    Uses compute_signed_value() and get_additive_rows(), the exact
    same helpers the real validator uses, so the two can't drift.
    """
    df = client.fetch_statement(ticker, "IS")
    if df is None or df.empty:
        print(f"!! No data for {ticker}")
        return
    df = df.reset_index(drop=True)

    if value_column not in df.columns:
        print(f"!! Column '{value_column}' not found. "
              f"Available: {list(df.columns)}")
        return

    print(f"\n{'=' * 74}")
    print(f"{ticker} — raw rows (column: {value_column})")
    print(f"{'=' * 74}")
    print(f"{'idx':>4} {'bold':>6} {'value':>14}  Line Item")
    for idx, row in df.iterrows():
        print(f"{idx:>4} {str(row['IsBold']):>6} "
              f"{str(row[value_column]):>14}  {row['Line Item']}")

    anchor_positions = locate_anchor_positions(df)
    zones = build_zones(anchor_positions)
    if not zones:
        print("\n!! No valid zones built (anchors out of order or missing)")
        return

    print(f"\n{'=' * 74}")
    print("ZONE RECONCILIATION")
    print(f"{'=' * 74}")

    for start_label, start_idx, end_label, end_idx in zones:
        zone_key = (start_label, end_label)
        header = f"[{start_label} -> {end_label}]"

        if zone_key in NON_RECONCILABLE_ZONES:
            zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]
            print(f"\n{header}  AUTO-TRUSTED (non-reconcilable)")
            for _, row in zone_rows.iterrows():
                print(f"        {'':>14}  {row['Line Item']}")
            continue

        convention = ZONE_SIGN_CONVENTION.get(zone_key, "AS_REPORTED")
        print(f"\n{header}  convention={convention}")

        zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]
        additive_rows = get_additive_rows(zone_rows)

        excluded = zone_rows[~zone_rows.index.isin(additive_rows.index)]
        for _, row in excluded.iterrows():
            if row["IsBold"]:
                reason = "bold"
            elif is_known_subtotal(row["Line Item"]):
                reason = "known subtotal"
            else:
                reason = "non-additive"
            print(f"    [skip:{reason:<15}] {'':>12}  {row['Line Item']}")

        total = 0.0
        for _, row in additive_rows.iterrows():
            signed, flipped = compute_signed_value(
                row["Line Item"], row[value_column], zone_key
            )
            if signed is None:
                print(f"    [UNPARSEABLE       ] "
                      f"{str(row[value_column]):>12}  {row['Line Item']}")
                continue
            total += signed
            print(f"    {'(FLIP)' if flipped else '      '}"
                  f"{'':>13} {signed:>12,.1f}  {row['Line Item']}")

        start_val = parse_numeric(df.loc[start_idx, value_column])
        end_val = parse_numeric(df.loc[end_idx, value_column])
        reported = end_val - start_val
        tolerance = max(1.0, abs(reported) * 0.02)
        passed = abs(total - reported) <= tolerance

        print(f"    {'-' * 60}")
        print(f"    calculated: {total:>14,.1f}")
        print(f"    reported:   {reported:>14,.1f}   "
              f"({end_label} {end_val:,.1f} - {start_label} {start_val:,.1f})")
        print(f"    diff:       {total - reported:>14,.1f}   "
              f"(tolerance {tolerance:,.1f})")
        print(f"    ==> {'PASS' if passed else 'FAIL'}")


# ==================================================================
# CSV EXPORTS
# ==================================================================

def export_canonical_order(canonical, filepath="canonical_order_IS.csv"):
    rows = sorted(
        canonical.items(),
        key=lambda kv: (kv[1]["zone"], kv[1]["avg_position"])
    )
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Zone Start", "Zone End", "Avg Position",
                    "Confidence", "Observations"])
        for label, info in rows:
            w.writerow([label, info["zone"][0], info["zone"][1],
                        round(info["avg_position"], 3),
                        round(info["confidence"], 3),
                        info["total_observations"]])
    print(f"Wrote {len(rows)} canonical items -> {filepath}")


def export_ambiguous_items(ambiguous, filepath="ambiguous_items_IS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Zone Votes (start->end : count)"])
        for label, zone_votes in ambiguous.items():
            vote_str = "; ".join(
                f"{s}->{e}: {c}" for (s, e), c in zone_votes.items()
            )
            w.writerow([label, vote_str])
    print(f"Wrote {len(ambiguous)} ambiguous items -> {filepath}")


def export_zone_reconciliation_summary(
        zone_recon_stats, filepath="zone_reconciliation_summary_IS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Zone Start", "Zone End", "Pass Count",
                    "Fail Count", "Pass Rate"])
        for (start, end), stats in zone_recon_stats.items():
            total = stats["pass"] + stats["fail"]
            rate = stats["pass"] / total if total else 0
            w.writerow([start, end, stats["pass"], stats["fail"],
                        round(rate, 3)])
    print(f"Wrote zone reconciliation summary -> {filepath}")

    print("\n=== Zone Reconciliation Pass Rates ===")
    for (start, end), stats in zone_recon_stats.items():
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0
        print(f"  {start} -> {end}: {rate:.1%}  "
              f"({stats['pass']} pass / {stats['fail']} fail)")


def export_master_draft(rows, filepath="master_draft_IS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Type", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Type"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


def export_subject_template(rows, filepath="subject_template_IS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Source", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Source"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")

def export_zone_failure_examples(zone_failure_examples,
                                  filepath="zone_failure_examples_IS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Zone Start", "Zone End", "Ticker", "Column",
                    "Calculated", "Reported", "Diff"])
        for (start, end), examples in zone_failure_examples.items():
            for ex in examples:
                w.writerow([start, end, ex["ticker"], ex["column"],
                            ex["calculated"], ex["reported"], ex["diff"]])
    print(f"Wrote {sum(len(v) for v in zone_failure_examples.values())} "
          f"failure examples -> {filepath}")

# ==================================================================
# MAIN
# ==================================================================
# MODE = "debug" -> ~1 second, one ticker, prints all recon math.
#                   Use this while tuning subtotal/sign lists.
# MODE = "full"  -> ~7 minutes, all 503 tickers, writes the CSVs.
# ==================================================================

MODE = "debug" 

TICKER_FILE = "constituents.csv"
SUBJECT_TICKER = "MMM"
DEBUG_TICKERS = ["AON", "AJG", "APA", "ADM"]
DEBUG_COLUMN = "LFY"


if __name__ == "__main__":
    client = StyledStatementClient()

    if MODE == "debug":
        for t in DEBUG_TICKERS:
            debug_ticker(t, client, value_column=DEBUG_COLUMN)
            time.sleep(0.3)

    elif MODE == "full":
        tickers = load_tickers_from_file(TICKER_FILE, column="Symbol")
        print(f"Loaded {len(tickers)} tickers from {TICKER_FILE}")

        (item_zone_votes, item_zone_positions,
         zone_recon_stats, zone_failure_examples) = build_master_order(
            tickers, client, min_valid_fraction=0.5, request_delay=0.3,
            max_examples_per_zone=15
        )

        canonical, ambiguous = resolve_canonical_positions(
            item_zone_votes, item_zone_positions, ambiguous_threshold=0.9
        )

        export_canonical_order(canonical)
        export_ambiguous_items(ambiguous)
        export_zone_reconciliation_summary(zone_recon_stats)
        export_zone_failure_examples(zone_failure_examples)

        draft_rows = build_master_draft_statement(canonical)
        export_master_draft(draft_rows)

        subject_rows = build_subject_company_template(
            SUBJECT_TICKER, client, canonical
        )
        export_subject_template(
            subject_rows, f"subject_template_IS_{SUBJECT_TICKER}.csv"
        )

    else:
        raise ValueError(f"Unknown MODE: {MODE!r} (expected 'debug' or 'full')")