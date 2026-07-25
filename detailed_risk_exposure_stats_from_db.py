import sqlite3
import pandas as pd
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

# 1. Configuration: Set your database file name here
db_file = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

# 2. List of the 18 risk exposure columns
risk_columns = [
    "risk_cognitive_load_exposure",
    "risk_error_and_exception_exposure",
    "risk_tech_debt_exposure",
    "risk_testing_exposure",
    "risk_api_exposure",
    "risk_concurrency_exposure",
    "risk_state_flux_exposure",
    "risk_graveyard_exposure",
    "risk_specification_exposure",
    "risk_instability_exposure",
    "risk_volatility_exposure",
    "risk_documentation_exposure",
    "risk_civil_war_exposure",
    "risk_obfuscation_and_evasion_surface",
    "risk_exploit_generation_surface",
    "risk_weaponizable_injection_vectors",
    "risk_raw_memory_manipulation",
    "risk_hardcoded_payload_artifacts"
]

# 3. Connect to the database and load the data
print(f"Connecting to {db_file}...")
try:
    conn = sqlite3.connect(db_file)
    
    # Build the SQL query dynamically
    columns_str = ",\n    ".join(risk_columns)
    query = f"""
    SELECT 
        {columns_str}
    FROM 
        galactic_census
    WHERE 
        is_malware = 0;
    """
    
    print("Fetching data (this might take a moment for 2 million rows)...")
    # Load directly into a pandas DataFrame for lightning-fast math
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    print(f"Successfully loaded {len(df):,} healthy files.")
    
    # 4. Calculate Comprehensive Statistics
    print("Calculating distributions and percentiles...")
    
    # Basic stats (count, mean, std, min, 25%, 50% (median), 75%, max)
    # The .T transposes it so the metrics are rows instead of columns
    stats = df.describe().T 
    
    # Add high-end percentiles (90th, 95th, 99th, 99.9th) to find the extreme outliers
    percentiles = df.quantile([0.90, 0.95, 0.99, 0.999]).T
    percentiles.columns = ['90%', '95%', '99%', '99.9%']
    
    # Merge the standard stats and custom percentiles together
    full_stats = pd.concat([stats, percentiles], axis=1)
    
    # Reorder the columns so it reads cleanly from left to right
    ordered_columns = [
        'count', 'mean', 'std', 'min', 
        '25%', '50%', '75%', 
        '90%', '95%', '99%', '99.9%', 
        'max'
    ]
    full_stats = full_stats[ordered_columns]
    
    # Rename for readability
    full_stats.rename(columns={'50%': 'median', 'mean': 'average'}, inplace=True)
    
    # Round the results to 3 decimal places
    full_stats = full_stats.round(3)
    
    # 5. Output the results
    print("\n" + "="*50)
    print("RISK EXPOSURE STATISTICS (HEALTHY BASELINE)")
    print("="*50)
    
    # Force pandas to print all columns and rows without truncating them
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    print(full_stats)
    
    # Save to a CSV so you don't have to deal with copy/paste formatting
    output_file = 'comprehensive_risk_stats.csv'
    full_stats.to_csv(output_file)
    print(f"\n[+] Saved full statistics spreadsheet to: {output_file}")

except Exception as e:
    print(f"An error occurred: {e}")