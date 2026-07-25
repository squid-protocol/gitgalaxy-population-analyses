import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from sklearn.metrics import classification_report, confusion_matrix
import warnings
import numpy as np
warnings.filterwarnings('ignore')

SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "data" / "gitgalaxy_master.db"

CLASS_NAMES = {
    0: "0: Safe Code",
    1: "1: Botnet / DDoS",
    2: "2: Stealer / Trojan",
    3: "3: Dropper / Webshell",
    4: "4: Native Infector"
}

def analyze_global_inference():
    print(f"📡 Connecting to Database: {DB_PATH.name}...")
    conn = sqlite3.connect(DB_PATH)
    
    print("📥 Pulling Multi-Class Global Inference Data...")
    query = """
        SELECT 
            c.repo_name, 
            c.file_path, 
            c.threat_class AS actual_label, 
            a.ai_confidence, 
            a.threat_class AS predicted_label
        FROM galactic_census c
        JOIN ai_predictions a ON c.id = a.file_id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"\n📦 Data Loaded: {len(df):,} total files analyzed.")

    print("\n" + "="*60)
    print(" 🎯 MULTI-CLASS GLOBAL EVALUATION")
    print("="*60)
    
    # 1. Comprehensive Classification Report
    print("\n📈 Standard Classification Report:")
    print(classification_report(df['actual_label'], df['predicted_label'], 
                                target_names=list(CLASS_NAMES.values()), zero_division=0))

    # 2. Cross-Tab Confusion Matrix (Better for Terminal viewing)
    print("\n🧮 Multi-Class Confusion Matrix (Rows = Actual, Columns = Predicted):")
    cm_df = pd.crosstab(df['actual_label'], df['predicted_label'], 
                        rownames=['Actual'], colnames=['Predicted'])
    
    # Rename axes for readability
    cm_df.index = [CLASS_NAMES.get(i, f"Class {i}") for i in cm_df.index]
    cm_df.columns = [CLASS_NAMES.get(i, f"Class {i}") for i in cm_df.columns]
    print(cm_df.to_string())

    # 3. Anomaly Hunting (The Zero-Day Suspects)
    false_positives = df[(df['actual_label'] == 0) & (df['predicted_label'] > 0)]
    if not false_positives.empty:
        print("\n🔍 TOP 10 ZERO-DAY SUSPECTS (Highest Confidence 'Threats' that were labeled Safe):")
        top_fps = false_positives.sort_values(by='ai_confidence', ascending=False).head(10)
        for _, row in top_fps.iterrows():
            pred_name = CLASS_NAMES.get(row['predicted_label'], "Unknown")
            print(f"   - [{row['ai_confidence']:>5.2f}% as {pred_name:<20}] {row['repo_name']}/{row['file_path']}")

    # =========================================================
    # PER-CLASS PROBABILITY DISTRIBUTION METRICS
    # =========================================================
    print("\n" + "="*60)
    print(" 📊 PER-CLASS PROBABILITY DISTRIBUTIONS")
    print("="*60)
    
    for cls_idx, cls_name in CLASS_NAMES.items():
        cls_data = df[df['actual_label'] == cls_idx]['ai_confidence']
        
        if len(cls_data) == 0:
            continue
            
        print(f"\n[ {cls_name.upper()} ] - {len(cls_data):,} files")
        print(f"  Mean Confidence  : {cls_data.mean():.2f}%")
        print(f"  Median Confidence: {cls_data.median():.2f}%")
        
        if cls_idx == 0:
            print(f"  95th Percentile  : {cls_data.quantile(0.95):.2f}% (95% of safe files score below this confidence)")
            print(f"  99th Percentile  : {cls_data.quantile(0.99):.2f}% (99% of safe files score below this confidence)")
        else:
            print(f"  5th Percentile   : {cls_data.quantile(0.05):.2f}% (Only 5% of this malware scores below this confidence)")
            print(f"  1st Percentile   : {cls_data.quantile(0.01):.2f}% (Only 1% of this malware scores below this confidence)")

    # =========================================================
    # VISUALIZATIONS
    # =========================================================
    print("\n🎨 Rendering Visualizations...")
    
    # Sample down safe code so it doesn't crush Matplotlib
    safe_sample = df[df['actual_label'] == 0].sample(n=min(50000, len(df[df['actual_label'] == 0])), random_state=42)
    malware_full = df[df['actual_label'] > 0]
    plot_df = pd.concat([safe_sample, malware_full])
    
    # Map friendly names for plotting
    plot_df['Class_Name'] = plot_df['actual_label'].map(CLASS_NAMES)

    # --- Chart 1: The Confidence Violin Plot ---
    plt.figure(figsize=(14, 8))
    sns.violinplot(
        data=plot_df, 
        x='actual_label', 
        y='ai_confidence', 
        palette="coolwarm", 
        inner="quartile"
    )
    plt.title('AI Confidence Distribution by Structural Taxonomy', fontsize=16, fontweight='bold')
    plt.xlabel('Actual Structural Class', fontsize=12)
    plt.ylabel('AI Output Confidence (%)', fontsize=12)
    plt.xticks(ticks=range(5), labels=[CLASS_NAMES[i] for i in range(5)], rotation=15)
    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    
    violin_path = SCRIPT_DIR / "analysis_outputs" / "ai_distribution_violin.png"
    plt.savefig(violin_path, dpi=300)
    print(f"✅ Distribution Violin Plot saved to : {violin_path.name}")

    # --- Chart 2: The Multi-Class Confusion Heatmap ---
    plt.figure(figsize=(10, 8))
    
    # THE FIX: Force the 5x5 labels array so the heatmap never crashes on missing classes
    cm = confusion_matrix(df['actual_label'], df['predicted_label'], labels=[0, 1, 2, 3, 4])
    
    # Convert to percentages (normalized by row/Actual class) for a fairer visual representation
    cm_normalized = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
    cm_normalized = np.nan_to_num(cm_normalized) * 100

    sns.heatmap(
        cm_normalized, 
        annot=True, 
        fmt=".1f", 
        cmap="Blues",
        xticklabels=[f"Class {i}" for i in range(5)],
        yticklabels=[CLASS_NAMES[i] for i in range(5)]
    )
    plt.title('Multi-Class Confusion Matrix (% Accuracy per Class)', fontsize=14, fontweight='bold')
    plt.xlabel('PREDICTED by AI', fontsize=12)
    plt.ylabel('ACTUAL Class', fontsize=12)
    plt.tight_layout()
    
    heatmap_path = SCRIPT_DIR / "analysis_outputs" / "ai_confusion_heatmap.png"
    plt.savefig(heatmap_path, dpi=300)
    print(f"✅ Confusion Heatmap saved to        : {heatmap_path.name}\n")

if __name__ == "__main__":
    analyze_global_inference()