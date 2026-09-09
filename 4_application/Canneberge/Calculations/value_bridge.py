"""
Canneberge/Calculations/value_bridge.py

Shared BEV <-> Equity, controlling <-> minority conversion engine.

Every valuation method has a NATURAL level it's produced at:
    DCF  -> controlling  (management-plan cash flows)
    GT   -> controlling  (observed acquisition prices)
    GPC  -> minority     (public trading multiples)

The Dashboard picks a TARGET level (controlling or minority). Only
methods whose natural level differs from the target need adjustment:

    target = controlling:  GPC needs +Control Premium
    target = minority:     DCF, GT need -DLOC

CP and DLOC are Dashboard-owned, last-edit-wins:
    DLOC = CP / (1 + CP)
    CP   = DLOC / (1 - DLOC)

Equity mode (GPC only) deliberately excludes gross Cash -- P/E and
P/Revenue multiples already embed the peer's own cash balance. BEV
mode includes Cash because EV multiples are cash-free by construction.
This asymmetry is intentional, not an oversight -- see 4_application.md
Phase 4.4 GPC bridge notes.

NWC Surplus/(Deficit) is expected to be cash-free/debt-free (DFCFNWC).
If the NWC page's Cash Treatment includes cash, the bridge will double
count -- that's a user-facing warning on the NWC page, not something
this engine silently corrects.
"""

from dataclasses import dataclass
from typing import Optional, List, Tuple


def cp_to_dloc(cp: Optional[float]) -> Optional[float]:
    """Control Premium -> Discount for Lack of Control. Exact inverse of dloc_to_cp."""
    if cp is None or cp <= -1.0:
        return None
    return cp / (1.0 + cp)


def dloc_to_cp(dloc: Optional[float]) -> Optional[float]:
    """Discount for Lack of Control -> Control Premium. Exact inverse of cp_to_dloc."""
    if dloc is None or dloc >= 1.0:
        return None
    return dloc / (1.0 - dloc)


@dataclass
class BridgeInputs:
    """
    Every field the bridge needs, sourced from wherever it actually
    lives (Dashboard for cp/dloc/non_op, NWC page for nwc_surplus,
    Subject Financials for debt/cash/preferred/minority_interest).
    """
    cash: Optional[float] = None
    nwc_surplus: Optional[float] = None
    non_operating: Optional[float] = None
    debt: Optional[float] = None
    preferred_stock: Optional[float] = None
    minority_interest: Optional[float] = None
    control_premium: Optional[float] = None   # e.g. 0.24
    dloc: Optional[float] = None              # e.g. 0.194 -- must already be cp_to_dloc(control_premium)
    shares_outstanding: Optional[float] = None
    share_price: Optional[float] = None


def _sum_present(*vals: Optional[float]) -> Optional[float]:
    """None-safe sum. Any None input -> None output (matches GPC page's _sum_or_na)."""
    if any(v is None for v in vals):
        return None
    return sum(vals)


def _fmt_pct_label(base: str, rate: Optional[float]) -> str:
    if rate is None:
        return f"{base} (NA)"
    return f"{base} ({rate * 100:.1f}%)"


