"""
projection_module_page.py
Canneberge — Projection Module popup dialog.

Shows historical periods (LFY-N ... LFY, TTM) as read-only reference
columns, pulled from Subject Financials via get_subject_historical_line,
followed by editable projection periods (NFY ... NFY+N).

Line items (IS only):
    Revenue          ($ + Growth %)
    Gross Profit     ($ computed, Margin % computed, Improvement % input)
    EBITDA           ($ computed, Margin % computed, Improvement % input)
    D&A              ($ computed, as % of Revenue input)
    CapEx            ($ computed, as % of Revenue input)

Two-way binding rules per projection column:
  NFY / NFY+1 / NFY+2  (MarketScreener covers these for public companies):
    - Public:  Revenue $ sourced from MarketScreener -> read-only label,
               Growth % computed from it -> read-only label.
               EBITDA $ sourced from MarketScreener -> read-only label,
               EBITDA Margin % computed from it -> read-only label.
    - Private: Revenue $ is user input; Growth % computed from it.
               If user edits Growth % instead, Revenue $ back-computes.
               EBITDA Improvement % is a user input.

  NFY+3 and beyond (no external source for any company status):
    - Always editable two-way: Revenue $ <-> Growth %.
    - EBITDA Improvement % always a user input.

  GP Improvement %, D&A %, CapEx %:
    - Always user inputs (lavender), for every projection period,
      regardless of company status.

  All historical periods (LFY-N ... LFY, TTM):
    - Always read-only, computed from actual historical data.
    - Serve as the seed anchor for NFY's calculation chain.
"""

import math
from typing import Optional, Dict, List

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QWidget,
)
from PyQt6.QtCore import Qt

from Canneberge.app_state import ProjectInputs, ProjectionData
from Canneberge.Ui.theme import theme_manager


def get_input_style() -> str:
    return theme_manager.current.input_style()


def get_pct_input_style() -> str:
    return theme_manager.current.pct_input_style()


def get_bold_style() -> str:
    return theme_manager.current.bold_style()


def get_source_style() -> str:
    # Greyed read-only historical/sourced values - locked_text is
    # deliberately neutral-grey on every theme (not note_text, which
    # is green on One Dark Pro and reads as "fine" rather than
    # "locked, can't type here" - this was the actual root cause of
    # historical/MS-estimate cells rendering green on the dark theme).
    return f"color: {theme_manager.current.locked_text};"

COL_WIDTH     = 100
LABEL_STRETCH = 2

# MarketScreener covers exactly these three projection periods for public cos.
MS_COVERED_PERIODS = {"NFY", "NFY+1", "NFY+2"}


# ---------------------------------------------------------------------------
# Parsing / formatting helpers
# ---------------------------------------------------------------------------

def _parse_float(text: str) -> Optional[float]:
    text = str(text).strip().replace(",", "").replace("%", "")
    if not text:
        return None
    try:
        v = float(text)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except ValueError:
        return None


def _fmt_dollars(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}"


def _fmt_pct(value: Optional[float]) -> str:
    """Format decimal 0.09 -> '9.0%'"""
    if value is None:
        return ""
    return f"{value * 100:.1f}%"


def _parse_pct_input(text: str) -> Optional[float]:
    """Parse user-typed percent string -> decimal. '9' or '9.0' or '9.0%' -> 0.09"""
    text = str(text).strip().replace("%", "").replace(",", "")
    if not text:
        return None
    try:
        v = float(text)
        if math.isnan(v) or math.isinf(v):
            return None
        if -1.0 < v < 1.0 and v != 0.0:
            return v
        return v / 100.0
    except ValueError:
        return None


