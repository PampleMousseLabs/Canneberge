from typing import Optional, List, Dict

import math

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QScrollArea,
    QButtonGroup,
    QPushButton,
    QFrame,
)
from PyQt6.QtCore import Qt

from Canneberge.Transforms.sa_key import get_sa_labels, get_sa_source, get_sign_flip
from Canneberge.utils.sa_utils import build_lookup, to_float
from Canneberge.Calculations.subject_is_bs_calc import (
    compute_is_calculated,
    compute_bs_calculated,
    BS_DIRECT_PULL_KEYS,
    _sub,
)
from Canneberge.app_state import ProjectInputs, PrivateFinancials, ProjectionData, IS_LINES, BS_LINES
from Canneberge.Ui.theme import theme_manager


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


# NOTE: SECTION_STYLE below has zero call sites anywhere in this file
# (confirmed via full-file search) - same dead-constant situation as
# CALC_STYLE in gpc_page.py/gt_page.py. Left in place, not deleted.
SECTION_STYLE = "font-weight: bold; font-size: 11px;"


def get_toggle_button_style() -> str:
    """
    The IS/BS toggle buttons (self.btn_is/self.btn_bs) had NO styling
    at all before this - riding raw native OS button chrome, which is
    exactly the "sore thumb against a dark theme" problem the QTabBar
    fix and WACC's combo-box fix both addressed earlier. These are
    QPushButton(checkable=True) acting as a segmented control, so this
    needs explicit :checked/:!checked states, not a single flat style.
    """
    t = theme_manager.current
    return f"""
        QPushButton {{
            background-color: {t.window_bg};
            color: {t.default_text};
            border: 1px solid {t.border_color};
            padding: 4px 14px;
        }}
        QPushButton:checked {{
            background-color: {t.input_bg};
            color: {t.input_text};
            font-weight: bold;
        }}
        QPushButton:!checked:hover {{
            background-color: {t.grey_disabled_bg};
        }}
    """


def _fmt(value) -> str:
    if value is None or str(value).lower() in ("nan", "none", "-"):
        return "-"
    try:
        f = float(str(value).replace(",", ""))
        return f"{f:,.0f}"
    except Exception:
        return "-"


def _make_hrule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _parse_val(value) -> Optional[float]:
    if value is None or str(value).strip().lower() in ("", "-", "nan", "none"):
        return None
    try:
        v = float(str(value).replace(",", ""))
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (ValueError, TypeError):
        return None


