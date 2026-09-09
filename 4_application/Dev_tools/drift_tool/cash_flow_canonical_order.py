"""
============================================================
CASH FLOW STATEMENT CANONICAL ORDERING ENGINE
============================================================

STRUCTURAL DIFFERENCE FROM BS AND IS:
CFS has FOUR INDEPENDENT ADDITIVE CHAINS, each starting fresh
at an implied value of zero:

    Operating:  0 -> Operating Cash Flow
    Investing:  0 -> Investing Cash Flow
    Financing:  0 -> Financing Cash Flow
    Net:        0 -> Net Cash Flow
                     (components: FX Adjustments + Misc Adjustments)

...plus a GLOBAL IDENTITY CHECK:
    Operating Cash Flow + Investing Cash Flow + Financing Cash Flow
    + FX Adjustments + Misc Adjustments == Net Cash Flow

SIGN CONVENTION: AS_REPORTED throughout. Outflows are already
stored negative on stockanalysis.com (e.g. Capital Expenditures
= -1,181, Repurchase of Common Stock = -1,801). No sign flips
needed anywhere — same as BS.

CONFIRMED VIA MMM LFY (hand-verified before writing any code):
  Operating components -> Operating Cash Flow:  1,819 = 1,819
  Investing components -> Investing Cash Flow:  -3,206 = -3,206
  Financing components -> Financing Cash Flow:  1,098 = 1,098
  Net components -> Net Cash Flow:              -333 = -333
  Operating + Investing + Financing + FX + Misc = Net Cash Flow:
    1,819 + (-3,206) + 1,098 + (-44) + 0 = -333 ✓

KNOWN INTRA-ZONE SUBTOTALS (excluded from summation):
    "Total Debt Issued"      = Short-Term Debt Issued +
                               Long-Term Debt Issued
    "Total Debt Repaid"      = Short-Term Debt Repaid +
                               Long-Term Debt Repaid
    "Net Debt Issued (Repaid)" = Total Debt Issued + Total Debt Repaid
    (all caught by bold-detection as belt-and-suspenders)

TRAILING / INFORMATIONAL ZONES (non-reconcilable):
    Free Cash Flow section: Free Cash Flow, FCF Growth, FCF Margin,
                            FCF Per Share, Levered FCF, Unlevered FCF
    Additional Metrics:     Cash Interest Paid, Cash Income Tax Paid,
                            Change in Working Capital

Reuses StyledStatementClient, parse_numeric, is_non_additive, and
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
    is_non_additive,
    resolve_canonical_positions,
)


# ==================================================================
# ANCHOR DEFINITIONS
# ==================================================================

CFS_ANCHOR_LABELS_IN_ORDER = [
    "Operating Cash Flow",
    "Investing Cash Flow",
    "Financing Cash Flow",
    "Net Cash Flow",
]

ANCHOR_LABELS = set(CFS_ANCHOR_LABELS_IN_ORDER)

SENTINEL_OPERATING_START = "__OPERATING_START__"
SENTINEL_INVESTING_START = "__INVESTING_START__"
SENTINEL_FINANCING_START = "__FINANCING_START__"
SENTINEL_NET_START = "__NET_START__"
SENTINEL_END = "__BOTTOM_OF_STATEMENT__"


# ==================================================================
# KNOWN INTRA-ZONE SUBTOTALS (CFS-specific)
# ==================================================================

KNOWN_INTRA_ZONE_SUBTOTALS_CFS = {
    "Total Debt Issued",
    "Total Debt Repaid",
    "Net Debt Issued (Repaid)",
}

SUBTOTAL_PREFIXES_CFS = (
    "total ",
)

NEVER_SKIP_LABELS_CFS = {
    "Net Income",
}


def is_known_subtotal_cfs(label, zone_rows=None) -> bool:
    stripped = str(label).strip()

    if stripped in KNOWN_INTRA_ZONE_SUBTOTALS_CFS:
        return True

    if stripped == "Net Sale / Acq. of Real Estate Assets":
        if zone_rows is not None:
            zone_labels = set(zone_rows["Line Item"].astype(str).str.strip())
            return ("Acquisition of Real Estate Assets" in zone_labels or
                    "Sale of Real Estate Assets" in zone_labels)
        return True

    lower = stripped.lower()
    return any(lower.startswith(p) for p in SUBTOTAL_PREFIXES_CFS)


def get_additive_rows_cfs(zone_rows):
    mask_never_skip = zone_rows["Line Item"].apply(
        lambda l: str(l).strip() in NEVER_SKIP_LABELS_CFS
    ).astype(bool)
    mask_not_bold = (~zone_rows["IsBold"]).astype(bool)
    mask_not_subtotal = (~zone_rows["Line Item"].apply(
        lambda l: is_known_subtotal_cfs(l, zone_rows)
    )).astype(bool)
    mask_not_nonadditive = (~zone_rows["Line Item"].apply(
        is_non_additive)).astype(bool)
    return zone_rows[
        (mask_never_skip) |
        (mask_not_bold & mask_not_subtotal & mask_not_nonadditive)
    ]


# ==================================================================
# SIGN CONVENTION (CFS-specific)
# ==================================================================
# AS_REPORTED throughout — outflows already stored negative.

ZONE_SIGN_CONVENTION_CFS = {}
SUBTRACT_SIGN_ITEMS_CFS = set()
AS_REPORTED_ITEMS_CFS = set()


def compute_signed_value_cfs(label, raw_value, zone_key):
    val = parse_numeric(raw_value)
    if val is None:
        return None, False
    label = str(label).strip()
    zone_default = ZONE_SIGN_CONVENTION_CFS.get(zone_key, "AS_REPORTED")
    if label in SUBTRACT_SIGN_ITEMS_CFS:
        return -val, True
    if label in AS_REPORTED_ITEMS_CFS:
        return val, False
    if zone_default == "SUBTRACT":
        return -val, True
    return val, False


# ==================================================================
# STEP 1 — Locate anchors & build the four independent zone chains
# ==================================================================

def locate_cfs_anchor_positions(df):
    positions = {}
    labels = [str(x).strip() for x in df["Line Item"].tolist()]
    for anchor_label in CFS_ANCHOR_LABELS_IN_ORDER:
        try:
            positions[anchor_label] = labels.index(anchor_label)
        except ValueError:
            continue
    return positions


def build_cfs_zones(df, anchor_positions):
    zones = []
    n_rows = len(df)

    # ---- Operating chain ----
    if "Operating Cash Flow" in anchor_positions:
        ocf_idx = anchor_positions["Operating Cash Flow"]
        zones.append({
            "section": "Operating",
            "start_label": SENTINEL_OPERATING_START, "start_idx": -1,
            "start_value_override": 0.0,
            "end_label": "Operating Cash Flow", "end_idx": ocf_idx,
            "reconcilable": True,
        })

    # ---- Investing chain ----
    if "Operating Cash Flow" in anchor_positions and \
       "Investing Cash Flow" in anchor_positions:
        ocf_idx = anchor_positions["Operating Cash Flow"]
        icf_idx = anchor_positions["Investing Cash Flow"]
        zones.append({
            "section": "Investing",
            "start_label": SENTINEL_INVESTING_START, "start_idx": ocf_idx,
            "start_value_override": 0.0,
            "end_label": "Investing Cash Flow", "end_idx": icf_idx,
            "reconcilable": True,
        })

    # ---- Financing chain ----
    if "Investing Cash Flow" in anchor_positions and \
       "Financing Cash Flow" in anchor_positions:
        icf_idx = anchor_positions["Investing Cash Flow"]
        fcf_idx = anchor_positions["Financing Cash Flow"]
        zones.append({
            "section": "Financing",
            "start_label": SENTINEL_FINANCING_START, "start_idx": icf_idx,
            "start_value_override": 0.0,
            "end_label": "Financing Cash Flow", "end_idx": fcf_idx,
            "reconcilable": True,
        })

    # ---- Net Cash Flow chain ----
    # Net Cash Flow = Operating + Investing + Financing + FX + Misc
    # Start value is NOT zero — it's the sum of the three section anchors.
    # FX Adjustments and Misc are the only additive components in this zone.
    # start_value_override = None signals get_zone_start_value to compute
    # it dynamically from the three anchor rows.
    if "Financing Cash Flow" in anchor_positions and \
       "Net Cash Flow" in anchor_positions:
        fcf_idx = anchor_positions["Financing Cash Flow"]
        ncf_idx = anchor_positions["Net Cash Flow"]
        zones.append({
            "section": "Net",
            "start_label": SENTINEL_NET_START, "start_idx": fcf_idx,
            "start_value_override": None,
            "end_label": "Net Cash Flow", "end_idx": ncf_idx,
            "reconcilable": True,
            "net_zone": True,  # flag for special start value computation
        })

    # ---- Trailing informational zone ----
    if "Net Cash Flow" in anchor_positions:
        ncf_idx = anchor_positions["Net Cash Flow"]
        zones.append({
            "section": "Trailing",
            "start_label": "Net Cash Flow", "start_idx": ncf_idx,
            "start_value_override": None,
            "end_label": SENTINEL_END, "end_idx": n_rows,
            "reconcilable": False,
        })

    return zones


def get_zone_start_value(df, zone, col, anchor_positions=None):
    # Net zone: start value = sum of three section anchor values
    if zone.get("net_zone") and anchor_positions is not None:
        ocf = (parse_numeric(df.loc[anchor_positions["Operating Cash Flow"], col])
               if "Operating Cash Flow" in anchor_positions else None)
        icf = (parse_numeric(df.loc[anchor_positions["Investing Cash Flow"], col])
               if "Investing Cash Flow" in anchor_positions else None)
        fcf = (parse_numeric(df.loc[anchor_positions["Financing Cash Flow"], col])
               if "Financing Cash Flow" in anchor_positions else None)
        if None in (ocf, icf, fcf):
            return None
        return ocf + icf + fcf

    if zone["start_value_override"] is not None:
        return zone["start_value_override"]
    return parse_numeric(df.loc[zone["start_idx"], col])


# ==================================================================
# STEP 2 — Reconciliation validation
# ==================================================================

def validate_cfs_zones(df, zones, value_columns, ticker=None,
                        zone_failure_examples=None, max_examples_per_zone=15,
                        anchor_positions=None):
    results = {}

    for zone in zones:
        if not zone["reconcilable"]:
            continue

        zone_key = (zone["start_label"], zone["end_label"])
        start_idx, end_idx = zone["start_idx"], zone["end_idx"]
        zone_rows = df[(df.index > start_idx) & (df.index < end_idx)]
        additive_rows = get_additive_rows_cfs(zone_rows)

        for col in value_columns:
            if col not in df.columns:
                continue

            total = 0.0
            skip_column = False
            for _, row in additive_rows.iterrows():
                signed, _flipped = compute_signed_value_cfs(
                    row["Line Item"], row[col], zone_key
                )
                if signed is None:
                    skip_column = True
                    break
                total += signed

            if skip_column:
                continue

            start_val = get_zone_start_value(df, zone, col, anchor_positions)
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
                if ticker not in tickers_logged and \
                   len(tickers_logged) < max_examples_per_zone:
                    bucket.append({
                        "ticker": ticker, "column": col,
                        "calculated": round(total, 1),
                        "reported": round(reported_delta, 1),
                        "diff": round(diff, 1),
                    })

    return results


def zone_is_trustworthy_cfs(validation_results, start_label, end_label,
                              min_valid_fraction=0.5):
    relevant = [v for (s, e, _), v in validation_results.items()
                if s == start_label and e == end_label]
    if not relevant:
        return False
    return (sum(relevant) / len(relevant)) >= min_valid_fraction


# ==================================================================
# GLOBAL IDENTITY CHECK
# ==================================================================

def validate_cfs_identity(df, anchor_positions, value_columns):
    """
    Operating Cash Flow + Investing Cash Flow + Financing Cash Flow
    + FX Adjustments + Misc Adjustments == Net Cash Flow
    Checked as: sum of three section anchors + net-zone components
    == Net Cash Flow anchor.
    """
    results = {"operating_plus_investing_plus_financing_eq_net": {}}

    for col in value_columns:
        if col not in df.columns:
            continue

        ocf = (parse_numeric(df.loc[anchor_positions["Operating Cash Flow"], col])
               if "Operating Cash Flow" in anchor_positions else None)
        icf = (parse_numeric(df.loc[anchor_positions["Investing Cash Flow"], col])
               if "Investing Cash Flow" in anchor_positions else None)
        fcf = (parse_numeric(df.loc[anchor_positions["Financing Cash Flow"], col])
               if "Financing Cash Flow" in anchor_positions else None)
        ncf = (parse_numeric(df.loc[anchor_positions["Net Cash Flow"], col])
               if "Net Cash Flow" in anchor_positions else None)

        if None in (ocf, icf, fcf, ncf):
            continue

        # Sum the three section totals plus any net-zone components
        # (FX adjustments, misc) that sit between Financing Cash Flow
        # and Net Cash Flow
        fcf_idx = anchor_positions["Financing Cash Flow"]
        ncf_idx = anchor_positions["Net Cash Flow"]
        net_zone_rows = df[(df.index > fcf_idx) & (df.index < ncf_idx)]
        additive_net = get_additive_rows_cfs(net_zone_rows)

        adj_total = 0.0
        skip = False
        for _, row in additive_net.iterrows():
            signed, _ = compute_signed_value_cfs(
                row["Line Item"], row[col],
                (SENTINEL_NET_START, "Net Cash Flow")
            )
            if signed is None:
                skip = True
                break
            adj_total += signed

        if skip:
            continue

        calculated = ocf + icf + fcf + adj_total
        tolerance = max(1.0, abs(ncf) * 0.02)
        results["operating_plus_investing_plus_financing_eq_net"][col] = (
            abs(calculated - ncf) <= tolerance
        )

    return results


# ==================================================================
# STEP 3 — Cross-ticker voting
# ==================================================================

def build_master_order_cfs(tickers, client, min_valid_fraction=0.5,
                            request_delay=0.3, max_examples_per_zone=15):
    item_zone_votes = {}
    item_zone_positions = {}
    zone_recon_stats = {}
    zone_failure_examples = {}
    identity_stats = {
        "operating_plus_investing_plus_financing_eq_net": {"pass": 0, "fail": 0}
    }

    value_columns_priority = ["LFY", "LFY-1", "LFY-2", "LFY-3", "TTM"]

    progress_bar = tqdm(
        tickers, desc="Building CFS canonical order", unit="ticker",
        file=sys.stdout, dynamic_ncols=True, mininterval=0.3, ascii=True,
    )

    for ticker in progress_bar:
        try:
            df = client.fetch_statement(ticker, "CFS")
            if df is None or df.empty:
                continue

            df = df.reset_index(drop=True)
            anchor_positions = locate_cfs_anchor_positions(df)
            zones = build_cfs_zones(df, anchor_positions)
            if not zones:
                continue

            available_cols = [c for c in value_columns_priority if c in df.columns]

            validation_results = validate_cfs_zones(
                df, zones, available_cols, ticker=ticker,
                zone_failure_examples=zone_failure_examples,
                max_examples_per_zone=max_examples_per_zone,
                anchor_positions=anchor_positions,
            )

            for (s, e, _col), is_valid in validation_results.items():
                zone_recon_stats.setdefault((s, e), {"pass": 0, "fail": 0})
                zone_recon_stats[(s, e)]["pass" if is_valid else "fail"] += 1

            identity_results = validate_cfs_identity(
                df, anchor_positions, available_cols
            )
            for check_name, per_col in identity_results.items():
                for _col, is_valid in per_col.items():
                    identity_stats[check_name]["pass" if is_valid else "fail"] += 1

            for zone in zones:
                if not zone_is_trustworthy_cfs(
                    validation_results, zone["start_label"], zone["end_label"],
                    min_valid_fraction
                ) and zone["reconcilable"]:
                    continue

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

CFS_ZONE_ORDER = [
    (SENTINEL_OPERATING_START, "Operating Cash Flow"),
    (SENTINEL_INVESTING_START, "Investing Cash Flow"),
    (SENTINEL_FINANCING_START, "Financing Cash Flow"),
    (SENTINEL_NET_START, "Net Cash Flow"),
]

CFS_SECTION_HEADERS = {
    (SENTINEL_OPERATING_START, "Operating Cash Flow"): "Operating Activities",
    (SENTINEL_INVESTING_START, "Investing Cash Flow"): "Investing Activities",
    (SENTINEL_FINANCING_START, "Financing Cash Flow"): "Financing Activities",
    (SENTINEL_NET_START, "Net Cash Flow"): "Net Cash Flow",
}


def build_master_draft_statement_cfs(canonical):
    rows = []
    for zone_key in CFS_ZONE_ORDER:
        header = CFS_SECTION_HEADERS.get(zone_key)
        if header:
            rows.append({"Line Item": f"--- {header} ---",
                         "Type": "SECTION", "Confidence": None})

        zone_items = [(l, i) for l, i in canonical.items()
                      if i["zone"] == zone_key]
        zone_items.sort(key=lambda x: x[1]["avg_position"])
        for label, info in zone_items:
            rows.append({"Line Item": label, "Type": "component",
                         "Confidence": round(info["confidence"], 2)})

        rows.append({"Line Item": zone_key[1], "Type": "ANCHOR",
                     "Confidence": None})

    return rows


# ==================================================================
# STEP 4b — Subject-company-specific template
# ==================================================================

def resolve_zone_start_idx_cfs(anchor_positions, start_label):
    if start_label == SENTINEL_OPERATING_START:
        return -1
    if start_label == SENTINEL_INVESTING_START:
        return anchor_positions.get("Operating Cash Flow")
    if start_label == SENTINEL_FINANCING_START:
        return anchor_positions.get("Investing Cash Flow")
    if start_label == SENTINEL_NET_START:
        return anchor_positions.get("Financing Cash Flow")
    return anchor_positions.get(start_label)


def build_subject_company_template_cfs(subject_ticker, client, canonical):
    df = client.fetch_statement(subject_ticker, "CFS")
    if df is None or df.empty:
        raise ValueError(f"Could not fetch CFS for {subject_ticker}")

    df = df.reset_index(drop=True)
    subject_labels = [str(x).strip() for x in df["Line Item"].tolist()]
    subject_label_set = set(subject_labels)
    anchor_positions = locate_cfs_anchor_positions(df)

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
        start_idx = resolve_zone_start_idx_cfs(anchor_positions, start_label)
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

def debug_ticker_cfs(ticker, client, value_column="LFY"):
    df = client.fetch_statement(ticker, "CFS")
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
    print(f"{'idx':>4} {'bold':>6} {'value':>14}  Line Item")
    for idx, row in df.iterrows():
        print(f"{idx:>4} {str(row['IsBold']):>6} "
              f"{str(row[value_column]):>14}  {row['Line Item']}")

    anchor_positions = locate_cfs_anchor_positions(df)
    zones = build_cfs_zones(df, anchor_positions)
    if not zones:
        print("\n!! No valid zones built")
        return

    print(f"\n{'=' * 74}\nZONE RECONCILIATION\n{'=' * 74}")

    for zone in zones:
        zone_key = (zone["start_label"], zone["end_label"])
        header = f"[{zone['section']}] {zone['start_label']} -> {zone['end_label']}"

        if not zone["reconcilable"]:
            print(f"\n{header}  AUTO-TRUSTED (informational / non-reconcilable)")
            zone_rows = df[(df.index > zone["start_idx"]) &
                           (df.index < zone["end_idx"])]
            for _, row in zone_rows.iterrows():
                print(f"        {'':>14}  {row['Line Item']}")
            continue

        print(f"\n{header}")
        zone_rows = df[(df.index > zone["start_idx"]) &
                       (df.index < zone["end_idx"])]
        additive_rows = get_additive_rows_cfs(zone_rows)

        excluded = zone_rows[~zone_rows.index.isin(additive_rows.index)]
        for _, row in excluded.iterrows():
            if row["IsBold"]:
                reason = "bold"
            elif is_known_subtotal_cfs(row["Line Item"]):
                reason = "known subtotal"
            else:
                reason = "non-additive"
            print(f"    [skip:{reason:<15}] {'':>12}  {row['Line Item']}")

        total = 0.0
        for _, row in additive_rows.iterrows():
            signed, flipped = compute_signed_value_cfs(
                row["Line Item"], row[value_column], zone_key
            )
            if signed is None:
                print(f"    [UNPARSEABLE       ] "
                      f"{str(row[value_column]):>12}  {row['Line Item']}")
                continue
            total += signed
            print(f"    {'(FLIP)' if flipped else '      '}"
                  f"{'':>13} {signed:>12,.1f}  {row['Line Item']}")

        start_val = get_zone_start_value(df, zone, value_column, anchor_positions)
        end_val = parse_numeric(df.loc[zone["end_idx"], value_column])
        reported = end_val - start_val
        tolerance = max(1.0, abs(reported) * 0.02)
        passed = abs(total - reported) <= tolerance

        print(f"    {'-' * 60}")
        print(f"    calculated: {total:>14,.1f}")
        print(f"    reported:   {reported:>14,.1f}   "
              f"({zone['end_label']} {end_val:,.1f} - start {start_val:,.1f})")
        print(f"    diff:       {total - reported:>14,.1f}   "
              f"(tolerance {tolerance:,.1f})")
        print(f"    ==> {'PASS' if passed else 'FAIL'}")

    print(f"\n{'=' * 74}\nGLOBAL IDENTITY CHECK\n{'=' * 74}")
    identity_results = validate_cfs_identity(
        df, anchor_positions, [value_column]
    )
    ocf = (parse_numeric(df.loc[anchor_positions["Operating Cash Flow"],
                                value_column])
           if "Operating Cash Flow" in anchor_positions else None)
    icf = (parse_numeric(df.loc[anchor_positions["Investing Cash Flow"],
                                value_column])
           if "Investing Cash Flow" in anchor_positions else None)
    fcf = (parse_numeric(df.loc[anchor_positions["Financing Cash Flow"],
                                value_column])
           if "Financing Cash Flow" in anchor_positions else None)
    ncf = (parse_numeric(df.loc[anchor_positions["Net Cash Flow"],
                                value_column])
           if "Net Cash Flow" in anchor_positions else None)

    if None not in (ocf, icf, fcf, ncf):
        result = identity_results[
            "operating_plus_investing_plus_financing_eq_net"
        ].get(value_column)
        print(f"  Operating ({ocf:,.1f}) + Investing ({icf:,.1f}) + "
              f"Financing ({fcf:,.1f}) + adjustments == "
              f"Net Cash Flow ({ncf:,.1f})  "
              f"==> {'PASS' if result else 'FAIL'}")


# ==================================================================
# CSV EXPORTS
# ==================================================================

def export_canonical_order_cfs(canonical,
                                filepath="canonical_order_CFS.csv"):
    rows = sorted(canonical.items(),
                  key=lambda kv: (kv[1]["zone"], kv[1]["avg_position"]))
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


def export_ambiguous_items_cfs(ambiguous,
                                filepath="ambiguous_items_CFS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Zone Votes (start->end : count)"])
        for label, zone_votes in ambiguous.items():
            vote_str = "; ".join(
                f"{s}->{e}: {c}" for (s, e), c in zone_votes.items()
            )
            w.writerow([label, vote_str])
    print(f"Wrote {len(ambiguous)} ambiguous items -> {filepath}")


def export_zone_reconciliation_summary_cfs(
        zone_recon_stats,
        filepath="zone_reconciliation_summary_CFS.csv"):
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

    print("\n=== CFS Zone Reconciliation Pass Rates ===")
    for (start, end), stats in zone_recon_stats.items():
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0
        print(f"  {start} -> {end}: {rate:.1%}  "
              f"({stats['pass']} pass / {stats['fail']} fail)")


def export_identity_check_summary_cfs(
        identity_stats,
        filepath="identity_check_summary_CFS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Check", "Pass Count", "Fail Count", "Pass Rate"])
        for check_name, stats in identity_stats.items():
            total = stats["pass"] + stats["fail"]
            rate = stats["pass"] / total if total else 0
            w.writerow([check_name, stats["pass"], stats["fail"],
                        round(rate, 3)])
    print(f"Wrote identity check summary -> {filepath}")

    print("\n=== CFS Global Identity Check ===")
    for check_name, stats in identity_stats.items():
        total = stats["pass"] + stats["fail"]
        rate = stats["pass"] / total if total else 0
        print(f"  {check_name}: {rate:.1%}  "
              f"({stats['pass']} pass / {stats['fail']} fail)")


def export_zone_failure_examples_cfs(
        zone_failure_examples,
        filepath="zone_failure_examples_CFS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Zone Start", "Zone End", "Ticker", "Column",
                    "Calculated", "Reported", "Diff"])
        for (start, end), examples in zone_failure_examples.items():
            for ex in examples:
                w.writerow([start, end, ex["ticker"], ex["column"],
                            ex["calculated"], ex["reported"], ex["diff"]])
    print(f"Wrote "
          f"{sum(len(v) for v in zone_failure_examples.values())} "
          f"failure examples -> {filepath}")


def export_master_draft_cfs(rows, filepath="master_draft_CFS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Type", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Type"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


def export_subject_template_cfs(rows,
                                 filepath="subject_template_CFS.csv"):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Line Item", "Source", "Confidence"])
        for r in rows:
            w.writerow([r["Line Item"], r["Source"], r["Confidence"]])
    print(f"Wrote {len(rows)} rows -> {filepath}")


# ==================================================================
# MAIN
# ==================================================================

MODE = "debug"

TICKER_FILE = "constituents.csv"
SUBJECT_TICKER = "MMM"
DEBUG_TICKERS = ["MMM", "ABBV", "AMD", "AES", "AFL", "ARE", "LNT", "ALL", "GOOGL", "AXP", "AIG", "AMT", "AWK", "APP"]
DEBUG_COLUMN = "LFY"


if __name__ == "__main__":
    client = StyledStatementClient()

    if MODE == "debug":
        for t in DEBUG_TICKERS:
            debug_ticker_cfs(t, client, value_column=DEBUG_COLUMN)
            time.sleep(0.3)

    elif MODE == "full":
        tickers = load_tickers_from_file(TICKER_FILE, column="Symbol")
        print(f"Loaded {len(tickers)} tickers from {TICKER_FILE}")

        (item_zone_votes, item_zone_positions, zone_recon_stats,
         zone_failure_examples, identity_stats) = build_master_order_cfs(
            tickers, client, min_valid_fraction=0.5, request_delay=0.3,
            max_examples_per_zone=15
        )

        canonical, ambiguous = resolve_canonical_positions(
            item_zone_votes, item_zone_positions, ambiguous_threshold=0.9
        )

        export_canonical_order_cfs(canonical)
        export_ambiguous_items_cfs(ambiguous)
        export_zone_reconciliation_summary_cfs(zone_recon_stats)
        export_identity_check_summary_cfs(identity_stats)
        export_zone_failure_examples_cfs(zone_failure_examples)

        draft_rows = build_master_draft_statement_cfs(canonical)
        export_master_draft_cfs(draft_rows)

        subject_rows = build_subject_company_template_cfs(
            SUBJECT_TICKER, client, canonical
        )
        export_subject_template_cfs(
            subject_rows,
            f"subject_template_CFS_{SUBJECT_TICKER}.csv"
        )

    else:
        raise ValueError(
            f"Unknown MODE: {MODE!r} (expected 'debug' or 'full')"
        )