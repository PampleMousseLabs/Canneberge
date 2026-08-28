from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict


def parse_ticker_text(text: str) -> List[str]:
    if not text:
        return []
    cleaned = text.replace("\n", ",").replace(";", ",")
    raw_items = cleaned.split(",")
    tickers = []
    seen = set()
    for item in raw_items:
        ticker = item.strip().upper()
        if ticker and ticker not in seen:
            tickers.append(ticker)
            seen.add(ticker)
    return tickers


def year_from_date_text(value: str, fallback: Optional[int] = None) -> Optional[int]:
    if not value:
        return fallback
    value = value.strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(value, fmt).year
        except ValueError:
            pass
    try:
        return int(value)
    except ValueError:
        return fallback


# IS/BS line item schema. Each tuple: (key, display_label, is_calculated, bold)
# Consumed by:
#   - Ui/private_financials_input_page.py (builds manual-entry grids for private companies)
#   - Ui/subject_financials_page.py (read-only display, both public/StockAnalysis and private paths)
# Keys here are also the same key strings used in PrivateFinancials.is_data/bs_data
# and in SA_KEY_MAP (Ui/subject_financials_page.py) for public-company StockAnalysis lookups.
# When adding a line item during audit, add it here once — both consumers pick it up automatically.
IS_LINES = [
    ("revenue",                    "Revenue",                          False, True),
    ("cogs",                       "COGS",                             False, False),
    ("cogs_adjustment",            "Adjustment to Cost of Goods Sold", False, False),
    ("cost_of_goods_sold",         "Cost of Goods Sold",               True,  True),
    ("gross_profit",               "Gross Profit",                     True,  True),
    ("sga",                        "Operating Expense (SG&A)",         False, False),
    ("rd",                         "Research & Development",           False, False),
    ("other_operating",            "Other Operating Expense",          False, False),
    ("operating_expense_adj",      "Adjustment to Operating Expense",  False, False),
    ("operating_expenses",         "Operating Expenses",               True,  True),
    ("ebitda",                     "EBITDA",                           True,  True),
    ("d&a_for_ebitda",       "Depreciation Expense",             False, False),
    ("amortization",               "Amortization Expense",             False, False),
    ("ebit",                       "EBIT",                             True,  True),
    ("interest_expense",           "Interest Expense",                 False, False),
    ("interest_income",            "Interest Income",                  False, False),
    ("other_income",               "Other Income/(Expense)",           False, False),
    ("pretax_income",              "Pretax Income",                    True,  True),
    ("taxes",                      "Taxes",                            False, False),
    ("income_before_nonrecurring", "Income Before Nonrecurring Items", True,  True),
    ("nonrecurring",               "Nonrecurring Income/(Expense)",    False, False),
    ("net_income",                 "Net Income",                       True,  True),
    ("interest_expense_after_tax", "Interest Expense (After Tax)",     True,  False),
    ("debt_free_net_income",       "Debt-free Net Income",             True,  True),
    ("capex",                      "Capital Expenditures",             False, False),
    ("acquisitions",               "Acquisitions",                     False, False),
]