class SubjectFinancialsPage(QWidget):
    """
    Read-only display of subject company IS and BS.
    - If Publicly Traded: shows StockAnalysis data pulled for subject ticker
    - If Private: shows data entered in PrivateFinancialsInputPage
    Always reflects current state — no editing here.

    Calculated rows (is_calc=True in IS_LINES/BS_LINES) are computed
    locally via compute_is_calculated/compute_bs_calculated from raw
    component values — never read pre-computed from either source.
    Exception: total_current_liab, total_liabilities, total_equity,
    total_liab_equity are is_calc=True for bolding purposes only —
    their raw components don't scrape reliably from StockAnalysis, so
    those four are pulled directly (see BS_DIRECT_PULL_KEYS).
    """

    def __init__(self, get_project_inputs_callback,
                 get_stockanalysis_results_callback,
                 get_private_financials_callback,
                 get_projection_data_callback, 
                 get_debt_interest_callback=None,
                ):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self.get_stockanalysis_results = get_stockanalysis_results_callback
        self.get_private_financials = get_private_financials_callback
        self.get_projection_data = get_projection_data_callback or (lambda: ProjectionData())
        self.get_debt_interest = get_debt_interest_callback 

        self._current_statement = "IS"
        self._build_ui()

        theme_manager.theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme=None):
        self.btn_is.setStyleSheet(get_toggle_button_style())
        self.btn_bs.setStyleSheet(get_toggle_button_style())
        # No metadata-tracking needed for the row/header labels below
        # the toggle - refresh() fully discards and rebuilds the
        # entire display widget from scratch every call (this is a
        # read-only display page, no typed input values at risk),
        # so a plain refresh() picks up every get_bold_style() call
        # with the current theme automatically.
        self.refresh()

    def _build_ui(self):
        outer = QVBoxLayout()

        top_bar = QHBoxLayout()

        self.stmt_group = QButtonGroup(self)
        self.stmt_group.setExclusive(True)

        self.btn_is = QPushButton("IS")
        self.btn_bs = QPushButton("BS")
        self.btn_is.setStyleSheet(get_toggle_button_style())
        self.btn_bs.setStyleSheet(get_toggle_button_style())

        for btn, stmt in [(self.btn_is, "IS"), (self.btn_bs, "BS")]:
            btn.setCheckable(True)
            btn.clicked.connect(
                lambda checked, s=stmt: self._switch_statement(s)
            )
            self.stmt_group.addButton(btn)
            top_bar.addWidget(btn)

        self.btn_is.setChecked(True)
        top_bar.addStretch()

        self.status_label = QLabel("")
        top_bar.addWidget(self.status_label)
        outer.addLayout(top_bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        outer.addWidget(self._scroll)

        self.setLayout(outer)
        self.refresh()

    def _switch_statement(self, stmt: str):
        self._current_statement = stmt
        self.refresh()

    def refresh(self):
        """Rebuild display from current data."""
        inputs = self.get_project_inputs()

        if inputs.is_publicly_traded:
            self.status_label.setText(
                f"Source: StockAnalysis ({inputs.subject_ticker})"
            )
            widget = self._build_public_view(inputs)
        else:
            self.status_label.setText(
                "Source: Private Company Input Form"
            )
            widget = self._build_private_view(inputs)

        self._scroll.setWidget(widget)

    def _get_periods(self, inputs: ProjectInputs) -> List[str]:
        return inputs.historical_period_columns + ["TTM"] + inputs.projection_period_columns

    def _get_periods_historical_only(self, inputs: ProjectInputs) -> List[str]:
        return inputs.historical_period_columns + ["TTM"]

        # ------------------------------------------------------------------
    # Shared row-building helpers
    # ------------------------------------------------------------------

    def _build_cfs_lookup(self, ticker: str) -> Dict[str, Dict[str, str]]:
        """CFS-statement rows for the subject ticker, keyed by lowercased
        Line Item — same shape as the IS/BS lookups built in
        _build_public_view, but pulled from results['CFS'] specifically.
        Used for IS_LINES keys in CFS_SOURCED_KEYS (capex, acquisitions),
        which don't live in the IS statement StockAnalysis returns."""
        results = self.get_stockanalysis_results()
        cfs_rows = results.get("CFS", []) if results else []
        lookup: Dict[str, Dict[str, str]] = {}
        for row in cfs_rows:
            if str(row.get("Ticker", "")).lower() != ticker:
                continue
            key = str(row.get("Line Item", "")).strip().lower()
            lookup[key] = {
                k: v for k, v in row.items()
                if k not in ("Ticker", "Key", "Line Item")
            }
        return lookup

    def _gather_raw_public(self, lines, periods, lookup, ticker: str = ""):
        raw_by_period = {p: {} for p in periods}
        cfs_lookup = (
            self._build_cfs_lookup(ticker)
            if ticker and self._current_statement == "IS"
            else {}
        )

        for key, label, is_calc, bold in lines:
            if is_calc and not (self._current_statement == "BS" and key in BS_DIRECT_PULL_KEYS):
                continue
            sa_source = get_sa_source(key)
            sa_labels = get_sa_labels(key)
            sign_flip = get_sign_flip(key)
            source_lookup = cfs_lookup if sa_source == "CFS" else lookup
            row_data = {}
            for sa_label in sa_labels:
                candidate = source_lookup.get(sa_label, {})
                if candidate:
                    row_data = candidate
                    break
            for period in periods:
                v = _parse_val(row_data.get(period, ""))
                if v is not None and sign_flip:
                    v = -v
                raw_by_period[period][key] = v

        # These are CFS-sourced inputs used by calculated IS rows but are
        # intentionally not standalone rows in IS_LINES.
        if self._current_statement == "IS":
            for extra_key in ("stock_based_compensation", "other_amortization"):
                row_data = {}
                for sa_label in get_sa_labels(extra_key):
                    candidate = cfs_lookup.get(sa_label, {})
                    if candidate:
                        row_data = candidate
                        break

                for period in periods:
                    raw_by_period[period][extra_key] = _parse_val(
                        row_data.get(period, "")
                    )

        return raw_by_period

    def _gather_raw_private(self, lines, periods, pf) -> Dict[str, Dict[str, Optional[float]]]:
        raw_by_period: Dict[str, Dict[str, Optional[float]]] = {p: {} for p in periods}
        for key, label, is_calc, bold in lines:
            if is_calc and not (self._current_statement == "BS" and key in BS_DIRECT_PULL_KEYS):
                continue
            for period in periods:
                if self._current_statement == "IS":
                    raw_by_period[period][key] = pf.get_is(key, period)
                else:
                    raw_by_period[period][key] = pf.get_bs(key, period)

        if self._current_statement == "IS":
            for extra_key in ("stock_based_compensation", "other_amortization"):
                for period in periods:
                    raw_by_period[period][extra_key] = pf.get_is(
                        extra_key, period
                    )

        return raw_by_period

    def _resolve_value(self, key, is_calc, period, raw_by_period, calc_by_period):
        if is_calc and self._current_statement == "BS" and key in BS_DIRECT_PULL_KEYS:
            return raw_by_period[period].get(key)
        elif is_calc:
            return calc_by_period[period].get(key)
        else:
            return raw_by_period[period].get(key)

    def _build_header(self, grid, periods):
        grid.addWidget(QLabel("Line Item"), 0, 0)
        for col_idx, period in enumerate(periods):
            lbl = QLabel(period)
            lbl.setStyleSheet(get_bold_style())
            lbl.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(lbl, 0, col_idx + 1)
        grid.setColumnStretch(0, 2)
        for i in range(len(periods)):
            grid.setColumnMinimumWidth(i + 1, 90)

    def _build_rows(self, grid, lines, periods, raw_by_period, calc_by_period):
        # Periods that decide "empty": historical + TTM, not projections
        # (the BS is never projected, so NFY/NFY+1 are always blank and
        # must not force every component row to hide).
        inputs = self.get_project_inputs()
        check_periods = [
            p for p in periods
            if p in inputs.historical_period_columns or p == "TTM"
        ] or list(periods)

        display_row = 1
        for key, label, is_calc, bold in lines:
            # Spacers are display-only (not IS_LINES keys).
            if key == "capex":
                for _ in range(2):
                    grid.addWidget(QLabel(""), display_row, 0)
                    display_row += 1
            if key == "stock_based_compensation":
                grid.addWidget(QLabel(""), display_row, 0)
                display_row += 1

            # Auto-hide non-bold component rows that are empty across all
            # historical/TTM periods. Bold rows (subtotals/totals) always show.
            if not bold:
                has_val = False

                # Most component rows are hidden if empty across historical/TTM.
                # But some projection-only rows, especially projected Other
                # Amortization, need to remain visible so EBITDA -> EBIT ties out.
                periods_to_check = list(check_periods)
                if self._current_statement == "IS" and key in (
                    "amortization",
                    "stock_based_compensation",
                ):
                    periods_to_check = list(periods)

                for period in periods_to_check:
                    if self._resolve_value(key, is_calc, period, raw_by_period, calc_by_period) is not None:
                        has_val = True
                        break
                if not has_val:
                    continue

            row = display_row
            display_row += 1

            name_lbl = QLabel(label)
            if bold:
                name_lbl.setStyleSheet(get_bold_style())
            grid.addWidget(name_lbl, row, 0)

            for col_idx, period in enumerate(periods):
                val = self._resolve_value(key, is_calc, period, raw_by_period, calc_by_period)
                val_lbl = QLabel(_fmt(val) if val is not None else "-")
                val_lbl.setAlignment(
                    Qt.AlignmentFlag.AlignRight |
                    Qt.AlignmentFlag.AlignVCenter
                )
                if bold:
                    val_lbl.setStyleSheet(get_bold_style())
                grid.addWidget(val_lbl, row, col_idx + 1)

    # ------------------------------------------------------------------
    # View builders
    # ------------------------------------------------------------------

    def _build_public_view(self, inputs: ProjectInputs) -> QWidget:
        """Build read-only grid from StockAnalysis results."""
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        results = self.get_stockanalysis_results()
        stmt_results = results.get(
            self._current_statement, []
        ) if results else []

        ticker = inputs.subject_ticker.lower()

        subject_rows = [
            r for r in stmt_results
            if str(r.get("Ticker", "")).lower() == ticker
        ]

        lines = IS_LINES if self._current_statement == "IS" else BS_LINES
        periods = self._get_periods(inputs)

        lookup: Dict[str, Dict[str, str]] = {}
        for row in subject_rows:
            key = str(row.get("Line Item", "")).strip().lower()
            lookup[key] = {
                k: v for k, v in row.items()
                if k not in ("Ticker", "Key", "Line Item")
            }

        self._build_header(grid, periods)

        raw_by_period = self._gather_raw_public(lines, periods, lookup, ticker=ticker)

        compute_fn = compute_is_calculated if self._current_statement == "IS" else compute_bs_calculated
        calc_by_period = {period: compute_fn(raw_by_period[period]) for period in periods}

        proj_periods = inputs.projection_period_columns
        if self._current_statement == "IS" and proj_periods:
            pd = self.get_projection_data()
            tax_rate = getattr(inputs, "subject_tax_rate", None)
            for period in proj_periods:
                raw_by_period.setdefault(period, {})
                calc_by_period.setdefault(period, {})

                # --- Raw / module-sourced inputs ---
                rev = pd.revenue.get(period)
                gp = pd.gross_profit.get(period)
                ebitda_mod = pd.ebitda.get(period)
                da = pd.da.get(period)

                raw_by_period[period]["revenue"] = rev
                raw_by_period[period]["d&a_for_ebitda"] = da
                raw_by_period[period]["depreciation"] = da
                raw_by_period[period]["amortization"] = pd.other_amort.get(period)
                raw_by_period[period]["stock_based_compensation"] = pd.sbc.get(period)
                raw_by_period[period]["capex"] = pd.capex.get(period)

                # Seed calc rows Projection Module already owns (keep as anchors)
                # Also invert into COGS / OpEx components so compute_is_calculated
                # can rebuild the same waterfall as historicals.
                if rev is not None and gp is not None:
                    raw_by_period[period]["cogs"] = rev - gp
                if gp is not None and ebitda_mod is not None:
                    # pd.ebitda is Adjusted EBITDA.
                    # Seed OpEx so GP - OpEx = EBIT, not Adjusted EBITDA.
                    ebit_seed = (
                        ebitda_mod
                        - (pd.da.get(period) or 0.0)
                        - (pd.other_amort.get(period) or 0.0)
                        - (pd.sbc.get(period) or 0.0)
                    )
                    raw_by_period[period]["other_operating"] = gp - ebit_seed

                if callable(self.get_debt_interest):
                    val = self.get_debt_interest(period)
                    raw_by_period[period]["interest_expense"] = (
                        -abs(val) if val is not None else None
                    )

                # Full IS waterfall (EBIT, Pretax, NI, DFNI, …)
                calc = compute_is_calculated(raw_by_period[period])

                # Prefer module GP/EBITDA when present (they are the planning drivers)
                if gp is not None:
                    calc["gross_profit"] = gp
                # pd.ebitda = Adjusted EBITDA. Do not write it onto "ebitda".
                if ebitda_mod is not None:
                    sbc_p = pd.sbc.get(period) or 0.0
                    da_p = pd.da.get(period) or 0.0
                    oa_p = pd.other_amort.get(period) or 0.0
                    calc["adj_ebitda"] = ebitda_mod
                    calc["ebitda"] = ebitda_mod - sbc_p
                    calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
                if pd.net_income.get(period) is not None:
                    calc["net_income"] = pd.net_income.get(period)
                calc["cost_of_goods_sold"] = _sub(rev, gp)
                calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

                # Projected tax: no separate forecast line — apply subject statutory rate
                pretax = calc.get("pretax_income")
                if pretax is not None and tax_rate is not None:
                    taxes = pretax * tax_rate
                    raw_by_period[period]["taxes"] = taxes
                    # Recompute NI stack with taxes in raw
                    calc = compute_is_calculated(raw_by_period[period])
                    if gp is not None:
                        calc["gross_profit"] = gp
                    if ebitda_mod is not None:
                        sbc_p = pd.sbc.get(period) or 0.0
                        da_p = pd.da.get(period) or 0.0
                        oa_p = pd.other_amort.get(period) or 0.0
                        calc["adj_ebitda"] = ebitda_mod
                        calc["ebitda"] = ebitda_mod - sbc_p
                        calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
                    if pd.net_income.get(period) is not None:
                        calc["net_income"] = pd.net_income.get(period)
                    calc["cost_of_goods_sold"] = _sub(rev, gp)
                    calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

                calc_by_period[period] = calc

        self._build_rows(grid, lines, periods, raw_by_period, calc_by_period)

        grid.setRowStretch(len(lines) + 2, 1)
        container.setLayout(grid)
        return container

    def _build_private_view(self, inputs: ProjectInputs) -> QWidget:
        """Build read-only grid from PrivateFinancials dataclass."""
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        pf = self.get_private_financials()
        lines = IS_LINES if self._current_statement == "IS" else BS_LINES
        periods = self._visible_private_periods(inputs)

        self._build_header(grid, periods)

        raw_by_period = self._gather_raw_private(lines, periods, pf)

        compute_fn = compute_is_calculated if self._current_statement == "IS" else compute_bs_calculated
        calc_by_period = {period: compute_fn(raw_by_period[period]) for period in periods}

        proj_periods = inputs.projection_period_columns
        if self._current_statement == "IS" and proj_periods:
            pd = self.get_projection_data()
            tax_rate = getattr(inputs, "subject_tax_rate", None)
            for period in proj_periods:
                raw_by_period.setdefault(period, {})
                calc_by_period.setdefault(period, {})

                # --- Raw / module-sourced inputs ---
                rev = pd.revenue.get(period)
                gp = pd.gross_profit.get(period)
                ebitda_mod = pd.ebitda.get(period)
                da = pd.da.get(period)

                raw_by_period[period]["revenue"] = rev
                raw_by_period[period]["d&a_for_ebitda"] = da
                raw_by_period[period]["depreciation"] = da
                raw_by_period[period]["amortization"] = pd.other_amort.get(period)
                raw_by_period[period]["stock_based_compensation"] = pd.sbc.get(period)
                raw_by_period[period]["capex"] = pd.capex.get(period)

                # Seed calc rows Projection Module already owns (keep as anchors)
                # Also invert into COGS / OpEx components so compute_is_calculated
                # can rebuild the same waterfall as historicals.
                if rev is not None and gp is not None:
                    raw_by_period[period]["cogs"] = rev - gp
                # pd.ebitda is Adjusted EBITDA. Seed OpEx so GP - OpEx = EBIT,
                # not so GP - OpEx = Adjusted EBITDA.
                if gp is not None and ebitda_mod is not None:
                    ebit_seed = (
                        ebitda_mod
                        - (pd.da.get(period) or 0.0)
                        - (pd.other_amort.get(period) or 0.0)
                        - (pd.sbc.get(period) or 0.0)
                    )
                    raw_by_period[period]["other_operating"] = gp - ebit_seed

                if callable(self.get_debt_interest):
                    val = self.get_debt_interest(period)
                    raw_by_period[period]["interest_expense"] = (
                        -abs(val) if val is not None else None
                    )

                # Full IS waterfall (EBIT, Pretax, NI, DFNI, …)
                calc = compute_is_calculated(raw_by_period[period])

                # Prefer module GP/EBITDA when present (they are the planning drivers)
                if gp is not None:
                    calc["gross_profit"] = gp
                if ebitda_mod is not None:
                    sbc_p = pd.sbc.get(period) or 0.0
                    da_p = pd.da.get(period) or 0.0
                    oa_p = pd.other_amort.get(period) or 0.0

                    # pd.ebitda = Adjusted EBITDA from the Projection Module.
                    calc["adj_ebitda"] = ebitda_mod
                    calc["ebitda"] = ebitda_mod - sbc_p
                    calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
                if pd.net_income.get(period) is not None:
                    calc["net_income"] = pd.net_income.get(period)
                calc["cost_of_goods_sold"] = _sub(rev, gp)
                calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

                # Projected tax: no separate forecast line — apply subject statutory rate
                pretax = calc.get("pretax_income")
                if pretax is not None and tax_rate is not None:
                    taxes = pretax * tax_rate
                    raw_by_period[period]["taxes"] = taxes
                    # Recompute NI stack with taxes in raw
                    calc = compute_is_calculated(raw_by_period[period])
                    if gp is not None:
                        calc["gross_profit"] = gp
                    if ebitda_mod is not None:
                        sbc_p = pd.sbc.get(period) or 0.0
                        da_p = pd.da.get(period) or 0.0
                        oa_p = pd.other_amort.get(period) or 0.0

                        # pd.ebitda = Adjusted EBITDA from the Projection Module.
                        calc["adj_ebitda"] = ebitda_mod
                        calc["ebitda"] = ebitda_mod - sbc_p
                        calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
                    if pd.net_income.get(period) is not None:
                        calc["net_income"] = pd.net_income.get(period)
                    calc["cost_of_goods_sold"] = _sub(rev, gp)
                    calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

                calc_by_period[period] = calc

        self._build_rows(grid, lines, periods, raw_by_period, calc_by_period)

        grid.setRowStretch(len(lines) + 2, 1)
        container.setLayout(grid)
        return container

    def _visible_private_periods(self, inputs: ProjectInputs) -> List[str]:
        from dateutil.relativedelta import relativedelta
        from datetime import datetime

        hist = inputs.historical_period_columns

        forward = ["TTM"] + inputs.projection_period_columns

        lfq_str = inputs.last_fiscal_quarter
        lfq = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m-%d-%Y"):
            try:
                lfq = datetime.strptime(lfq_str.strip(), fmt)
                break
            except ValueError:
                pass

        if lfq:
            prior = lfq - relativedelta(years=1)
            ytd = [
                f"YTD {prior.month}/{prior.day}/{prior.year}",
                f"YTD {lfq.month}/{lfq.day}/{lfq.year}",
            ]
        else:
            ytd = ["YTD Prior", "YTD Current"]

        return hist + forward

    def get_subject_debt(self) -> float:
        inputs = self.get_project_inputs()
        res = 0.0
        keys = ["st_debt", "current_ltd", "lt_debt"]
        if inputs.is_private:
            pf = self.get_private_financials()
            for k in keys:
                res += (pf.get_bs(k, "TTM") or 0.0)
        else:
            sa = self.get_stockanalysis_results().get("BS", [])
            tick = inputs.subject_ticker.lower()
            bs_lookup = build_lookup(sa, tick)
            for k in keys:
                for sa_label in get_sa_labels(k):
                    row_data = bs_lookup.get(sa_label, {})
                    if row_data:
                        v = to_float(row_data.get("TTM"))
                        if v is not None:
                            res += v
                        break
        return res

    def get_historical_line_values(self, key: str, statement: str = "IS") -> Dict[str, Optional[float]]:
        """
        Returns {period_label: float_or_None} for the given line-item key,
        across historical periods + TTM (LFY-N ... LFY, TTM).

        Single source of truth for other pages (Projection Module, GT,
        GPC) needing subject company historicals as raw floats.
        """
        inputs = self.get_project_inputs()
        periods = inputs.historical_period_columns + ["TTM"]
        lines = IS_LINES if statement == "IS" else BS_LINES

        # Allow lookup of sa_key aliases that may not appear as their own IS_LINES row
        # (e.g. d&a_for_ebitda) by temporarily resolving via get_sa_labels in the gather loop.
        is_calc = next((c for k, l, c, b in lines if k == key), False)

        raw_by_period: Dict[str, Dict[str, Optional[float]]] = {p: {} for p in periods}

        if inputs.is_publicly_traded:
            results = self.get_stockanalysis_results()
            stmt_results = results.get(statement, []) if results else []
            ticker = inputs.subject_ticker.lower()
            subject_rows = [r for r in stmt_results if str(r.get("Ticker", "")).lower() == ticker]
            lookup = {}
            for row in subject_rows:
                lk = str(row.get("Line Item", "")).strip().lower()
                lookup[lk] = {k: v for k, v in row.items() if k not in ("Ticker", "Key", "Line Item")}
            cfs_lookup = self._build_cfs_lookup(ticker) if statement == "IS" else {}
            for k2, l2, c2, b2 in lines:
                if c2 and not (statement == "BS" and k2 in BS_DIRECT_PULL_KEYS):
                    continue
                sa_source = get_sa_source(k2)
                sa_labels = get_sa_labels(k2)
                sign_flip = get_sign_flip(k2)
                source_lookup = cfs_lookup if sa_source == "CFS" else lookup
                row_data = {}
                for sa_label in sa_labels:
                    candidate = source_lookup.get(sa_label, {})
                    if candidate:
                        row_data = candidate
                        break
                for period in periods:
                    v = _parse_val(row_data.get(period, ""))
                    if v is not None and sign_flip:
                        v = -v
                    raw_by_period[period][k2] = v

            # CFS-sourced historical add-backs are not standalone IS_LINES,
            # but Projection Module and Adjusted EBITDA require them.
            if statement == "IS":
                for extra_key in ("stock_based_compensation", "other_amortization"):
                    row_data = {}
                    for sa_label in get_sa_labels(extra_key):
                        candidate = cfs_lookup.get(sa_label, {})
                        if candidate:
                            row_data = candidate
                            break

                    for period in periods:
                        raw_by_period[period][extra_key] = _parse_val(
                            row_data.get(period, "")
                        )

        else:
            pf = self.get_private_financials()
            for k2, l2, c2, b2 in lines:
                if c2 and not (statement == "BS" and k2 in BS_DIRECT_PULL_KEYS):
                    continue
                for period in periods:
                    raw_by_period[period][k2] = (
                        pf.get_is(k2, period)
                        if statement == "IS"
                        else pf.get_bs(k2, period)
                    )

            if statement == "IS":
                for extra_key in ("stock_based_compensation", "other_amortization"):
                    for period in periods:
                        raw_by_period[period][extra_key] = pf.get_is(
                            extra_key, period
                        )

        compute_fn = compute_is_calculated if statement == "IS" else compute_bs_calculated
        result: Dict[str, Optional[float]] = {}
        for period in periods:
            if is_calc and statement == "BS" and key in BS_DIRECT_PULL_KEYS:
                result[period] = raw_by_period[period].get(key)
            elif is_calc:
                result[period] = compute_fn(raw_by_period[period]).get(key)
            else:
                result[period] = raw_by_period[period].get(key)

        # If key was missing from IS_LINES gather (alias-only sa_key), pull via sa_key directly
        if statement == "IS" and not any(v is not None for v in result.values()):
            results = self.get_stockanalysis_results() if inputs.is_publicly_traded else None
            if results and inputs.is_publicly_traded:
                ticker = inputs.subject_ticker.lower()
                sa_source = get_sa_source(key)
                sa_labels = get_sa_labels(key)
                sign_flip = get_sign_flip(key)
                if sa_source == "CFS":
                    source_lookup = self._build_cfs_lookup(ticker)
                else:
                    stmt_results = results.get("IS", []) or []
                    subject_rows = [
                        r for r in stmt_results
                        if str(r.get("Ticker", "")).lower() == ticker
                    ]
                    source_lookup = {}
                    for row in subject_rows:
                        lk = str(row.get("Line Item", "")).strip().lower()
                        source_lookup[lk] = {
                            k: v for k, v in row.items()
                            if k not in ("Ticker", "Key", "Line Item")
                        }
                row_data = {}
                for sa_label in sa_labels:
                    candidate = source_lookup.get(sa_label, {})
                    if candidate:
                        row_data = candidate
                        break
                for period in periods:
                    v = _parse_val(row_data.get(period, ""))
                    if v is not None and sign_flip:
                        v = -v
                    result[period] = v

        return result

    def get_metric_value(self, key: str, period: str) -> Optional[float]:
        """
        Single entry point for any other page (GPC, DCF) needing one
        subject-company metric at one specific period — historical,
        TTM, or a projection period (NFY, NFY+1, ...).

        Historical/TTM: delegates to get_historical_line_values, which
        already handles public/private branching and calc-row resolution.

        Projection periods: mirrors exactly what _build_public_view /
        _build_private_view already resolve and display for that column
        — revenue and depreciation come straight from ProjectionData;
        gross_profit/ebitda/capex are ProjectionData's own resolved
        fields; cost_of_goods_sold and operating_expenses are derived
        the same way the page derives them for display
        (Revenue-GrossProfit, GrossProfit-EBITDA). "amortization" and
        "ebit" have no projected source anywhere and correctly return
        None rather than guessing at one.

        NOTE: this method was previously reverted to an older
        revenue/ebitda-only version between sessions, which silently
        broke DCF's projected COGS/Gross Profit/Operating Expenses
        (they all read through this method). Restored here — if this
        regresses again, check whether something is overwriting this
        file from an older branch/commit.

        NOTE 2: historical lookups used to hardcode statement="IS",
        which silently broke for every Balance Sheet key (cash,
        accounts_receivable, accounts_payable, etc. — anything NWC
        needs). Now auto-detects IS vs BS from the key itself against
        IS_LINES/BS_LINES, same schema already defined in app_state.py.
        """
        inputs = self.get_project_inputs()

        if period in inputs.historical_period_columns + ["TTM"]:
            statement = "BS" if any(k == key for k, *_r in BS_LINES) else "IS"

            # D&A schema drift: SA/IS uses "d&a for ebitda" (internal d&a_for_ebitda).
            # Callers still request "depreciation" — try modern key first, then legacy.
            if key == "depreciation" and statement == "IS":
                for try_key in (
                    "d&a_for_ebitda",
                    "depreciation_amortization",
                    "depreciation",
                ):
                    val = self.get_historical_line_values(try_key, "IS").get(period)
                    if val is not None:
                        return val
                return None

            # Interest income alias drift: RKLB and similar list this as
            # "Interest & Investment Income" on the IS. sa_key already lists
            # every alias; this just ensures the alias-fallback branch in
            # get_historical_line_values runs when the primary label misses.
            if key == "interest_income" and statement == "IS":
                val = self.get_historical_line_values("interest_income", "IS").get(period)
                return val

            return self.get_historical_line_values(key, statement).get(period)

        if period in inputs.projection_period_columns:
            pd = self.get_projection_data()
            # Build the same raw + calc stack the IS grid uses for projections
            raw: Dict[str, Optional[float]] = {
                "revenue": pd.revenue.get(period),
                "d&a_for_ebitda": pd.da.get(period),
                "depreciation": pd.da.get(period),
                "amortization": pd.other_amort.get(period),
                "stock_based_compensation": pd.sbc.get(period),
                "capex": pd.capex.get(period),
            }
            rev = pd.revenue.get(period)
            gp = pd.gross_profit.get(period)
            ebitda_mod = pd.ebitda.get(period)
            if rev is not None and gp is not None:
                raw["cogs"] = rev - gp
            if gp is not None and ebitda_mod is not None:
                # pd.ebitda is Adjusted EBITDA.
                ebit_seed = (
                    ebitda_mod
                    - (pd.da.get(period) or 0.0)
                    - (pd.other_amort.get(period) or 0.0)
                    - (pd.sbc.get(period) or 0.0)
                )
                raw["other_operating"] = gp - ebit_seed
            if callable(self.get_debt_interest):
                val = self.get_debt_interest(period)
                raw["interest_expense"] = -abs(val) if val is not None else None

            tax_rate = getattr(inputs, "subject_tax_rate", None)
            calc = compute_is_calculated(raw)
            if gp is not None:
                calc["gross_profit"] = gp
            if ebitda_mod is not None:
                sbc_p = pd.sbc.get(period) or 0.0
                da_p = pd.da.get(period) or 0.0
                oa_p = pd.other_amort.get(period) or 0.0

                # pd.ebitda = Adjusted EBITDA from the Projection Module.
                calc["adj_ebitda"] = ebitda_mod
                calc["ebitda"] = ebitda_mod - sbc_p
                calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
            if pd.net_income.get(period) is not None:
                calc["net_income"] = pd.net_income.get(period)
            calc["cost_of_goods_sold"] = _sub(rev, gp)
            calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

            pretax = calc.get("pretax_income")
            if pretax is not None and tax_rate is not None:
                raw["taxes"] = pretax * tax_rate
                calc = compute_is_calculated(raw)
                if gp is not None:
                    calc["gross_profit"] = gp
                if ebitda_mod is not None:
                    sbc_p = pd.sbc.get(period) or 0.0
                    da_p = pd.da.get(period) or 0.0
                    oa_p = pd.other_amort.get(period) or 0.0

                    # pd.ebitda = Adjusted EBITDA from the Projection Module.
                    calc["adj_ebitda"] = ebitda_mod
                    calc["ebitda"] = ebitda_mod - sbc_p
                    calc["ebit"] = ebitda_mod - da_p - oa_p - sbc_p
                if pd.net_income.get(period) is not None:
                    calc["net_income"] = pd.net_income.get(period)
                calc["cost_of_goods_sold"] = _sub(rev, gp)
                calc["operating_expenses"] = _sub(gp, calc.get("ebit"))

            if key in raw and raw.get(key) is not None:
                return raw.get(key)
            if key in calc:
                return calc.get(key)
            return None

        return None

    def _append_additional_metrics(self, container, grid, raw_by_period, calc_by_period, periods):
        metric_keys = [
            "land", "buildings", "machinery",
            "construction_in_progress", "leasehold_improvements",
            "total_debt", "net_cash_debt", "net_cash_growth",
            "net_cash_debt_growth", "net_cash_per_share",
            "filing_date_shares_outstanding",
            "total_common_shares_outstanding",
            "working_capital", "book_value_per_share",
            "tangible_book_value", "tangible_book_value_per_share",
            "order_backlog", "cash_growth",
        ]
        # Only render if at least one metric has a value in at least one period
        has_any = False
        for key in metric_keys:
            for p in periods:
                val = self._resolve_value(
                    key, False, p, raw_by_period, calc_by_period
                )
                if val is not None:
                    has_any = True
                    break
            if has_any:
                break

        if not has_any:
            return

        # Insert after existing grid by rebuilding container layout
        # Since container is already set with grid, easiest is to add
        # a separator + new subsection grid below the existing one.
        # But container uses single grid layout already.
        # Instead, add rows directly to existing grid at bottom.
        # Find next available row.
        start_row = len(lines) + 2  # after header + rows + spacer

        # Section header
        hdr = QLabel("Additional Metrics", styleSheet=get_header_style())
        hdr.setAlignment(Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(hdr, start_row, 0, 1, len(periods) + 1)

        r = start_row + 1
        for key in metric_keys:
            label = next((l for k, l, *_ in BS_LINES if k == key), key.replace("_", " ").title())
            # Build row only if at least one period has data (respects hide-empty)
            row_has = False
            for p in periods:
                val = self._resolve_value(key, False, p, raw_by_period, calc_by_period)
                if val is not None:
                    row_has = True
                    break
            if not row_has:
                continue

            lbl_row = QLabel(label)
            lbl_row.setStyleSheet(get_bold_style() if key in ("land","buildings","machine","ppe") else "")
            # For simplicity, show all as regular weight
            grid.addWidget(lbl_row, r, 0)

            for idx, p in enumerate(periods):
                val = self._resolve_value(key, False, p, raw_by_period, calc_by_period)
                val_lbl = QLabel(_fmt(val) if val is not None else "-")
                val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(val_lbl, r, idx + 1)
            r += 1