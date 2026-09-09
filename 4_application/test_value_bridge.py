import json
from pathlib import Path
from Canneberge.Calculations.value_bridge import (
    BridgeInputs, run_bridge, value_for, cp_to_dloc, dloc_to_cp,
)

# --- 1. CP/DLOC round-trip is exact ---
cp = 0.24
dloc = cp_to_dloc(cp)
cp_back = dloc_to_cp(dloc)
assert abs(cp_back - cp) < 1e-12, f"round-trip broke: {cp} -> {dloc} -> {cp_back}"
print(f"CP {cp} -> DLOC {dloc:.6f} -> CP {cp_back:.6f}  OK")

# --- 2. CP = 0 collapses every level to the same minority value ---
bi_zero = BridgeInputs(
    cash=500, nwc_surplus=-50, non_operating=0,
    debt=6150, preferred_stock=0, minority_interest=0,
    control_premium=0.0, dloc=cp_to_dloc(0.0),
    shares_outstanding=700,
)
r = run_bridge(1000, 1200, "minority", "BEV", bi_zero)
assert r["bev_controlling"] == r["bev_minority"], "CP=0 should be a no-op"
assert r["equity_controlling"] == r["equity_minority"]
print("CP=0 identity check: OK ->", r["bev_controlling"], r["bev_minority"])

# --- 3. BEV_ctrl - BEV_min == CP * Equity_min  (GPC, minority-native, BEV basis) ---
bi = BridgeInputs(
    cash=4919, nwc_surplus=-8, non_operating=0,
    debt=6150, preferred_stock=0, minority_interest=0,
    control_premium=0.24, dloc=cp_to_dloc(0.24),
    shares_outstanding=700,
)
r = run_bridge(90000, 95000, "minority", "BEV", bi)
bev_ctrl_lo, bev_ctrl_hi = r["bev_controlling"]
bev_min_lo, bev_min_hi = r["bev_minority"]
eq_min_lo, eq_min_hi = r["equity_minority"]
expected_diff_lo = 0.24 * eq_min_lo
expected_diff_hi = 0.24 * eq_min_hi
assert abs((bev_ctrl_lo - bev_min_lo) - expected_diff_lo) < 1e-6
assert abs((bev_ctrl_hi - bev_min_hi) - expected_diff_hi) < 1e-6
print(f"BEV_ctrl - BEV_min == CP * Equity_min: OK  (lo diff={bev_ctrl_lo - bev_min_lo:.4f}, "
      f"expected={expected_diff_lo:.4f})")

# --- 4. Equity mode excludes gross cash; BEV mode includes it ---
r_eq = run_bridge(500, 600, "minority", "Equity", bi, equity_mode_includes_cash=False)
r_eq_with_cash = run_bridge(500, 600, "minority", "Equity", bi, equity_mode_includes_cash=True)
lo_no_cash, _ = r_eq["equity_minority"]
lo_with_cash, _ = r_eq_with_cash["equity_minority"]
assert abs((lo_with_cash - lo_no_cash) - bi.cash) < 1e-6
print(f"Equity mode cash toggle: no_cash={lo_no_cash:.2f} with_cash={lo_with_cash:.2f} "
      f"diff={lo_with_cash - lo_no_cash:.2f} (expected {bi.cash})  OK")

# --- 5. DCF/GT controlling-native, minority target applies DLOC once ---
r_dcf = run_bridge(100000, 110000, "controlling", "BEV", bi)
eq_ctrl_lo, eq_ctrl_hi = r_dcf["equity_controlling"]
eq_min_lo2, eq_min_hi2 = r_dcf["equity_minority"]
d = bi.dloc
assert abs(eq_min_lo2 - eq_ctrl_lo * (1 - d)) < 1e-6
print(f"DCF/GT controlling->minority DLOC applied once: OK "
      f"(ctrl={eq_ctrl_lo:.2f}, min={eq_min_lo2:.2f}, dloc={d:.4f})")

print("\nAll value_bridge.py checks passed.")