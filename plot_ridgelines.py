import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import warnings

# Silence the 0-variance math warnings
warnings.filterwarnings('ignore', module='seaborn')

# 1. Setup Paths & Directories
SCRIPT_DIR = Path(__file__).parent.resolve()

# Pointing directly to the DB in the same directory as the script
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
OUTPUT_DIR = SCRIPT_DIR / "analyses_ridgeplots"

OUTPUT_DIR.mkdir(exist_ok=True)

# --- LANGUAGE METRICS (Grouped by Language) ---
METRICS_TO_PLOT = {
    # --- CORE RISKS (0-100%) ---
    "risk_cognitive_load_exposure": "Cognitive Load Exposure",
    "risk_error_and_exception_exposure": "Error & Exception Exposure",
    "risk_tech_debt_exposure": "Tech Debt Exposure",
    "risk_testing_exposure": "Testing/Verification Exposure",
    "risk_api_exposure": "API Surface Exposure",
    "risk_concurrency_exposure": "Concurrency Risk Exposure",
    "risk_state_flux_exposure": "State Flux Exposure",
    "risk_graveyard_exposure": "Dead Code / Graveyard Exposure",
    "risk_specification_exposure": "Specification / Doc Match Exposure",
    "risk_instability_exposure": "File Instability Exposure",
    "risk_volatility_exposure": "Deep Churn Exposure",
    "risk_documentation_exposure": "Documentation Debt Exposure",
    "risk_civil_war_exposure": "Layout Unity / Civil War",
    
    # --- SECURITY LENS (0-100%) ---
    "risk_obfuscation_and_evasion_surface": "Obscured Payload Risk",
    "risk_exploit_generation_surface": "Logic Bomb Exposure",
    "risk_weaponizable_injection_vectors": "Injection Surface Exposure",
    "risk_raw_memory_manipulation": "Memory Corruption Risk",
    "risk_hardcoded_payload_artifacts": "Hardcoded Secrets Exposure",
    
    # --- ADVANCED ARCHITECTURAL METRICS ---
    "silo_risk": "Author Silo Risk (Bus Factor)",
    "ownership_entropy": "Ownership Entropy (Collaboration)",
    "structural_mass": "Structural Mass (Gravitational Pull)",
    "max_func_complexity": "Max Function Complexity (God Functions)",
    "avg_func_args": "Average Arguments per Function",
    "control_flow_ratio": "Control Flow Ratio",
    "import_count": "Outbound Dependencies",
    "hit_control_flow_branches": "Branching Logic Density",
    "hit_i_o_and_network_boundaries": "I/O Operation Density",
    
    # ---> NEW: LOGIC DENSITY <---
    "logic_density": "Logic Density (Signals per LOC)"
}

# --- ARCHETYPE METRICS (Grouped by Archetype) ---
ARCHETYPE_METRICS = {
    "global_drift": "Archetype Drift (Z-Score Euclidean Distance)"
}

if not DB_PATH.exists():
    print(f"❌ Error: Master Database not found at {DB_PATH}")
    exit(1)

print(f"Connecting to Galactic Census Database at: {DB_PATH}...")

# 2. Pull ALL data into RAM directly from SQLite
query = """
    SELECT * FROM galactic_census 
    WHERE language NOT IN ('markdown', 'csv', 'xml', 'yaml', 'json', 'unknown')
    AND (coding_loc > 0 OR language = 'plaintext')
"""
conn = sqlite3.connect(DB_PATH)
df = pd.read_sql_query(query, conn)
conn.close()

if df.empty:
    print("❌ No valid data returned from the database.")
    exit(1)

# --- PREP DATA FOR LANGUAGE PLOTS ---
lang_counts = df['language'].value_counts()
valid_languages = lang_counts[lang_counts >= 180].index
df_lang = df[df['language'].isin(valid_languages)].copy()
df_lang['language'] = df_lang['language'].apply(lambda l: f"{l} ({lang_counts[l]:,} files)")

# --- PREP DATA FOR ARCHETYPE PLOTS ---
if 'archetype' in df.columns:
    arch_counts = df['archetype'].value_counts()
    # Filter out unknown or extremely small clusters
    valid_archetypes = arch_counts[(arch_counts >= 180) & (arch_counts.index != "Unknown Archetype")].index
    df_arch = df[df['archetype'].isin(valid_archetypes)].copy()
    df_arch['archetype'] = df_arch['archetype'].apply(lambda a: f"{a.split(':')[0]} ({arch_counts[a]:,} files)")
else:
    df_arch = pd.DataFrame()

# 3. Setup Seaborn Visuals
sns.set_theme(style="white", rc={
    "axes.facecolor": (0, 0, 0, 0),
    "figure.facecolor": "#020617",
    "axes.grid": False,
    "text.color": "#f8fafc",
    "xtick.color": "#94a3b8",
})