BS_LINES = [
    ("cash",                    "Cash and Cash Equivalents",               False, False),
    ("st_investments",          "Short-Term Investments",                  False, False),
    ("trading_asset_securities","Trading Asset Securities",                False, False),
    ("cash_short_term_investments", "Cash & Short-Term Investments",       False, False),
    ("accounts_receivable",     "Accounts Receivable",                     False, False),
    ("receivables",             "Receivables",                             False, False),
    ("other_receivables",       "Other Receivables",                       False, False),
    ("finance_div_loans_and_leases", "Finance Div. Loans and Leases",      False, False),
    ("inventory",               "Inventory",                               False, False),
    ("finance_div_other_current_assets", "Finance Div. Other Current Assets", False, False),
    ("prepaid_expenses",        "Prepaid Expenses",                        False, False),
    ("loans_receivable_current","Loans Receivable Current",                False, False),
    ("restricted_cash",         "Restricted Cash",                         False, False),
    ("other_current_assets",    "Other Current Assets",                    False, False),
    ("total_current_assets",    "Total Current Assets",                    True,  True),
    ("ppe",                     "Net Property Plant & Equipment",          False, False),
    ("net_nuclear_fuel",        "Net Nuclear Fuel",                        False, False),
    ("lt_investments",          "Long-Term Investments",                   False, False),
    ("regulatory_assets",       "Regulatory Assets",                       False, False),
    ("goodwill",                "Goodwill",                                False, False),
    ("intangible_assets",       "Intangible Assets",                       False, False),
    ("finance_div_loans_and_leases_long_term", "Finance Div. Loans and Leases Long-Term", False, False),
    ("long_term_accounts_receivable", "Long-Term Accounts Receivable",     False, False),
    ("long_term_loans_receivable", "Long-Term Loans Receivable",           False, False),
    ("long_term_deferred_tax_assets", "Long-Term Deferred Tax Assets",     False, False),
    ("long_term_deferred_charges", "Long-Term Deferred Charges",           False, False),
    ("other_lt_assets",         "Other Long-Term Assets",                  False, False),
    ("total_assets",            "Total Assets",                            True,  True),
    ("accounts_payable",        "Accounts Payable",                        False, False),
    ("accrued_expenses",        "Accrued Expenses",                        False, False),
    ("st_debt",                 "Short-Term Debt",                         False, False),
    ("current_ltd",             "Current Portion of Long Term Debt",       False, False),
    ("current_leases",          "Current Portion of Long Term Leases",     False, False),
    ("finance_div_debt_current","Finance Div. Debt Current",               False, False),
    ("finance_div_other_current_liabilities", "Finance Div. Other Current Liabilities", False, False),
    ("current_income_taxes_payable", "Current Income Taxes Payable",       False, False),
    ("unearned_revenue",        "Unearned Revenue",                        False, False),
    ("other_current_liab",      "Other Current Liabilities",               False, False),
    ("total_current_liab",      "Total Current Liabilities",               True,  True),
    ("lt_debt",                 "Long-Term Debt",                          False, False),
    ("finance_div_debt_long_term", "Finance Div. Debt Long-Term",          False, False),
    ("lt_leases",               "Long-Term Leases",                        False, False),
    ("lt_operating_leases",     "Long-Term Portion of Operating Leases",   False, False),
    ("finance_div_other_long_term_liabilities", "Finance Div. Other Long-Term Liabilities", False, False),
    ("trust_preferred_securities", "Trust Preferred Securities",           False, False),
    ("long_term_unearned_revenue", "Long-Term Unearned Revenue",           False, False),
    ("pension_post_retirement_benefits", "Pension & Post-Retirement Benefits", False, False),
    ("long_term_deferred_tax_liabilities", "Long-Term Deferred Tax Liabilities", False, False),
    ("other_lt_liab",           "Other Long-Term Liabilities",             False, False),
    ("total_liabilities",       "Total Liabilities",                       True,  True),
    ("preferred_stock_redeemable", "Preferred Stock, Redeemable",          False, False),
    ("preferred_stock_non_redeemable", "Preferred Stock, Non-Redeemable",  False, False),
    ("preferred_stock_convertible", "Preferred Stock, Convertible",        False, False),
    ("preferred_stock",         "Preferred Stock",                         False, False),
    ("preferred_stock_other",   "Preferred Stock, Other",                  False, False),
    ("common_stock",            "Common Stock",                            False, False),
    ("apic",                    "Additional Paid in Capital",              False, False),
    ("retained_earnings",       "Retained Earnings",                       False, False),
    ("distributions_in_excess_of_earnings", "Distributions in Excess of Earnings", False, False),
    ("treasury_stock",          "Treasury Stock",                          False, False),
    ("aoci",                    "Accumulated Other Comprehensive",         False, False),
    ("minority_interest",       "Minority Interest",                       False, False),
    ("placeholder2",            "PLACEHOLDER 2 positive (negative)",       False, False),
    ("placeholder",             "PLACEHOLDER positive (negative)",         False, False),
    ("total_equity",            "Total Shareholders' Equity",              True,  True),
    ("total_liab_equity",       "Total Liabilities & Shareholders' Equity", True, True),
]


