import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("CANNEBERGE_CONFIG",
                    Path.home() / ".canneberge" / "config.json"))

DEFAULT_FRED_SERIES = {
    "DFF": "Federal Funds Rate",
    "SOFR": "Overnight SOFR",
    "WPRIME": "Bank Prime Loan Rate",
    "BAMLC0A0CMEY": "ICE BofA US Corporate Master",
    "BAMLC0A1CAAAEY": "ICE BofA AAA US Corporate",
    "BAMLC0A2CAAEY": "ICE BofA AA US Corporate",
    "BAMLC0A3CAEY": "ICE BofA A US Corporate",
    "BAMLC0A4CBBBEY": "ICE BofA BBB US Corporate",
    "DGS20": "US Treasury 20yr Constant Maturity",
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
            if not content:
                raise RuntimeError(f"{CONFIG_PATH} exists but is empty.")
            return json.loads(content)
    return {}


def get_fred_api_key() -> str:
    cfg = load_config()
    key = cfg.get("fred_api_key") or os.environ.get("FRED_API_KEY", "")
    if not key:
        raise RuntimeError(
            "No FRED API key found. Set FRED_API_KEY env var or add "
            f"'fred_api_key' to {CONFIG_PATH}"
        )
    return key


def get_fred_series() -> dict:
    cfg = load_config()
    return cfg.get("fred_series", DEFAULT_FRED_SERIES)