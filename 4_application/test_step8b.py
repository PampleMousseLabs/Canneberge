"""Smoke test for web/lib/gpc_data.py.

Uses your test_run.json session (must have gpc_tickers configured and
StockAnalysis + MarketScreener data harvested for those tickers).
"""
from pathlib import Path
from web.lib.session_io import load_session_to_stores
from web.lib.gpc_data import (
    get_all_gpc_multiples,
    get_all_ticker_bevs,
    get_all_ticker_equity,
    get_gpc_subject_cash,
)

session_path = Path.home() / ".canneberge" / "sessions" / "test_run.json"
if not session_path.exists():
    print(f"❌ Session file not found at {session_path}")
    exit(1)

session_data, source_results, saved_at = load_session_to_stores(session_path)
tickers = session_data.get("gpc_tickers", [])
print(f"✅ Loaded session. GPC tickers: {tickers}")

if not tickers:
    print("⚠️  No GPC tickers configured in this session. Add some on Home page,")
    print("   harvest Source Data for them, save, and re-run this test.")
    exit(0)

print("\n--- BEV per ticker ---")
bevs = get_all_ticker_bevs(session_data, source_results)
for t, v in bevs.items():
    print(f"  {t:8s} = {f'${v:,.0f}' if v is not None else 'None'}")

print("\n--- Market Cap (Equity) per ticker ---")
equities = get_all_ticker_equity(session_data, source_results)
for t, v in equities.items():
    print(f"  {t:8s} = {f'${v:,.0f}' if v is not None else 'None'}")

print("\n--- BEV-mode multiples (first ticker only) ---")
multiples_bev = get_all_gpc_multiples(session_data, source_results, basis_mode="BEV")
first_ticker = tickers[0]
for metric, val in list(multiples_bev.get(first_ticker, {}).items())[:5]:
    print(f"  {metric:20s} = {f'{val:.2f}x' if val is not None else 'None'}")

print("\n--- Subject cash (for bridge) ---")
cash = get_gpc_subject_cash(session_data, source_results)
print(f"  Subject cash (TTM) = {f'${cash:,.0f}' if cash is not None else 'None'}")

print("\n✅ Smoke test complete.")