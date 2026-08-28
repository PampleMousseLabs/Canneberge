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
        operating_expense_adj, d&a_for_ebitda, amortization,
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

    da = _add(raw.get("d&a_for_ebitda"), raw.get("amortization"))
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
    Component sums for Subject BS totals.
    Subtotal rule: if a published subtotal is present, use it;
    otherwise sum the parts. Never add both.
    """
    cash_sti = raw.get("cash_short_term_investments")
    if cash_sti is not None:
        # Subtotal already includes Cash + ST Investments + Trading Asset
        # Securities, so those three must NOT be added again below.
        cash_val = cash_sti
        trading_val = None
    else:
        cash_val = _add(raw.get("cash"), raw.get("st_investments"))
        trading_val = raw.get("trading_asset_securities")

    unearned_val = raw.get("unearned_revenue")
    if unearned_val is None:
        unearned_val = raw.get("current_unearned_revenue")

    pref_val = raw.get("preferred_stock")
    if pref_val is None:
        pref_val = _add(
            raw.get("preferred_stock_redeemable"),
            raw.get("preferred_stock_non_redeemable"),
            raw.get("preferred_stock_convertible"),
            raw.get("preferred_stock_other"),
        )

    total_current_assets = _add(
        cash_val,
        trading_val,
        raw.get("accounts_receivable"),
        raw.get("receivables"),
        raw.get("other_receivables"),
        raw.get("inventory"),
        raw.get("finance_div_loans_and_leases"),
        raw.get("finance_div_other_current_assets"),
        raw.get("prepaid_expenses"),
        raw.get("loans_receivable_current"),
        raw.get("restricted_cash"),
        raw.get("other_current_assets"),
    )

    total_assets = _add(
        total_current_assets,
        raw.get("ppe"),
        raw.get("net_nuclear_fuel"),
        raw.get("lt_investments"),
        raw.get("regulatory_assets"),
        raw.get("goodwill"),
        raw.get("intangible_assets"),
        raw.get("finance_div_loans_and_leases_long_term"),
        raw.get("long_term_accounts_receivable"),
        raw.get("long_term_loans_receivable"),
        raw.get("long_term_deferred_tax_assets"),
        raw.get("long_term_deferred_charges"),
        raw.get("other_lt_assets"),
    )

    total_current_liab = _add(
        raw.get("st_debt"),
        raw.get("current_ltd"),
        raw.get("current_leases"),
        raw.get("accounts_payable"),
        raw.get("accrued_expenses"),
        unearned_val,
        raw.get("other_current_liab"),
        raw.get("finance_div_debt_current"),
        raw.get("finance_div_other_current_liabilities"),
        raw.get("current_income_taxes_payable"),
    )

    total_liabilities = _add(
        total_current_liab,
        raw.get("lt_debt"),
        raw.get("finance_div_debt_long_term"),
        raw.get("lt_leases"),
        raw.get("lt_operating_leases"),
        raw.get("finance_div_other_long_term_liabilities"),
        raw.get("trust_preferred_securities"),
        raw.get("long_term_unearned_revenue"),
        raw.get("pension_post_retirement_benefits"),
        raw.get("long_term_deferred_tax_liabilities"),
        raw.get("other_lt_liab"),
    )

    total_equity = _add(
        pref_val,
        raw.get("common_stock"),
        raw.get("apic"),
        raw.get("treasury_stock"),
        raw.get("aoci"),
        raw.get("minority_interest"),
        raw.get("retained_earnings"),
        raw.get("distributions_in_excess_of_earnings"),
        raw.get("placeholder2"),
        raw.get("placeholder"),
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