def label_ridge(x, color, label):
    ax = plt.gca()
    ax.text(-0.02, 0.2, label, fontweight="bold", color=color, 
            ha="right", va="center", transform=ax.transAxes, fontsize=14.5)

# ==============================================================================
# GENERATOR 1: LANGUAGE-BASED RIDGEPLOTS
# ==============================================================================
print(f"Loaded {len(df):,} files. Generating Language Ridgeplots...")

for column, title in METRICS_TO_PLOT.items():
    print(f" -> Rendering Language Plot: {title}...")
    
    if column not in df_lang.columns or df_lang[column].var() == 0:
        print(f"    ⚠️ Skipping '{title}' (Missing or zero variance)")
        continue
    
    metric_means = df_lang.groupby('language')[column].mean().sort_values(ascending=False)
    dynamic_lang_order = metric_means.index
    
    if column == "control_flow_ratio":
        upper_bound = 1.0
        hard_stops = (0.0, 1.0)
    elif column.startswith("risk_") or column in ["silo_risk", "ownership_entropy"]:
        upper_bound = 100
        hard_stops = (0, 100) 
    else:
        # Code metrics follow extreme power laws. Clip at 95th percentile + 5% pad.
        p95 = df_lang[column].quantile(0.95)
        upper_bound = max(p95 * 1.05, 1.0)
        hard_stops = (0, upper_bound)
        
    pal = sns.color_palette("turbo", len(dynamic_lang_order))
    g = sns.FacetGrid(df_lang, row="language", hue="language", aspect=12, height=0.8, 
                      palette=pal, row_order=dynamic_lang_order, sharey=False)

    g.map(sns.kdeplot, column, bw_adjust=0.5, clip_on=False, fill=True, alpha=0.5, linewidth=1.5, warn_singular=False, clip=hard_stops)
    g.map(sns.kdeplot, column, clip_on=False, color="white", lw=1.5, bw_adjust=0.5, warn_singular=False, clip=hard_stops)
    g.map(plt.axhline, y=0, lw=1.5, color="white", clip_on=False)
    g.map(label_ridge, column)

    g.set(xlim=(0, upper_bound))
    g.figure.subplots_adjust(hspace=-0.4)
    g.set_titles("")
    g.set(yticks=[], ylabel="")
    g.despine(bottom=True, left=True)
    
    g.fig.suptitle(f"{title} Distribution by Language", fontsize=22, fontweight='bold', color="#38bdf8", y=0.98)
    plt.xlabel("Score / Density", fontsize=14, fontweight='bold', color="#94a3b8", labelpad=15)
    
    output_path = OUTPUT_DIR / f"{column}_lang_ridgeplot.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

# ==============================================================================
# GENERATOR 2: ARCHETYPE-BASED RIDGEPLOTS
# ==============================================================================
if not df_arch.empty:
    print(f"\nGenerating Archetype Ridgeplots...")
    
    for column, title in ARCHETYPE_METRICS.items():
        print(f" -> Rendering Archetype Plot: {title}...")
        
        if column not in df_arch.columns or df_arch[column].var() == 0:
            print(f"    ⚠️ Skipping '{title}' (Missing or zero variance)")
            continue
        
        # Sort by lowest average drift (tightest clusters at the top)
        metric_means = df_arch.groupby('archetype')[column].mean().sort_values(ascending=True)
        dynamic_arch_order = metric_means.index
        
        # Power-law clamp for Euclidean Distance (Z-Scores)
        p95 = df_arch[column].quantile(0.95)
        upper_bound = max(p95 * 1.05, 1.0)
        hard_stops = (0, upper_bound)
            
        pal = sns.color_palette("coolwarm", len(dynamic_arch_order))
        g = sns.FacetGrid(df_arch, row="archetype", hue="archetype", aspect=12, height=0.8, 
                          palette=pal, row_order=dynamic_arch_order, sharey=False)

        g.map(sns.kdeplot, column, bw_adjust=0.5, clip_on=False, fill=True, alpha=0.5, linewidth=1.5, warn_singular=False, clip=hard_stops)
        g.map(sns.kdeplot, column, clip_on=False, color="white", lw=1.5, bw_adjust=0.5, warn_singular=False, clip=hard_stops)
        g.map(plt.axhline, y=0, lw=1.5, color="white", clip_on=False)
        g.map(label_ridge, column)

        g.set(xlim=(0, upper_bound))
        g.figure.subplots_adjust(hspace=-0.4)
        g.set_titles("")
        g.set(yticks=[], ylabel="")
        g.despine(bottom=True, left=True)
        
        g.fig.suptitle(f"{title} by Archetype", fontsize=22, fontweight='bold', color="#f43f5e", y=0.98)
        plt.xlabel("Drift Distance (IQR)", fontsize=14, fontweight='bold', color="#94a3b8", labelpad=15)
        
        output_path = OUTPUT_DIR / f"{column}_arch_ridgeplot.png"
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()

print(f"\n✅ All Ridgeplots successfully saved to: {OUTPUT_DIR}")