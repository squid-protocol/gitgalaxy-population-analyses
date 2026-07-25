import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import re
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db" 
OUTPUT_DIR = SCRIPT_DIR / "archetype_scatters_by_lang"

# The languages we want to specifically isolate
TARGET_LANGUAGES = ['Python', 'Typescript', 'Javascript']

# Create the output directory if it doesn't exist
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def slugify(text):
    text = text.lower().replace(" & ", " and ")
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def run_scatter_generation():
    print(f"📡 Connecting to database: {DB_PATH}...")
    conn = sqlite3.connect(str(DB_PATH))
    
    df = pd.read_sql_query("SELECT * FROM galactic_census WHERE coding_loc > 0", conn)
    conn.close()

    # Fill missing values with 0.0 to prevent Pandas from accidentally dropping valid files
    risk_cols = [c for c in df.columns if c.startswith('risk_') and c != 'risk_civil_war']
    df[risk_cols] = df[risk_cols].fillna(0.0)
    df['archetype'] = df['archetype'].fillna("Unknown")
    
    # Grab the top 16 most populated archetypes globally to ensure consistency
    top_archetypes = df['archetype'].value_counts().head(16).index.tolist()
    archetypes = sorted([a for a in top_archetypes if "Cluster" in a])

    print(f"\n🎨 Generating Language-Specific Hexbin Plots in: {OUTPUT_DIR.name}")
    
    # --- LOOP 1: Iterate through our target languages ---
    for lang in TARGET_LANGUAGES:
        print("\n" + "=" * 85)
        print(f"🌍 ISOLATING ECOSYSTEM: {lang.upper()}")
        print("=" * 85)
        
        # Filter the DataFrame to ONLY include this language
        df_lang = df[df['language'].str.lower() == lang.lower()].copy()
        
        if len(df_lang) == 0:
            print(f"⚠️ No files found for {lang}. Skipping...")
            continue
            
        # --- LOOP 2: Iterate through the archetypes for this language ---
        for arch in archetypes:
            # We revert back to your original, clean naming convention
            prefix = arch.split(':')[0]
            safe_name = slugify(prefix)
            col_name = "arch_" + safe_name  # e.g., "arch_cluster_15"
            
            if col_name not in df_lang.columns: 
                print(f"  - ⚠️ Skipped {prefix:<15} (Column '{col_name}' not found in DB)")
                continue
                
            # Grab only the files of this language that belong to this cluster
            subset = df_lang[df_lang['archetype'] == arch].dropna(subset=[col_name])
            
            # We need a minimum number of files to run a reliable regression model
            if len(subset) < 10: 
                print(f"  - ⏭️ Skipped {prefix:<15} (Only {len(subset)} {lang} files found, need 10+)")
                continue
                
            X = subset[risk_cols].values
            y_actual = subset[col_name].values
            
            if np.std(y_actual) == 0: 
                print(f"  - ⏭️ Skipped {prefix:<15} (No mathematical variance in drift)")
                continue

            # Train the Toxic Cocktail Model
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            model = LinearRegression()
            model.fit(X_scaled, y_actual)
            
            # Calculate what the math PREDICTS the drift should be based on the cocktail
            y_pred = model.predict(X_scaled)
            
            r2 = model.score(X_scaled, y_actual)
            multiple_r = np.sqrt(max(0, r2))
            
            # Determine the top 3 ingredients for the chart subtitle
            coeffs = list(zip(risk_cols, model.coef_))
            coeffs.sort(key=lambda item: abs(item[1]), reverse=True)
            top_factors = []
            for i in range(min(3, len(coeffs))):
                name = coeffs[i][0].replace('risk_', '').replace('_exposure', '').replace('_', ' ').title()
                weight = coeffs[i][1]
                sign = "+" if weight > 0 else "-"
                top_factors.append(f"{sign}{abs(weight):.2f} {name}")
            subtitle = "Primary Drivers: " + " | ".join(top_factors)

            # --- PLOTTING ---
            plt.figure(figsize=(10, 8))
            
            # Hexbin plot creates a heatmap of density
            hb = plt.hexbin(y_pred, y_actual, gridsize=50, cmap='magma', mincnt=1, bins='log')
            cb = plt.colorbar(hb, label='log10(File Count)')
            
            # Perfect Prediction Line (y=x)
            min_val = min(y_pred.min(), y_actual.min())
            max_val = max(y_pred.max(), y_actual.max())
            plt.plot([min_val, max_val], [min_val, max_val], color='cyan', linestyle='--', linewidth=2, label='Perfect Prediction (y=x)')
            
            # Add a real trendline
            m, b = np.polyfit(y_pred, y_actual, 1)
            plt.plot(y_pred, m*y_pred + b, color='lime', linewidth=1.5, label='Actual Trend')

            # Inject the Language name into the Title
            plt.title(f"{lang} | {prefix} Drift Model (R={multiple_r:.2f})\n", fontsize=16, fontweight='bold')
            plt.suptitle(subtitle, fontsize=10, color='gray', y=0.91)
            
            plt.xlabel("Predicted Drift (Toxic Cocktail Math)", fontsize=12)
            plt.ylabel("Actual Architectural Drift (Euclidean Distance)", fontsize=12)
            plt.legend(loc='upper left')
            plt.grid(alpha=0.2)
            
            # Save output with language prefix
            output_file = OUTPUT_DIR / f"{lang.lower()}_{safe_name}_drift_model.png"
            plt.savefig(output_file, bbox_inches='tight', dpi=150)
            plt.close()
            
            print(f"  - ✅ Saved: {output_file.name} (R={multiple_r:.2f})")

    print("-" * 85)
    print("🚀 All plots successfully generated!")

if __name__ == "__main__":
    run_scatter_generation()