def run_bridge(
    low: Optional[float],
    high: Optional[float],
    natural_level: str,
    source_basis: str,
    bi: BridgeInputs,
    equity_mode_includes_cash: bool = False,
) -> dict:
    """
    Convert a method's natural valuation level into all relevant
    BEV/Equity and Controlling/Minority outputs.

    Natural levels:
        GPC -> minority
        DCF / GT -> controlling

    Source bases:
        Equity -> equity value
        BEV    -> business enterprise value
    """
    if natural_level not in ("controlling", "minority"):
        raise ValueError("natural_level must be 'controlling' or 'minority'")
    if source_basis not in ("BEV", "Equity"):
        raise ValueError("source_basis must be 'BEV' or 'Equity'")

    debt = bi.debt or 0.0
    preferred = bi.preferred_stock or 0.0
    nci = bi.minority_interest or 0.0
    cash = bi.cash or 0.0
    nwc = bi.nwc_surplus or 0.0
    non_op = bi.non_operating or 0.0
    cp = bi.control_premium
    dloc = bi.dloc
    shares = bi.shares_outstanding

    deductions_from_bev = debt + preferred + nci
    additions_to_equity = cash + nwc + non_op

    def pair_add(a, b):
        return (
            None if a is None or b is None else a + b,
            None if a is None or b is None else b + a,
        )

    def pair_apply(values, fn):
        lo, hi = values
        return (
            fn(lo) if lo is not None else None,
            fn(hi) if hi is not None else None,
        )

    lines: List[Tuple[str, Optional[float], Optional[float]]] = []

    # ------------------------------------------------------------------
    # Minority-native methods: GPC
    # ------------------------------------------------------------------
    if natural_level == "minority":
        if source_basis == "Equity":
            # Equity multiples are already equity-based. Gross cash is
            # intentionally excluded; NWC and Non-Op are separate
            # normalization items.
            equity_minority = (
                low + nwc + non_op
                if low is not None
                else None,
                high + nwc + non_op
                if high is not None
                else None,
            )

            lines.append((
                "Equity Value (minority, marketable)",
                low,
                high,
            ))
            lines.append((
                "Plus: NWC Surplus/(Deficit) + Non-Operating Assets "
                "= Adjusted Equity Value (minority, marketable)",
                equity_minority[0],
                equity_minority[1],
            ))
        else:
            # BEV multiples are cash-free/debt-free.
            equity_minority = (
                low - deductions_from_bev + additions_to_equity
                if low is not None
                else None,
                high - deductions_from_bev + additions_to_equity
                if high is not None
                else None,
            )

            lines.append((
                "BEV (minority, marketable)",
                low,
                high,
            ))
            lines.append((
                "Less: Debt + Preferred Stock + Minority Interest; "
                "Plus: Cash + NWC Surplus/(Deficit) + Non-Operating Assets "
                "= Equity Value (minority, marketable)",
                equity_minority[0],
                equity_minority[1],
            ))

        if cp is not None:
            equity_controlling = (
                equity_minority[0] * (1.0 + cp)
                if equity_minority[0] is not None
                else None,
                equity_minority[1] * (1.0 + cp)
                if equity_minority[1] is not None
                else None,
            )
            lines.append((
                f"Plus: Control Premium ({cp * 100:.1f}%) "
                "= Equity Value (controlling, marketable)",
                equity_controlling[0],
                equity_controlling[1],
            ))
        else:
            equity_controlling = (None, None)

        bev_minority = (
            equity_minority[0]
            + deductions_from_bev
            - additions_to_equity
            if equity_minority[0] is not None
            else None,
            equity_minority[1]
            + deductions_from_bev
            - additions_to_equity
            if equity_minority[1] is not None
            else None,
        )

        bev_controlling = (
            equity_controlling[0]
            + deductions_from_bev
            - additions_to_equity
            if equity_controlling[0] is not None
            else None,
            equity_controlling[1]
            + deductions_from_bev
            - additions_to_equity
            if equity_controlling[1] is not None
            else None,
        )

        if source_basis == "BEV":
            lines.append((
                "Plus: Debt + Preferred Stock + Minority Interest; "
                "Less: Cash + NWC Surplus/(Deficit) + Non-Operating Assets "
                "= BEV (controlling, marketable)",
                bev_controlling[0],
                bev_controlling[1],
            ))

    # ------------------------------------------------------------------
    # Controlling-native methods: DCF / GT
    # ------------------------------------------------------------------
    else:
        if source_basis == "Equity":
            # FCFE is already controlling equity. Do not add GPC-style
            # NWC/Non-Op adjustments a second time.
            equity_controlling = (low, high)
        else:
            # FCFF/GT are controlling BEV values. Convert BEV to
            # controlling equity.
            equity_controlling = (
                low - deductions_from_bev + additions_to_equity
                if low is not None
                else None,
                high - deductions_from_bev + additions_to_equity
                if high is not None
                else None,
            )

        if source_basis == "Equity":
            lines.append((
                "Equity Value (controlling, marketable)",
                equity_controlling[0],
                equity_controlling[1],
            ))
        else:
            lines.append((
                "BEV (controlling, marketable)",
                low,
                high,
            ))
            lines.append((
                "Less: Debt + Preferred Stock + Minority Interest; "
                "Plus: Cash + NWC Surplus/(Deficit) + Non-Operating Assets "
                "= Equity Value (controlling, marketable)",
                equity_controlling[0],
                equity_controlling[1],
            ))

        if dloc is not None:
            equity_minority = (
                equity_controlling[0] * (1.0 - dloc)
                if equity_controlling[0] is not None
                else None,
                equity_controlling[1] * (1.0 - dloc)
                if equity_controlling[1] is not None
                else None,
            )
            lines.append((
                f"Less: Discount for Lack of Control ({dloc * 100:.1f}%) "
                "= Equity Value (minority, marketable)",
                equity_minority[0],
                equity_minority[1],
            ))
        else:
            equity_minority = (None, None)

        bev_controlling = (
            equity_controlling[0]
            + deductions_from_bev
            - additions_to_equity
            if equity_controlling[0] is not None
            else None,
            equity_controlling[1]
            + deductions_from_bev
            - additions_to_equity
            if equity_controlling[1] is not None
            else None,
        )

        bev_minority = (
            equity_minority[0]
            + deductions_from_bev
            - additions_to_equity
            if equity_minority[0] is not None
            else None,
            equity_minority[1]
            + deductions_from_bev
            - additions_to_equity
            if equity_minority[1] is not None
            else None,
        )

    per_share_minority = (
        equity_minority[0] / shares
        if equity_minority[0] is not None and shares
        else None,
        equity_minority[1] / shares
        if equity_minority[1] is not None and shares
        else None,
    )

    per_share_controlling = (
        equity_controlling[0] / shares
        if equity_controlling[0] is not None and shares
        else None,
        equity_controlling[1] / shares
        if equity_controlling[1] is not None and shares
        else None,
    )

    return {
        "equity_minority": equity_minority,
        "equity_controlling": equity_controlling,
        "bev_minority": bev_minority,
        "bev_controlling": bev_controlling,
        "per_share_minority": per_share_minority,
        "per_share_controlling": per_share_controlling,
        "lines": lines,
    }


def value_for(result: dict, level: str, basis: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Pulls the (low, high) pair matching a Dashboard (level, basis) selection
    from a run_bridge() result.

    level: "controlling" | "minority"
    basis: "BEV" | "Equity" | "$/Share"
    """
    assert level in ("controlling", "minority")
    if basis == "$/Share":
        return result[f"per_share_{level}"]
    if basis == "Equity":
        return result[f"equity_{level}"]
    return result[f"bev_{level}"]