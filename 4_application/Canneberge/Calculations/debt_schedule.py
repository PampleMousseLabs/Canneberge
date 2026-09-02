"""
debt_schedule.py
Canneberge — Debt Schedule calculation engine.

Pure calculation layer. No Qt, no page imports. Mirrors the Excel
Debt Schedule proration convention exactly:

    interest = balance * rate                       (full period)
    interest = balance * rate * overlap_frac        (partial period)

    overlap_days = (min(maturity, period_end)
                    - max(issuance, prior_end + 1 day)).days + 1
    overlap_frac = overlap_days / (period_end - prior_end).days

A tranche accrues in a period when:
    issuance <= period_end  AND  maturity > prior_end
"""

from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple, Any

DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y")


def parse_date(text) -> Optional[date]:
    if text is None:
        return None
    if isinstance(text, date):
        return text
    s = str(text).strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def add_years(d: date, n: int) -> date:
    """Same month/day n years later; clamps 2/29 to 2/28."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


def build_period_boundaries(
    lfy_end: date,
    nfy_end: date,
    nfy1_end: Optional[date],
    nfy2_end: Optional[date],
    projection_years: int,
    hist_years: int = 1,
) -> List[Tuple[str, date, date]]:
    """
    Returns ordered [(label, prior_end, end)] covering:
    LFY-{hist_years} ... LFY, NFY ... NFY+(projection_years-1).

    Fiscal year ends come from Home's actual date fields; periods
    beyond NFY+2 extrapolate nfy2's month/day forward.
    """
    ends: List[Tuple[str, date]] = []

    for i in range(hist_years, 0, -1):
        ends.append((f"LFY-{i}", add_years(lfy_end, -i)))
    ends.append(("LFY", lfy_end))

    proj_ends: List[date] = [nfy_end]
    if nfy1_end:
        proj_ends.append(nfy1_end)
    if nfy2_end:
        proj_ends.append(nfy2_end)
    anchor = proj_ends[-1]
    while len(proj_ends) < projection_years:
        anchor = add_years(anchor, 1)
        proj_ends.append(anchor)

    for i, end in enumerate(proj_ends[:projection_years]):
        label = "NFY" if i == 0 else f"NFY+{i}"
        ends.append((label, end))

    boundaries: List[Tuple[str, date, date]] = []
    for idx, (label, end) in enumerate(ends):
        if idx == 0:
            prior_end = add_years(end, -1)
        else:
            prior_end = ends[idx - 1][1]
        boundaries.append((label, prior_end, end))
    return boundaries


def tranche_interest_for_period(
    issuance: Optional[date],
    maturity: Optional[date],
    balance: Optional[float],
    rate: Optional[float],
    prior_end: date,
    end: date,
) -> Optional[float]:
    """One tranche, one period. None = not computable; 0.0 = not outstanding."""
    if None in (issuance, maturity) or balance is None or rate is None:
        return None
    if not (issuance <= end and maturity > prior_end):
        return 0.0
    period_days = (end - prior_end).days
    if period_days <= 0:
        return 0.0
    full_from_start = issuance <= prior_end + timedelta(days=1)
    runs_past_end = maturity > end
    if full_from_start and runs_past_end:
        return balance * rate
    overlap_days = (
        min(maturity, end) - max(issuance, prior_end + timedelta(days=1))
    ).days + 1
    if overlap_days <= 0:
        return 0.0
    return balance * rate * overlap_days / period_days


def compute_debt_schedule(
    tranches: List[Dict[str, Any]],
    boundaries: List[Tuple[str, date, date]],
    rate_key: str = "effective_rate",
) -> Dict[str, Any]:
    """
    tranches: [{name, issuance (date), maturity (date), principal (float),
                coupon_rate (decimal), effective_rate (decimal)}]
    Returns:
        interest_by_tranche: [ {period_label: float|None} ] parallel to tranches
        interest_expense_by_period, ending_debt_by_period,
        net_borrowing_by_period: {period_label: float}
    """
    interest_by_tranche: List[Dict[str, Optional[float]]] = []
    total_interest: Dict[str, float] = {}
    ending_debt: Dict[str, float] = {}
    net_borrowing: Dict[str, float] = {}

    for label, prior_end, end in boundaries:
        total_interest[label] = 0.0
        ending_debt[label] = 0.0
        net_borrowing[label] = 0.0

    for tr in tranches:
        row: Dict[str, Optional[float]] = {}
        iss = tr.get("issuance")
        mat = tr.get("maturity")
        bal = tr.get("principal")
        rate = tr.get(rate_key)
        for label, prior_end, end in boundaries:
            v = tranche_interest_for_period(iss, mat, bal, rate, prior_end, end)
            row[label] = v
            if v is not None:
                total_interest[label] += v
            if iss is not None and mat is not None and bal is not None:
                if iss <= end and mat > end:
                    ending_debt[label] += bal
                issued = prior_end < iss <= end
                matured = prior_end < mat <= end
                if issued:
                    net_borrowing[label] += bal
                if matured:
                    net_borrowing[label] -= bal
        interest_by_tranche.append(row)

    return {
        "interest_by_tranche": interest_by_tranche,
        "interest_expense_by_period": total_interest,
        "ending_debt_by_period": ending_debt,
        "net_borrowing_by_period": net_borrowing,
    }