"""
============================================================
BALANCE SHEET CANONICAL ORDERING ENGINE
============================================================

STRUCTURAL DIFFERENCE FROM INCOME STATEMENT:
IS is one continuous waterfall (Revenue -> ... -> Net Income) where
every zone is "delta between two adjacent anchors". BS is instead
THREE INDEPENDENT ADDITIVE CHAINS that each start fresh at an
implied value of zero:

    Assets:      0 -> Total Current Assets -> Total Assets
    Liabilities: 0 -> Total Current Liabilities -> Total Liabilities
    Equity:      0 -> Shareholders' Equity

...plus a GLOBAL IDENTITY CHECK that doesn't fit the zone-delta
pattern at all: Total Assets == Total Liabilities & Equity (the
fundamental balance sheet equation), checked separately.

CONFIRMED VIA MMM, FY2023 (hand-verified before writing any code):
  Current Assets components  -> Total Current Assets:  16,379 = 16,379
  Non-current Assets         -> Total Assets:           34,201 = 34,201
  Current Liabilities        -> Total Current Liab.:    15,297 = 15,297
  Non-current Liabilities    -> Total Liabilities:      30,415 = 30,415
  Equity components + Minority Interest -> Sh. Equity:   4,868 =  4,868
  Total Assets == Total Liabilities & Equity:           50,580 = 50,580

UNLIKE IS: no sign flips are needed anywhere. Every BS line item is
stored with its natural contribution sign already applied (assets
positive, Treasury Stock / Comprehensive Income negative), so every
zone reconciles via straight addition (AS_REPORTED convention
throughout). This is intentionally left as a per-zone-configurable
convention (see ZONE_SIGN_CONVENTION_BS) in case a real exception
turns up during the 503-ticker run, mirroring IS's infrastructure.

CONFIRMED NESTED SUBTOTALS (excluded from summation, same
bold-detection + manual-list belt-and-suspenders approach as IS):
    "Cash & Short-Term Investments" = Cash & Equivalents + ST Investments
    "Receivables"                   = Accounts Receivable + Other Receivables
    "Total Common Equity"           = Common Stock + APIC + Retained
                                       Earnings + Treasury Stock +
                                       Comprehensive Income & Other
                                       (caught automatically by the
                                       "total " prefix rule, same as IS)

KNOWN GAP, DELIBERATELY PARKED (same treatment as IS's financials
sector): banks/insurers with unclassified balance sheets (no
Current/Non-Current split) will contribute zero votes to the
Current-vs-Total zones. Not fixed here, same reasoning as IS.

Reuses StyledStatementClient, parse_numeric, is_non_additive, and
resolve_canonical_positions from income_statement_canonical_order.py
rather than re-implementing them a second time.
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
    is_non_additive,
    resolve_canonical_positions,
)


# ==================================================================
# ANCHOR DEFINITIONS
# ==================================================================
# The six fixed checkpoint subtotals, in the order they physically
# appear on stockanalysis.com's STANDARDIZED Balance Sheet view.
#
# HOW TO EDIT: labels must EXACTLY match the scraped "Line Item"
# text. Order matters for section-boundary detection in
# build_bs_zones() below (e.g. "Total Assets" marks the end of the
# Assets table and the implied start of the Liabilities table).
# ==================================================================

BS_ANCHOR_LABELS_IN_ORDER = [
    "Total Current Assets",
    "Total Assets",
    "Total Current Liabilities",
    "Total Liabilities",
    "Shareholders' Equity",
    "Total Liabilities & Equity",
]

ANCHOR_LABELS = set(BS_ANCHOR_LABELS_IN_ORDER)

# Virtual zone-start labels representing "top of a section, implied
# value = 0". These never appear in scraped data - they're synthetic
# markers used only internally for zone bookkeeping and canonical
# ordering.
SENTINEL_ASSETS_START = "__ASSETS_START__"
SENTINEL_LIABILITIES_START = "__LIABILITIES_START__"
SENTINEL_EQUITY_START = "__EQUITY_START__"
SENTINEL_END = "__BOTTOM_OF_STATEMENT__"


# ==================================================================
# KNOWN INTRA-ZONE SUBTOTALS (BS-specific)
# ==================================================================
KNOWN_INTRA_ZONE_SUBTOTALS_BS = {
    "Cash & Short-Term Investments",
    # "Receivables" removed - handled dynamically in is_known_subtotal_bs
}

SUBTOTAL_PREFIXES_BS = (
    "total ",   # catches "Total Common Equity" automatically
)


def is_known_subtotal_bs(label, zone_rows=None) -> bool:
    stripped = str(label).strip()

    # Always a subtotal
    if stripped in KNOWN_INTRA_ZONE_SUBTOTALS_BS:
        return True

    # Only a subtotal if its components are also present in the zone
    if stripped == "Receivables":
        if zone_rows is not None:
            zone_labels = set(zone_rows["Line Item"].astype(str).str.strip())
            return "Accounts Receivable" in zone_labels or "Other Receivables" in zone_labels
        return True  # conservative fallback

    lower = stripped.lower()
    return any(lower.startswith(p) for p in SUBTOTAL_PREFIXES_BS)


def get_additive_rows_bs(zone_rows):
    mask_not_bold = (~zone_rows["IsBold"]).astype(bool)
    mask_not_subtotal = (~zone_rows["Line Item"].apply(
        lambda label: is_known_subtotal_bs(label, zone_rows)
    )).astype(bool)
    mask_not_nonadditive = (~zone_rows["Line Item"].apply(
        is_non_additive)).astype(bool)
    return zone_rows[mask_not_bold & mask_not_subtotal & mask_not_nonadditive]


# ==================================================================
# SIGN CONVENTION (BS-specific)
# ==================================================================
# Unlike IS, every BS line item is stored pre-signed (assets
# positive, contra accounts like Treasury Stock already negative),
# so the default is pure addition everywhere. Kept as configurable
# infrastructure in case the 503-ticker run reveals a real exception
# (e.g. a company storing Treasury Stock as a positive "reduction"
# amount needing a flip).
# ==================================================================

ZONE_SIGN_CONVENTION_BS = {}   # empty = AS_REPORTED (straight sum) everywhere
SUBTRACT_SIGN_ITEMS_BS = set()
AS_REPORTED_ITEMS_BS = set()


def compute_signed_value_bs(label, raw_value, zone_key):
    val = parse_numeric(raw_value)
    if val is None:
        return None, False
    label = str(label).strip()
    zone_default = ZONE_SIGN_CONVENTION_BS.get(zone_key, "AS_REPORTED")
    if label in SUBTRACT_SIGN_ITEMS_BS:
        return -val, True
    if label in AS_REPORTED_ITEMS_BS:
        return val, False
    if zone_default == "SUBTRACT":
        return -val, True
    return val, False


# ==================================================================
# STEP 1 — Locate anchors & build the three independent zone chains
# ==================================================================

def locate_bs_anchor_positions(df):
    positions = {}
    labels = [str(x).strip() for x in df["Line Item"].tolist()]
    for anchor_label in BS_ANCHOR_LABELS_IN_ORDER:
        try:
            positions[anchor_label] = labels.index(anchor_label)
        except ValueError:
            continue
    return positions


def build_bs_zones(df, anchor_positions):
    """
    Returns a list of zone dicts, one per reconcilable (or trailing
    non-reconcilable) segment:
        {section, start_label, start_idx, start_value_override,
         end_label, end_idx, reconcilable}

    `start_value_override` is 0.0 for the implied-zero start of each
    of the three chains (Assets/Liabilities/Equity each begin fresh,
    unlike IS's single continuous waterfall). `start_idx` is still a
    REAL row index in all cases - used only for slicing which rows
    belong to the zone, not for value lookup when overridden.
    """
    zones = []
    n_rows = len(df)

    # ---- Assets chain: starts at row 0, implied value = 0 ----
    if "Total Current Assets" in anchor_positions:
        tca_idx = anchor_positions["Total Current Assets"]
        zones.append({
            "section": "Assets",
            "start_label": SENTINEL_ASSETS_START, "start_idx": -1,
            "start_value_override": 0.0,
            "end_label": "Total Current Assets", "end_idx": tca_idx,
            "reconcilable": True,
        })
        if "Total Assets" in anchor_positions:
            ta_idx = anchor_positions["Total Assets"]
            zones.append({
                "section": "Assets",
                "start_label": "Total Current Assets", "start_idx": tca_idx,
                "start_value_override": None,
                "end_label": "Total Assets", "end_idx": ta_idx,
                "reconcilable": True,
            })

    # ---- Liabilities chain: starts right after the Total Assets row ----
    if "Total Assets" in anchor_positions and "Total Current Liabilities" in anchor_positions:
        ta_idx = anchor_positions["Total Assets"]
        tcl_idx = anchor_positions["Total Current Liabilities"]
        zones.append({
            "section": "Liabilities",
            "start_label": SENTINEL_LIABILITIES_START, "start_idx": ta_idx,
            "start_value_override": 0.0,
            "end_label": "Total Current Liabilities", "end_idx": tcl_idx,
            "reconcilable": True,
        })
        if "Total Liabilities" in anchor_positions:
            tl_idx = anchor_positions["Total Liabilities"]
            zones.append({
                "section": "Liabilities",
                "start_label": "Total Current Liabilities", "start_idx": tcl_idx,
                "start_value_override": None,
                "end_label": "Total Liabilities", "end_idx": tl_idx,
                "reconcilable": True,
            })

    # ---- Equity chain: starts right after the Total Liabilities row ----
    if "Total Liabilities" in anchor_positions and "Shareholders' Equity" in anchor_positions:
        tl_idx = anchor_positions["Total Liabilities"]
        se_idx = anchor_positions["Shareholders' Equity"]
        zones.append({
            "section": "Equity",
            "start_label": SENTINEL_EQUITY_START, "start_idx": tl_idx,
            "start_value_override": 0.0,
            "end_label": "Shareholders' Equity", "end_idx": se_idx,
            "reconcilable": True,
        })

    # ---- Trailing informational zone: Total Liab&Equity -> end ----
    # Never reconciled (Additional Metrics: Total Debt, Net Cash,
    # Book Value Per Share, Land, Buildings, etc.) - same role as
    # IS's post-EPS sentinel zone. Note: Shareholders' Equity ->
    # Total Liabilities & Equity has ZERO component rows between
    # them and is NOT a same-section rollup (it's Total Liabilities
    # + Shareholders' Equity, a cross-section addition) - covered by
    # validate_bs_identity() instead, not as a zone here.
    if "Total Liabilities & Equity" in anchor_positions:
        tle_idx = anchor_positions["Total Liabilities & Equity"]
        zones.append({
            "section": "Trailing",
            "start_label": "Total Liabilities & Equity", "start_idx": tle_idx,
            "start_value_override": None,
            "end_label": SENTINEL_END, "end_idx": n_rows,
            "reconcilable": False,
        })

    return zones


def get_zone_start_value(df, zone, col):
    if zone["start_value_override"] is not None:
        return zone["start_value_override"]
    return parse_numeric(df.loc[zone["start_idx"], col])


# ==================================================================
# STEP 2 — Reconciliation validation (per independent chain)
# ==================================================================

def validate_bs_zones(df, zones, value_columns, ticker=None,
                       zone_failure_examples=None, max_examples_per_zone=15):
    """
    Same mechanics as IS's validate_ticker_zones, but each zone's
    "start value" may be an implied 0.0 (see start_value_override)
    rather than a real anchor lookup, since BS has three independent
    chains rather than one continuous waterfall.

    Failure examples are deduped by UNIQUE TICKER (not row), so a
    ticker failing across all 5 fiscal-year columns only costs one
    slot in the sample - this was a real bug caught during the IS
    build (AON alone ate 5 of a 15-slot budget) and is fixed here
    from the start.
    """
    results = {}

    for zone in zones:
        if not zone["reconcilable"]:
            continue

        zone_key = (zone["start_label"], zone["end_label"])
        start_idx, end_idx = zone["start_idx"], zone["end_idx"]
        zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]
        additive_rows = get_additive_rows_bs(zone_rows)

        for col in value_columns:
            if col not in df.columns:
                continue

            total = 0.0
            skip_column = False
            for _, row in additive_rows.iterrows():
                signed, _flipped = compute_signed_value_bs(
                    row["Line Item"], row[col], zone_key
                )
                if signed is None:
                    skip_column = True
                    break
                total += signed

            if skip_column:
                continue

            start_val = get_zone_start_value(df, zone, col)
            end_val = parse_numeric(df.loc[end_idx, col])
            if start_val is None or end_val is None:
                continue

            reported_delta = end_val - start_val
            tolerance = max(1.0, abs(reported_delta) * 0.02)
            diff = total - reported_delta
            is_valid = abs(diff) <= tolerance
            results[(zone["start_label"], zone["end_label"], col)] = is_valid

            if not is_valid and zone_failure_examples is not None:
                bucket = zone_failure_examples.setdefault(zone_key, [])
                tickers_logged = {ex["ticker"] for ex in bucket}
                if ticker not in tickers_logged and len(tickers_logged) < max_examples_per_zone:
                    bucket.append({
                        "ticker": ticker, "column": col,
                        "calculated": round(total, 1),
                        "reported": round(reported_delta, 1),
                        "diff": round(diff, 1),
                    })

    return results


def zone_is_trustworthy_bs(validation_results, start_label, end_label,
                            min_valid_fraction=0.5):
    relevant = [v for (s, e, _), v in validation_results.items()
                if s == start_label and e == end_label]
    if not relevant:
        return False
    return (sum(relevant) / len(relevant)) >= min_valid_fraction


# ==================================================================
# GLOBAL IDENTITY CHECKS
# ==================================================================
# These don't fit the zone-delta pattern (they're equalities between
# two independently-computed totals, not a component sum), so they're
# tracked and reported separately from the per-zone reconciliation.
# ==================================================================

def validate_bs_identity(df, anchor_positions, value_columns):
    """
    1. Total Assets == Total Liabilities & Equity
         (the fundamental balance sheet equation)
    2. Total Liabilities + Shareholders' Equity == Total Liabilities & Equity
         (confirms the final rollup itself, since there's no
         component zone between Shareholders' Equity and Total
         Liabilities & Equity to check any other way)
    """
    results = {"assets_eq_liab_and_equity": {}, "liab_plus_equity_eq_total": {}}

    for col in value_columns:
        if col not in df.columns:
            continue

        ta = (parse_numeric(df.loc[anchor_positions["Total Assets"], col])
              if "Total Assets" in anchor_positions else None)
        tle = (parse_numeric(df.loc[anchor_positions["Total Liabilities & Equity"], col])
               if "Total Liabilities & Equity" in anchor_positions else None)
        tl = (parse_numeric(df.loc[anchor_positions["Total Liabilities"], col])
              if "Total Liabilities" in anchor_positions else None)
        se = (parse_numeric(df.loc[anchor_positions["Shareholders' Equity"], col])
              if "Shareholders' Equity" in anchor_positions else None)

        if ta is not None and tle is not None:
            tolerance = max(1.0, abs(ta) * 0.02)
            results["assets_eq_liab_and_equity"][col] = abs(ta - tle) <= tolerance

        if tl is not None and se is not None and tle is not None:
            tolerance = max(1.0, abs(tle) * 0.02)
            results["liab_plus_equity_eq_total"][col] = abs((tl + se) - tle) <= tolerance

    return results


# ==================================================================
# STEP 3 — Cross-ticker voting
# ==================================================================

def build_master_order_bs(tickers, client, min_valid_fraction=0.5,
                           request_delay=0.3, max_examples_per_zone=15):
    item_zone_votes = {}
    item_zone_positions = {}
    zone_recon_stats = {}
    zone_failure_examples = {}
    identity_stats = {"assets_eq_liab_and_equity": {"pass": 0, "fail": 0},
                       "liab_plus_equity_eq_total": {"pass": 0, "fail": 0}}

    value_columns_priority = ["LFY", "LFY-1", "LFY-2", "LFY-3", "TTM"]

    progress_bar = tqdm(
        tickers, desc="Building BS canonical order", unit="ticker",
        file=sys.stdout, dynamic_ncols=True, mininterval=0.3, ascii=True,
    )

    for ticker in progress_bar:
        try:
            df = client.fetch_statement(ticker, "BS")
            if df is None or df.empty:
                continue

            df = df.reset_index(drop=True)
            anchor_positions = locate_bs_anchor_positions(df)
            zones = build_bs_zones(df, anchor_positions)
            if not zones:
                continue

            available_cols = [c for c in value_columns_priority if c in df.columns]

            validation_results = validate_bs_zones(
                df, zones, available_cols, ticker=ticker,
                zone_failure_examples=zone_failure_examples,
                max_examples_per_zone=max_examples_per_zone,
            )

            for (s, e, _col), is_valid in validation_results.items():
                zone_recon_stats.setdefault((s, e), {"pass": 0, "fail": 0})
                zone_recon_stats[(s, e)]["pass" if is_valid else "fail"] += 1

            identity_results = validate_bs_identity(df, anchor_positions, available_cols)
            for check_name, per_col in identity_results.items():
                for _col, is_valid in per_col.items():
                    identity_stats[check_name]["pass" if is_valid else "fail"] += 1

            for zone in zones:
                if not zone_is_trustworthy_bs(
                    validation_results, zone["start_label"], zone["end_label"],
                    min_valid_fraction
                ) and zone["reconcilable"]:
                    continue
                if not zone["reconcilable"]:
                    pass  # trailing zone always trusted for ordering purposes

                start_idx, end_idx = zone["start_idx"], zone["end_idx"]
                zone_span = end_idx - start_idx
                if zone_span <= 0:
                    continue

                zone_key = (zone["start_label"], zone["end_label"])
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
            zone_recon_stats, zone_failure_examples, identity_stats)


# ==================================================================
# STEP 4a — Master DRAFT statement
# ==================================================================

BS_ZONE_ORDER = [
    (SENTINEL_ASSETS_START, "Total Current Assets"),
    ("Total Current Assets", "Total Assets"),
    (SENTINEL_LIABILITIES_START, "Total Current Liabilities"),
    ("Total Current Liabilities", "Total Liabilities"),
    (SENTINEL_EQUITY_START, "Shareholders' Equity"),
]

BS_SECTION_HEADERS = {
    (SENTINEL_ASSETS_START, "Total Current Assets"): "Assets",
    (SENTINEL_LIABILITIES_START, "Total Current Liabilities"): "Liabilities",
    (SENTINEL_EQUITY_START, "Shareholders' Equity"): "Shareholders' Equity",
}


def build_master_draft_statement_bs(canonical):
    rows = []
    for zone_key in BS_ZONE_ORDER:
        header = BS_SECTION_HEADERS.get(zone_key)
        if header:
            rows.append({"Line Item": f"--- {header} ---",
                         "Type": "SECTION", "Confidence": None})

        zone_items = [(l, i) for l, i in canonical.items() if i["zone"] == zone_key]
        zone_items.sort(key=lambda x: x[1]["avg_position"])
        for label, info in zone_items:
            rows.append({"Line Item": label, "Type": "component",
                         "Confidence": round(info["confidence"], 2)})

        rows.append({"Line Item": zone_key[1], "Type": "ANCHOR", "Confidence": None})

    rows.append({"Line Item": "Total Liabilities & Equity",
                 "Type": "ANCHOR", "Confidence": None})
    return rows


# ==================================================================
# STEP 4b — Subject-company-specific template
# ==================================================================

def resolve_zone_start_idx_bs(anchor_positions, start_label):
    if start_label == SENTINEL_ASSETS_START:
        return -1
    if start_label == SENTINEL_LIABILITIES_START:
        return anchor_positions.get("Total Assets")
    if start_label == SENTINEL_EQUITY_START:
        return anchor_positions.get("Total Liabilities")
    return anchor_positions.get(start_label)


def build_subject_company_template_bs(subject_ticker, client, canonical):
    df = client.fetch_statement(subject_ticker, "BS")
    if df is None or df.empty:
        raise ValueError(f"Could not fetch BS for {subject_ticker}")

    df = df.reset_index(drop=True)
    subject_labels = [str(x).strip() for x in df["Line Item"].tolist()]
    subject_label_set = set(subject_labels)
    anchor_positions = locate_bs_anchor_positions(df)

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
        start_idx = resolve_zone_start_idx_bs(anchor_positions, start_label)
        end_idx = anchor_positions.get(end_label)

        if start_idx is None or end_idx is None:
            skipped.append(label)
            continue

        span = end_idx - start_idx
        if span <= 0:
            skipped.append(label)
            continue

        target_key = start_idx + info["avg_position"] * span
        rows.append({
            "sort_key": target_key, "Line Item": label,
            "Source": "inserted", "Confidence": round(info["confidence"], 2),
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

def debug_ticker_bs(ticker, client, value_column="LFY"):
    df = client.fetch_statement(ticker, "BS")
    if df is None or df.empty:
        print(f"!! No data for {ticker}")
        return
    df = df.reset_index(drop=True)

    if value_column not in df.columns:
        print(f"!! Column '{value_column}' not found. Available: {list(df.columns)}")
        return

    print(f"\n{'=' * 74}\n{ticker} — raw rows (column: {value_column})\n{'=' * 74}")
    print(f"{'idx':>4} {'bold':>6} {'value':>14}  Line Item")
    for idx, row in df.iterrows():
        print(f"{idx:>4} {str(row['IsBold']):>6} "
              f"{str(row[value_column]):>14}  {row['Line Item']}")

    anchor_positions = locate_bs_anchor_positions(df)
    zones = build_bs_zones(df, anchor_positions)
    if not zones:
        print("\n!! No valid zones built")
        return

    print(f"\n{'=' * 74}\nZONE RECONCILIATION\n{'=' * 74}")

    for zone in zones:
        zone_key = (zone["start_label"], zone["end_label"])
        header = f"[{zone['section']}] {zone['start_label']} -> {zone['end_label']}"

        if not zone["reconcilable"]:
            print(f"\n{header}  AUTO-TRUSTED (informational / non-reconcilable)")
            zone_rows = df[(df.index > zone["start_idx"]) & (df.index < zone["end_idx"])]
            for _, row in zone_rows.iterrows():
                print(f"        {'':>14}  {row['Line Item']}")
            continue

        print(f"\n{header}")
        zone_rows = df[(df.index > zone["start_idx"]) & (df.index < zone["end_idx"])]
        additive_rows = get_additive_rows_bs(zone_rows)

        excluded = zone_rows[~zone_rows.index.isin(additive_rows.index)]
        for _, row in excluded.iterrows():
            if row["IsBold"]:
                reason = "bold"
            elif is_known_subtotal_bs(row["Line Item"]):
                reason = "known subtotal"
            else:
                reason = "non-additive"
            print(f"    [skip:{reason:<15}] {'':>12}  {row['Line Item']}")

        total = 0.0
        for _, row in additive_rows.iterrows():
            signed, flipped = compute_signed_value_bs(
                row["Line Item"], row[value_column], zone_key
            )
            if signed is None:
                print(f"    [UNPARSEABLE       ] "
                      f"{str(row[value_column]):>12}  {row['Line Item']}")
                continue
            total += signed
            print(f"    {'(FLIP)' if flipped else '      '}"
                  f"{'':>13} {signed:>12,.1f}  {row['Line Item']}")

        start_val = get_zone_start_value(df, zone, value_column)
        end_val = parse_numeric(df.loc[zone["end_idx"], value_column])
        reported = end_val - start_val
        tolerance = max(1.0, abs(reported) * 0.02)
        passed = abs(total - reported) <= tolerance

        print(f"    {'-' * 60}")
        print(f"    calculated: {total:>14,.1f}")
        print(f"    reported:   {reported:>14,.1f}   "
              f"({zone['end_label']} {end_val:,.1f} - start {start_val:,.1f})")
        print(f"    diff:       {total - reported:>14,.1f}   (tolerance {tolerance:,.1f})")
        print(f"    ==> {'PASS' if passed else 'FAIL'}")

    print(f"\n{'=' * 74}\nGLOBAL IDENTITY CHECKS\n{'=' * 74}")
    identity_results = validate_bs_identity(df, anchor_positions, [value_column])
    ta = (parse_numeric(df.loc[anchor_positions["Total Assets"], value_column])
          if "Total Assets" in anchor_positions else None)
    tle = (parse_numeric(df.loc[anchor_positions["Total Liabilities & Equity"], value_column])
           if "Total Liabilities & Equity" in anchor_positions else None)
    tl = (parse_numeric(df.loc[anchor_positions["Total Liabilities"], value_column])
          if "Total Liabilities" in anchor_positions else None)
    se = (parse_numeric(df.loc[anchor_positions["Shareholders' Equity"], value_column])
          if "Shareholders' Equity" in anchor_positions else None)

    if ta is not None and tle is not None:
        result = identity_results["assets_eq_liab_and_equity"].get(value_column)
        print(f"  Total Assets ({ta:,.1f}) == Total Liab & Equity ({tle:,.1f})  "
              f"==> {'PASS' if result else 'FAIL'}")
    if tl is not None and se is not None and tle is not None:
        result = identity_results["liab_plus_equity_eq_total"].get(value_column)
        print(f"  Total Liabilities ({tl:,.1f}) + Sh. Equity ({se:,.1f}) = "
              f"{tl + se:,.1f}  vs  Total Liab & Equity ({tle:,.1f})  "
              f"==> {'PASS' if result else 'FAIL'}")


# ==================================================================
# CSV EXPORTS
# ==================================================================

def export_canonical_order_bs(canonical, filepath="canonical_order_BS.csv"):
    rows = sorted(canonical.items(), key=lambda kv: (kv[1]["zone"], kv[1]["avg_position"]))
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


def export_ambiguous_items_bs(ambiguous, filepath="ambiguous_items_BS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Zone Votes (start->end : count)"])
        for label, zone_votes in ambiguous.items():
            vote_str = "; ".join(f"{s}->{e}: {c}" for (s, e), c in zone_votes.items())
            w.writerow([label, vote_str])
    print(f"Wrote {len(ambiguous)} ambiguous items -> {filepath}")


def export_zone_reconciliation_summary_bs(
        zone_recon_stats, filepath="zone_reconciliation_summary_BS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Zone Start", "Zone End", "Pass Count", "Fail Count", "Pass Rate"])
        for (start, end), stats in zone_recon_stats.items():
            total = stats["pass"] + stats["fail"]
            rate = stats["pass"] / total if total else 0
            w.writerow([start, end, stats["pass"], stats["fail"], round(rate, 3)])
    print(f"Wrote zone reconciliation summary -> {filepath}")

    print("\n=== BS Zone Reconciliation Pass Rates ===")
    for (start, end), stats in zone_recon_stats.items():
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0
        print(f"  {start} -> {end}: {rate:.1%}  ({stats['pass']} pass / {stats['fail']} fail)")


def export_identity_check_summary(identity_stats, filepath="identity_check_summary_BS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Check", "Pass Count", "Fail Count", "Pass Rate"])
        for check_name, stats in identity_stats.items():
            total = stats["pass"] + stats["fail"]
            rate = stats["pass"] / total if total else 0
            w.writerow([check_name, stats["pass"], stats["fail"], round(rate, 3)])
    print(f"Wrote identity check summary -> {filepath}")

    print("\n=== BS Global Identity Checks ===")
    for check_name, stats in identity_stats.items():
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0
        print(f"  {check_name}: {rate:.1%}  ({stats['pass']} pass / {stats['fail']} fail)")


def export_zone_failure_examples_bs(zone_failure_examples,
                                     filepath="zone_failure_examples_BS.csv"):
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


def export_master_draft_bs(rows, filepath="master_draft_BS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Type", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Type"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


def export_subject_template_bs(rows, filepath="subject_template_BS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Source", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Source"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


# ==================================================================
# MAIN
# ==================================================================
# MODE = "debug" -> ~1 second, few tickers, prints all recon math.
# MODE = "full"  -> ~7 minutes, all 503 tickers, writes the CSVs.
# ==================================================================

MODE = "debug"

TICKER_FILE = "constituents.csv"
SUBJECT_TICKER = "MMM"
DEBUG_TICKERS = ["AMZN", "BRK.B", "CAT", "CBOE", "DE", "DELL", "EW", "EMR", "ERIE", "F", "GM", "GPN", "HPE", "LVS", "LEN"]
DEBUG_COLUMN = "LFY"


if __name__ == "__main__":
    client = StyledStatementClient()

    if MODE == "debug":
        for t in DEBUG_TICKERS:
            debug_ticker_bs(t, client, value_column=DEBUG_COLUMN)
            time.sleep(0.3)

    elif MODE == "full":
        tickers = load_tickers_from_file(TICKER_FILE, column="Symbol")
        print(f"Loaded {len(tickers)} tickers from {TICKER_FILE}")

        (item_zone_votes, item_zone_positions, zone_recon_stats,
         zone_failure_examples, identity_stats) = build_master_order_bs(
            tickers, client, min_valid_fraction=0.5, request_delay=0.3,
            max_examples_per_zone=15
        )

        canonical, ambiguous = resolve_canonical_positions(
            item_zone_votes, item_zone_positions, ambiguous_threshold=0.9
        )

        export_canonical_order_bs(canonical)
        export_ambiguous_items_bs(ambiguous)
        export_zone_reconciliation_summary_bs(zone_recon_stats)
        export_identity_check_summary(identity_stats)
        export_zone_failure_examples_bs(zone_failure_examples)

        draft_rows = build_master_draft_statement_bs(canonical)
        export_master_draft_bs(draft_rows)

        subject_rows = build_subject_company_template_bs(
            SUBJECT_TICKER, client, canonical
        )
        export_subject_template_bs(
            subject_rows, f"subject_template_BS_{SUBJECT_TICKER}.csv"
        )

    else:
        raise ValueError(f"Unknown MODE: {MODE!r} (expected 'debug' or 'full')")