def _mul(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    return a * b


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


# ---------------------------------------------------------------------------
# Main dialog
# ---------------------------------------------------------------------------

class ProjectionModulePage(QDialog):
    """
    Modal popup for projection period inputs, with historical reference
    columns pulled from Subject Financials.

    Constructor args:
        projection_data            — ProjectionData instance to read/write
        get_project_inputs         — callback -> ProjectInputs
        get_marketscreener_results — callback -> list of MarketScreener rows
        get_subject_historical_line — callback(key: str) -> {period: float|None}
                                       pulls resolved historical values from
                                       SubjectFinancialsPage (public or private,
                                       already resolved there)
        parent                     — Qt parent widget
    """

    def __init__(
        self,
        projection_data: ProjectionData,
        get_project_inputs,
        get_marketscreener_results,
        get_subject_historical_line,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Projection Module")
        self.setMinimumSize(1700, 600)

        self._projection_data = projection_data
        self._get_project_inputs = get_project_inputs
        self._get_ms_results = get_marketscreener_results
        self._get_hist_line = get_subject_historical_line

        inputs = self._get_project_inputs()
        self._historical_periods: List[str] = inputs.historical_period_columns + ["TTM"]
        self._projection_periods: List[str] = inputs.projection_period_columns
        self._all_periods: List[str] = self._historical_periods + self._projection_periods
        self._is_public: bool = inputs.is_publicly_traded

        # MarketScreener data for projection periods
        self._ms_revenue: Dict[str, Optional[float]] = {}
        self._ms_ebitda:  Dict[str, Optional[float]] = {}
        self._ms_net_income: Dict[str, Optional[float]] = {}
        self._load_ms_data(inputs)

        # Historical raw line values, pulled from Subject Financials
        self._hist_revenue      = self._get_hist_line("revenue")
        self._hist_gross_profit = self._get_hist_line("gross_profit")
        self._hist_ebitda       = self._get_hist_line("ebitda")
        self._hist_net_income   = self._get_hist_line("net_income")

        # D&A Resolution: Fallback chain matching updated sa_key blueprint
        hist_da = self._get_hist_line("d&a_for_ebitda")
        if not any(v is not None for v in hist_da.values()):
            hist_da = self._get_hist_line("depreciation")
        if not any(v is not None for v in hist_da.values()):
            hist_da = self._get_hist_line("depreciation_amortization")

        self._hist_depreciation = hist_da
        self._hist_amortization = self._get_hist_line("amortization")
        self._hist_sbc          = self._get_hist_line("stock_based_compensation")
        self._hist_other_amort  = self._get_hist_line("other_amortization")
        self._hist_capex        = self._get_hist_line("capex")

        # Historical derived metrics (margins, growth, improvement) — computed once
        self._hist_gp_margin: Dict[str, Optional[float]] = {}
        self._hist_ebitda_margin: Dict[str, Optional[float]] = {}
        self._hist_da: Dict[str, Optional[float]] = {}
        self._hist_da_pct: Dict[str, Optional[float]] = {}
        self._hist_sbc_pct: Dict[str, Optional[float]] = {}
        self._hist_other_amort_pct: Dict[str, Optional[float]] = {}
        self._hist_net_income_margin: Dict[str, Optional[float]] = {}
        self._hist_capex_pct: Dict[str, Optional[float]] = {}
        self._hist_growth: Dict[str, Optional[float]] = {}
        self._hist_gp_improvement: Dict[str, Optional[float]] = {}
        self._hist_ebitda_improvement: Dict[str, Optional[float]] = {}
        self._compute_historical_derived()

        # Tracks which driver was last edited per projection period: "revenue" | "growth"
        self._last_edited_revenue: Dict[str, str] = {}
        self._last_edited_ni: Dict[str, str] = {}

        # Widget registries
        self._inputs: Dict[str, Dict[str, QLineEdit]] = {}
        self._labels: Dict[str, Dict[str, QLabel]]   = {}

        self._recalc_guard: bool = False

        # Resolved dollar values per projection period, populated during
        # _recalculate(). This is what actually gets persisted to
        # ProjectionData on Save — the single source of truth Subject
        # Financials reads from, so nothing downstream ever needs to
        # touch MarketScreener again.
        self._resolved: Dict[str, Dict[str, Optional[float]]] = {}

        self._build_ui()
        self._load_saved_data()
        self._recalculate()

        theme_manager.theme_changed.connect(self._apply_theme)
        self._apply_theme(theme_manager.current)

    def _apply_theme(self, theme=None):
        t = theme or theme_manager.current
        if hasattr(self, "save_btn"):
            self.save_btn.setStyleSheet(t.primary_button_style())
        if hasattr(self, "cancel_btn"):
            self.cancel_btn.setStyleSheet(t.button_style())

    # -----------------------------------------------------------------------
    # MarketScreener data loading
    # -----------------------------------------------------------------------

    def _load_ms_data(self, inputs: ProjectInputs):
        """
        Pull revenue and EBITDA estimates for the subject ticker from
        MarketScreener results, keyed by our projection period labels.

        MarketScreener row shape (confirmed from source_data_page):
            {"Ticker": "adbe", "Line Item": "Revenue", "Key": "adbe|revenue",
             "NFY": "26,523", "NFY+1": "28,919", "NFY+2": "31,484"}

        We only trust NFY / NFY+1 / NFY+2 from MarketScreener.
        """
        ticker = inputs.subject_ticker.strip().upper()
        rows = self._get_ms_results()
        if not rows:
            return

        for row in rows:
            if str(row.get("Ticker", "")).strip().upper() != ticker:
                continue
            metric = str(row.get("Line Item", "")).strip().lower()
            for period in MS_COVERED_PERIODS:
                raw = row.get(period)
                val = None
                if raw is not None:
                    try:
                        v = float(str(raw).replace(",", ""))
                        if not math.isnan(v) and not math.isinf(v):
                            val = v
                    except (ValueError, TypeError):
                        pass
                if metric == "revenue":
                    self._ms_revenue[period] = val
                elif metric == "ebitda":
                    self._ms_ebitda[period] = val
                elif metric == "net income":
                    self._ms_net_income[period] = val

    # -----------------------------------------------------------------------
    # Historical derived metrics — computed once at init, never recalculated
    # -----------------------------------------------------------------------

    def _compute_historical_derived(self):
        periods = self._historical_periods

        for idx, period in enumerate(periods):
            rev    = self._hist_revenue.get(period)
            gp     = self._hist_gross_profit.get(period)
            ebitda = self._hist_ebitda.get(period)
            dep    = self._hist_depreciation.get(period)
            amort  = self._hist_amortization.get(period)
            capex  = self._hist_capex.get(period)

            gp_margin     = _div(gp, rev)
            ebitda_margin = _div(ebitda, rev)

            da = None
            if dep is not None or amort is not None:
                da = (dep or 0.0) + (amort or 0.0)
            da_pct    = _div(da, rev)
            capex_pct = _div(capex, rev)
            sbc         = self._hist_sbc.get(period)
            sbc_pct     = _div(sbc, rev)
            other_am    = self._hist_other_amort.get(period)
            other_amort_pct = _div(other_am, rev)
            ni          = self._hist_net_income.get(period)
            ni_margin   = _div(ni, rev)

            self._hist_gp_margin[period]     = gp_margin
            self._hist_ebitda_margin[period] = ebitda_margin
            self._hist_net_income_margin[period] = ni_margin
            self._hist_da[period]            = da
            self._hist_da_pct[period]        = da_pct
            self._hist_capex_pct[period]     = capex_pct
            self._hist_sbc_pct[period]       = sbc_pct
            self._hist_other_amort_pct[period] = other_amort_pct

            # TTM never displays its own growth/improvement rates —
            # it only serves as the "prior" anchor for NFY's calculation.
            if idx > 0 and period != "TTM":
                prior_period = periods[idx - 1]
                prior_rev           = self._hist_revenue.get(prior_period)
                prior_gp_margin     = self._hist_gp_margin.get(prior_period)
                prior_ebitda_margin = self._hist_ebitda_margin.get(prior_period)

                self._hist_growth[period] = self._compute_growth(rev, prior_rev)
                self._hist_gp_improvement[period] = (
                    gp_margin - prior_gp_margin
                    if (gp_margin is not None and prior_gp_margin is not None)
                    else None
                )
                self._hist_ebitda_improvement[period] = (
                    ebitda_margin - prior_ebitda_margin
                    if (ebitda_margin is not None and prior_ebitda_margin is not None)
                    else None
                )
            else:
                self._hist_growth[period] = None
                self._hist_gp_improvement[period] = None
                self._hist_ebitda_improvement[period] = None

    # -----------------------------------------------------------------------
    # UI construction
    # -----------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout()

        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self.save_btn = QPushButton("Save")
        self.save_btn.setStyleSheet(theme_manager.current.primary_button_style())
        self.save_btn.clicked.connect(self._on_save)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(theme_manager.current.button_style())
        self.cancel_btn.clicked.connect(self.reject)

        top_bar.addWidget(self.save_btn)
        top_bar.addWidget(self.cancel_btn)
        outer.addLayout(top_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        content = self._build_grid()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self.setLayout(outer)

    def _build_grid(self) -> QWidget:
        container = QWidget()
        grid = QGridLayout()
        grid.setSpacing(2)
        grid.setContentsMargins(8, 8, 8, 8)

        # Header row
        grid.addWidget(QLabel("Line Item"), 0, 0)
        for col_idx, period in enumerate(self._all_periods):
            lbl = QLabel(period)
            lbl.setStyleSheet(get_bold_style())
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lbl, 0, col_idx + 1)

        grid.setColumnStretch(0, LABEL_STRETCH)
        for i in range(len(self._all_periods)):
            grid.setColumnMinimumWidth(i + 1, COL_WIDTH)

        gr = 1
        gr = self._build_revenue_section(grid, gr)
        gr = self._build_gross_profit_section(grid, gr)
        gr = self._build_ebitda_section(grid, gr)
        gr = self._build_da_section(grid, gr)
        gr = self._build_other_amort_section(grid, gr)
        gr = self._build_sbc_section(grid, gr)
        gr = self._build_other_adj_section(grid, gr)
        gr = self._build_taxes_section(grid, gr)
        gr = self._build_net_income_section(grid, gr)
        gr = self._build_capex_section(grid, gr)

        grid.setRowStretch(gr, 1)
        container.setLayout(grid)
        return container

    # -----------------------------------------------------------------------
    # Section builders — each iterates ALL periods, branching per-cell on
    # whether the period is historical (read-only) or projection (editable)
    # -----------------------------------------------------------------------

    def _build_revenue_section(self, grid: QGridLayout, gr: int) -> int:
        self._inputs.setdefault("revenue", {})
        self._inputs.setdefault("revenue_growth", {})
        self._labels.setdefault("revenue", {})
        self._labels.setdefault("revenue_growth", {})

        rev_lbl = QLabel("Revenue")
        rev_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(rev_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            cell = self._make_revenue_cell(period)
            grid.addWidget(cell, gr, col_idx + 1)
        gr += 1

        growth_lbl = QLabel("    Growth (%)")
        grid.addWidget(growth_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            cell = self._make_growth_cell(period)
            grid.addWidget(cell, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_gross_profit_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("gross_profit", {})
        self._labels.setdefault("gp_margin", {})
        self._inputs.setdefault("gp_improvement", {})
        self._labels.setdefault("gp_improvement_hist", {})

        gp_lbl = QLabel("Gross Profit")
        gp_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(gp_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_gross_profit.get(period)))
            self._labels["gross_profit"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        margin_lbl = QLabel("    Margin (%)")
        grid.addWidget(margin_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_pct(self._hist_gp_margin.get(period)))
            self._labels["gp_margin"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        imp_lbl = QLabel("    Improvement (%)")
        grid.addWidget(imp_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            if period in self._historical_periods:
                lbl = self._make_calc_label(sourced=True)
                lbl.setText(_fmt_pct(self._hist_gp_improvement.get(period)))
                self._labels["gp_improvement_hist"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_pct_input(period, "gp_improvement")
                self._inputs["gp_improvement"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_ebitda_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("ebitda", {})
        self._labels.setdefault("ebitda_margin", {})
        self._inputs.setdefault("ebitda_improvement", {})
        self._labels.setdefault("ebitda_improvement_sourced", {})

        ebitda_lbl = QLabel("EBITDA")
        ebitda_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(ebitda_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            is_ms_sourced = self._is_public and period in MS_COVERED_PERIODS
            lbl = self._make_calc_label(sourced=is_hist or is_ms_sourced)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_ebitda.get(period)))
            self._labels["ebitda"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        em_lbl = QLabel("    Margin (%)")
        grid.addWidget(em_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            is_ms_sourced = self._is_public and period in MS_COVERED_PERIODS
            lbl = self._make_calc_label(sourced=is_hist or is_ms_sourced)
            if is_hist:
                lbl.setText(_fmt_pct(self._hist_ebitda_margin.get(period)))
            self._labels["ebitda_margin"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        eim_lbl = QLabel("    Improvement (%)")
        grid.addWidget(eim_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            cell = self._make_ebitda_improvement_cell(period)
            grid.addWidget(cell, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_other_adj_section(self, grid: QGridLayout, gr: int) -> int:
        """
        +Other Adjustments — spill between (EBITDA − D&A − OA − SBC) and Taxes.
        MS-covered public periods: computed plug so waterfall foots to analyst NI.
        Later periods / private: user-editable $, default 0.
        Positive adds to pretax base (lifts NI); negative subtracts.
        """
        self._labels.setdefault("other_adj", {})
        self._inputs.setdefault("other_adj", {})

        oa_lbl = QLabel("+Other Adjustments")
        oa_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(oa_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            is_ms = self._is_public and period in MS_COVERED_PERIODS
            if is_hist or is_ms:
                lbl = self._make_calc_label(sourced=is_hist or is_ms)
                self._labels["other_adj"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_input(period, "other_adj")
                inp.setStyleSheet(get_pct_input_style())
                self._inputs["other_adj"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1
        return gr

    def _build_taxes_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("taxes", {})

        tax_lbl = QLabel("Taxes")
        tax_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(tax_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            self._labels["taxes"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1
        return gr

    def _build_net_income_section(self, grid: QGridLayout, gr: int) -> int:
        """
        Net Income is never a free type-in on projection years.
        MS-covered: analyst-wins locked label.
        Otherwise: computed from EBITDA − D&A − OA − SBC + OtherAdj − Taxes.
        """
        self._labels.setdefault("net_income", {})
        self._labels.setdefault("net_income_margin", {})

        ni_lbl = QLabel("Net Income")
        ni_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(ni_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            is_ms = self._is_public and period in MS_COVERED_PERIODS
            lbl = self._make_calc_label(sourced=is_hist or is_ms)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_net_income.get(period)))
            self._labels["net_income"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        nim_lbl = QLabel("    Margin (%)")
        grid.addWidget(nim_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            is_ms = self._is_public and period in MS_COVERED_PERIODS
            lbl = self._make_calc_label(sourced=is_hist or is_ms)
            if is_hist:
                lbl.setText(_fmt_pct(self._hist_net_income_margin.get(period)))
            self._labels["net_income_margin"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1
        return gr

    def _build_da_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("da", {})
        self._inputs.setdefault("da_pct", {})
        self._labels.setdefault("da_pct_hist", {})

        da_lbl = QLabel("D&A")
        da_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(da_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_da.get(period)))
            self._labels["da"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        da_pct_lbl = QLabel("    as % of Revenue")
        grid.addWidget(da_pct_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            if period in self._historical_periods:
                lbl = self._make_calc_label(sourced=True)
                lbl.setText(_fmt_pct(self._hist_da_pct.get(period)))
                self._labels["da_pct_hist"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_pct_input(period, "da_pct")
                self._inputs["da_pct"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_sbc_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("sbc", {})
        self._inputs.setdefault("sbc_pct", {})
        self._labels.setdefault("sbc_pct_hist", {})

        sbc_lbl = QLabel("Stock-Based Compensation")
        sbc_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(sbc_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_sbc.get(period)))
            self._labels["sbc"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        sbc_pct_lbl = QLabel("    as % of Revenue")
        grid.addWidget(sbc_pct_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            if period in self._historical_periods:
                lbl = self._make_calc_label(sourced=True)
                lbl.setText(_fmt_pct(self._hist_sbc_pct.get(period)))
                self._labels["sbc_pct_hist"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_pct_input(period, "sbc_pct")
                self._inputs["sbc_pct"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_other_amort_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("other_amort", {})
        self._inputs.setdefault("other_amort_pct", {})
        self._labels.setdefault("other_amort_pct_hist", {})

        oa_lbl = QLabel("Other Amortization")
        oa_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(oa_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_other_amort.get(period)))
            self._labels["other_amort"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        oa_pct_lbl = QLabel("    as % of Revenue")
        grid.addWidget(oa_pct_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            if period in self._historical_periods:
                lbl = self._make_calc_label(sourced=True)
                lbl.setText(_fmt_pct(self._hist_other_amort_pct.get(period)))
                self._labels["other_amort_pct_hist"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_pct_input(period, "other_amort_pct")
                self._inputs["other_amort_pct"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1

        return gr

    def _build_capex_section(self, grid: QGridLayout, gr: int) -> int:
        self._labels.setdefault("capex", {})
        self._inputs.setdefault("capex_pct", {})
        self._labels.setdefault("capex_pct_hist", {})

        capex_lbl = QLabel("CapEx")
        capex_lbl.setStyleSheet(get_bold_style())
        grid.addWidget(capex_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            is_hist = period in self._historical_periods
            lbl = self._make_calc_label(sourced=is_hist)
            if is_hist:
                lbl.setText(_fmt_dollars(self._hist_capex.get(period)))
            self._labels["capex"][period] = lbl
            grid.addWidget(lbl, gr, col_idx + 1)
        gr += 1

        capex_pct_lbl = QLabel("    as % of Revenue")
        grid.addWidget(capex_pct_lbl, gr, 0)
        for col_idx, period in enumerate(self._all_periods):
            if period in self._historical_periods:
                lbl = self._make_calc_label(sourced=True)
                lbl.setText(_fmt_pct(self._hist_capex_pct.get(period)))
                self._labels["capex_pct_hist"][period] = lbl
                grid.addWidget(lbl, gr, col_idx + 1)
            else:
                inp = self._make_pct_input(period, "capex_pct")
                self._inputs["capex_pct"][period] = inp
                grid.addWidget(inp, gr, col_idx + 1)
        gr += 1

        return gr

    # -----------------------------------------------------------------------
    # Cell factory helpers
    # -----------------------------------------------------------------------

    def _make_calc_label(self, sourced: bool = False) -> QLabel:
        lbl = QLabel("")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if sourced:
            lbl.setStyleSheet(get_source_style())
        return lbl

    def _make_input(self, period: str, field_key: str, pct: bool = False) -> QLineEdit:
        inp = QLineEdit()
        inp.setAlignment(Qt.AlignmentFlag.AlignRight)
        inp.setFixedWidth(COL_WIDTH - 4)
        inp.setStyleSheet(get_pct_input_style() if pct else get_input_style())
        inp.editingFinished.connect(
            lambda fk=field_key, p=period: self._on_input_edited(fk, p)
        )
        return inp

    def _make_pct_input(self, period: str, field_key: str) -> QLineEdit:
        return self._make_input(period, field_key, pct=True)

    def _make_revenue_cell(self, period: str) -> QWidget:
        if period in self._historical_periods:
            lbl = self._make_calc_label(sourced=True)
            lbl.setText(_fmt_dollars(self._hist_revenue.get(period)))
            self._labels["revenue"][period] = lbl
            return lbl
        if self._is_public and period in MS_COVERED_PERIODS:
            lbl = self._make_calc_label(sourced=True)
            self._labels["revenue"][period] = lbl
            return lbl
        inp = self._make_input(period, "revenue")
        # Deliberate override: Revenue is a dollar amount, so
        # _make_input() gives it the blue "dollar" style by default -
        # Ted asked for these specific boxes (user-typed revenue past
        # the MarketScreener-covered window) to use the purple combo
        # instead. Not touching _make_input()'s general convention,
        # every other dollar field in this file stays blue.
        inp.setStyleSheet(get_pct_input_style())
        self._inputs["revenue"][period] = inp
        return inp

    def _make_growth_cell(self, period: str) -> QWidget:
        if period in self._historical_periods:
            lbl = self._make_calc_label(sourced=True)
            lbl.setText(_fmt_pct(self._hist_growth.get(period)))
            self._labels["revenue_growth"][period] = lbl
            return lbl
        if self._is_public and period in MS_COVERED_PERIODS:
            lbl = self._make_calc_label(sourced=True)
            self._labels["revenue_growth"][period] = lbl
            return lbl
        inp = self._make_input(period, "revenue_growth", pct=True)
        self._inputs["revenue_growth"][period] = inp
        return inp

    def _make_ebitda_improvement_cell(self, period: str) -> QWidget:
        if period in self._historical_periods:
            lbl = self._make_calc_label(sourced=True)
            lbl.setText(_fmt_pct(self._hist_ebitda_improvement.get(period)))
            self._labels["ebitda_improvement_sourced"][period] = lbl
            return lbl
        if self._is_public and period in MS_COVERED_PERIODS:
            lbl = self._make_calc_label(sourced=True)
            self._labels["ebitda_improvement_sourced"][period] = lbl
            return lbl
        inp = self._make_input(period, "ebitda_improvement", pct=True)
        self._inputs["ebitda_improvement"][period] = inp
        return inp

    # -----------------------------------------------------------------------
    # Signal handler
    # -----------------------------------------------------------------------

    def _on_input_edited(self, field_key: str, period: str):
        if field_key == "revenue":
            self._last_edited_revenue[period] = "revenue"
        elif field_key == "revenue_growth":
            self._last_edited_revenue[period] = "growth"
        self._recalculate()

    # -----------------------------------------------------------------------
    # Core recalculation — only walks projection periods; historical values
    # are pre-computed once in _compute_historical_derived and never change.
    # -----------------------------------------------------------------------

    def _recalculate(self):
        if self._recalc_guard:
            return
        self._recalc_guard = True

        try:
            # Seed resolved dicts with historical values so the first
            # projection period (NFY) can look back to TTM as "prior".
            resolved_revenue: Dict[str, Optional[float]] = dict(self._hist_revenue)
            resolved_gp_margin: Dict[str, Optional[float]] = dict(self._hist_gp_margin)
            resolved_ebitda_margin: Dict[str, Optional[float]] = dict(self._hist_ebitda_margin)

            for col_idx, period in enumerate(self._projection_periods):
                if col_idx == 0:
                    prior_period = self._historical_periods[-1] if self._historical_periods else None
                else:
                    prior_period = self._projection_periods[col_idx - 1]

                # --- Revenue ---
                rev = self._resolve_revenue(period, prior_period, resolved_revenue)
                resolved_revenue[period] = rev

                prior_rev = resolved_revenue.get(prior_period) if prior_period else None
                growth = self._compute_growth(rev, prior_rev)
                self._display_growth(period, growth)

                # --- Gross Profit ---
                prior_gp_margin = resolved_gp_margin.get(prior_period) if prior_period else None
                gp_imp = self._get_pct_input("gp_improvement", period)
                gp_margin = self._resolve_gp_margin(prior_gp_margin, gp_imp)
                resolved_gp_margin[period] = gp_margin
                gp = _mul(rev, gp_margin)

                self._set_label("gross_profit", period, _fmt_dollars(gp))
                self._set_label("gp_margin", period, _fmt_pct(gp_margin))

                # --- EBITDA ---
                prior_ebitda_margin = (
                    resolved_ebitda_margin.get(prior_period) if prior_period else None
                )

                sbc_pct = self._get_pct_input("sbc_pct", period)
                sbc = _mul(rev, sbc_pct)

                if self._is_public and period in MS_COVERED_PERIODS:
                    # Sourced directly from MarketScreener analyst estimate (analyst-wins).
                    ebitda = self._ms_ebitda.get(period)
                    ebitda_margin = _div(ebitda, rev)
                    ebitda_imp_display = (
                        ebitda_margin - prior_ebitda_margin
                        if (ebitda_margin is not None and prior_ebitda_margin is not None)
                        else None
                    )
                    self._set_label(
                        "ebitda_improvement_sourced", period, _fmt_pct(ebitda_imp_display)
                    )
                else:
                    ebitda_imp = self._get_pct_input("ebitda_improvement", period)
                    ebitda_margin = self._resolve_ebitda_margin(prior_ebitda_margin, ebitda_imp)
                    ebitda = _mul(rev, ebitda_margin)

                resolved_ebitda_margin[period] = ebitda_margin
                self._set_label("ebitda", period, _fmt_dollars(ebitda))
                self._set_label("ebitda_margin", period, _fmt_pct(ebitda_margin))

                # --- D&A ---
                da_pct = self._get_pct_input("da_pct", period)
                da = _mul(rev, da_pct)
                self._set_label("da", period, _fmt_dollars(da))

                # --- CapEx ---
                capex_pct = self._get_pct_input("capex_pct", period)
                capex = _mul(rev, capex_pct)
                self._set_label("capex", period, _fmt_dollars(capex))

                other_amort_pct = self._get_pct_input("other_amort_pct", period)
                other_amort = _mul(rev, other_amort_pct)
                self._set_label("sbc", period, _fmt_dollars(sbc))
                self._set_label("other_amort", period, _fmt_dollars(other_amort))

                # --- Net Income ---
                # Analyst-wins for MS-covered periods; user $ or margin %
                # (two-way bound, same pattern as Revenue) beyond that.
                ni = self._resolve_net_income(period, resolved_revenue)
                ni_margin = _div(ni, rev)
                self._display_ni_margin(period, ni_margin)
                self._set_label("net_income", period, _fmt_dollars(ni))

                # --- +Other Adjustments (MS-covered periods: computed plug) ---
                other_adj = None
                if self._is_public and period in MS_COVERED_PERIODS:
                    other_adj = self._resolve_other_adjustment(
                        period, ebitda, da, other_amort, sbc, ni
                    )
                    self._set_label("other_adj", period, _fmt_dollars(other_adj))

                self._resolved[period] = {
                    "revenue": rev,
                    "gross_profit": gp,
                    "ebitda": ebitda,
                    "da": da,
                    "sbc": sbc,
                    "other_amort": other_amort,
                    "capex": capex,
                    "net_income": ni,
                    "other_adj": other_adj,
                }

        finally:
            self._recalc_guard = False

    # -----------------------------------------------------------------------
    # Resolution helpers
    # -----------------------------------------------------------------------

    def _resolve_other_adjustment(
        self,
        period: str,
        ebitda: Optional[float],
        da: Optional[float],
        other_amort: Optional[float],
        sbc: Optional[float],
        analyst_ni: Optional[float],
    ) -> Optional[float]:
        """
        MS-covered periods only: back-solve the plug that reconciles
        (EBITDA - D&A - OtherAmort - SBC) after tax to the analyst's
        own Net Income figure. This is the gap this whole feature exists
        to surface — it should never be user-typed for these periods.

        A blank D&A/Other Amort/SBC input is treated as zero for this
        calc (an empty override cell means "assume none," not "unknown"),
        matching how those drivers behave everywhere else in this grid.
        EBITDA and the analyst NI figure are NOT defaulted — those two
        genuinely cannot be assumed, so a missing value there still
        blocks the plug rather than silently computing against zero.
        """
        if ebitda is None or analyst_ni is None:
            return None

        da = da or 0.0
        other_amort = other_amort or 0.0
        sbc = sbc or 0.0

        inputs = self._get_project_inputs()
        tax_rate = getattr(inputs, "subject_tax_rate", None)
        if tax_rate is None:
            return None

        ebit = ebitda - da - other_amort - sbc
        implied_ni_before_adj = ebit * (1 - tax_rate)
        other_adj = analyst_ni - implied_ni_before_adj
        return other_adj

    def _resolve_net_income(
        self,
        period: str,
        resolved_revenue: Dict[str, Optional[float]],
    ) -> Optional[float]:
        if self._is_public and period in MS_COVERED_PERIODS:
            ni = self._ms_net_income.get(period)
            return ni

        rev = resolved_revenue.get(period)
        ni_text = self._get_input_text("net_income", period)
        nim_text = self._get_input_text("net_income_margin", period)
        last = self._last_edited_ni.get(period)

        ni_val = _parse_float(ni_text)
        nim_val = _parse_pct_input(nim_text)

        if last == "margin" and nim_val is not None and rev is not None:
            computed_ni = rev * nim_val
            inp = self._inputs.get("net_income", {}).get(period)
            if inp and not inp.hasFocus():
                inp.setText(_fmt_dollars(computed_ni))
            return computed_ni

        if ni_val is not None:
            return ni_val

        if nim_val is not None and rev is not None:
            computed_ni = rev * nim_val
            inp = self._inputs.get("net_income", {}).get(period)
            if inp and not inp.hasFocus():
                inp.setText(_fmt_dollars(computed_ni))
            return computed_ni

        return None

    def _display_ni_margin(self, period: str, ni_margin: Optional[float]):
        if self._is_public and period in MS_COVERED_PERIODS:
            self._set_label("net_income_margin", period, _fmt_pct(ni_margin))
            return

        inp = self._inputs.get("net_income_margin", {}).get(period)
        if inp is None:
            return
        last = self._last_edited_ni.get(period)
        if last != "margin" and not inp.hasFocus():
            inp.setText(_fmt_pct(ni_margin) if ni_margin is not None else "")

    def _resolve_revenue(
        self,
        period: str,
        prior_period: Optional[str],
        resolved: Dict[str, Optional[float]],
    ) -> Optional[float]:
        if self._is_public and period in MS_COVERED_PERIODS:
            rev = self._ms_revenue.get(period)
            self._set_label("revenue", period, _fmt_dollars(rev))
            return rev

        rev_text  = self._get_input_text("revenue", period)
        grow_text = self._get_input_text("revenue_growth", period)
        last      = self._last_edited_revenue.get(period)
        prior_rev = resolved.get(prior_period) if prior_period else None

        rev_val  = _parse_float(rev_text)
        grow_val = _parse_pct_input(grow_text)

        if last == "growth" and grow_val is not None and prior_rev is not None:
            computed_rev = prior_rev * (1.0 + grow_val)
            inp = self._inputs.get("revenue", {}).get(period)
            if inp and not inp.hasFocus():
                inp.setText(_fmt_dollars(computed_rev))
            return computed_rev

        if rev_val is not None:
            return rev_val

        if grow_val is not None and prior_rev is not None:
            computed_rev = prior_rev * (1.0 + grow_val)
            inp = self._inputs.get("revenue", {}).get(period)
            if inp and not inp.hasFocus():
                inp.setText(_fmt_dollars(computed_rev))
            return computed_rev

        return None

    def _compute_growth(
        self, revenue: Optional[float], prior_revenue: Optional[float]
    ) -> Optional[float]:
        return _div(revenue, prior_revenue) - 1.0 if _div(revenue, prior_revenue) is not None else None

    def _display_growth(self, period: str, growth: Optional[float]):
        if self._is_public and period in MS_COVERED_PERIODS:
            self._set_label("revenue_growth", period, _fmt_pct(growth))
            return

        inp = self._inputs.get("revenue_growth", {}).get(period)
        if inp is None:
            return
        last = self._last_edited_revenue.get(period)
        if last != "growth" and not inp.hasFocus():
            inp.setText(_fmt_pct(growth) if growth is not None else "")

    def _resolve_gp_margin(
        self, prior_gp_margin: Optional[float], gp_improvement: Optional[float]
    ) -> Optional[float]:
        if prior_gp_margin is None and gp_improvement is None:
            return None
        return (prior_gp_margin or 0.0) + (gp_improvement or 0.0)

    def _resolve_ebitda_margin(
        self, prior_ebitda_margin: Optional[float], ebitda_improvement: Optional[float]
    ) -> Optional[float]:
        if prior_ebitda_margin is None and ebitda_improvement is None:
            return None
        return (prior_ebitda_margin or 0.0) + (ebitda_improvement or 0.0)

    # -----------------------------------------------------------------------
    # Widget read helpers
    # -----------------------------------------------------------------------

    def _get_input_text(self, field_key: str, period: str) -> str:
        inp = self._inputs.get(field_key, {}).get(period)
        return inp.text().strip() if inp else ""

    def _get_pct_input(self, field_key: str, period: str) -> Optional[float]:
        return _parse_pct_input(self._get_input_text(field_key, period))

    def _set_label(self, field_key: str, period: str, text: str):
        lbl = self._labels.get(field_key, {}).get(period)
        if lbl:
            lbl.setText(text)

    # -----------------------------------------------------------------------
    # Load saved state into widgets — projection periods only
    # -----------------------------------------------------------------------

    def _load_saved_data(self):
        pd = self._projection_data

        for period in self._projection_periods:
            if not (self._is_public and period in MS_COVERED_PERIODS):
                inp = self._inputs.get("revenue", {}).get(period)
                if inp:
                    val = pd.revenue.get(period)
                    if val is not None:
                        inp.setText(_fmt_dollars(val))

                inp_g = self._inputs.get("revenue_growth", {}).get(period)
                if inp_g:
                    val_g = pd.revenue_growth.get(period)
                    if val_g is not None:
                        inp_g.setText(_fmt_pct(val_g))

                inp_ni = self._inputs.get("net_income", {}).get(period)
                if inp_ni:
                    val_ni = pd.net_income.get(period)
                    if val_ni is not None:
                        inp_ni.setText(_fmt_dollars(val_ni))

                inp_nim = self._inputs.get("net_income_margin", {}).get(period)
                if inp_nim:
                    val_nim = pd.net_income_margin.get(period)
                    if val_nim is not None:
                        inp_nim.setText(_fmt_pct(val_nim))

                inp_ei = self._inputs.get("ebitda_improvement", {}).get(period)
                if inp_ei:
                    val_ei = pd.ebitda_improvement.get(period)
                    if val_ei is not None:
                        inp_ei.setText(_fmt_pct(val_ei))

            inp_gp = self._inputs.get("gp_improvement", {}).get(period)
            if inp_gp:
                val_gp = pd.gp_improvement.get(period)
                if val_gp is not None:
                    inp_gp.setText(_fmt_pct(val_gp))

            inp_da = self._inputs.get("da_pct", {}).get(period)
            if inp_da:
                val_da = pd.da_pct.get(period)
                if val_da is not None:
                    inp_da.setText(_fmt_pct(val_da))

            inp_sbc = self._inputs.get("sbc_pct", {}).get(period)
            if inp_sbc:
                val_sbc = pd.sbc_pct.get(period)
                if val_sbc is not None:
                    inp_sbc.setText(_fmt_pct(val_sbc))

            inp_oa = self._inputs.get("other_amort_pct", {}).get(period)
            if inp_oa:
                val_oa = pd.other_amort_pct.get(period)
                if val_oa is not None:
                    inp_oa.setText(_fmt_pct(val_oa))

            inp_cx = self._inputs.get("capex_pct", {}).get(period)
            if inp_cx:
                val_cx = pd.capex_pct.get(period)
                if val_cx is not None:
                    inp_cx.setText(_fmt_pct(val_cx))

            last = pd.last_edited_revenue.get(period)
            if last:
                self._last_edited_revenue[period] = last

            last_ni = pd.last_edited_ni.get(period)
            if last_ni:
                self._last_edited_ni[period] = last_ni

    # -----------------------------------------------------------------------
    # Collect and save — projection periods only
    # -----------------------------------------------------------------------

    def _collect_data(self) -> ProjectionData:
        pd = ProjectionData()

        for period in self._projection_periods:
            if not (self._is_public and period in MS_COVERED_PERIODS):
                rev_text = self._get_input_text("revenue", period)
                pd.revenue[period] = _parse_float(rev_text)

                grow_text = self._get_input_text("revenue_growth", period)
                pd.revenue_growth[period] = _parse_pct_input(grow_text)

                ni_text = self._get_input_text("net_income", period)
                pd.net_income[period] = _parse_float(ni_text)

                nim_text = self._get_input_text("net_income_margin", period)
                pd.net_income_margin[period] = _parse_pct_input(nim_text)

                ei_text = self._get_input_text("ebitda_improvement", period)
                pd.ebitda_improvement[period] = _parse_pct_input(ei_text)
            else:
                pd.revenue[period] = self._ms_revenue.get(period)
                pd.net_income[period] = self._ms_net_income.get(period)
                pd.net_income_margin[period] = None
                pd.ebitda_improvement[period] = None  # computed, not stored

            gp_text = self._get_input_text("gp_improvement", period)
            pd.gp_improvement[period] = _parse_pct_input(gp_text)

            da_text = self._get_input_text("da_pct", period)
            pd.da_pct[period] = _parse_pct_input(da_text)

            sbc_text = self._get_input_text("sbc_pct", period)
            pd.sbc_pct[period] = _parse_pct_input(sbc_text)

            oa_text = self._get_input_text("other_amort_pct", period)
            pd.other_amort_pct[period] = _parse_pct_input(oa_text)

            cx_text = self._get_input_text("capex_pct", period)
            pd.capex_pct[period] = _parse_pct_input(cx_text)

            last = self._last_edited_revenue.get(period)
            if last:
                pd.last_edited_revenue[period] = last

            last_ni = self._last_edited_ni.get(period)
            if last_ni:
                pd.last_edited_ni[period] = last_ni

            # Resolved dollar values — the actual numbers Subject
            # Financials and every downstream page (GT, GPC, DCF, NWC)
            # should read. Sourced from self._resolved, populated by
            # _recalculate(), not recomputed here.
            resolved = self._resolved.get(period, {})
            pd.gross_profit[period] = resolved.get("gross_profit")
            pd.ebitda[period] = resolved.get("ebitda")
            pd.da[period] = resolved.get("da")
            pd.sbc[period] = resolved.get("sbc")
            pd.other_amort[period] = resolved.get("other_amort")
            pd.capex[period] = resolved.get("capex")

        return pd

    def _on_save(self):
        collected = self._collect_data()
        self._projection_data.revenue             = collected.revenue
        self._projection_data.revenue_growth      = collected.revenue_growth
        self._projection_data.gross_profit        = collected.gross_profit
        self._projection_data.gp_improvement       = collected.gp_improvement
        self._projection_data.ebitda               = collected.ebitda
        self._projection_data.ebitda_improvement  = collected.ebitda_improvement
        self._projection_data.da                   = collected.da
        self._projection_data.da_pct              = collected.da_pct
        self._projection_data.sbc                 = collected.sbc
        self._projection_data.sbc_pct             = collected.sbc_pct
        self._projection_data.other_amort         = collected.other_amort
        self._projection_data.other_amort_pct     = collected.other_amort_pct
        self._projection_data.capex                = collected.capex
        self._projection_data.capex_pct           = collected.capex_pct
        self._projection_data.net_income           = collected.net_income
        self._projection_data.net_income_margin    = collected.net_income_margin
        self._projection_data.last_edited_revenue = collected.last_edited_revenue
        self._projection_data.last_edited_ni      = collected.last_edited_ni
        self.accept()