"""
Debt Schedule tab — ISOLATED. Reads only ProjectInputs (dates/period
counts). Nothing else reads from this page yet; DCF wiring comes later
via get_projected_interest_expense() / get_net_borrowing().
"""

from typing import Optional, List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QScrollArea, QComboBox, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt

from Canneberge.Ui.theme import theme_manager
from Canneberge.Ui.dcf_page import _fmt_currency, _parse_label_as_float
from Canneberge.Calculations.debt_schedule import (
    parse_date, add_years, build_period_boundaries, compute_debt_schedule,
)

COL_W = 85
INPUT_COLS = [
    ("name", "Note", 130), ("issuance", "Issued", 80),
    ("maturity", "Matures", 80), ("coupon", "Coupon %", 70),
    ("effective", "Effective %", 70), ("principal", "Principal", 80),
]
DEFAULT_ROWS = 3
MAX_ROWS = 20


def get_input_style():
    return theme_manager.current.input_style()


def get_bold_style():
    return theme_manager.current.bold_style()


def get_header_style():
    return theme_manager.current.header_style()


def _parse_pct(text) -> Optional[float]:
    v = _parse_label_as_float(str(text)) if text else None
    return v / 100.0 if v is not None else None


class DebtSchedulePage(QWidget):
    def __init__(self, get_project_inputs_callback):
        super().__init__()
        self.get_project_inputs = get_project_inputs_callback
        self._row_count = DEFAULT_ROWS
        self._saved_rows: List[Dict[str, str]] = []
        self._tranche_widgets: List[Dict] = []
        self._building = False
        self.table_container = None
        self._built_signature = None
        self._latest_results: Dict = {}
        self._build_ui()
        self._recalculate()
        theme_manager.theme_changed.connect(lambda _t: self._restyle())

    # -------------------------------------------------- structure
    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.page_container = QWidget()
        self.page_layout = QVBoxLayout(self.page_container)
        self.page_layout.setContentsMargins(10, 10, 10, 10)
        self.page_layout.setSpacing(6)

        top = QHBoxLayout()
        self.lbl_title = QLabel("Debt Schedule", styleSheet=get_header_style())
        top.addWidget(self.lbl_title)
        top.addSpacing(24)
        top.addWidget(QLabel("Rate Basis:"))
        self.rate_basis_combo = QComboBox()
        self.rate_basis_combo.addItems(["Effective Rate", "Coupon Rate"])
        self.rate_basis_combo.setStyleSheet(get_input_style())
        self.rate_basis_combo.currentTextChanged.connect(self._recalculate)
        top.addWidget(self.rate_basis_combo)
        top.addStretch(1)
        self.page_layout.addLayout(top)

        self._table_insert_index = self.page_layout.count()
        self._rebuild_table(force=True)
        self.page_layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(self.page_container)
        outer.addWidget(scroll)

    def _period_labels(self):
        b = self._boundaries()
        return [lbl for lbl, _p, _e in b] if b else []

    def _boundaries(self):
        inputs = self.get_project_inputs()
        lfy = parse_date(inputs.last_fiscal_year)
        nfy = parse_date(inputs.next_fiscal_year)
        if lfy is None or nfy is None:
            return []
        return build_period_boundaries(
            lfy_end=lfy, nfy_end=nfy,
            nfy1_end=parse_date(inputs.nfy_1),
            nfy2_end=parse_date(inputs.nfy_2),
            projection_years=inputs.projection_years,
            hist_years=1,
        )

    def _rebuild_table(self, force=False, preserve_saved=False):
        sig = (self._row_count, tuple(self._period_labels()))
        if not force and sig == self._built_signature:
            return
        if self._building:
            return
        self._building = True
        try:
            if self.table_container is not None:
                if not preserve_saved:
                    self._save_rows()
                self.page_layout.removeWidget(self.table_container)
                self.table_container.setParent(None)
                self.table_container.deleteLater()

            self._tranche_widgets = []
            self.table_container = QWidget()
            grid = QGridLayout(self.table_container)
            grid.setSpacing(3)
            self.grid = grid
            periods = self._period_labels()

            # header
            col = 0
            for _key, hdr, w in INPUT_COLS:
                lbl = QLabel(hdr, styleSheet=get_bold_style())
                grid.addWidget(lbl, 0, col)
                grid.setColumnMinimumWidth(col, w)
                col += 1
            self._first_period_col = col
            for i, p in enumerate(periods):
                lbl = QLabel(p, styleSheet=get_bold_style(),
                             alignment=Qt.AlignmentFlag.AlignRight)
                lbl.setFixedWidth(COL_W)
                grid.addWidget(lbl, 0, col + i)
            refi_col = col + len(periods)
            grid.addWidget(QLabel(""), 0, refi_col)

            # tranche rows
            r = 1
            for slot in range(self._row_count):
                widgets = {"cells": []}
                saved = self._saved_rows[slot] if slot < len(self._saved_rows) else {}
                c = 0
                for key, _hdr, w in INPUT_COLS:
                    inp = QLineEdit(saved.get(key, ""))
                    inp.setStyleSheet(get_input_style())
                    inp.setFixedWidth(w)
                    inp.editingFinished.connect(self._recalculate)
                    grid.addWidget(inp, r, c)
                    widgets[key] = inp
                    c += 1
                for i in range(len(periods)):
                    cell = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight)
                    cell.setFixedWidth(COL_W)
                    grid.addWidget(cell, r, c + i)
                    widgets["cells"].append(cell)
                btn = QPushButton("↻ ReFi")
                btn.setStyleSheet(get_input_style())
                btn.setFixedWidth(52)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _ch, s=slot: self._add_refi_row(s))
                grid.addWidget(btn, r, refi_col)
                widgets["refi_btn"] = btn
                self._tranche_widgets.append(widgets)
                r += 1

            # +/- row buttons
            btn_row = QHBoxLayout()
            self.btn_add = QPushButton("+")
            self.btn_sub = QPushButton("−")
            for b in (self.btn_add, self.btn_sub):
                b.setFixedWidth(26)
                b.setStyleSheet(get_input_style())
                b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_add.clicked.connect(lambda: self._change_rows(+1))
            self.btn_sub.clicked.connect(lambda: self._change_rows(-1))
            btn_row.addWidget(self.btn_add)
            btn_row.addWidget(self.btn_sub)
            btn_row.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(btn_row)
            grid.addWidget(wrap, r, 0, 1, 2)
            r += 1

            # totals
            self._total_rows = {}
            for label in ("Total Interest Expense", "Ending Debt Balance",
                          "Net Borrowing"):
                lbl = QLabel(label, styleSheet=get_bold_style())
                grid.addWidget(lbl, r, 0, 1, len(INPUT_COLS))
                cells = []
                for i in range(len(periods)):
                    cell = QLabel("-", alignment=Qt.AlignmentFlag.AlignRight,
                                  styleSheet=get_bold_style())
                    cell.setFixedWidth(COL_W)
                    grid.addWidget(cell, r, self._first_period_col + i)
                    cells.append(cell)
                self._total_rows[label] = cells
                r += 1

            self.page_layout.insertWidget(self._table_insert_index,
                                          self.table_container)
            self._built_signature = sig
        finally:
            self._building = False

    def _save_rows(self):
        self._saved_rows = []
        for w in self._tranche_widgets:
            self._saved_rows.append({
                "name": w["name"].text().strip(),
                "issuance": w["issuance"].text().strip(),
                "maturity": w["maturity"].text().strip(),
                "coupon": w["coupon"].text().strip(),
                "effective": w["effective"].text().strip(),
                "principal": w["principal"].text().strip(),
            })

    def _change_rows(self, delta):
        n = self._row_count + delta
        if n < 1 or n > MAX_ROWS:
            return
        self._save_rows()
        self._row_count = n
        self._rebuild_table(force=True)
        self._recalculate()

    def _add_refi_row(self, slot):
        if self._row_count >= MAX_ROWS:
            return
        self._save_rows()
        src = self._saved_rows[slot] if slot < len(self._saved_rows) else {}
        mat = parse_date(src.get("maturity"))
        refi = {
            "name": f"ReFi - {src.get('name', '')}".strip(),
            "issuance": src.get("maturity", ""),
            "maturity": add_years(mat, 5).strftime("%m/%d/%Y") if mat else "",
            "coupon": "", "effective": "",
            "principal": src.get("principal", ""),
        }
        self._saved_rows.append(refi)
        self._row_count += 1
        self._rebuild_table(force=True, preserve_saved=True)
        self._recalculate()

    # -------------------------------------------------- calc
    def _gather_tranches(self):
        tranches = []
        for w in self._tranche_widgets:
            tranches.append({
                "name": w["name"].text().strip(),
                "issuance": parse_date(w["issuance"].text()),
                "maturity": parse_date(w["maturity"].text()),
                "coupon_rate": _parse_pct(w["coupon"].text()),
                "effective_rate": _parse_pct(w["effective"].text()),
                "principal": _parse_label_as_float(w["principal"].text()),
            })
        return tranches

    def _recalculate(self):
        if self._building:
            return
        self._rebuild_table()
        boundaries = self._boundaries()
        if not boundaries:
            return
        periods = [lbl for lbl, _p, _e in boundaries]
        rate_key = ("effective_rate"
                    if self.rate_basis_combo.currentText() == "Effective Rate"
                    else "coupon_rate")
        results = compute_debt_schedule(
            self._gather_tranches(), boundaries, rate_key=rate_key
        )
        self._latest_results = results

        for w, row in zip(self._tranche_widgets,
                          results["interest_by_tranche"]):
            for cell, p in zip(w["cells"], periods):
                v = row.get(p)
                cell.setText("-" if v is None else f"{v:,.2f}")

        for label, key in (
            ("Total Interest Expense", "interest_expense_by_period"),
            ("Ending Debt Balance", "ending_debt_by_period"),
            ("Net Borrowing", "net_borrowing_by_period"),
        ):
            for cell, p in zip(self._total_rows[label], periods):
                cell.setText(_fmt_currency(results[key].get(p)))

    def _restyle(self):
        self.lbl_title.setStyleSheet(get_header_style())
        self.rate_basis_combo.setStyleSheet(get_input_style())
        for w in self._tranche_widgets:
            for key, _h, _w in INPUT_COLS:
                w[key].setStyleSheet(get_input_style())
            w["refi_btn"].setStyleSheet(get_input_style())
        for b in (self.btn_add, self.btn_sub):
            b.setStyleSheet(get_input_style())
        self._recalculate()

    # -------------------------------------------------- future wiring (NOT registered yet)
    def get_projected_interest_expense(self, period: str) -> Optional[float]:
        return self._latest_results.get(
            "interest_expense_by_period", {}
        ).get(period)

    def get_net_borrowing(self, period: str) -> Optional[float]:
        return self._latest_results.get(
            "net_borrowing_by_period", {}
        ).get(period)

    def collect_state(self) -> dict:
        self._save_rows()
        return {
            "rate_basis": self.rate_basis_combo.currentText(),
            "row_count": self._row_count,
            "rows": self._saved_rows,
        }

    def apply_state(self, state: dict):
        if not state:
            return
        self._saved_rows = state.get("rows", [])
        self._row_count = max(1, min(state.get("row_count", DEFAULT_ROWS), MAX_ROWS))
        idx = self.rate_basis_combo.findText(state.get("rate_basis", "Effective Rate"))
        if idx >= 0:
            self.rate_basis_combo.setCurrentIndex(idx)
        # Fix: Tell it to preserve the newly loaded _saved_rows instead of overwriting them with empty fields
        self._rebuild_table(force=True, preserve_saved=True) 
        self._recalculate()