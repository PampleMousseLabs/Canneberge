"""
chart_helper.py — hidden value-bridge engine behind the Dashboard's
Reconciliation of Values box and football-field chart.

Mirrors the Excel NEW_Chart Helper tab exactly:

    Indicated BEV
    + Cash & Equivalents
    + DFCFNWC Surplus (Deficit)
    + Acquired NOL            (0 for now — public subject)
    + Non-Operating           (0 for now)
    = Invested Capital
    - Debt
    - Liquidation             (subject TTM Preferred Stock)
    = FMV of Equity           (x (1 - DLOC) on controlling-basis rows)
    / Shares Outstanding
    = $ / Share

DLOC applies only to controlling-basis methods (DCF, GT). GPC is
already marketable-noncontrolling, so no DLOC on GPC rows.

Never displayed anywhere; consumed by the Dashboard only.
"""

from dataclasses import dataclass, field
from typing import Optional, List

DEBUG = False  # set True to see debug output in console    


def _dbg(stage: str, msg: str):
    if DEBUG:
        print(f"[ChartHelper] {stage}: {msg}")


@dataclass
class MethodRow:
    """One row of the bridge (one method-multiple)."""
    name: str
    bev_low: Optional[float]
    bev_high: Optional[float]
    apply_dloc: bool  # True for controlling basis (DCF, GT)

    # computed
    ic_low: Optional[float] = None
    ic_high: Optional[float] = None
    equity_low: Optional[float] = None
    equity_high: Optional[float] = None
    per_share_low: Optional[float] = None
    per_share_high: Optional[float] = None

    def values_for_basis(self, basis: str):
        if basis == "Equity":
            return self.equity_low, self.equity_high
        if basis == "$/Share":
            return self.per_share_low, self.per_share_high
        return self.bev_low, self.bev_high


@dataclass
class BridgeInputs:
    cash: Optional[float] = None
    nwc_surplus: Optional[float] = None
    acquired_nol: float = 0.0
    non_operating: float = 0.0
    debt: Optional[float] = None
    liquidation: Optional[float] = None   # subject TTM preferred stock
    dloc: Optional[float] = None          # fraction, e.g. 0.194
    shares_outstanding: Optional[float] = None
    share_price: Optional[float] = None   # for the chart marker line


def compute_bridge(rows: List[MethodRow], inputs: BridgeInputs) -> List[MethodRow]:
    """Runs the full Excel bridge on every method row, in place."""
    cash = inputs.cash or 0.0
    nwc = inputs.nwc_surplus or 0.0
    nol = inputs.acquired_nol or 0.0
    non_op = inputs.non_operating or 0.0
    debt = inputs.debt or 0.0
    liq = inputs.liquidation or 0.0
    dloc = inputs.dloc or 0.0
    shares = inputs.shares_outstanding

    additions = cash + nwc + nol + non_op

    _dbg("inputs",
         f"cash={cash:,.2f} nwc={nwc:,.2f} nol={nol:,.2f} "
         f"non_op={non_op:,.2f} debt={debt:,.2f} liq={liq:,.2f} "
         f"dloc={dloc:.4f} shares={shares}")

    for row in rows:
        if row.bev_low is None and row.bev_high is None:
            _dbg("row", f"{row.name}: no BEV values, skipped")
            continue

        for side in ("low", "high"):
            bev = getattr(row, f"bev_{side}")
            if bev is None:
                continue

            ic = bev + additions
            equity = ic - debt - liq
            if row.apply_dloc and dloc:
                equity *= (1.0 - dloc)

            per_share = (equity / shares) if shares else None

            setattr(row, f"ic_{side}", ic)
            setattr(row, f"equity_{side}", equity)
            setattr(row, f"per_share_{side}", per_share)

        _dbg("row",
             f"{row.name}: BEV=({row.bev_low}, {row.bev_high}) "
             f"IC=({row.ic_low}, {row.ic_high}) "
             f"Eq=({row.equity_low}, {row.equity_high}) "
             f"$/sh=({row.per_share_low}, {row.per_share_high}) "
             f"dloc={'Y' if row.apply_dloc else 'N'}")

    return rows


def weighted_conclusion(low_high_pairs, weights) -> Optional[float]:
    """
    Concluded FV = sum of weight * average(low, high) per method.
    Methods missing a value or weight are skipped, matching the
    _weighted_sum convention used on the GT/GPC pages.
    """
    total = 0.0
    any_present = False
    for (low, high), w in zip(low_high_pairs, weights):
        if low is None or high is None or w is None:
            continue
        total += w * ((low + high) / 2.0)
        any_present = True
    result = total if any_present else None
    _dbg("conclusion", f"weighted FV = {result}")
    return result