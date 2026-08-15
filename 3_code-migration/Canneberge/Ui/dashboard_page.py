# Canneberge/Ui/dashboard_page.py

from typing import Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QSizePolicy,
    QDialog,
    QDialogButtonBox,
)
from PyQt6.QtCore import Qt

from Canneberge.Ui.wacc_page import (
    CORPORATE_RATE_SERIES,
    BETA_TYPE_OPTIONS,
    BETA_FREQUENCY_OPTIONS,
    CAPITAL_STRUCTURE_OPTIONS,
    COL_DEBT_TIC,
    COL_RELEVERED_BETA,
)
from Canneberge.Calculations.gpc_metrics import (
    dropdown_options as gpc_dropdown_options,
)
from Canneberge.Calculations.chart_helper import (
    MethodRow,
    BridgeInputs,
    compute_bridge,
    weighted_conclusion,
)
from Canneberge.Ui.football_field_chart import FootballFieldChart

# ----------------------------------------------------------------------
# Dashboard constants
# ----------------------------------------------------------------------

GT_METRIC_OPTIONS = [
    "TTM Revenue",
    "TTM EBITDA",
    "TTM EBIT",
]

# "Custom" is appended so the dropdown can represent a user-typed
# override that no longer matches any summary statistic. It is never
# selected programmatically except when an override is detected.
STAT_OPTIONS = [
    "Maximum",
    "Third Quartile",
    "Average",
    "Median",
    "First Quartile",
    "Minimum",
    "Custom",
]

STAT_DEFAULT_INDEX = STAT_OPTIONS.index("Median")
STAT_CUSTOM_INDEX = STAT_OPTIONS.index("Custom")

TV_MODELS = [
    "Gordon Growth",
    "EBITDA Multiple",
    "Revenue Multiple",
    "H-Model",
]

INPUT_STYLE = "background-color: #dce9f7; color: #1a4a8a;"
DARK_HEADER_BG = "#2f2fa0"
DARK_HEADER_FG = "#ffffff"

SECTION_HEADER_STYLE = (
    f"background-color: {DARK_HEADER_BG}; "
    f"color: {DARK_HEADER_FG}; "
    "font-weight: bold; "
    "font-size: 12px; "
    "padding: 4px;"
)

SUBHEADER_STYLE = (
    "font-weight: bold; "
    "font-size: 11px; "
    "color: #1a1a1a;"
)

BORDER = "1px solid #2b2b2b"


# ----------------------------------------------------------------------
# Reusable widget helpers
# ----------------------------------------------------------------------

def _hdr(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(SECTION_HEADER_STYLE)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setFixedHeight(26)
    return label


def _link_label(text: str) -> QLabel:
    """
    Creates a clickable hyperlink-style label.
    """
    label = QLabel(f'<a href="#">{text}</a>')
    label.setStyleSheet("color: #1a4a8a;")
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.LinksAccessibleByMouse
    )
    return label


def _value_line(width: int = 90) -> QLineEdit:
    """
    Editable dashboard input placeholder.
    """
    edit = QLineEdit("-")
    edit.setFixedWidth(width)
    edit.setFixedHeight(22)
    edit.setStyleSheet(INPUT_STYLE)
    edit.setAlignment(
        Qt.AlignmentFlag.AlignRight |
        Qt.AlignmentFlag.AlignVCenter
    )
    edit.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    return edit


def _small_spin(
    minimum: int,
    maximum: int,
    value: int,
    width: int = 60,
) -> QSpinBox:
    spin = QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setValue(value)
    spin.setFixedWidth(width)
    spin.setFixedHeight(22)
    spin.setStyleSheet(INPUT_STYLE)
    spin.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    return spin


def _combo(
    options,
    width: int,
    default_index: int = 0,
) -> QComboBox:
    combo = QComboBox()
    combo.addItems(list(options))

    if 0 <= default_index < combo.count():
        combo.setCurrentIndex(default_index)

    combo.setFixedWidth(width)
    combo.setFixedHeight(22)
    combo.setStyleSheet(INPUT_STYLE)
    combo.setSizePolicy(
        QSizePolicy.Policy.Fixed,
        QSizePolicy.Policy.Fixed,
    )
    return combo


# ----------------------------------------------------------------------
# WACC popup
# ----------------------------------------------------------------------

class WACCOptionsDialog(QDialog):
    """
    Dashboard popup for the WACC page's three top-level selectors:

      - Beta Type
      - Beta Frequency
      - Capital Structure

    The dashboard currently stores the selected values locally.
    Later, these will be pushed into WACCPage and trigger its
    recalculation.
    """

    def __init__(
        self,
        parent=None,
        beta_type_index: int = 0,
        beta_frequency_index: int = 0,
        capital_structure_index: int = 0,
    ):
        super().__init__(parent)

        self.setWindowTitle("WACC Options")
        self.setModal(True)
        self.setMinimumWidth(390)

        layout = QVBoxLayout()
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Beta Type
        beta_type_row = QHBoxLayout()
        beta_type_label = QLabel("Beta Type:")
        beta_type_label.setFixedWidth(125)
        beta_type_label.setStyleSheet("font-weight: bold;")

        self.beta_type_combo = _combo(
            BETA_TYPE_OPTIONS,
            width=210,
            default_index=beta_type_index,
        )

        beta_type_row.addWidget(beta_type_label)
        beta_type_row.addWidget(self.beta_type_combo)
        beta_type_row.addStretch(1)
        layout.addLayout(beta_type_row)

        # Beta Frequency
        beta_frequency_row = QHBoxLayout()
        beta_frequency_label = QLabel("Beta Frequency:")
        beta_frequency_label.setFixedWidth(125)
        beta_frequency_label.setStyleSheet("font-weight: bold;")

        self.beta_frequency_combo = _combo(
            BETA_FREQUENCY_OPTIONS,
            width=210,
            default_index=beta_frequency_index,
        )

        beta_frequency_row.addWidget(beta_frequency_label)
        beta_frequency_row.addWidget(self.beta_frequency_combo)
        beta_frequency_row.addStretch(1)
        layout.addLayout(beta_frequency_row)

        # Capital Structure
        capital_structure_row = QHBoxLayout()
        capital_structure_label = QLabel("Capital Structure:")
        capital_structure_label.setFixedWidth(125)
        capital_structure_label.setStyleSheet("font-weight: bold;")

        self.capital_structure_combo = _combo(
            CAPITAL_STRUCTURE_OPTIONS,
            width=210,
            default_index=capital_structure_index,
        )

        capital_structure_row.addWidget(capital_structure_label)
        capital_structure_row.addWidget(self.capital_structure_combo)
        capital_structure_row.addStretch(1)
        layout.addLayout(capital_structure_row)

        layout.addSpacing(8)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def selected_values(self) -> tuple[str, str, str]:
        return (
            self.beta_type_combo.currentText(),
            self.beta_frequency_combo.currentText(),
            self.capital_structure_combo.currentText(),
        )


# ----------------------------------------------------------------------
# Football field placeholder
# ----------------------------------------------------------------------