@dataclass
class Transaction:
    """One guideline transaction row."""
    closing_date: str = ""
    target: str = ""
    acquirer: str = ""
    bev: Optional[float] = None
    ttm_revenue: Optional[float] = None
    ttm_ebitda: Optional[float] = None
    ttm_ebit: Optional[float] = None

    def implied_multiple(self, metric: str) -> Optional[float]:
        if self.bev is None:
            return None
        if metric == "TTM Revenue":
            denom = self.ttm_revenue
        elif metric == "TTM EBITDA":
            denom = self.ttm_ebitda
        elif metric == "TTM EBIT":
            denom = self.ttm_ebit
        else:
            return None
        if denom is None or denom == 0:
            return None
        return self.bev / denom


@dataclass
class PrivateFinancials:
    """
    Holds all manually entered IS and BS data for a private subject company.
    Each field is a dict keyed by period label:
    'LFY-4', 'LFY-3', 'LFY-2', 'LFY-1', 'LFY', 'TTM', 'YTD', 'NFY', 'NFY+1', 'NFY+2'
    Values are floats or None.
    """

    # IS line items
    is_data: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)

    # BS line items
    bs_data: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)

    def get_is(self, line_item: str, period: str) -> Optional[float]:
        return self.is_data.get(line_item, {}).get(period)

    def get_bs(self, line_item: str, period: str) -> Optional[float]:
        return self.bs_data.get(line_item, {}).get(period)

    def set_is(self, line_item: str, period: str, value: Optional[float]):
        if line_item not in self.is_data:
            self.is_data[line_item] = {}
        self.is_data[line_item][period] = value

    def set_bs(self, line_item: str, period: str, value: Optional[float]):
        if line_item not in self.bs_data:
            self.bs_data[line_item] = {}
        self.bs_data[line_item][period] = value


@dataclass
class ProjectionData:
    """
    Stores all user-typed Projection Module inputs, keyed by projection
    period label (NFY, NFY+1, NFY+2, ..., NFY+N).

    Primary driver fields (user-editable inputs):
      revenue          — $ amount (may be back-computed from growth %)
      revenue_growth   — decimal, e.g. 0.09 = 9% (may be back-computed from revenue $)
      gp_improvement   — decimal; GP margin improvement vs prior year
      ebitda_improvement — decimal; EBITDA margin improvement vs prior year
      da_pct           — decimal; D&A as % of revenue
      capex_pct        — decimal; CapEx as % of revenue

    last_edited_revenue — per period: "revenue" | "growth" | None
      Tracks which of {revenue $, revenue growth %} was typed last so
      two-way binding knows which direction to recompute.

    last_edited_ebitda — per period: "ebitda" | "improvement" | None
      Same pattern for EBITDA $ vs EBITDA improvement %.
      (EBITDA $ is not directly typed — it's computed — but this tracks
      whether improvement % was user-typed or computed from source data,
      which determines whether the cell is editable.)
    """
    revenue:               Dict[str, Optional[float]] = field(default_factory=dict)
    revenue_growth:        Dict[str, Optional[float]] = field(default_factory=dict)
    gross_profit:          Dict[str, Optional[float]] = field(default_factory=dict)
    gp_improvement:        Dict[str, Optional[float]] = field(default_factory=dict)
    ebitda:                Dict[str, Optional[float]] = field(default_factory=dict)
    ebitda_improvement:    Dict[str, Optional[float]] = field(default_factory=dict)
    da:                    Dict[str, Optional[float]] = field(default_factory=dict)
    da_pct:                Dict[str, Optional[float]] = field(default_factory=dict)
    capex:                 Dict[str, Optional[float]] = field(default_factory=dict)
    capex_pct:             Dict[str, Optional[float]] = field(default_factory=dict)
    last_edited_revenue:   Dict[str, Optional[str]]   = field(default_factory=dict)

    def get(self, field_name: str, period: str):
        return getattr(self, field_name, {}).get(period)

    def set(self, field_name: str, period: str, value):
        getattr(self, field_name)[period] = value


