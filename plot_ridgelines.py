import argparse
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
DEFAULT_DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
OUTPUT_DIR = SCRIPT_DIR / "analyses_ridgeplots"
OUTPUT_DIR.mkdir(exist_ok=True)

# Rewritten against the current engine schema (file_data) instead of the legacy
# `galactic_census` table, which no longer exists for any post-#325 database. See
# detailed_risk_exposure_stats_from_db.py's header comment for the full old->new risk-column
# mapping, and squid-protocol/gitgalaxy#1144 for how the gap was found.
#
# The ARCHETYPE-based ridgeplot generator (the old script's second half, keyed on `archetype`/
# `global_drift`) is dropped entirely here, not just remapped: those are KMeans-cluster-derived
# fields that only existed because galactic_census was built by re-running master_db_updater.py's
# ML enrichment pipeline against an older ~150-column schema. Re-running that pipeline against
# today's schema is real, separate work (the models would need retraining/re-validating against
# the current feature set, not just a column rename) -- out of scope for this rewrite.
METRICS_TO_PLOT = {
    # --- CORE RISKS (0-100%), from RISK_SCHEMA in analysis_lens.py ---
    "risk_cognitive_load": "Cognitive Load Exposure",
    "risk_safety_score": "Error & Exception / Safety Exposure",
    "risk_tech_debt": "Tech Debt Exposure",
    "risk_verification": "Testing/Verification Exposure",
    "risk_api_exposure": "API Surface Exposure",
    "risk_concurrency": "Concurrency Risk Exposure",
    "risk_state_flux": "State Flux Exposure",
    "risk_dead_code": "Dead Code / Graveyard Exposure",
    "risk_spec_match": "Specification / Doc Match Exposure",
    "risk_stability": "File Instability Exposure",
    "risk_churn": "Deep Churn Exposure",
    "risk_documentation": "Documentation Debt Exposure",
    "risk_tabs_vs_spaces": "Layout Unity / Civil War",
    "risk_secrets_risk": "Hardcoded Secrets Exposure",

    # --- ADVANCED ARCHITECTURAL METRICS ---
    "silo_risk": "Author Silo Risk (Bus Factor)",
    "ownership_entropy": "Ownership Entropy (Collaboration)",
    "structural_mass": "Structural Mass (Gravitational Pull)",
    "max_func_complexity": "Max Function Complexity (God Functions)",
    "avg_func_args": "Average Arguments per Function",
    "control_flow_ratio": "Control Flow Ratio",
    "import_count": "Outbound Dependencies",
    "struct_branch": "Branching Logic Density",
    "arch_io": "I/O Operation Density",
}

def main(db_path: Path):
    if not db_path.exists():
        print(f"❌ Error: Master Database not found at {db_path}")
        return

    print(f"Connecting to Master Database at: {db_path}...")

    # 2. Pull ALL data into RAM directly from SQLite
    query = """
        SELECT * FROM file_data
        WHERE language NOT IN ('markdown', 'csv', 'xml', 'yaml', 'json', 'unknown')
        AND (coding_loc > 0 OR language = 'plaintext')
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(query, conn)
    conn.close()

    if df.empty:
        print("❌ No valid data returned from the database.")
        return

    # --- PREP DATA FOR LANGUAGE PLOTS ---
    lang_counts = df['language'].value_counts()
    valid_languages = lang_counts[lang_counts >= 180].index
    df_lang = df[df['language'].isin(valid_languages)].copy()
    df_lang['language'] = df_lang['language'].apply(lambda l: f"{l} ({lang_counts[l]:,} files)")

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
    # LANGUAGE-BASED RIDGEPLOTS
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

    print(f"\n✅ All Ridgeplots successfully saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GitGalaxy Ridgeplot Generator (per-language distributions)")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH,
                         help=f"Path to the master SQLite DB. Default: {DEFAULT_DB_PATH}")
    args = parser.parse_args()
    main(args.db)