class FootballFieldChartPlaceholder(QWidget):
    """
    Temporary chart-area placeholder.

    This will later be replaced by the actual football-field chart,
    including:
      - range bars
      - share-price line
      - concluded-value line
      - bottom number axis
      - chart legend
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setFixedSize(600, 260)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.setStyleSheet(
            "border: 1px solid #b9b9b9; "
            "background: white;"
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addStretch(1)

        label = QLabel("Football Field Chart (placeholder)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(
            "color: #666666; "
            "font-weight: bold;"
        )
        layout.addWidget(label)

        layout.addStretch(1)
        self.setLayout(layout)


# ----------------------------------------------------------------------
# Dashboard page
# ----------------------------------------------------------------------

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()

        # WACC popup state. This is dashboard-local for now.
        # It will later be synchronized with WACCPage.
        self._wacc_options_state = (
            "Raw Betas",
            "5-Year Monthly",
            "As of Valuation Date",
        )

        # Keep chart windows alive after opening them.
        self._gpc_chart_dialog = None
        self._gt_chart_dialog = None

        # Set by MainWindow via bind_pages() once the source pages exist.
        self._wacc_page = None
        self._dcf_page = None
        self._gpc_page = None
        self._gt_page = None
        self._syncing = False

        self._build_ui()

    # ------------------------------------------------------------------
    # Main layout
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        # --------------------------------------------------------------
        # Top row:
        # Income Approach | Market Approach | Future Space
        # --------------------------------------------------------------
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.setContentsMargins(0, 0, 0, 0)

        top_row.addWidget(
            self._build_income_panel(),
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        top_row.addWidget(
            self._build_market_panel(),
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        top_row.addWidget(
            self._build_top_right_probe(),
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        top_row.addStretch(1)
        root.addLayout(top_row)

        # --------------------------------------------------------------
        # Bottom row:
        # Reconciliation | Cost Approach | Football Field Chart
        # --------------------------------------------------------------
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        bottom_row.addWidget(
            self._build_reconciliation_panel(),
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        bottom_row.addWidget(
            self._build_cost_panel(),
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        self.football_chart = FootballFieldChart()
        bottom_row.addWidget(
            self.football_chart,
            0,
            alignment=Qt.AlignmentFlag.AlignTop,
        )

        bottom_row.addStretch(1)
        root.addLayout(bottom_row)

        # Preserve unused space intentionally.
        root.addStretch(1)

        self.setLayout(root)

    def _panel_frame(self, width: int) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        # Border applies to the frame only. Child QLabels inherit
        # otherwise, which puts a box around every static text item.
        frame.setStyleSheet(
            f"QFrame {{ border: {BORDER}; background: white; }}"
            "QLabel { border: none; }"
        )
        frame.setFixedWidth(width)
        frame.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        return frame

    # ------------------------------------------------------------------
    # Income Approach
    # ------------------------------------------------------------------

    def _build_income_panel(self) -> QFrame:
        # Wide enough for the three-column layout and the longer
        # descriptor dropdowns.
        frame = self._panel_frame(465)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        outer.addWidget(_hdr("Income Approach"))

        # WACC hyperlink
        wacc_link_row = QHBoxLayout()
        wacc_link_row.setContentsMargins(8, 2, 8, 0)

        wacc_link = _link_label("WACC")
        wacc_link.linkActivated.connect(
            self._open_wacc_options
        )

        wacc_link_row.addWidget(wacc_link)
        wacc_link_row.addStretch(1)
        outer.addLayout(wacc_link_row)

        grid = QGridLayout()
        grid.setContentsMargins(8, 0, 8, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(4)

        LABEL_WIDTH = 165
        VALUE_WIDTH = 80
        STAT_WIDTH = 125
        FRED_WIDTH = 210

        def label_cell(text: str) -> QLabel:
            label = QLabel(text)
            label.setFixedWidth(LABEL_WIDTH)
            return label

        row = 0

        # Debt/TIC
        grid.addWidget(label_cell("Debt/TIC"), row, 0)

        self.income_debt_tic_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_debt_tic_value,
            row,
            1,
        )

        self.income_debt_tic_stat = _combo(
            STAT_OPTIONS,
            STAT_WIDTH,
            STAT_DEFAULT_INDEX,
        )
        grid.addWidget(
            self.income_debt_tic_stat,
            row,
            2,
        )
        row += 1

        # Beta
        grid.addWidget(label_cell("Beta"), row, 0)

        self.income_beta_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_beta_value,
            row,
            1,
        )

        self.income_beta_stat = _combo(
            STAT_OPTIONS,
            STAT_WIDTH,
            STAT_DEFAULT_INDEX,
        )
        grid.addWidget(
            self.income_beta_stat,
            row,
            2,
        )
        row += 1

        # ERP
        grid.addWidget(label_cell("ERP"), row, 0)

        self.income_erp_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_erp_value,
            row,
            1,
        )

        grid.addWidget(
            QLabel("Per Kroll"),
            row,
            2,
        )
        row += 1

        # Size Premium
        grid.addWidget(label_cell("Size Premium"), row, 0)

        self.income_size_premium_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_size_premium_value,
            row,
            1,
        )

        grid.addWidget(
            QLabel(""),
            row,
            2,
        )
        row += 1

        # CSRP
        grid.addWidget(label_cell("CSRP"), row, 0)

        self.income_csrp_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_csrp_value,
            row,
            1,
        )

        grid.addWidget(
            QLabel("Projection Risk"),
            row,
            2,
        )
        row += 1

        # Pre-Tax Cost of Debt
        grid.addWidget(
            label_cell("Pre-Tax Cost of Debt"),
            row,
            0,
        )

        self.income_pretax_cost_of_debt_value = _value_line(VALUE_WIDTH)
        grid.addWidget(
            self.income_pretax_cost_of_debt_value,
            row,
            1,
        )

        self.income_pretax_debt_series = _combo(
            list(CORPORATE_RATE_SERIES.keys()),
            FRED_WIDTH,
        )
        grid.addWidget(
            self.income_pretax_debt_series,
            row,
            2,
        )
        row += 1

        # WACC output
        wacc_label = QLabel("WACC")
        wacc_label.setFixedWidth(LABEL_WIDTH)
        wacc_label.setStyleSheet("font-weight: bold;")
        grid.addWidget(wacc_label, row, 0)

        self.income_wacc_value = QLabel("-")
        self.income_wacc_value.setFixedWidth(VALUE_WIDTH)
        self.income_wacc_value.setAlignment(
            Qt.AlignmentFlag.AlignRight |
            Qt.AlignmentFlag.AlignVCenter
        )
        self.income_wacc_value.setStyleSheet("font-weight: bold;")
        grid.addWidget(self.income_wacc_value, row, 1)

        outer.addLayout(grid)

        # DCF Options
        outer.addWidget(self._build_dcf_options())

        frame.setLayout(outer)
        frame.adjustSize()
        return frame

    def _open_wacc_options(self, *_):
        """
        Opens the WACC selector popup. On OK, the three selections are
        pushed into the WACC page, which recalculates; the resulting
        values are then pulled back into the Dashboard.
        """
        current = self._wacc_options_state

        beta_type_index = (
            BETA_TYPE_OPTIONS.index(current[0])
            if current[0] in BETA_TYPE_OPTIONS
            else 0
        )
        beta_frequency_index = (
            BETA_FREQUENCY_OPTIONS.index(current[1])
            if current[1] in BETA_FREQUENCY_OPTIONS
            else 0
        )
        capital_structure_index = (
            CAPITAL_STRUCTURE_OPTIONS.index(current[2])
            if current[2] in CAPITAL_STRUCTURE_OPTIONS
            else 0
        )

        dialog = WACCOptionsDialog(
            parent=self,
            beta_type_index=beta_type_index,
            beta_frequency_index=beta_frequency_index,
            capital_structure_index=capital_structure_index,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self._wacc_options_state = dialog.selected_values()

        if self._wacc_page is None:
            return

        beta_type, beta_frequency, capital_structure = (
            self._wacc_options_state
        )

        self._syncing = True
        try:
            self._set_combo_silently(
                self._wacc_page.beta_type_combo,
                beta_type,
            )
            self._set_combo_silently(
                self._wacc_page.beta_frequency_combo,
                beta_frequency,
            )
            self._set_combo_silently(
                self._wacc_page.capital_structure_combo,
                capital_structure,
            )
            self._wacc_page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()

    # ------------------------------------------------------------------
    # PAGE BINDING (called by MainWindow after all pages exist)
    # ------------------------------------------------------------------

    def bind_pages(self, wacc_page, dcf_page, gpc_page, gt_page,
                   nwc_page, get_project_inputs,
                   get_stockanalysis_results, get_subject_debt,
                   get_subject_metric_value):
        self._wacc_page = wacc_page
        self._dcf_page = dcf_page
        self._gpc_page = gpc_page
        self._gt_page = gt_page
        self._nwc_page = nwc_page
        self._get_project_inputs = get_project_inputs
        self._get_sa_results = get_stockanalysis_results
        self._get_subject_debt = get_subject_debt
        self._get_subject_metric_value = get_subject_metric_value

        self._syncing = False

        self._connect_income_signals()
        self._connect_dcf_signals()
        self._connect_market_signals()
        self._connect_source_page_signals()

        # Recon reacts to the display toggle and weight edits.
        self.display_combo.currentTextChanged.connect(
            lambda _: self.recompute_reconciliation()
        )
        for widget in self.recon_weight_inputs.values():
            widget.editingFinished.connect(self.recompute_reconciliation)

        self.refresh_from_pages()

    def _connect_income_signals(self):
        # Stat dropdowns pick a summary statistic from the WACC page.
        self.income_debt_tic_stat.currentTextChanged.connect(
            self._on_debt_tic_stat_changed
        )
        self.income_beta_stat.currentTextChanged.connect(
            self._on_beta_stat_changed
        )

        # Typing over a stat-driven value means the value no longer
        # corresponds to a statistic, so the dropdown becomes "Custom".
        self.income_debt_tic_value.editingFinished.connect(
            self._on_debt_tic_value_edited
        )
        self.income_beta_value.editingFinished.connect(
            self._on_beta_value_edited
        )

        # Plain pass-through inputs.
        self.income_erp_value.editingFinished.connect(
            self._on_erp_edited
        )
        self.income_size_premium_value.editingFinished.connect(
            self._on_size_premium_edited
        )
        self.income_csrp_value.editingFinished.connect(
            self._on_csrp_edited
        )

        # FRED series selector for Pre-Tax Cost of Debt.
        self.income_pretax_debt_series.currentTextChanged.connect(
            self._on_pretax_series_changed
        )

    def _connect_dcf_signals(self):
        self.tv_model_combo.currentTextChanged.connect(
            self._on_tv_model_changed
        )
        self.tv_ltgr_input.editingFinished.connect(
            self._on_ltgr_edited
        )
        self.tv_selected_multiple_input.editingFinished.connect(
            self._on_selected_multiple_edited
        )
        self.tv_number_of_years_input.editingFinished.connect(
            self._on_number_of_years_edited
        )
        self.tv_short_term_growth_input.editingFinished.connect(
            self._on_short_term_growth_edited
        )
        self.capex_depreciation_input.editingFinished.connect(
            self._on_dep_pct_edited
        )

    def _connect_market_signals(self):
        """
        GPC and GT share an identical control shape, so both are wired
        through the same generic handlers with a 'kind' discriminator.
        """
        self.gpc_how_many.valueChanged.connect(
            lambda v: self._on_how_many_changed("gpc", v)
        )
        self.gt_how_many.valueChanged.connect(
            lambda v: self._on_how_many_changed("gt", v)
        )

        self.control_premium_input.editingFinished.connect(
            self._on_control_premium_edited)

        for index, combo in enumerate(self.gpc_metric_combos):
            combo.currentTextChanged.connect(
                lambda text, i=index: self._on_metric_changed("gpc", i, text)
            )
        for index, combo in enumerate(self.gt_metric_combos):
            combo.currentTextChanged.connect(
                lambda text, i=index: self._on_metric_changed("gt", i, text)
            )

        for index, widget in enumerate(self.gpc_low_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gpc", "low", i)
            )
        for index, widget in enumerate(self.gpc_high_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gpc", "high", i)
            )
        for index, widget in enumerate(self.gpc_weight_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gpc", "weight", i)
            )

        for index, widget in enumerate(self.gt_low_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gt", "low", i)
            )
        for index, widget in enumerate(self.gt_high_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gt", "high", i)
            )
        for index, widget in enumerate(self.gt_weight_inputs):
            widget.editingFinished.connect(
                lambda i=index: self._on_market_value_edited("gt", "weight", i)
            )
        # Control Premium (Dashboard) -> derives DLOC, pushes to GPC/GT
        self.control_premium_input.editingFinished.connect(
            self._on_control_premium_edited
        )

    def _connect_source_page_signals(self):
        """
        Edits made directly on WACC/DCF must flow back to the
        Dashboard. Both directions are needed for last-edit-wins.
        """
        wacc = self._wacc_page

        wacc.beta_type_combo.currentTextChanged.connect(
            self.refresh_from_pages
        )
        wacc.beta_frequency_combo.currentTextChanged.connect(
            self.refresh_from_pages
        )
        wacc.capital_structure_combo.currentTextChanged.connect(
            self.refresh_from_pages
        )
        wacc.pretax_debt_combo.currentTextChanged.connect(
            self.refresh_from_pages
        )
        wacc.input_equity_risk_premium.editingFinished.connect(
            self.refresh_from_pages
        )
        wacc.input_size_premium.editingFinished.connect(
            self.refresh_from_pages
        )
        wacc.input_csrp.editingFinished.connect(
            self.refresh_from_pages
        )

        # A WACC-side override of these two also invalidates the
        # Dashboard's stat dropdown, per the same rule as a
        # Dashboard-side override.
        wacc.selected_debt_tic_input.editingFinished.connect(
            self._on_wacc_debt_tic_edited
        )
        wacc.selected_relevered_beta_input.editingFinished.connect(
            self._on_wacc_beta_edited
        )

        dcf = self._dcf_page
        dcf.tv_model_combo.currentTextChanged.connect(
            self.refresh_from_pages
        )
        dcf.ltg_input.editingFinished.connect(
            self.refresh_from_pages
        )
        dcf.capex_dep_pct.editingFinished.connect(
            self.refresh_from_pages
        )
        # GPC / GT edits made on their own pages flow back here.
        for page in (self._gpc_page, self._gt_page):
            page.num_multiples_spin.valueChanged.connect(
                self.refresh_from_pages
            )
            for combo in page.metric_combos:
                combo.currentTextChanged.connect(
                    self.refresh_from_pages
                )
            for widget in page.selected_low_inputs:
                widget.editingFinished.connect(
                    self.refresh_from_pages
                )
            for widget in page.selected_high_inputs:
                widget.editingFinished.connect(
                    self.refresh_from_pages
                )
            for widget in page.weight_inputs:
                widget.editingFinished.connect(
                    self.refresh_from_pages
                )
        # Control Premium edited on the GPC page flows back to the
        # Dashboard, which re-derives DLOC and pushes it everywhere.
        self._gpc_page.control_premium_input.editingFinished.connect(
            self._on_gpc_control_premium_edited
        )

    # ------------------------------------------------------------------
    # PULL: source pages -> dashboard
    # ------------------------------------------------------------------

    def refresh_from_pages(self, *_):
        """
        Repopulate every bound Dashboard field from WACC and DCF.
        Signals are suppressed so this never re-triggers a push.
        """
        if getattr(self, "_wacc_page", None) is None:
            return
        if self._syncing:
            return

        self._syncing = True
        try:
            self._pull_income_from_wacc()
            self._pull_dcf_options()
            self._pull_market_from_pages()
        finally:
            self._syncing = False
            self.recompute_reconciliation()

    def _set_text_silently(self, widget, text: str):
        blocked = widget.blockSignals(True)
        widget.setText(text)
        widget.blockSignals(blocked)

    def _set_combo_silently(self, combo, text: str):
        index = combo.findText(text)
        if index < 0:
            return
        blocked = combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(blocked)

    def _pull_income_from_wacc(self):
        wacc = self._wacc_page

        # Mirror the WACC page's own Selected-row inputs.
        self._set_text_silently(
            self.income_debt_tic_value,
            wacc.selected_debt_tic_input.text(),
        )
        self._set_text_silently(
            self.income_beta_value,
            wacc.selected_relevered_beta_input.text(),
        )
        self._set_text_silently(
            self.income_erp_value,
            wacc.input_equity_risk_premium.text(),
        )
        self._set_text_silently(
            self.income_size_premium_value,
            wacc.input_size_premium.text(),
        )
        self._set_text_silently(
            self.income_csrp_value,
            wacc.input_csrp.text(),
        )

        # Pre-Tax Cost of Debt: the series is selectable, the rate
        # itself is a FRED lookup and therefore read-only here.
        self._set_combo_silently(
            self.income_pretax_debt_series,
            wacc.pretax_debt_combo.currentText(),
        )
        self._set_text_silently(
            self.income_pretax_cost_of_debt_value,
            wacc.lbl_pretax_cost_of_debt.text(),
        )

        # WACC is a pure output.
        self.income_wacc_value.setText(
            wacc.lbl_wacc_rounded.text()
        )

        # Keep the popup's remembered state aligned with the WACC page.
        self._wacc_options_state = (
            wacc.beta_type_combo.currentText(),
            wacc.beta_frequency_combo.currentText(),
            wacc.capital_structure_combo.currentText(),
        )

    def _pull_dcf_options(self):
        dcf = self._dcf_page

        self._set_combo_silently(
            self.tv_model_combo,
            dcf.tv_model_combo.currentText(),
        )
        self._set_text_silently(
            self.tv_ltgr_input,
            dcf.ltg_input.text(),
        )
        self._set_text_silently(
            self.capex_depreciation_input,
            dcf.capex_dep_pct.text(),
        )

        model = dcf.tv_model_combo.currentText()

        if model in ("EBITDA Multiple", "Revenue Multiple"):
            widget = dcf._tv_inputs.get(model, {}).get("multiple")
            if widget is not None:
                self._set_text_silently(
                    self.tv_selected_multiple_input,
                    widget.text(),
                )

        if model == "H-Model":
            years = dcf._tv_inputs.get("H-Model", {}).get("num_years")
            growth = dcf._tv_inputs.get("H-Model", {}).get(
                "short_term_growth"
            )
            if years is not None:
                self._set_text_silently(
                    self.tv_number_of_years_input,
                    years.text(),
                )
            if growth is not None:
                self._set_text_silently(
                    self.tv_short_term_growth_input,
                    growth.text(),
                )

        self._apply_tv_model_visibility(model)

    # ------------------------------------------------------------------
    # MARKET APPROACH: shared GPC / GT plumbing
    # ------------------------------------------------------------------

    def _market_page(self, kind: str):
        return self._gpc_page if kind == "gpc" else self._gt_page

    def _market_dashboard_widgets(self, kind: str) -> dict:
        if kind == "gpc":
            return {
                "how_many": self.gpc_how_many,
                "combos": self.gpc_metric_combos,
                "low": self.gpc_low_inputs,
                "high": self.gpc_high_inputs,
                "weight": self.gpc_weight_inputs,
            }
        return {
            "how_many": self.gt_how_many,
            "combos": self.gt_metric_combos,
            "low": self.gt_low_inputs,
            "high": self.gt_high_inputs,
            "weight": self.gt_weight_inputs,
        }

    def _set_spin_silently(self, spin, value: int):
        blocked = spin.blockSignals(True)
        spin.setValue(value)
        spin.blockSignals(blocked)

    def _pull_market_from_pages(self):
        for kind in ("gpc", "gt"):
            self._pull_one_market_block(kind)

    def _pull_one_market_block(self, kind: str):
        page = self._market_page(kind)
        widgets = self._market_dashboard_widgets(kind)

        active_count = page.num_multiples_spin.value()
        self._set_spin_silently(widgets["how_many"], active_count)

        row_count = len(widgets["combos"])

        for index in range(row_count):
            is_active = index < active_count

            self._set_combo_silently(
                widgets["combos"][index],
                page.metric_combos[index].currentText(),
            )
            self._set_text_silently(
                widgets["low"][index],
                page.selected_low_inputs[index].text(),
            )
            self._set_text_silently(
                widgets["high"][index],
                page.selected_high_inputs[index].text(),
            )
            self._set_text_silently(
                widgets["weight"][index],
                page.weight_inputs[index].text(),
            )

            self._set_market_row_enabled(kind, index, is_active)

    def _set_market_row_enabled(self, kind: str, index: int, enabled: bool):
        """
        Rows beyond 'How Many Multiples' stay visible but are greyed
        out and non-editable, so the block's height never changes.
        """
        widgets = self._market_dashboard_widgets(kind)

        for key in ("combos", "low", "high", "weight"):
            widget = widgets[key][index]
            widget.setEnabled(enabled)

            if enabled:
                widget.setStyleSheet(INPUT_STYLE)
            else:
                widget.setStyleSheet(
                    "background-color: #f0f0f0; color: #9a9a9a;"
                )

    def _push_to_market_page(self, kind: str, apply_fn):
        if self._syncing:
            return

        page = self._market_page(kind)

        self._syncing = True
        try:
            apply_fn(page)
            page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()

    def _even_weight_text(self, count: int) -> str:
        if count <= 0:
            return "0.0%"
        return f"{100.0 / count:.1f}%"

    def _on_how_many_changed(self, kind: str, value: int):
        """
        Changing the count resets every weight to an even split, which
        is the documented default. The user may then override any
        individual weight on either page.
        """
        even_weight = self._even_weight_text(value)

        def apply(page):
            page.num_multiples_spin.setValue(value)
            for index, widget in enumerate(page.weight_inputs):
                widget.setText(even_weight if index < value else "0.0%")

        self._push_to_market_page(kind, apply)

    def _on_metric_changed(self, kind: str, index: int, text: str):
        def apply(page):
            combo = page.metric_combos[index]
            combo_index = combo.findText(text)
            if combo_index >= 0:
                combo.setCurrentIndex(combo_index)

        self._push_to_market_page(kind, apply)

    def _on_market_value_edited(self, kind: str, field: str, index: int):
        widgets = self._market_dashboard_widgets(kind)
        text = widgets[field][index].text()

        def apply(page):
            target = {
                "low": page.selected_low_inputs,
                "high": page.selected_high_inputs,
                "weight": page.weight_inputs,
            }[field][index]
            target.setText(text)

        self._push_to_market_page(kind, apply)

    
    # ------------------------------------------------------------------
    # PUSH: dashboard -> WACC
    # ------------------------------------------------------------------

    def _push_to_wacc(self, widget, text: str):
        """
        Write a value into a WACC input and force that page to
        recalculate, then pull the results back.
        """
        if self._syncing:
            return

        self._syncing = True
        try:
            widget.setText(text)
            self._wacc_page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()

    def _stat_value_from_wacc(self, stat: str, column: int) -> str:
        """
        Read one cell out of the WACC page's Statistics block.
        Returns an empty string when the statistic is unavailable.
        """
        labels = self._wacc_page.stat_label_widgets.get(stat)
        if not labels:
            return ""

        label = labels.get(column)
        if label is None:
            return ""

        text = label.text()
        return "" if text in ("NA", "-", "") else text

    def _on_debt_tic_stat_changed(self, stat: str):
        if self._syncing or stat == "Custom":
            return

        value = self._stat_value_from_wacc(stat, COL_DEBT_TIC)
        if not value:
            return

        self._set_text_silently(self.income_debt_tic_value, value)
        self._push_to_wacc(
            self._wacc_page.selected_debt_tic_input,
            value,
        )

    def _on_beta_stat_changed(self, stat: str):
        if self._syncing or stat == "Custom":
            return

        value = self._stat_value_from_wacc(stat, COL_RELEVERED_BETA)
        if not value:
            return

        self._set_text_silently(self.income_beta_value, value)
        self._push_to_wacc(
            self._wacc_page.selected_relevered_beta_input,
            value,
        )

    def _on_debt_tic_value_edited(self):
        if self._syncing:
            return

        self._set_combo_silently(self.income_debt_tic_stat, "Custom")
        self._push_to_wacc(
            self._wacc_page.selected_debt_tic_input,
            self.income_debt_tic_value.text(),
        )

    def _on_beta_value_edited(self):
        if self._syncing:
            return

        self._set_combo_silently(self.income_beta_stat, "Custom")
        self._push_to_wacc(
            self._wacc_page.selected_relevered_beta_input,
            self.income_beta_value.text(),
        )

    def _on_wacc_debt_tic_edited(self):
        """A WACC-side edit invalidates the Dashboard stat dropdown."""
        if self._syncing:
            return
        self._set_combo_silently(self.income_debt_tic_stat, "Custom")
        self.refresh_from_pages()

    def _on_wacc_beta_edited(self):
        if self._syncing:
            return
        self._set_combo_silently(self.income_beta_stat, "Custom")
        self.refresh_from_pages()

    def _on_erp_edited(self):
        self._push_to_wacc(
            self._wacc_page.input_equity_risk_premium,
            self.income_erp_value.text(),
        )

    def _on_size_premium_edited(self):
        self._push_to_wacc(
            self._wacc_page.input_size_premium,
            self.income_size_premium_value.text(),
        )

    def _on_csrp_edited(self):
        self._push_to_wacc(
            self._wacc_page.input_csrp,
            self.income_csrp_value.text(),
        )

    def _on_pretax_series_changed(self, series_name: str):
        if self._syncing:
            return

        self._syncing = True
        try:
            self._set_combo_silently(
                self._wacc_page.pretax_debt_combo,
                series_name,
            )
            self._wacc_page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()

    # ------------------------------------------------------------------
    # PUSH: dashboard -> DCF
    # ------------------------------------------------------------------

    def _push_to_dcf(self, apply_fn):
        if self._syncing:
            return

        self._syncing = True
        try:
            apply_fn()
            self._dcf_page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()

    def _on_tv_model_changed(self, model: str):
        # Local visibility updates immediately so the box does not
        # flicker while the DCF page recalculates.
        self._apply_tv_model_visibility(model)

        def apply():
            self._set_combo_silently(
                self._dcf_page.tv_model_combo,
                model,
            )
            self._dcf_page._apply_tv_model_visibility()

        self._push_to_dcf(apply)

    def _on_ltgr_edited(self):
        def apply():
            self._dcf_page.ltg_input.setText(
                self.tv_ltgr_input.text()
            )

        self._push_to_dcf(apply)

    def _on_selected_multiple_edited(self):
        model = self.tv_model_combo.currentText()
        if model not in ("EBITDA Multiple", "Revenue Multiple"):
            return

        def apply():
            widget = self._dcf_page._tv_inputs.get(model, {}).get(
                "multiple"
            )
            if widget is not None:
                widget.setText(
                    self.tv_selected_multiple_input.text()
                )

        self._push_to_dcf(apply)

    def _on_number_of_years_edited(self):
        def apply():
            widget = self._dcf_page._tv_inputs.get(
                "H-Model", {}
            ).get("num_years")
            if widget is not None:
                widget.setText(
                    self.tv_number_of_years_input.text()
                )

        self._push_to_dcf(apply)

    def _on_short_term_growth_edited(self):
        def apply():
            widget = self._dcf_page._tv_inputs.get(
                "H-Model", {}
            ).get("short_term_growth")
            if widget is not None:
                widget.setText(
                    self.tv_short_term_growth_input.text()
                )

        self._push_to_dcf(apply)

    def _on_dep_pct_edited(self):
        def apply():
            self._dcf_page.capex_dep_pct.setText(
                self.capex_depreciation_input.text()
            )

        self._push_to_dcf(apply)



    # ------------------------------------------------------------------
    # DCF Options
    # ------------------------------------------------------------------

    def _build_dcf_options(self) -> QWidget:
        wrapper = QWidget()

        outer = QVBoxLayout()
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(4)

        title = QLabel("DCF Options")
        title.setStyleSheet(SUBHEADER_STYLE)
        outer.addWidget(title)

        # Terminal Value model
        model_row = QHBoxLayout()
        model_row.setSpacing(6)

        model_label = QLabel("Terminal Year")
        model_label.setFixedWidth(165)
        model_row.addWidget(model_label)

        self.tv_model_combo = _combo(
            TV_MODELS,
            width=180,
        )
        self.tv_model_combo.currentTextChanged.connect(
            self._apply_tv_model_visibility
        )
        model_row.addWidget(self.tv_model_combo)
        model_row.addStretch(1)
        outer.addLayout(model_row)

        # All models: Long Term Growth Rate
        (
            self.tv_ltgr_row,
            self.tv_ltgr_input,
        ) = self._dcf_input_row(
            "Long Term Growth Rate",
            "3.0%",
        )
        outer.addLayout(self.tv_ltgr_row)

        # EBITDA / Revenue Multiple models
        (
            self.tv_selected_multiple_row,
            self.tv_selected_multiple_input,
        ) = self._dcf_input_row(
            "Selected Multiple",
            "10.00x",
        )
        outer.addLayout(self.tv_selected_multiple_row)

        # H-Model
        (
            self.tv_number_of_years_row,
            self.tv_number_of_years_input,
        ) = self._dcf_input_row(
            "Number of Years",
            "5",
        )
        outer.addLayout(self.tv_number_of_years_row)

        (
            self.tv_short_term_growth_row,
            self.tv_short_term_growth_input,
        ) = self._dcf_input_row(
            "Short Term Growth Rate",
            "20.0%",
        )
        outer.addLayout(self.tv_short_term_growth_row)

        # CapEx Options
        capex_title = QLabel("CapEx Options")
        capex_title.setStyleSheet(SUBHEADER_STYLE)
        outer.addWidget(capex_title)

        (
            self.capex_depreciation_row,
            self.capex_depreciation_input,
        ) = self._dcf_input_row(
            "Dep. as % of CapEx",
            "100.0%",
        )
        outer.addLayout(self.capex_depreciation_row)

        wrapper.setLayout(outer)

        self._apply_tv_model_visibility(
            self.tv_model_combo.currentText()
        )

        return wrapper

    def _dcf_input_row(
        self,
        label_text: str,
        default_text: str,
    ):
        row = QHBoxLayout()
        row.setSpacing(6)

        label = QLabel(label_text)
        label.setFixedWidth(165)
        row.addWidget(label)

        input_widget = QLineEdit(default_text)
        input_widget.setFixedWidth(90)
        input_widget.setFixedHeight(22)
        input_widget.setStyleSheet(INPUT_STYLE)
        input_widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        input_widget.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        row.addWidget(input_widget)

        row.addStretch(1)
        return row, input_widget

    def _set_row_visible(
        self,
        layout: QHBoxLayout,
        visible: bool,
    ):
        for index in range(layout.count()):
            item = layout.itemAt(index)
            widget = item.widget()

            if widget is not None:
                widget.setVisible(visible)

    def _apply_tv_model_visibility(self, model: str = None):
        model = model or self.tv_model_combo.currentText()

        is_multiple_model = model in (
            "EBITDA Multiple",
            "Revenue Multiple",
        )
        is_h_model = model == "H-Model"

        # Selected Multiple appears only for EBITDA/Revenue Multiple.
        self._set_row_visible(
            self.tv_selected_multiple_row,
            is_multiple_model,
        )

        # Number of Years and Short Term Growth Rate appear only for
        # the H-Model.
        self._set_row_visible(
            self.tv_number_of_years_row,
            is_h_model,
        )
        self._set_row_visible(
            self.tv_short_term_growth_row,
            is_h_model,
        )

    # ------------------------------------------------------------------
    # Market Approach
    # ------------------------------------------------------------------

    def _build_market_panel(self) -> QFrame:
        text_column_width = 250
        value_column_width = 85

        panel_width = (
            8
            + text_column_width
            + 4
            + value_column_width
            + 4
            + value_column_width
            + 4
            + value_column_width
            + 8
        )

        frame = self._panel_frame(panel_width)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        outer.addWidget(_hdr("Market Approach"))

        # GPC hyperlink
        gpc_link_row = QHBoxLayout()
        gpc_link_row.setContentsMargins(8, 0, 8, 0)

        gpc_link = _link_label("GPC")
        gpc_link.linkActivated.connect(
            self._open_gpc_chart
        )

        gpc_link_row.addWidget(gpc_link)
        gpc_link_row.addStretch(1)
        outer.addLayout(gpc_link_row)

        # GPC count
        gpc_count_row = QHBoxLayout()
        gpc_count_row.setContentsMargins(8, 0, 8, 0)
        gpc_count_row.setSpacing(6)

        gpc_count_row.addWidget(
            QLabel("How Many Multiples:")
        )

        self.gpc_how_many = _small_spin(
            1,
            7,
            7,
            80,
        )
        gpc_count_row.addWidget(self.gpc_how_many)
        gpc_count_row.addStretch(1)
        outer.addLayout(gpc_count_row)

        # GPC multiple controls
        self.gpc_metric_combos = []
        self.gpc_low_inputs = []
        self.gpc_high_inputs = []
        self.gpc_weight_inputs = []

        outer.addLayout(
            self._build_multiple_grid(
                row_count=7,
                options=gpc_dropdown_options(),
                text_column_width=text_column_width,
                value_column_width=value_column_width,
                combo_list=self.gpc_metric_combos,
                low_list=self.gpc_low_inputs,
                high_list=self.gpc_high_inputs,
                weight_list=self.gpc_weight_inputs,
            )
        )

        # GT hyperlink
        gt_link_row = QHBoxLayout()
        gt_link_row.setContentsMargins(8, 0, 8, 0)

        gt_link = _link_label("GT")
        gt_link.linkActivated.connect(
            self._open_gt_chart
        )

        gt_link_row.addWidget(gt_link)
        gt_link_row.addStretch(1)
        outer.addLayout(gt_link_row)

        # GT count
        gt_count_row = QHBoxLayout()
        gt_count_row.setContentsMargins(8, 0, 8, 0)
        gt_count_row.setSpacing(6)

        gt_count_row.addWidget(
            QLabel("How Many Multiples:")
        )

        self.gt_how_many = _small_spin(
            1,
            3,
            3,
            80,
        )
        gt_count_row.addWidget(self.gt_how_many)
        gt_count_row.addStretch(1)
        outer.addLayout(gt_count_row)

        # GT multiple controls
        self.gt_metric_combos = []
        self.gt_low_inputs = []
        self.gt_high_inputs = []
        self.gt_weight_inputs = []

        outer.addLayout(
            self._build_multiple_grid(
                row_count=3,
                options=GT_METRIC_OPTIONS,
                text_column_width=text_column_width,
                value_column_width=value_column_width,
                combo_list=self.gt_metric_combos,
                low_list=self.gt_low_inputs,
                high_list=self.gt_high_inputs,
                weight_list=self.gt_weight_inputs,
            )
        )

        frame.setLayout(outer)
        frame.adjustSize()
        return frame

    def _build_multiple_grid(
        self,
        row_count: int,
        options,
        text_column_width: int,
        value_column_width: int,
        combo_list: list,
        low_list: list,
        high_list: list,
        weight_list: list,
    ) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(8, 0, 8, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(2)

        grid.addWidget(QLabel(""), 0, 0)
        grid.addWidget(QLabel("Low"), 0, 1)
        grid.addWidget(QLabel("High"), 0, 2)
        grid.addWidget(QLabel("Weight"), 0, 3)

        for row in range(1, row_count + 1):
            combo = _combo(
                options,
                width=text_column_width,
                default_index=min(
                    row - 1,
                    len(options) - 1,
                ),
            )
            grid.addWidget(combo, row, 0)
            combo_list.append(combo)

            low = _value_line(value_column_width)
            high = _value_line(value_column_width)
            weight = _value_line(value_column_width)

            grid.addWidget(low, row, 1)
            grid.addWidget(high, row, 2)
            grid.addWidget(weight, row, 3)

            low_list.append(low)
            high_list.append(high)
            weight_list.append(weight)

        return grid

    def _open_gpc_chart(self, *_):
        """
        Open the real GPC chart through GPCPage.

        Dashboard should not create a raw GPCCandlestickChart because
        the raw chart has no data. GPCPage._on_chart_link_clicked()
        already knows how to:
          1. create/reuse the chart dialog,
          2. recalculate GPC multiples,
          3. push chart data via update_data().
        """
        if self._gpc_page is None:
            print("[Dashboard] GPC page not bound; cannot open GPC chart.")
            return

        self._gpc_page._on_chart_link_clicked()

    def _open_gt_chart(self, *_):
        """
        Open the real GT chart through GTPage.

        GTPage._on_chart_link_clicked() creates/reuses the GT chart
        and pushes the current transaction multiple data into it.
        """
        if self._gt_page is None:
            print("[Dashboard] GT page not bound; cannot open GT chart.")
            return

        self._gt_page._on_chart_link_clicked()

    # ------------------------------------------------------------------
    # Temporary top-right space probe
    # ------------------------------------------------------------------

    def _build_top_right_probe(self) -> QFrame:
        frame = self._panel_frame(220)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(_hdr("Future Space"))

        inner = QVBoxLayout()
        inner.setContentsMargins(8, 8, 8, 8)

        for text in [
            "Top-right probe",
            "Use this area later for:",
            "• dynamic charts",
            "• helper lists",
            "• summaries",
        ]:
            inner.addWidget(
                QLabel(text),
                alignment=Qt.AlignmentFlag.AlignLeft,
            )

        inner.addStretch(1)
        outer.addLayout(inner)

        frame.setLayout(outer)
        frame.adjustSize()
        return frame

    # ------------------------------------------------------------------
    # Cost Approach
    # ------------------------------------------------------------------

    def _build_cost_panel(self) -> QFrame:
        frame = self._panel_frame(360)

        outer = QVBoxLayout()
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.addWidget(_hdr("Cost Approach"))

        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(8, 0, 8, 0)
        nav_row.addWidget(QLabel("NAV Method"))
        nav_row.addStretch(1)
        outer.addLayout(nav_row)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(8, 0, 8, 0)
        header_row.setSpacing(6)

        basis_label = QLabel(
            "Asset Value - Liquidation Basis"
        )
        basis_label.setFixedWidth(190)
        header_row.addWidget(basis_label)

        header_row.addStretch(1)
        header_row.addWidget(QLabel("Cost Count"))

        self.cost_count_spin = _small_spin(
            1,
            10,
            5,
            60,
        )
        header_row.addWidget(self.cost_count_spin)
        outer.addLayout(header_row)

        grid = QGridLayout()
        grid.setContentsMargins(8, 0, 8, 8)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)

        self.cost_value_inputs = []

        cost_rows = [
            "Legal Fees",
            "Accounting Fees",
            "Auction Fees",
            "Advertising",
            "Insolvency Practitioner",
        ]

        for row, text in enumerate(cost_rows):
            label = QLabel(text)
            label.setFixedWidth(155)
            grid.addWidget(
                label,
                row,
                0,
                alignment=Qt.AlignmentFlag.AlignLeft,
            )

            value = _value_line(85)
            grid.addWidget(
                value,
                row,
                1,
                alignment=Qt.AlignmentFlag.AlignRight,
            )
            self.cost_value_inputs.append(value)

        outer.addLayout(grid)

        frame.setLayout(outer)
        frame.adjustSize()
        return frame

    # ------------------------------------------------------------------
    # Reconciliation of Values
    # ------------------------------------------------------------------

    def _build_reconciliation_panel(self) -> QFrame:
        frame = self._panel_frame(330)

        outer = QVBoxLayout()
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        outer.addWidget(_hdr("Reconciliation of Values"))

        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(3)

        headers = [
            ("", 40),
            ("Low", 85),
            ("High", 85),
            ("Weighting", 85),
        ]

        for column, (text, width) in enumerate(headers):
            label = QLabel(text)
            label.setFixedWidth(width)
            grid.addWidget(label, 0, column)

        self.recon_low_inputs = {}
        self.recon_high_inputs = {}
        self.recon_weight_inputs = {}

        reconciliation_rows = [
            "DCF",
            "GPC",
            "GT",
            "GIPO",
            "NAV",
        ]

        for row, name in enumerate(reconciliation_rows, start=1):
            label = QLabel(name)
            label.setFixedWidth(40)
            grid.addWidget(label, row, 0)

            low = _value_line(85)
            high = _value_line(85)
            weight = _value_line(85)

            grid.addWidget(low, row, 1)
            grid.addWidget(high, row, 2)
            grid.addWidget(weight, row, 3)

            self.recon_low_inputs[name] = low
            self.recon_high_inputs[name] = high
            self.recon_weight_inputs[name] = weight

        outer.addLayout(grid)

        # Control Premium — single source of truth for the whole app.
        cp_row = QHBoxLayout()
        cp_row.setSpacing(6)
        cp_lbl = QLabel("Control Premium:")
        cp_lbl.setFixedWidth(140)
        cp_row.addWidget(cp_lbl)
        self.control_premium_input = _value_line(70)
        self.control_premium_input.setText("24.0%")
        cp_row.addWidget(self.control_premium_input)
        cp_row.addStretch(1)
        outer.addLayout(cp_row)

        # DLOC — derived, never typed: DLOC = CP / (1 + CP)
        dloc_row = QHBoxLayout()
        dloc_row.setSpacing(6)
        dloc_lbl = QLabel("Implied DLOC:")
        dloc_lbl.setFixedWidth(140)
        dloc_row.addWidget(dloc_lbl)
        self.implied_dloc_label = QLabel("19.4%")
        self.implied_dloc_label.setFixedWidth(70)
        self.implied_dloc_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        dloc_row.addWidget(self.implied_dloc_label)
        dloc_row.addStretch(1)
        outer.addLayout(dloc_row)

        # Display toggle
        display_row = QHBoxLayout()
        display_row.setSpacing(6)
        display_row.addWidget(QLabel("Display:"))

        self.display_combo = _combo(
            ["BEV", "Equity", "$/Share"],
            width=90,
        )
        self.display_combo.currentTextChanged.connect(
            self._on_display_toggle
        )

        display_row.addWidget(self.display_combo)
        display_row.addStretch(1)
        outer.addLayout(display_row)

        # Concluded value row
        value_row = QHBoxLayout()
        value_row.setSpacing(6)

        self.fv_bottom_label = QLabel(
            "FV of Business Enterprise (Base):"
        )
        self.fv_bottom_label.setStyleSheet(
            "font-weight: bold;"
        )
        self.fv_bottom_label.setFixedWidth(210)

        self.fv_value = _value_line(95)

        value_row.addWidget(self.fv_bottom_label)
        value_row.addWidget(self.fv_value)
        value_row.addStretch(1)
        outer.addLayout(value_row)

        frame.setLayout(outer)
        frame.adjustSize()
        return frame

    def _derive_dloc(self) -> Optional[float]:
        """DLOC = CP / (1 + CP). The inverse relationship between a
        control premium and the discount for lack of control."""
        from Canneberge.Ui.gt_page import _parse_pct
        cp = _parse_pct(self.control_premium_input.text())
        if cp is None or cp <= -1.0:
            return None
        return cp / (1.0 + cp)

    def _on_control_premium_edited(self):
        if self._syncing:
            return
        dloc = self._derive_dloc()
        self.implied_dloc_label.setText(
            f"{dloc * 100:.1f}%" if dloc is not None else "-")
        if dloc is None:
            return
        dloc_text = f"{dloc * 100:.1f}%"
        cp_text = self.control_premium_input.text()

        self._syncing = True
        try:
            # Push the SAME derived DLOC everywhere it's consumed.
            self._gpc_page.control_premium_input.setText(cp_text)
            self._gpc_page.dloc_input.setText(dloc_text)
            self._gt_page.dloc_input.setText(dloc_text)
            self._gpc_page._recalculate()
            self._gt_page._recalculate()
        finally:
            self._syncing = False

        self.refresh_from_pages()
        self.recompute_reconciliation()

    def _on_gpc_control_premium_edited(self):
        """GPC-page CP edited: mirror it into the Dashboard input,
        then run the normal Dashboard-side derivation/push."""
        if self._syncing:
            return
        self._set_text_silently(
            self.control_premium_input,
            self._gpc_page.control_premium_input.text(),
        )
        self._on_control_premium_edited()

    # ------------------------------------------------------------------
    # RECONCILIATION OF VALUES (bridge + concluded FV)
    # ------------------------------------------------------------------

    def _collect_bridge_inputs(self) -> BridgeInputs:
        from Canneberge.Ui.dcf_page import _parse_label_as_float
        from Canneberge.Calculations.gpc_multiples import get_subject_cash

        inputs = self._get_project_inputs()
        sa = self._get_sa_results() or {}

        cash = get_subject_cash(sa.get("BS", []), inputs.subject_ticker)

        nwc_surplus = _parse_label_as_float(
            self._nwc_page.nwc_surplus_deficit_label.text()
        )

        try:
            debt = self._get_subject_debt()
        except Exception:
            debt = None

        liquidation = self._get_subject_metric_value(
            "preferred_stock", "TTM"
        )

        shares, price = self._subject_shares_and_price(inputs, sa)

        # DLOC is always derived from the Dashboard's Control Premium.
        dloc = self._derive_dloc()

        return BridgeInputs(
            cash=cash,
            nwc_surplus=nwc_surplus,
            debt=debt,
            liquidation=liquidation,
            dloc=dloc,
            shares_outstanding=shares,
            share_price=price,
        )

    def _subject_shares_and_price(self, inputs, sa):
        """Shares Outstanding = Market Cap / Last Close Price, both
        from the StockAnalysis Ratios statement for the subject."""
        tick = inputs.subject_ticker.lower()
        market_cap = None
        price = None

        for row in sa.get("Ratios", []):
            if str(row.get("Ticker", "")).lower() != tick:
                continue
            line = str(row.get("Line Item", "")).strip().lower()
            raw = str(row.get("TTM", "")).replace(",", "")
            if line == "market capitalization":
                try:
                    market_cap = float(raw)
                except (ValueError, TypeError):
                    pass
            elif line == "last close price":
                try:
                    price = float(raw)
                except (ValueError, TypeError):
                    pass

        shares = (market_cap / price) if (market_cap and price) else None
        return shares, price

    def _collect_method_rows(self):
        """One MethodRow per chart line: DCF, each active GPC
        multiple, each active GT multiple."""
        from Canneberge.Ui.dcf_page import _parse_label_as_float as parse

        rows = []

        rows.append(MethodRow(
            name="Discounted Cash Flow Method",
            bev_low=parse(self._dcf_page.bridge_fv_low_label.text()),
            bev_high=parse(self._dcf_page.bridge_fv_high_label.text()),
            apply_dloc=True,
        ))

        gpc_count = self._gpc_page.num_multiples_spin.value()
        for i in range(gpc_count):
            rows.append(MethodRow(
                name=f"GPC - {self._gpc_page.metric_combos[i].currentText()}",
                bev_low=parse(
                    self._gpc_page.indicated_bev_low_labels[i].text()
                ),
                bev_high=parse(
                    self._gpc_page.indicated_bev_high_labels[i].text()
                ),
                apply_dloc=False,   # GPC already noncontrolling
            ))

        gt_count = self._gt_page.num_multiples_spin.value()
        for i in range(gt_count):
            rows.append(MethodRow(
                name=f"GT - {self._gt_page.metric_combos[i].currentText()}",
                bev_low=parse(
                    self._gt_page.indicated_bev_low_labels[i].text()
                ),
                bev_high=parse(
                    self._gt_page.indicated_bev_high_labels[i].text()
                ),
                apply_dloc=True,
            ))

        return rows

    def _single_bridged_pair(self, name, low, high, apply_dloc,
                             bridge_inputs, basis):
        """Run ONE (low, high) BEV pair through the bridge and return
        the values on the requested display basis."""
        if low is None and high is None:
            return None, None
        row = MethodRow(
            name=name, bev_low=low, bev_high=high, apply_dloc=apply_dloc
        )
        compute_bridge([row], bridge_inputs)
        return row.values_for_basis(basis)

    def _method_pair(self, name, basis):
        """Find a named row in the already-computed bridge rows."""
        for row in getattr(self, "_bridge_rows", []):
            if row.name == name:
                return row.values_for_basis(basis)
        return None, None

    def recompute_reconciliation(self):
        """Populate the Reconciliation box + concluded FV from the
        bridge. Chart wiring consumes self._bridge_rows separately."""
        if self._gpc_page is None:
            return

        from Canneberge.Ui.dcf_page import _parse_label_as_float as parse
        from Canneberge.Ui.gt_page import _parse_pct

        bridge_inputs = self._collect_bridge_inputs()
        self._bridge_rows = compute_bridge(
            self._collect_method_rows(), bridge_inputs
        )

        basis = self.display_combo.currentText()

        # Box rows are METHOD-level: DCF's own pair, plus the GPC/GT
        # pages' weighted FMV BEV run through the same bridge.
        method_pairs = {
            "DCF": self._method_pair(
                "Discounted Cash Flow Method", basis
            ),
            "GPC": self._single_bridged_pair(
                "GPC (weighted)",
                parse(self._gpc_page.fmv_low_label.text()),
                parse(self._gpc_page.fmv_high_label.text()),
                False,
                bridge_inputs,
                basis,
            ),
            "GT": self._single_bridged_pair(
                "GT (weighted)",
                parse(self._gt_page.fmv_low_label.text()),
                parse(self._gt_page.fmv_high_label.text()),
                True,
                bridge_inputs,
                basis,
            ),
            "GIPO": (None, None),
            "NAV": (None, None),
        }

        def fmt(value):
            if value is None:
                return "-"
            if basis == "$/Share":
                return f"{value:,.2f}"
            return f"{value:,.0f}"

        pairs = []
        weights = []
        for name in ("DCF", "GPC", "GT", "GIPO", "NAV"):
            low, high = method_pairs[name]
            self._set_text_silently(self.recon_low_inputs[name], fmt(low))
            self._set_text_silently(self.recon_high_inputs[name], fmt(high))
            pairs.append((low, high))
            weights.append(
                _parse_pct(self.recon_weight_inputs[name].text())
            )

        concluded = weighted_conclusion(pairs, weights)
        self.fv_value.setText(fmt(concluded))

        self._update_football_field(bridge_inputs, basis, concluded)

    def _share_price_on_basis(self, bridge_inputs, basis) -> Optional[float]:
        """
        Convert the market share price to the active display basis:
          $/Share : price as-is
          Equity  : price * shares = market cap
          BEV     : market cap + debt - cash (back out the bridge)
        """
        price = bridge_inputs.share_price
        shares = bridge_inputs.shares_outstanding
        if price is None:
            return None
        if basis == "$/Share":
            return price
        if shares is None:
            return None
        market_cap = price * shares
        if basis == "Equity":
            return market_cap
        debt = bridge_inputs.debt or 0.0
        cash = bridge_inputs.cash or 0.0
        return market_cap + debt - cash

    def _update_football_field(self, bridge_inputs, basis, concluded_fv):
        rows = [
            (row.name, *row.values_for_basis(basis))
            for row in getattr(self, "_bridge_rows", [])
        ]
        self.football_chart.update_chart(
            rows=rows,
            share_price_marker=self._share_price_on_basis(
                bridge_inputs, basis
            ),
            concluded_fv=concluded_fv,
            basis=basis,
        )

    def _on_display_toggle(self, mode: str):
        if mode == "Equity":
            self.fv_bottom_label.setText("FV of Equity (Base):")
        elif mode == "$/Share":
            self.fv_bottom_label.setText("Concluded FV ($/Share):")
        else:
            self.fv_bottom_label.setText(
                "FV of Business Enterprise (Base):"
            )

    