@dataclass
class ProjectInputs:
    # General
    client: str = "Ted & Co."
    subject_company_name: str = "COMPANY NAME"
    main_title: str = f"Sensitivity Analysis of {subject_company_name}"
    valuation_date: str = "7/21/2026"
    numeric_scale: str = "Millions"
    draft_final: str = "Draft"
    standard_of_value: str = "Fair Market Value"
    taxable_nontaxable: str = "Taxable/Nontaxable"
    basis_of_value: str = "BEV / Equity Value"

    # Subject company
    company_status: str = "Private Company"
    subject_ticker: str = "SPCX"
    subject_tax_rate: float = 0.21

    last_fiscal_year: str = "12/31/2025"
    last_fiscal_quarter: str = "3/31/2026"
    next_fiscal_year: str = "12/31/2026"
    nfy_1: str = "12/31/2027"
    nfy_2: str = "12/31/2028"

    # Market inputs
    gpc_tickers: List[str] = field(default_factory=list)
    gpc_company_names: Dict[str, str] = field(default_factory=dict)
    gt_transactions: List[Transaction] = field(default_factory=list)

    # Projection controls
    historical_years: int = 5
    projection_years: int = 5

    # Private company financials (populated via private input dialog)
    private_financials: PrivateFinancials = field(
        default_factory=PrivateFinancials
    )

    # Projection module inputs (populated via projection module dialog)
    projection_data: ProjectionData = field(
        default_factory=ProjectionData
    )

    @property
    def is_private(self) -> bool:
        return self.company_status.strip().lower() == "private company"

    @property
    def is_publicly_traded(self) -> bool:
        return self.company_status.strip().lower() == "publicly traded"

    @property
    def last_fiscal_year_year(self) -> Optional[int]:
        return year_from_date_text(self.last_fiscal_year)

    @property
    def next_fiscal_year_year(self) -> Optional[int]:
        return year_from_date_text(self.next_fiscal_year)

    @property
    def nfy_1_year(self) -> Optional[int]:
        return year_from_date_text(self.nfy_1)

    @property
    def nfy_2_year(self) -> Optional[int]:
        return year_from_date_text(self.nfy_2)

    @property
    def historical_period_columns(self) -> List[str]:
        """
        Historical-only labels (LFY-N ... LFY), no TTM/forward/YTD.
        Single source of truth for historical column generation —
        do not duplicate this loop elsewhere.
        """
        hist = []
        for i in range(self.historical_years - 1, 0, -1):
            hist.append(f"LFY-{i}")
        hist.append("LFY")
        return hist

    @property
    def projection_period_columns(self) -> List[str]:
        """
        Ordered projection period labels: NFY, NFY+1, ..., NFY+(N-1).
        Count driven by projection_years spinbox on Home page.
        Single source of truth — do not duplicate this loop elsewhere.
        """
        cols = ["NFY"]
        for i in range(1, self.projection_years):
            cols.append(f"NFY+{i}")
        return cols

    @property
    def period_columns(self) -> List[str]:
        """
        Ordered list of all period column labels for display.
        Historical years + TTM + YTD + NFY + NFY+1 + NFY+2.
        """
        return self.historical_period_columns + ["TTM", "YTD", "NFY", "NFY+1", "NFY+2"]

    @property
    def active_public_tickers(self) -> List[str]:
        tickers = []
        seen = set()
        for ticker in self.gpc_tickers:
            ticker = ticker.strip().upper()
            if ticker and ticker not in seen:
                tickers.append(ticker)
                seen.add(ticker)
        if self.is_publicly_traded:
            subject = self.subject_ticker.strip().upper()
            if subject and subject not in seen:
                tickers.append(subject)
                seen.add(subject)
        return tickers