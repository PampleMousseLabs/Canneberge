"""
Shared IS/BS calculated-line logic for Subject Financials.

Takes only the RAW (is_calc=False) line-item values for one period —
regardless of whether those raw values came from StockAnalysis (public)
or PrivateFinancials (private) — and computes every is_calc=True row
from them. Subject Financials must never read a pre-computed value
from either source; it computes its own, every time, from raw inputs.

Formulas mirror private_financials_input_page.py's _recalculate exactly.
That dialog's own calculated fields are irrelevant here — even in
private mode, this module recomputes from the dialog's RAW inputs
independently, rather than trusting what the dialog already computed
and saved.
"""

from typing import Optional, Dict


def _add(*values: Optional[float]) -> Optional[float]:
    result = 0.0
    any_value = False
    for v in values:
        if v is not None:
            result += v
            any_value = True
    return result if any_value else None


def _sub(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None and b is None:
        return None
    return (a or 0.0) - (b or 0.0)


def _neg(v: Optional[float]) -> Optional[float]:
    return -v if v is not None else None


def compute_is_calculated(raw: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """
    raw keys expected (all optional, missing = None):
        revenue, cogs, cogs_adjustment, sga, rd, other_operating,
        operating_expense_adj, depreciation, amortization,
        interest_expense, interest_income, other_income, taxes,
        nonrecurring

    Returns every is_calc=True IS key for this one period.
    """
    cost_of_goods_sold = _add(raw.get("cogs"), raw.get("cogs_adjustment"))
    gross_profit = _sub(raw.get("revenue"), cost_of_goods_sold)

    operating_expenses = _add(
        raw.get("sga"), raw.get("rd"),
        raw.get("other_operating"), raw.get("operating_expense_adj"),
    )

    ebitda = _sub(gross_profit, operating_expenses)

    da = _add(raw.get("depreciation"), raw.get("amortization"))
    ebit = _sub(ebitda, da)

    pretax_income = _add(
        ebit,
        _neg(raw.get("interest_expense")),
        raw.get("interest_income"),
        raw.get("other_income"),
    )

    income_before_nonrecurring = _sub(pretax_income, raw.get("taxes"))
    net_income = _add(income_before_nonrecurring, raw.get("nonrecurring"))

    int_exp = raw.get("interest_expense")
    taxes = raw.get("taxes")
    if int_exp is not None and taxes is not None and pretax_income not in (None, 0):
        interest_expense_after_tax = int_exp * (1 - taxes / pretax_income)
    elif int_exp is not None:
        interest_expense_after_tax = int_exp
    else:
        interest_expense_after_tax = None

    debt_free_net_income = _add(net_income, interest_expense_after_tax)

    return {
        "cost_of_goods_sold": cost_of_goods_sold,
        "gross_profit": gross_profit,
        "operating_expenses": operating_expenses,
        "ebitda": ebitda,
        "ebit": ebit,
        "pretax_income": pretax_income,
        "income_before_nonrecurring": income_before_nonrecurring,
        "net_income": net_income,
        "interest_expense_after_tax": interest_expense_after_tax,
        "debt_free_net_income": debt_free_net_income,
    }


def compute_bs_calculated(raw: Dict[str, Optional[float]]) -> Dict[str, Optional[float]]:
    """
    raw keys expected: cash, st_investments, accounts_receivable,
        receivables, other_receivables, inventory, other_current_assets,
        ppe, intangible_assets, goodwill, lt_investments, other_lt_assets,
        st_debt, current_ltd, current_leases, accounts_payable,
        accrued_expenses, unearned_revenue, other_current_liab,
        lt_debt, lt_leases, lt_operating_leases, other_lt_liab,
        preferred_stock, common_stock, apic, treasury_stock, aoci,
        minority_interest, retained_earnings, placeholder2, placeholder
    """
    total_current_assets = _add(
        raw.get("cash"), raw.get("st_investments"),
        raw.get("accounts_receivable"), raw.get("receivables"),
        raw.get("other_receivables"), raw.get("inventory"),
        raw.get("other_current_assets"),
    )
    total_assets = _add(
        total_current_assets, raw.get("ppe"), raw.get("intangible_assets"),
        raw.get("goodwill"), raw.get("lt_investments"), raw.get("other_lt_assets"),
    )

    total_current_liab = _add(
        raw.get("st_debt"), raw.get("current_ltd"), raw.get("current_leases"),
        raw.get("accounts_payable"), raw.get("accrued_expenses"),
        raw.get("unearned_revenue"), raw.get("other_current_liab"),
    )
    total_liabilities = _add(
        total_current_liab, raw.get("lt_debt"), raw.get("lt_leases"),
        raw.get("lt_operating_leases"), raw.get("other_lt_liab"),
    )

    total_equity = _add(
        raw.get("preferred_stock"), raw.get("common_stock"), raw.get("apic"),
        raw.get("treasury_stock"), raw.get("aoci"), raw.get("minority_interest"),
        raw.get("retained_earnings"), raw.get("placeholder2"), raw.get("placeholder"),
    )
    total_liab_equity = _add(total_liabilities, total_equity)

    return {
        "total_current_assets": total_current_assets,
        "total_assets": total_assets,
        "total_current_liab": total_current_liab,
        "total_liabilities": total_liabilities,
        "total_equity": total_equity,
        "total_liab_equity": total_liab_equity,
    }

# These four are flagged is_calc=True in BS_LINES for display-bolding
# purposes only — StockAnalysis publishes them as literal rows, and
# their raw components (AP, ST Debt, Common Stock, APIC, etc.) don't
# scrape reliably enough to sum locally. Pull these four directly from
# source instead of computing. Total Current Assets/Total Assets are
# the opposite case — their components DO scrape reliably — so those
# two stay computed.
BS_DIRECT_PULL_KEYS = {"total_current_liab", "total_liabilities", "total_equity", "total_liab_equity"}