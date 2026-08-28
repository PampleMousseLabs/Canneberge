"""
sa_key.py
Canneberge — Transforms

Statically compiled StockAnalysis keymap. 
Compiled once from master_schema_blueprint.json.
Provides 100% offline, zero-overhead lookup for every line item in the 503-company universe.
"""

from typing import Optional, List, Dict

# ------------------------------------------------------------------
# Explicit Core Aliases
# Hand-mapped keys where the app's internal key differs from the
# standard snake_case version of the SA label.
# ------------------------------------------------------------------
_EXPLICIT_ALIASES: Dict[str, dict] = {
    "revenue": {
        "sa_labels": ["revenue"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "cogs": {
        "sa_labels": ["cost of revenue"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "sga": {
        "sa_labels": ["selling, general & admin", "selling, general & administrative"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "rd": {
        "sa_labels": ["research & development"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "other_operating": {
        "sa_labels": ["other operating expenses"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "d&a_for_ebitda": {
        "sa_labels": ["d&a for ebitda", "depreciation & amortization"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "interest_expense": {
        "sa_labels": ["interest expense"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "interest_income": {
        "sa_labels": ["interest income", "interest & investment income"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "other_income": {
        "sa_labels": [
            "other non operating income (expenses)",
            "other non-operating income (expenses)",
            "other non-operating income",
        ],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "pretax_income": {
        "sa_labels": ["pretax income"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "taxes": {
        "sa_labels": ["income tax expense"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "net_income": {
        "sa_labels": ["net income"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "capex": {
        "sa_labels": ["capital expenditures"],
        "sa_source": "CFS",
        "sign_flip": True,
    },
    "acquisitions": {
        "sa_labels": ["cash acquisitions", "cash acquisition"],
        "sa_source": "CFS",
        "sign_flip": True,
    },
    "cash": {
        "sa_labels": ["cash & equivalents"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "st_investments": {
        "sa_labels": ["short-term investments"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "accounts_receivable": {
        "sa_labels": ["accounts receivable"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "receivables": {
        "sa_labels": ["receivables"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "other_receivables": {
        "sa_labels": ["other receivables"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "inventory": {
        "sa_labels": ["inventory"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "prepaid_expenses": {
        "sa_labels": ["prepaid expenses"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "other_current_assets": {
        "sa_labels": ["other current assets"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "ppe": {
        "sa_labels": ["property, plant & equipment"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "intangible_assets": {
        "sa_labels": ["other intangible assets"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "goodwill": {
        "sa_labels": ["goodwill"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "lt_investments": {
        "sa_labels": ["long-term investments"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "other_lt_assets": {
        "sa_labels": ["other long-term assets"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "st_debt": {
        "sa_labels": ["short-term debt"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "current_ltd": {
        "sa_labels": ["current portion of long-term debt"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "current_leases": {
        "sa_labels": ["current portion of leases"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "accounts_payable": {
        "sa_labels": ["accounts payable"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "accrued_expenses": {
        "sa_labels": ["accrued expenses"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "unearned_revenue": {
        "sa_labels": ["current unearned revenue", "long-term unearned revenue"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "other_current_liab": {
        "sa_labels": ["other current liabilities"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "lt_debt": {
        "sa_labels": ["long-term debt"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "lt_leases": {
        "sa_labels": ["long-term leases"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "other_lt_liab": {
        "sa_labels": ["other long-term liabilities"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "common_stock": {
        "sa_labels": ["common stock"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "apic": {
        "sa_labels": ["additional paid-in capital"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "treasury_stock": {
        "sa_labels": ["treasury stock"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "aoci": {
        "sa_labels": ["comprehensive income & other"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "minority_interest": {
        "sa_labels": ["minority interest"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "retained_earnings": {
        "sa_labels": ["retained earnings"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_current_assets": {
        "sa_labels": ["total current assets"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_assets": {
        "sa_labels": ["total assets"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_current_liab": {
        "sa_labels": ["total current liabilities"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_liabilities": {
        "sa_labels": ["total liabilities"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_equity": {
        "sa_labels": ["shareholders' equity"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "total_liab_equity": {
        "sa_labels": ["total liabilities & equity"],
        "sa_source": "BS",
        "sign_flip": False,
    },
    "market_cap": {
        "sa_labels": ["market capitalization"],
        "sa_source": "Ratios",
        "sign_flip": False,
    },
    "effective_tax_rate": {
        "sa_labels": ["effective tax rate"],
        "sa_source": "IS",
        "sign_flip": False,
    },
    "depreciation_amortization": {
        "sa_labels": ["depreciation & amortization"],
        "sa_source": "CFS",
        "sign_flip": False,
    },
}

# ------------------------------------------------------------------
# Statically Compiled Blueprint Keys (REITs, Utilities, Banks, etc.)
# Every single line item found during S&P 500 drift profiling is mapped
# below to its clean snake_case programmatic accessor.
# ------------------------------------------------------------------
_BLUEPRINT_KEYS: Dict[str, dict] = {
    # --- Income Statement (IS) ---
    "revenue_growth": {"sa_labels": ["revenue growth"], "sa_source": "IS", "sign_flip": False},
    "operating_income": {"sa_labels": ["operating income"], "sa_source": "IS", "sign_flip": False},
    "earnings_from_equity_investments": {"sa_labels": ["earnings from equity investments"], "sa_source": "IS", "sign_flip": False},
    "ebt_excluding_unusual_items": {"sa_labels": ["ebt excluding unusual items"], "sa_source": "IS", "sign_flip": False},
    "merger_restructuring_charges": {"sa_labels": ["merger & restructuring charges"], "sa_source": "IS", "sign_flip": False},
    "impairment_of_goodwill": {"sa_labels": ["impairment of goodwill"], "sa_source": "IS", "sign_flip": False},
    "gain_loss_on_sale_of_investments": {"sa_labels": ["gain (loss) on sale of investments"], "sa_source": "IS", "sign_flip": False},
    "gain_loss_on_sale_of_assets": {"sa_labels": ["gain (loss) on sale of assets"], "sa_source": "IS", "sign_flip": False},
    "legal_settlements": {"sa_labels": ["legal settlements"], "sa_source": "IS", "sign_flip": False},
    "earnings_from_continuing_operations": {"sa_labels": ["earnings from continuing operations"], "sa_source": "IS", "sign_flip": False},
    "earnings_from_discontinued_operations": {"sa_labels": ["earnings from discontinued operations"], "sa_source": "IS", "sign_flip": False},
    "net_income_to_company": {"sa_labels": ["net income to company"], "sa_source": "IS", "sign_flip": False},
    "minority_interest_in_earnings": {"sa_labels": ["minority interest in earnings"], "sa_source": "IS", "sign_flip": False},
    "net_income_to_common": {"sa_labels": ["net income to common"], "sa_source": "IS", "sign_flip": False},
    "net_income_growth": {"sa_labels": ["net income growth"], "sa_source": "IS", "sign_flip": False},
    "shares_outstanding_basic": {"sa_labels": ["shares outstanding (basic)"], "sa_source": "IS", "sign_flip": False},
    "shares_outstanding_diluted": {"sa_labels": ["shares outstanding (diluted)"], "sa_source": "IS", "sign_flip": False},
    "shares_change": {"sa_labels": ["shares change"], "sa_source": "IS", "sign_flip": False},
    "eps_basic": {"sa_labels": ["eps (basic)"], "sa_source": "IS", "sign_flip": False},
    "eps_diluted": {"sa_labels": ["eps (diluted)"], "sa_source": "IS", "sign_flip": False},
    "eps_growth": {"sa_labels": ["eps growth"], "sa_source": "IS", "sign_flip": False},
    "free_cash_flow": {"sa_labels": ["free cash flow"], "sa_source": "IS", "sign_flip": False},
    "free_cash_flow_per_share": {"sa_labels": ["free cash flow per share"], "sa_source": "IS", "sign_flip": False},
    "dividend_per_share": {"sa_labels": ["dividend per share"], "sa_source": "IS", "sign_flip": False},
    "dividend_growth": {"sa_labels": ["dividend growth"], "sa_source": "IS", "sign_flip": False},
    "gross_margin": {"sa_labels": ["gross margin"], "sa_source": "IS", "sign_flip": False},
    "operating_margin": {"sa_labels": ["operating margin"], "sa_source": "IS", "sign_flip": False},
    "profit_margin": {"sa_labels": ["profit margin"], "sa_source": "IS", "sign_flip": False},
    "free_cash_flow_margin": {"sa_labels": ["free cash flow margin"], "sa_source": "IS", "sign_flip": False},
    "ebitda_margin": {"sa_labels": ["ebitda margin"], "sa_source": "IS", "sign_flip": False},
    "ebit_margin": {"sa_labels": ["ebit margin"], "sa_source": "IS", "sign_flip": False},
    "advertising_expenses": {"sa_labels": ["advertising expenses"], "sa_source": "IS", "sign_flip": False},
    "currency_exchange_gain_loss": {"sa_labels": ["currency exchange gain (loss)"], "sa_source": "IS", "sign_flip": False},
    "other_non_operating_income_expenses": {"sa_labels": ["other non operating income (expenses)"], "sa_source": "IS", "sign_flip": False},
    "asset_writedown": {"sa_labels": ["asset writedown"], "sa_source": "IS", "sign_flip": False},
    "other_unusual_items": {"sa_labels": ["other unusual items"], "sa_source": "IS", "sign_flip": False},
    "amortization_of_goodwill_intangibles": {"sa_labels": ["amortization of goodwill & intangibles"], "sa_source": "IS", "sign_flip": False},
    "preferred_dividends_other_adjustments": {"sa_labels": ["preferred dividends & other adjustments"], "sa_source": "IS", "sign_flip": False},
    "other_operating_expenses": {"sa_labels": ["other operating expenses"], "sa_source": "IS", "sign_flip": False},
    "revenue_as_reported": {"sa_labels": ["revenue as reported"], "sa_source": "IS", "sign_flip": False},
    "total_operating_expenses": {"sa_labels": ["total operating expenses"], "sa_source": "IS", "sign_flip": False},
    "net_interest_expense": {"sa_labels": ["net interest expense"], "sa_source": "IS", "sign_flip": False},
    "income_loss_on_equity_investments": {"sa_labels": ["income (loss) on equity investments"], "sa_source": "IS", "sign_flip": False},
    "allowance_for_equity_funds_for_construction": {"sa_labels": ["allowance for equity funds for construction"], "sa_source": "IS", "sign_flip": False},
    "other_non_operating_income_expenses_dash": {"sa_labels": ["other non-operating income (expenses)"], "sa_source": "IS", "sign_flip": False},
    "restructuring_charges": {"sa_labels": ["restructuring charges"], "sa_source": "IS", "sign_flip": False},
    "insurance_settlements": {"sa_labels": ["insurance settlements"], "sa_source": "IS", "sign_flip": False},
    "earnings_from_continuing_ops": {"sa_labels": ["earnings from continuing ops."], "sa_source": "IS", "sign_flip": False},
    "earnings_from_discontinued_ops": {"sa_labels": ["earnings from discontinued ops."], "sa_source": "IS", "sign_flip": False},
    "premiums_annuity_revenue": {"sa_labels": ["premiums & annuity revenue"], "sa_source": "IS", "sign_flip": False},
    "total_interest_dividend_income": {"sa_labels": ["total interest & dividend income"], "sa_source": "IS", "sign_flip": False},
    "other_revenue": {"sa_labels": ["other revenue"], "sa_source": "IS", "sign_flip": False},
    "total_revenue": {"sa_labels": ["total revenue"], "sa_source": "IS", "sign_flip": False},
    "policy_benefits": {"sa_labels": ["policy benefits"], "sa_source": "IS", "sign_flip": False},
    "policy_acquisition_underwriting_costs": {"sa_labels": ["policy acquisition & underwriting costs"], "sa_source": "IS", "sign_flip": False},
    "selling_general_administrative": {"sa_labels": ["selling, general & administrative"], "sa_source": "IS", "sign_flip": False},
    "rental_revenue": {"sa_labels": ["rental revenue"], "sa_source": "IS", "sign_flip": False},
    "revenue_growth_yoy": {"sa_labels": ["revenue growth (yoy"], "sa_source": "IS", "sign_flip": False},
    "property_expenses": {"sa_labels": ["property expenses"], "sa_source": "IS", "sign_flip": False},
    "depreciation_amortization": {"sa_labels": ["depreciation & amortization"], "sa_source": "IS", "sign_flip": False},
    "basic_shares_outstanding": {"sa_labels": ["basic shares outstanding"], "sa_source": "IS", "sign_flip": False},
    "diluted_shares_outstanding": {"sa_labels": ["diluted shares outstanding"], "sa_source": "IS", "sign_flip": False},
    "da_for_ebitda": {"sa_labels": ["d&a for ebitda"], "sa_source": "IS", "sign_flip": False},
    "funds_from_operations_ffo": {"sa_labels": ["funds from operations (ffo)"], "sa_source": "IS", "sign_flip": False},
    "ffo_per_share": {"sa_labels": ["ffo per share"], "sa_source": "IS", "sign_flip": False},
    "adjusted_funds_from_operations_affo": {"sa_labels": ["adjusted funds from operations (affo)"], "sa_source": "IS", "sign_flip": False},
    "affo_per_share": {"sa_labels": ["affo per share"], "sa_source": "IS", "sign_flip": False},
    "ffo_payout_ratio": {"sa_labels": ["ffo payout ratio"], "sa_source": "IS", "sign_flip": False},
    "fuel_purchased_power": {"sa_labels": ["fuel & purchased power"], "sa_source": "IS", "sign_flip": False},
    "operations_maintenance": {"sa_labels": ["operations & maintenance"], "sa_source": "IS", "sign_flip": False},
    "operating_revenue": {"sa_labels": ["operating revenue"], "sa_source": "IS", "sign_flip": False},
    "interest_and_dividend_income": {"sa_labels": ["interest and dividend income"], "sa_source": "IS", "sign_flip": False},
    "total_interest_expense": {"sa_labels": ["total interest expense"], "sa_source": "IS", "sign_flip": False},
    "net_interest_income": {"sa_labels": ["net interest income"], "sa_source": "IS", "sign_flip": False},
    "commissions_and_fees": {"sa_labels": ["commissions and fees"], "sa_source": "IS", "sign_flip": False},
    "revenue_before_loan_losses": {"sa_labels": ["revenue before loan losses"], "sa_source": "IS", "sign_flip": False},
    "provision_for_loan_losses": {"sa_labels": ["provision for loan losses"], "sa_source": "IS", "sign_flip": False},
    "salaries_employee_benefits": {"sa_labels": ["salaries & employee benefits"], "sa_source": "IS", "sign_flip": False},
    "cost_of_services_provided": {"sa_labels": ["cost of services provided"], "sa_source": "IS", "sign_flip": False},
    "other_non_operating_income": {"sa_labels": ["other non-operating income"], "sa_source": "IS", "sign_flip": False},
    "asset_management_fee": {"sa_labels": ["asset management fee"], "sa_source": "IS", "sign_flip": False},
    "gain_on_sale_of_investments_rev": {"sa_labels": ["gain on sale of investments (rev)"], "sa_source": "IS", "sign_flip": False},
    "interest_income_on_loans": {"sa_labels": ["interest income on loans"], "sa_source": "IS", "sign_flip": False},
    "total_interest_income": {"sa_labels": ["total interest income"], "sa_source": "IS", "sign_flip": False},
    "interest_paid_on_deposits": {"sa_labels": ["interest paid on deposits"], "sa_source": "IS", "sign_flip": False},
    "net_interest_income_growth": {"sa_labels": ["net interest income growth"], "sa_source": "IS", "sign_flip": False},
    "other_non_interest_income": {"sa_labels": ["other non-interest income"], "sa_source": "IS", "sign_flip": False},
    "total_non_interest_income": {"sa_labels": ["total non-interest income"], "sa_source": "IS", "sign_flip": False},
    "non_interest_income_growth": {"sa_labels": ["non-interest income growth"], "sa_source": "IS", "sign_flip": False},
    "revenues_before_loan_losses": {"sa_labels": ["revenues before loan losses"], "sa_source": "IS", "sign_flip": False},
    "salaries_and_employee_benefits": {"sa_labels": ["salaries and employee benefits"], "sa_source": "IS", "sign_flip": False},
    "occupancy_expenses": {"sa_labels": ["occupancy expenses"], "sa_source": "IS", "sign_flip": False},
    "other_non_interest_expense": {"sa_labels": ["other non-interest expense"], "sa_source": "IS", "sign_flip": False},
    "total_non_interest_expense": {"sa_labels": ["total non-interest expense"], "sa_source": "IS", "sign_flip": False},
    "trading_principal_transactions": {"sa_labels": ["trading & principal transactions"], "sa_source": "IS", "sign_flip": False},
    "currency_exchange_gains": {"sa_labels": ["currency exchange gains"], "sa_source": "IS", "sign_flip": False},
    "trust_income": {"sa_labels": ["trust income"], "sa_source": "IS", "sign_flip": False},
    "property_management_fees": {"sa_labels": ["property management fees"], "sa_source": "IS", "sign_flip": False},
    "interest_income_on_investments": {"sa_labels": ["interest income on investments"], "sa_source": "IS", "sign_flip": False},
    "interest_paid_on_borrowings": {"sa_labels": ["interest paid on borrowings"], "sa_source": "IS", "sign_flip": False},
    "income_from_trading_activities": {"sa_labels": ["income from trading activities"], "sa_source": "IS", "sign_flip": False},
    "mortgage_banking_activities": {"sa_labels": ["mortgage banking activities"], "sa_source": "IS", "sign_flip": False},
    "allowance_for_borrowed_funds_for_construction": {"sa_labels": ["allowance for borrowed funds for construction"], "sa_source": "IS", "sign_flip": False},
    "total_merger_restructuring_charges": {"sa_labels": ["total merger & restructuring charges"], "sa_source": "IS", "sign_flip": False},
    "total_legal_settlements": {"sa_labels": ["total legal settlements"], "sa_source": "IS", "sign_flip": False},
    "gain_loss_on_sale_of_equity_investments": {"sa_labels": ["gain (loss) on sale of equity investments"], "sa_source": "IS", "sign_flip": False},
    "brokerage_commission": {"sa_labels": ["brokerage commission"], "sa_source": "IS", "sign_flip": False},
    "underwriting_investment_banking_fee": {"sa_labels": ["underwriting & investment banking fee"], "sa_source": "IS", "sign_flip": False},
    "total_insurance_settlements": {"sa_labels": ["total insurance settlements"], "sa_source": "IS", "sign_flip": False},
    "federal_deposit_insurance": {"sa_labels": ["federal deposit insurance"], "sa_source": "IS", "sign_flip": False},
    "non_insurance_activities_revenue": {"sa_labels": ["non-insurance activities revenue"], "sa_source": "IS", "sign_flip": False},
    "non_insurance_activities_expense": {"sa_labels": ["non-insurance activities expense"], "sa_source": "IS", "sign_flip": False},
    "provision_for_bad_debts": {"sa_labels": ["provision for bad debts"], "sa_source": "IS", "sign_flip": False},
    "gain_loss_on_sale_of_assets_rev": {"sa_labels": ["gain (loss) on sale of assets (rev)"], "sa_source": "IS", "sign_flip": False},

    # --- Balance Sheet (BS) ---
    "cash_short_term_investments": {"sa_labels": ["cash & short-term investments"], "sa_source": "BS", "sign_flip": False},
    "cash_growth": {"sa_labels": ["cash growth"], "sa_source": "BS", "sign_flip": False},
    "long_term_deferred_tax_assets": {"sa_labels": ["long-term deferred tax assets"], "sa_source": "BS", "sign_flip": False},
    "current_income_taxes_payable": {"sa_labels": ["current income taxes payable"], "sa_source": "BS", "sign_flip": False},
    "current_unearned_revenue": {"sa_labels": ["current unearned revenue"], "sa_source": "BS", "sign_flip": False},
    "pension_post_retirement_benefits": {"sa_labels": ["pension & post-retirement benefits"], "sa_source": "BS", "sign_flip": False},
    "long_term_deferred_tax_liabilities": {"sa_labels": ["long-term deferred tax liabilities"], "sa_source": "BS", "sign_flip": False},
    "total_common_equity": {"sa_labels": ["total common equity"], "sa_source": "BS", "sign_flip": False},
    "total_debt": {"sa_labels": ["total debt"], "sa_source": "BS", "sign_flip": False},
    "net_cash_debt": {"sa_labels": ["net cash (debt)"], "sa_source": "BS", "sign_flip": False},
    "net_cash_growth": {"sa_labels": ["net cash growth"], "sa_source": "BS", "sign_flip": False},
    "net_cash_per_share": {"sa_labels": ["net cash per share"], "sa_source": "BS", "sign_flip": False},
    "filing_date_shares_outstanding": {"sa_labels": ["filing date shares outstanding"], "sa_source": "BS", "sign_flip": False},
    "total_common_shares_outstanding": {"sa_labels": ["total common shares outstanding"], "sa_source": "BS", "sign_flip": False},
    "working_capital": {"sa_labels": ["working capital"], "sa_source": "BS", "sign_flip": False},
    "book_value_per_share": {"sa_labels": ["book value per share"], "sa_source": "BS", "sign_flip": False},
    "tangible_book_value": {"sa_labels": ["tangible book value"], "sa_source": "BS", "sign_flip": False},
    "tangible_book_value_per_share": {"sa_labels": ["tangible book value per share"], "sa_source": "BS", "sign_flip": False},
    "land": {"sa_labels": ["land"], "sa_source": "BS", "sign_flip": False},
    "buildings": {"sa_labels": ["buildings"], "sa_source": "BS", "sign_flip": False},
    "machinery": {"sa_labels": ["machinery"], "sa_source": "BS", "sign_flip": False},
    "construction_in_progress": {"sa_labels": ["construction in progress"], "sa_source": "BS", "sign_flip": False},
    "trading_asset_securities": {"sa_labels": ["trading asset securities"], "sa_source": "BS", "sign_flip": False},
    "long_term_accounts_receivable": {"sa_labels": ["long-term accounts receivable"], "sa_source": "BS", "sign_flip": False},
    "long_term_deferred_charges": {"sa_labels": ["long-term deferred charges"], "sa_source": "BS", "sign_flip": False},
    "long_term_unearned_revenue": {"sa_labels": ["long-term unearned revenue"], "sa_source": "BS", "sign_flip": False},
    "leasehold_improvements": {"sa_labels": ["leasehold improvements"], "sa_source": "BS", "sign_flip": False},
    "restricted_cash": {"sa_labels": ["restricted cash"], "sa_source": "BS", "sign_flip": False},
    "loans_receivable_current": {"sa_labels": ["loans receivable current"], "sa_source": "BS", "sign_flip": False},
    "regulatory_assets": {"sa_labels": ["regulatory assets"], "sa_source": "BS", "sign_flip": False},
    "long_term_loans_receivable": {"sa_labels": ["long-term loans receivable"], "sa_source": "BS", "sign_flip": False},
    "total_preferred_equity": {"sa_labels": ["total preferred equity"], "sa_source": "BS", "sign_flip": False},
    "investments_in_debt_securities": {"sa_labels": ["investments in debt securities"], "sa_source": "BS", "sign_flip": False},
    "investments_in_equity_preferred_securities": {"sa_labels": ["investments in equity & preferred securities"], "sa_source": "BS", "sign_flip": False},
    "policy_loans": {"sa_labels": ["policy loans"], "sa_source": "BS", "sign_flip": False},
    "other_investments": {"sa_labels": ["other investments"], "sa_source": "BS", "sign_flip": False},
    "total_investments": {"sa_labels": ["total investments"], "sa_source": "BS", "sign_flip": False},
    "reinsurance_recoverable": {"sa_labels": ["reinsurance recoverable"], "sa_source": "BS", "sign_flip": False},
    "deferred_policy_acquisition_cost": {"sa_labels": ["deferred policy acquisition cost"], "sa_source": "BS", "sign_flip": False},
    "insurance_annuity_liabilities": {"sa_labels": ["insurance & annuity liabilities"], "sa_source": "BS", "sign_flip": False},
    "unpaid_claims": {"sa_labels": ["unpaid claims"], "sa_source": "BS", "sign_flip": False},
    "unearned_premiums": {"sa_labels": ["unearned premiums"], "sa_source": "BS", "sign_flip": False},
    "total_real_estate_assets": {"sa_labels": ["total real estate assets"], "sa_source": "BS", "sign_flip": False},
    "investment_in_debt_and_equity_securities": {"sa_labels": ["investment in debt and equity securities"], "sa_source": "BS", "sign_flip": False},
    "deferred_long_term_charges": {"sa_labels": ["deferred long-term charges"], "sa_source": "BS", "sign_flip": False},
    "net_cash_debt_growth": {"sa_labels": ["net cash (debt) growth"], "sa_source": "BS", "sign_flip": False},
    "order_backlog": {"sa_labels": ["order backlog"], "sa_source": "BS", "sign_flip": False},
    "loans_lease_receivables": {"sa_labels": ["loans & lease receivables"], "sa_source": "BS", "sign_flip": False},
    "interest_bearing_deposits": {"sa_labels": ["interest bearing deposits"], "sa_source": "BS", "sign_flip": False},
    "non_interest_bearing_deposits": {"sa_labels": ["non-interest bearing deposits"], "sa_source": "BS", "sign_flip": False},
    "total_deposits": {"sa_labels": ["total deposits"], "sa_source": "BS", "sign_flip": False},
    "separate_account_assets": {"sa_labels": ["separate account assets"], "sa_source": "BS", "sign_flip": False},
    "separate_account_liability": {"sa_labels": ["separate account liability"], "sa_source": "BS", "sign_flip": False},
    "preferred_stock_redeemable": {"sa_labels": ["preferred stock, redeemable"], "sa_source": "BS", "sign_flip": False},
    "deferred_long_term_tax_assets": {"sa_labels": ["deferred long-term tax assets"], "sa_source": "BS", "sign_flip": False},
    "distributions_in_excess_of_earnings": {"sa_labels": ["distributions in excess of earnings"], "sa_source": "BS", "sign_flip": False},
    "investments_in_debt_equity_securities": {"sa_labels": ["investments in debt & equity securities"], "sa_source": "BS", "sign_flip": False},
    "reinsurance_payable": {"sa_labels": ["reinsurance payable"], "sa_source": "BS", "sign_flip": False},
    "investment_securities": {"sa_labels": ["investment securities"], "sa_source": "BS", "sign_flip": False},
    "mortgage_backed_securities": {"sa_labels": ["mortgage-backed securities"], "sa_source": "BS", "sign_flip": False},
    "gross_loans": {"sa_labels": ["gross loans"], "sa_source": "BS", "sign_flip": False},
    "allowance_for_loan_losses": {"sa_labels": ["allowance for loan losses"], "sa_source": "BS", "sign_flip": False},
    "net_loans": {"sa_labels": ["net loans"], "sa_source": "BS", "sign_flip": False},
    "loans_held_for_sale": {"sa_labels": ["loans held for sale"], "sa_source": "BS", "sign_flip": False},
    "accrued_interest_receivable": {"sa_labels": ["accrued interest receivable"], "sa_source": "BS", "sign_flip": False},
    "other_real_estate_owned_foreclosed": {"sa_labels": ["other real estate owned & foreclosed"], "sa_source": "BS", "sign_flip": False},
    "short_term_borrowings": {"sa_labels": ["short-term borrowings"], "sa_source": "BS", "sign_flip": False},
    "federal_home_loan_bank_debt_long_term": {"sa_labels": ["federal home loan bank debt, long-term"], "sa_source": "BS", "sign_flip": False},
    "trust_preferred_securities": {"sa_labels": ["trust preferred securities"], "sa_source": "BS", "sign_flip": False},
    "other_adjustments_to_gross_loans": {"sa_labels": ["other adjustments to gross loans"], "sa_source": "BS", "sign_flip": False},
    "institutional_deposits": {"sa_labels": ["institutional deposits"], "sa_source": "BS", "sign_flip": False},
    "finance_div_loans_and_leases": {"sa_labels": ["finance div. loans and leases"], "sa_source": "BS", "sign_flip": False},
    "finance_div_loans_and_leases_long_term": {"sa_labels": ["finance div. loans and leases long-term"], "sa_source": "BS", "sign_flip": False},
    "finance_div_debt_current": {"sa_labels": ["finance div. debt current"], "sa_source": "BS", "sign_flip": False},
    "finance_div_debt_long_term": {"sa_labels": ["finance div. debt long-term"], "sa_source": "BS", "sign_flip": False},
    "accrued_interest_payable": {"sa_labels": ["accrued interest payable"], "sa_source": "BS", "sign_flip": False},
    "preferred_stock_other": {"sa_labels": ["preferred stock, other"], "sa_source": "BS", "sign_flip": False},
    "finance_div_other_current_assets": {"sa_labels": ["finance div. other current assets"], "sa_source": "BS", "sign_flip": False},
    "finance_div_other_current_liabilities": {"sa_labels": ["finance div. other current liabilities"], "sa_source": "BS", "sign_flip": False},
    "finance_div_other_long_term_liabilities": {"sa_labels": ["finance div. other long-term liabilities"], "sa_source": "BS", "sign_flip": False},
    "preferred_stock_convertible": {"sa_labels": ["preferred stock, convertible"], "sa_source": "BS", "sign_flip": False},
    "net_nuclear_fuel": {"sa_labels": ["net nuclear fuel"], "sa_source": "BS", "sign_flip": False},
    "preferred_stock_non_redeemable": {"sa_labels": ["preferred stock, non-redeemable"], "sa_source": "BS", "sign_flip": False},

    # --- Cash Flow Statement (CFS) ---
    "loss_gain_from_sale_of_assets": {"sa_labels": ["loss (gain) from sale of assets"], "sa_source": "CFS", "sign_flip": False},
    "asset_writedown_restructuring_costs": {"sa_labels": ["asset writedown & restructuring costs"], "sa_source": "CFS", "sign_flip": False},
    "stock_based_compensation": {"sa_labels": ["stock-based compensation"], "sa_source": "CFS", "sign_flip": False},
    "other_operating_activities": {"sa_labels": ["other operating activities"], "sa_source": "CFS", "sign_flip": False},
    "change_in_accounts_receivable": {"sa_labels": ["change in accounts receivable"], "sa_source": "CFS", "sign_flip": False},
    "change_in_inventory": {"sa_labels": ["change in inventory"], "sa_source": "CFS", "sign_flip": False},
    "change_in_accounts_payable": {"sa_labels": ["change in accounts payable"], "sa_source": "CFS", "sign_flip": False},
    "change_in_income_taxes": {"sa_labels": ["change in income taxes"], "sa_source": "CFS", "sign_flip": False},
    "change_in_other_net_operating_assets": {"sa_labels": ["change in other net operating assets"], "sa_source": "CFS", "sign_flip": False},
    "operating_cash_flow": {"sa_labels": ["operating cash flow"], "sa_source": "CFS", "sign_flip": False},
    "operating_cash_flow_growth": {"sa_labels": ["operating cash flow growth"], "sa_source": "CFS", "sign_flip": False},
    "sale_of_property_plant_equipment": {"sa_labels": ["sale of property, plant & equipment"], "sa_source": "CFS", "sign_flip": False},
    "divestitures": {"sa_labels": ["divestitures"], "sa_source": "CFS", "sign_flip": False},
    "investment_in_securities": {"sa_labels": ["investment in securities"], "sa_source": "CFS", "sign_flip": False},
    "other_investing_activities": {"sa_labels": ["other investing activities"], "sa_source": "CFS", "sign_flip": False},
    "investing_cash_flow": {"sa_labels": ["investing cash flow"], "sa_source": "CFS", "sign_flip": False},
    "short_term_debt_issued": {"sa_labels": ["short-term debt issued"], "sa_source": "CFS", "sign_flip": False},
    "long_term_debt_issued": {"sa_labels": ["long-term debt issued"], "sa_source": "CFS", "sign_flip": False},
    "total_debt_issued": {"sa_labels": ["total debt issued"], "sa_source": "CFS", "sign_flip": False},
    "short_term_debt_repaid": {"sa_labels": ["short-term debt repaid"], "sa_source": "CFS", "sign_flip": False},
    "long_term_debt_repaid": {"sa_labels": ["long-term debt repaid"], "sa_source": "CFS", "sign_flip": False},
    "total_debt_repaid": {"sa_labels": ["total debt repaid"], "sa_source": "CFS", "sign_flip": False},
    "net_debt_issued_repaid": {"sa_labels": ["net debt issued (repaid)"], "sa_source": "CFS", "sign_flip": False},
    "issuance_of_common_stock": {"sa_labels": ["issuance of common stock"], "sa_source": "CFS", "sign_flip": False},
    "repurchase_of_common_stock": {"sa_labels": ["repurchase of common stock"], "sa_source": "CFS", "sign_flip": False},
    "common_dividends_paid": {"sa_labels": ["common dividends paid"], "sa_source": "CFS", "sign_flip": False},
    "other_financing_activities": {"sa_labels": ["other financing activities"], "sa_source": "CFS", "sign_flip": False},
    "financing_cash_flow": {"sa_labels": ["financing cash flow"], "sa_source": "CFS", "sign_flip": False},
    "foreign_exchange_rate_adjustments": {"sa_labels": ["foreign exchange rate adjustments"], "sa_source": "CFS", "sign_flip": False},
    "miscellaneous_cash_flow_adjustments": {"sa_labels": ["miscellaneous cash flow adjustments"], "sa_source": "CFS", "sign_flip": False},
    "net_cash_flow": {"sa_labels": ["net cash flow"], "sa_source": "CFS", "sign_flip": False},
    "free_cash_flow_growth": {"sa_labels": ["free cash flow growth"], "sa_source": "CFS", "sign_flip": False},
    "free_cash_flow_margin": {"sa_labels": ["free cash flow margin"], "sa_source": "CFS", "sign_flip": False},
    "levered_free_cash_flow": {"sa_labels": ["levered free cash flow"], "sa_source": "CFS", "sign_flip": False},
    "unlevered_free_cash_flow": {"sa_labels": ["unlevered free cash flow"], "sa_source": "CFS", "sign_flip": False},
    "cash_interest_paid": {"sa_labels": ["cash interest paid"], "sa_source": "CFS", "sign_flip": False},
    "cash_income_tax_paid": {"sa_labels": ["cash income tax paid"], "sa_source": "CFS", "sign_flip": False},
    "change_in_working_capital": {"sa_labels": ["change in working capital"], "sa_source": "CFS", "sign_flip": False},
    "cash_acquisitions": {"sa_labels": ["cash acquisitions"], "sa_source": "CFS", "sign_flip": False},
    "other_amortization": {"sa_labels": ["other amortization"], "sa_source": "CFS", "sign_flip": False},
    "change_in_unearned_revenue": {"sa_labels": ["change in unearned revenue"], "sa_source": "CFS", "sign_flip": False},
    "loss_gain_from_sale_of_investments": {"sa_labels": ["loss (gain) from sale of investments"], "sa_source": "CFS", "sign_flip": False},
    "loss_gain_on_equity_investments": {"sa_labels": ["loss (gain) on equity investments"], "sa_source": "CFS", "sign_flip": False},
    "loss_gain_on_sale_of_assets": {"sa_labels": ["loss (gain) on sale of assets"], "sa_source": "CFS", "sign_flip": False},
    "loss_gain_on_sale_of_investments": {"sa_labels": ["loss (gain) on sale of investments"], "sa_source": "CFS", "sign_flip": False},
    "asset_writedown_cfs": {"sa_labels": ["asset writedown"], "sa_source": "CFS", "sign_flip": False},
    "gain_loss_on_sale_of_investments_cfs": {"sa_labels": ["gain (loss) on sale of investments"], "sa_source": "CFS", "sign_flip": False},
    "change_in_insurance_reserves_liabilities": {"sa_labels": ["change in insurance reserves / liabilities"], "sa_source": "CFS", "sign_flip": False},
    "repurchases_of_common_stock": {"sa_labels": ["repurchases of common stock"], "sa_source": "CFS", "sign_flip": False},
    "sale_purchase_of_intangibles": {"sa_labels": ["sale (purchase) of intangibles"], "sa_source": "CFS", "sign_flip": False},
    "preferred_dividends_paid": {"sa_labels": ["preferred dividends paid"], "sa_source": "CFS", "sign_flip": False},
    "dividends_paid": {"sa_labels": ["dividends paid"], "sa_source": "CFS", "sign_flip": False},
    "acquisition_of_real_estate_assets": {"sa_labels": ["acquisition of real estate assets"], "sa_source": "CFS", "sign_flip": False},
    "sale_of_real_estate_assets": {"sa_labels": ["sale of real estate assets"], "sa_source": "CFS", "sign_flip": False},
    "net_sale_acq_of_real_estate_assets": {"sa_labels": ["net sale / acq. of real estate assets"], "sa_source": "CFS", "sign_flip": False},
    "investment_in_marketable_equity_securities": {"sa_labels": ["investment in marketable & equity securities"], "sa_source": "CFS", "sign_flip": False},
    "total_dividends_paid": {"sa_labels": ["total dividends paid"], "sa_source": "CFS", "sign_flip": False},
    "reinsurance_recoverable_cfs": {"sa_labels": ["reinsurance recoverable"], "sa_source": "CFS", "sign_flip": False},
    "issuance_of_preferred_stock": {"sa_labels": ["issuance of preferred stock"], "sa_source": "CFS", "sign_flip": False},
    "repurchases_of_preferred_stock": {"sa_labels": ["repurchases of preferred stock"], "sa_source": "CFS", "sign_flip": False},
    "nuclear_fuel_expenditures": {"sa_labels": ["nuclear fuel expenditures"], "sa_source": "CFS", "sign_flip": False},
    "contributions_to_nuclear_demissioning_trust": {"sa_labels": ["contributions to nuclear demissioning trust"], "sa_source": "CFS", "sign_flip": False},
    "provision_for_credit_losses": {"sa_labels": ["provision for credit losses"], "sa_source": "CFS", "sign_flip": False},
    "net_decrease_increase_in_loans_originated_sold_operating": {"sa_labels": ["net decrease (increase) in loans originated / sold - operating"], "sa_source": "CFS", "sign_flip": False},
    "net_decrease_increase_in_loans_originated_sold_investing": {"sa_labels": ["net decrease (increase) in loans originated / sold - investing"], "sa_source": "CFS", "sign_flip": False},
    "preferred_share_repurchases": {"sa_labels": ["preferred share repurchases"], "sa_source": "CFS", "sign_flip": False},
    "restructuring_activities": {"sa_labels": ["restructuring activities"], "sa_source": "CFS", "sign_flip": False},
    "net_cash_from_discontinued_operations": {"sa_labels": ["net cash from discontinued operations"], "sa_source": "CFS", "sign_flip": False},
    "cash_acquisition": {"sa_labels": ["cash acquisition"], "sa_source": "CFS", "sign_flip": False},
    "depreciation_amortization_total": {"sa_labels": ["depreciation & amortization, total"], "sa_source": "CFS", "sign_flip": False},
    "gain_loss_on_sale_of_investments_cfs_caps": {"sa_labels": ["gain (loss) on sale of investments"], "sa_source": "CFS", "sign_flip": False},
    "change_in_deferred_taxes": {"sa_labels": ["change in deferred taxes"], "sa_source": "CFS", "sign_flip": False},
    "provision_write_off_of_bad_debts": {"sa_labels": ["provision & write-off of bad debts"], "sa_source": "CFS", "sign_flip": False},
    "preferred_stock_issued": {"sa_labels": ["preferred stock issued"], "sa_source": "CFS", "sign_flip": False},
    "net_increase_decrease_in_deposit_accounts": {"sa_labels": ["net increase (decrease) in deposit accounts"], "sa_source": "CFS", "sign_flip": False},
    "total_asset_writedown": {"sa_labels": ["total asset writedown"], "sa_source": "CFS", "sign_flip": False},
    "change_in_trading_asset_securities": {"sa_labels": ["change in trading asset securities"], "sa_source": "CFS", "sign_flip": False},
    "sale_of_property_plant_and_equipment": {"sa_labels": ["sale of property, plant and equipment"], "sa_source": "CFS", "sign_flip": False},
    "accrued_interest_receivable_cfs": {"sa_labels": ["accrued interest receivable"], "sa_source": "CFS", "sign_flip": False},
    "sale_purchase_of_real_estate": {"sa_labels": ["sale (purchase) of real estate"], "sa_source": "CFS", "sign_flip": False},
    "common_preferred_dividends_paid": {"sa_labels": ["common & preferred dividends paid"], "sa_source": "CFS", "sign_flip": False},
    "purchase_sale_of_intangibles": {"sa_labels": ["purchase / sale of intangibles"], "sa_source": "CFS", "sign_flip": False},

    # --- Ratios (Ratios) ---
    "market_cap_growth": {"sa_labels": ["market cap growth"], "sa_source": "Ratios", "sign_flip": False},
    "enterprise_value": {"sa_labels": ["enterprise value"], "sa_source": "Ratios", "sign_flip": False},
    "last_close_price": {"sa_labels": ["last close price"], "sa_source": "Ratios", "sign_flip": False},
    "forward_pe": {"sa_labels": ["forward pe"], "sa_source": "Ratios", "sign_flip": False},
    "ps_ratio": {"sa_labels": ["ps ratio"], "sa_source": "Ratios", "sign_flip": False},
    "pb_ratio": {"sa_labels": ["pb_ratio"], "sa_source": "Ratios", "sign_flip": False},
    "p_fcf_ratio": {"sa_labels": ["p/fcf ratio"], "sa_source": "Ratios", "sign_flip": False},
    "p_ocf_ratio": {"sa_labels": ["p/ocf ratio"], "sa_source": "Ratios", "sign_flip": False},
    "peg_ratio": {"sa_labels": ["peg ratio"], "sa_source": "Ratios", "sign_flip": False},
    "ev_sales_ratio": {"sa_labels": ["ev/sales ratio"], "sa_source": "Ratios", "sign_flip": False},
    "ev_ebitda_ratio": {"sa_labels": ["ev/ebitda ratio"], "sa_source": "Ratios", "sign_flip": False},
    "ev_ebit_ratio": {"sa_labels": ["ev/ebit ratio"], "sa_source": "Ratios", "sign_flip": False},
    "ev_fcf_ratio": {"sa_labels": ["ev/fcf ratio"], "sa_source": "Ratios", "sign_flip": False},
    "debt_equity_ratio": {"sa_labels": ["debt / equity ratio"], "sa_source": "Ratios", "sign_flip": False},
    "debt_ebitda_ratio": {"sa_labels": ["debt / ebitda ratio"], "sa_source": "Ratios", "sign_flip": False},
    "debt_fcf_ratio": {"sa_labels": ["debt / fcf ratio"], "sa_source": "Ratios", "sign_flip": False},
    "net_debt_equity_ratio": {"sa_labels": ["net debt / equity ratio"], "sa_source": "Ratios", "sign_flip": False},
    "net_debt_ebitda_ratio": {"sa_labels": ["net debt / ebitda ratio"], "sa_source": "Ratios", "sign_flip": False},
    "net_debt_fcf_ratio": {"sa_labels": ["net debt / fcf ratio"], "sa_source": "Ratios", "sign_flip": False},
    "asset_turnover": {"sa_labels": ["asset turnover"], "sa_source": "Ratios", "sign_flip": False},
    "inventory_turnover": {"sa_labels": ["inventory turnover"], "sa_source": "Ratios", "sign_flip": False},
    "quick_ratio_ratio": {"sa_labels": ["quick ratio"], "sa_source": "Ratios", "sign_flip": False},
    "current_ratio_ratio": {"sa_labels": ["current ratio"], "sa_source": "Ratios", "sign_flip": False},
    "return_on_equity_roe": {"sa_labels": ["return on equity (roe)"], "sa_source": "Ratios", "sign_flip": False},
    "return_on_assets_roa": {"sa_labels": ["return on assets (roa)"], "sa_source": "Ratios", "sign_flip": False},
    "return_on_invested_capital_roic": {"sa_labels": ["return on invested capital (roic)"], "sa_source": "Ratios", "sign_flip": False},
    "return_on_capital_employed_roce": {"sa_labels": ["return on capital employed (roce)"], "sa_source": "Ratios", "sign_flip": False},
    "earnings_yield": {"sa_labels": ["earnings yield"], "sa_source": "Ratios", "sign_flip": False},
    "fcf_yield": {"sa_labels": ["fcf yield"], "sa_source": "Ratios", "sign_flip": False},
    "dividend_yield": {"sa_labels": ["dividend yield"], "sa_source": "Ratios", "sign_flip": False},
    "payout_ratio": {"sa_labels": ["payout ratio"], "sa_source": "Ratios", "sign_flip": False},
    "buyback_yield_dilution": {"sa_labels": ["buyback yield / dilution"], "sa_source": "Ratios", "sign_flip": False},
    "total_shareholder_return": {"sa_labels": ["total shareholder return"], "sa_source": "Ratios", "sign_flip": False},
    "p_tbv_ratio": {"sa_labels": ["p/tbv ratio"], "sa_source": "Ratios", "sign_flip": False},
    "price_ffo_ratio": {"sa_labels": ["price/ffo ratio"], "sa_source": "Ratios", "sign_flip": False},
    "price_affo_ratio": {"sa_labels": ["price/affo ratio"], "sa_source": "Ratios", "sign_flip": False},
}

# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def get_sa_labels(internal_key: str) -> List[str]:
    """
    Returns the priority fallback chain of lowercased SA labels for a key.
    Checks explicit aliases first, then falls back to blueprint keys.
    """
    if internal_key in _EXPLICIT_ALIASES:
        return _EXPLICIT_ALIASES[internal_key]["sa_labels"]
    if internal_key in _BLUEPRINT_KEYS:
        return _BLUEPRINT_KEYS[internal_key]["sa_labels"]
    
    # Fallback to direct string conversion if key isn't in either mapping
    label = internal_key.replace("_", " ").strip().lower()
    return [label] if label else []


def get_sa_label(internal_key: str) -> str:
    """
    Returns the primary lowercased SA label for a key.
    """
    labels = get_sa_labels(internal_key)
    return labels[0] if labels else ""


def get_sa_source(internal_key: str) -> Optional[str]:
    """
    Returns the source statement type ("IS", "BS", "CFS", "Ratios") for a key.
    """
    if internal_key in _EXPLICIT_ALIASES:
        return _EXPLICIT_ALIASES[internal_key]["sa_source"]
    if internal_key in _BLUEPRINT_KEYS:
        return _BLUEPRINT_KEYS[internal_key]["sa_source"]
    return None


def get_sign_flip(internal_key: str) -> bool:
    """
    Returns whether to negate the SA value on ingest (for CFS outflows).
    """
    if internal_key in _EXPLICIT_ALIASES:
        return _EXPLICIT_ALIASES[internal_key]["sign_flip"]
    return False


# Reverse lookup cache for drift analyzer mapping
SA_REVERSE: Dict[str, str] = {}
for _key, _def in _EXPLICIT_ALIASES.items():
    for _lbl in _def["sa_labels"]:
        SA_REVERSE[_lbl] = _key

for _key, _def in _BLUEPRINT_KEYS.items():
    for _lbl in _def["sa_labels"]:
        if _lbl not in SA_REVERSE:
            SA_REVERSE[_lbl] = _key