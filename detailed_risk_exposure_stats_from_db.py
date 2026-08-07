import argparse
import sqlite3
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
DEFAULT_DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
OUTPUT_DIR = SCRIPT_DIR / "analysis_outputs"

# Rewritten against the current engine schema (file_data.risk_*) instead of the legacy
# `galactic_census` table, which no longer exists for any post-#325 database -- it was a
# hand-built denormalized table from an older schema generation that nothing regenerates.
# See squid-protocol/gitgalaxy#1144 for how that gap was found.
#
# Mapping from the old 18-column galactic_census risk_*_exposure set to today's 14
# RISK_SCHEMA columns (gitgalaxy/standards/analysis_lens.py):
#   risk_cognitive_load_exposure        -> risk_cognitive_load
#   risk_error_and_exception_exposure   -> risk_safety_score      (renamed concept: defensive/error handling)
#   risk_tech_debt_exposure             -> risk_tech_debt
#   risk_testing_exposure               -> risk_verification
#   risk_api_exposure                   -> risk_api_exposure      (unchanged)
#   risk_concurrency_exposure           -> risk_concurrency
#   risk_state_flux_exposure            -> risk_state_flux
#   risk_graveyard_exposure             -> risk_dead_code
#   risk_specification_exposure         -> risk_spec_match
#   risk_instability_exposure           -> risk_stability
#   risk_volatility_exposure            -> risk_churn
#   risk_documentation_exposure         -> risk_documentation
#   risk_civil_war_exposure             -> risk_tabs_vs_spaces
#   risk_hardcoded_payload_artifacts    -> risk_secrets_risk
# Four old columns have NO current risk_* equivalent and are dropped, not just the two
# explicitly-removed ones:
#   risk_exploit_generation_surface (logic_bomb)     -- removed from the engine entirely, #1029
#   risk_weaponizable_injection_vectors              -- no longer a scored risk_* dimension
#     (raw threat_tainted_injection hit-count exists, but that's not a comparable 0-100 score)
#   risk_obfuscation_and_evasion_surface             -- same: only threat_obfuscated (raw hits) remains
#   risk_raw_memory_manipulation                     -- same: only state_pointers/state_memory_alloc (raw hits) remain
RISK_COLUMNS = [
    "risk_cognitive_load",
    "risk_safety_score",
    "risk_tech_debt",
    "risk_verification",
    "risk_api_exposure",
    "risk_concurrency",
    "risk_state_flux",
    "risk_dead_code",
    "risk_spec_match",
    "risk_stability",
    "risk_churn",
    "risk_documentation",
    "risk_tabs_vs_spaces",
    "risk_secrets_risk",
]


def run(db_path: Path):
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        return

    print(f"Connecting to {db_path}...")
    conn = sqlite3.connect(db_path)

    columns_str = ",\n    ".join(RISK_COLUMNS)
    query = f"""
    SELECT
        {columns_str}
    FROM
        file_data
    WHERE
        is_malware = 0;
    """

    print("Fetching data (this might take a moment for a few hundred thousand rows)...")
    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"Successfully loaded {len(df):,} healthy files (is_malware = 0).")

    print("Calculating distributions and percentiles...")
    stats = df.describe().T
    percentiles = df.quantile([0.90, 0.95, 0.99, 0.999]).T
    percentiles.columns = ['90%', '95%', '99%', '99.9%']
    full_stats = pd.concat([stats, percentiles], axis=1)

    ordered_columns = [
        'count', 'mean', 'std', 'min',
        '25%', '50%', '75%',
        '90%', '95%', '99%', '99.9%',
        'max'
    ]
    full_stats = full_stats[ordered_columns]
    full_stats.rename(columns={'50%': 'median', 'mean': 'average'}, inplace=True)
    full_stats = full_stats.round(3)

    print("\n" + "=" * 50)
    print("RISK EXPOSURE STATISTICS (HEALTHY BASELINE)")
    print("=" * 50)

    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(full_stats)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "comprehensive_risk_stats.csv"
    full_stats.to_csv(output_file)
    print(f"\n[+] Saved full statistics spreadsheet to: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitGalaxy Detailed Risk Exposure Statistics")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                         help=f"Path to the master SQLite DB. Default: {DEFAULT_DB_PATH}")
    args = parser.parse_args()
    run(args.db)
