"""
============================================================
COMPARATIVE SCHEMA-DRIFT ANALYZER (DRIFT ENGINE)
============================================================
This module compiles the 4 statement blueprints (IS, BS, CFS, Ratios)
into a unified master schema configuration, matches them against live 
scrapes, and reports structural changes or label name drifts.
============================================================
"""

import os
import csv
import json
import difflib
from typing import Dict, List, Tuple
from line_item_scraper import StockAnalysisClient


class MasterSchemaCompiler:
    """Consolidates the 503-ticker universe (line_items_*.csv) into a master blueprint."""

    def __init__(self, output_dir: str = "."):
        self.output_dir = output_dir
        self.statements = ["IS", "BS", "CFS", "Ratios"]

    def compile_blueprint(self, subject_ticker: str = None) -> str:
        """
        Loads the 4 universe CSVs (line_items_*.csv) for completeness.
        subject_ticker is ignored (kept for API compatibility).
        """
        master_blueprint = {}

        for stmt in self.statements:
            universe_path = os.path.join(self.output_dir, f"line_items_{stmt}.csv")
            if not os.path.exists(universe_path):
                print(f"⚠️ Warning: Universe file not found: {universe_path}")
                master_blueprint[stmt] = []
                continue

            items = []
            with open(universe_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    label = row["Line Item"].strip()
                    if label:
                        items.append({
                            "Line Item": label,
                            "Example Ticker": row.get("Example Ticker", ""),
                            "Seen Count": int(row.get("Seen Count", 0))
                        })

            master_blueprint[stmt] = items
            print(f"Compiled {len(items)} items for {stmt} from {universe_path}")

        out_path = os.path.join(self.output_dir, "master_schema_blueprint.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(master_blueprint, f, indent=4)

        print(f"\n✅ Master blueprint successfully written to {out_path}")
        return out_path


class SchemaDriftAnalyzer:
    """Compares a fresh live scrape against the Master Blueprint JSON to detect schema drift."""

    def __init__(self, blueprint_path: str = "master_schema_blueprint.json"):
        self.blueprint_path = blueprint_path
        self.client = StockAnalysisClient()
        self.master_schema = self._load_blueprint()

    def _load_blueprint(self) -> Dict[str, List[Dict]]:
        if not os.path.exists(self.blueprint_path):
            raise FileNotFoundError(f"Missing master blueprint: {self.blueprint_path}. Run compiler first.")
        with open(self.blueprint_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Standard sequence matcher ratio for fuzzy matching string changes."""
        return difflib.SequenceMatcher(None, s1.lower().strip(), s2.lower().strip()).ratio()

    def detect_drift(self, ticker: str) -> Dict[str, List[Dict]]:
        """
        Scrapes the live website for a given ticker and checks it
        against the master schema blueprint.
        """
        drift_results = {}
        ticker_lower = ticker.lower()

        print(f"\n{'='*70}\nRUNNING LIVE DRIFT DETECTION FOR: {ticker.upper()}\n{'='*70}")

        for stmt, master_items in self.master_schema.items():
            drift_results[stmt] = []
            master_set = {item["Line Item"] for item in master_items}
            
            # Fetch a live slice of the statement
            try:
                live_df = self.client.fetch_statement(ticker_lower, stmt)
            except Exception as e:
                print(f"❌ Error scraping {ticker} {stmt}: {e}")
                continue

            if live_df is None or live_df.empty or "Line Item" not in live_df.columns:
                print(f"⚠️ Live statement {stmt} is empty or unparseable for {ticker}")
                continue

            live_items = [str(x).strip() for x in live_df["Line Item"].tolist() if str(x).strip()]
            live_set = set(live_items)

            # 1. Detect New Items (on live page, but missing from blueprint)
            new_items = live_set - master_set
            
            # 2. Detect Missing Items (in blueprint, but absent from live page)
            # Only consider missing items that we EXPECTED to be present (source='subject' for MMM)
            expected_master_items = {
                item["Line Item"] for item in master_items 
                if item["Source"] == "subject"
            }
            missing_items = expected_master_items - live_set

            # 3. Fuzzy match candidates to find potential renames
            renamed_candidates = {}
            unmatched_new = list(new_items)
            unmatched_missing = list(missing_items)

            for live_item in unmatched_new[:]:
                best_match = None
                best_score = 0.0
                for missing_item in unmatched_missing:
                    score = self._calculate_similarity(live_item, missing_item)
                    if score > best_score:
                        best_score = score
                        best_match = missing_item

                # Threshold of 0.70 holds high-probability matches (e.g. "Market Cap" vs "Market Capitalization" ~0.8)
                if best_score >= 0.70 and best_match:
                    renamed_candidates[live_item] = {
                        "old_name": best_match,
                        "new_name": live_item,
                        "confidence": best_score
                    }
                    unmatched_new.remove(live_item)
                    if best_match in unmatched_missing:
                        unmatched_missing.remove(best_match)

            # Package output logs
            for item in renamed_candidates.values():
                drift_results[stmt].append({
                    "Type": "POSSIBLE_RENAME",
                    "Details": f"Master item '{item['old_name']}' has likely drifted to '{item['new_name']}'",
                    "Score": round(item["confidence"], 2)
                })

            for item in unmatched_new:
                drift_results[stmt].append({
                    "Type": "NEW_ITEM",
                    "Details": f"Live scrape discovered brand-new line item: '{item}'",
                    "Score": 1.0
                })

            for item in unmatched_missing:
                drift_results[stmt].append({
                    "Type": "MISSING_ITEM",
                    "Details": f"Expected master item missing from live scrape: '{item}'",
                    "Score": 1.0
                })

            # Output findings to console
            print(f"Statement: {stmt:<8} | Live items: {len(live_set):<3} | Master: {len(master_set):<3}")
            stmt_drifts = drift_results[stmt]
            if not stmt_drifts:
                print("  ✅ Schema matches baseline perfectly. No drift detected.")
            else:
                for drift in stmt_drifts:
                    print(f"  [{drift['Type']}] - {drift['Details']} (Confidence: {drift['Score']})")

        return drift_results

    def compare_against_scraped_universe(
        self,
        universe_dir=".",
        filepath="master_vs_scraper_drift.csv",
    ):
        """
        Compares the compiled comprehensive master blueprint against the
        latest 503-ticker outputs from line_item_scraper.py.

        Flags:
          NEW_ON_WEBSITE:
              Present in line_items_{statement}.csv but absent from master.

          MISSING_FROM_WEBSITE:
              Present in master but absent from the latest scraped universe.

          POSSIBLE_RENAME:
              Informational fuzzy pairing between one missing and one new label.
              Original NEW/MISSING records are preserved.
        """
        results = []

        for stmt, master_items in self.master_schema.items():
            universe_path = os.path.join(
                universe_dir,
                f"line_items_{stmt}.csv",
            )

            if not os.path.exists(universe_path):
                results.append({
                    "Statement": stmt,
                    "Drift Type": "MISSING_UNIVERSE_FILE",
                    "Master Label": "",
                    "Current Label": "",
                    "Score": "",
                    "Details": f"File not found: {universe_path}",
                })
                continue

            master_labels = {
                str(item["Line Item"]).strip()
                for item in master_items
                if str(item.get("Line Item", "")).strip()
            }

            current_labels = set()
            with open(universe_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)

                if "Line Item" not in (reader.fieldnames or []):
                    results.append({
                        "Statement": stmt,
                        "Drift Type": "INVALID_UNIVERSE_FILE",
                        "Master Label": "",
                        "Current Label": "",
                        "Score": "",
                        "Details": (
                            f"'Line Item' column not found in "
                            f"{universe_path}"
                        ),
                    })
                    continue

                for row in reader:
                    label = str(row.get("Line Item", "")).strip()
                    if label:
                        current_labels.add(label)

            new_labels = sorted(current_labels - master_labels)
            missing_labels = sorted(master_labels - current_labels)

            for label in new_labels:
                results.append({
                    "Statement": stmt,
                    "Drift Type": "NEW_ON_WEBSITE",
                    "Master Label": "",
                    "Current Label": label,
                    "Score": 1.0,
                    "Details": (
                        "Current 503-ticker scrape contains a label "
                        "not present in the compiled master."
                    ),
                })

            for label in missing_labels:
                results.append({
                    "Statement": stmt,
                    "Drift Type": "MISSING_FROM_WEBSITE",
                    "Master Label": label,
                    "Current Label": "",
                    "Score": 1.0,
                    "Details": (
                        "Compiled master contains a label not found "
                        "anywhere in the current 503-ticker scrape."
                    ),
                })

            # Rename suggestions are informational only.
            # Do not remove original NEW/MISSING findings.
            for old_label in missing_labels:
                best_new = None
                best_score = 0.0

                for new_label in new_labels:
                    score = self._calculate_similarity(
                        old_label,
                        new_label,
                    )
                    if score > best_score:
                        best_score = score
                        best_new = new_label

                if best_new is not None and best_score >= 0.60:
                    results.append({
                        "Statement": stmt,
                        "Drift Type": "POSSIBLE_RENAME",
                        "Master Label": old_label,
                        "Current Label": best_new,
                        "Score": round(best_score, 3),
                        "Details": (
                            "Possible label rename; manual review required."
                        ),
                    })

            print(
                f"{stmt:<8} "
                f"Master: {len(master_labels):<4} "
                f"Current universe: {len(current_labels):<4} "
                f"New: {len(new_labels):<3} "
                f"Missing: {len(missing_labels):<3}"
            )

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Statement",
                "Drift Type",
                "Master Label",
                "Current Label",
                "Similarity Score",
                "Details",
            ])

            for result in results:
                writer.writerow([
                    result["Statement"],
                    result["Drift Type"],
                    result["Master Label"],
                    result["Current Label"],
                    result["Score"],
                    result["Details"],
                ])

        print(f"\nWrote {len(results)} drift findings -> {filepath}")
        return results

    def export_report(self, drift_results: Dict[str, List[Dict]], filepath: str = "schema_drift_report.csv"):
        """Writes drift anomalies to a standard diagnostic CSV."""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Statement", "Drift Type", "Details", "Match Match Score"])
            for stmt, issues in drift_results.items():
                for issue in issues:
                    w.writerow([stmt, issue["Type"], issue["Details"], issue["Score"]])
        print(f"\n📂 Written schema drift diagnostics to {filepath}")


# ==================================================================
# MAIN / EXECUTION INTERFACE
# ==================================================================

SUBJECT_TICKER = "MMM"
COMPILE_BASELINE = False

if __name__ == "__main__":
    blueprint_file = "master_schema_blueprint.json"

    # Set to True while constructing/refreshing the approved master.
    # Once the master becomes the frozen production baseline, set this
    # to False so an audit does not overwrite it.
    if COMPILE_BASELINE:
        compiler = MasterSchemaCompiler()
        blueprint_file = compiler.compile_blueprint(SUBJECT_TICKER)

    analyzer = SchemaDriftAnalyzer(blueprint_file)

    analyzer.compare_against_scraped_universe(
        universe_dir=".",
        filepath="master_vs_scraper_drift.csv",
    )