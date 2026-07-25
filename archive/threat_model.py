import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import xgboost as xgb
import warnings
warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "gitgalaxy_master.db"
MODEL_OUT_PATH = SCRIPT_DIR / "gitgalaxy_malware_xgb.json"

def extract_goldilocks_dataset():
    print(f"📡 Connecting to Database at: {DB_PATH.name}...")
    conn = sqlite3.connect(DB_PATH)

    print(" 1/3 Extracting True Positives (Confirmed Malware)...")
    df_malware = pd.read_sql_query("SELECT * FROM galactic_census WHERE is_malware = 1", conn)

    print(" 2/3 Extracting Hard Negatives (Highly Suspicious but Safe)...")
    # Grabs Tier 1 False Positives to force the model to learn nuance
    df_hard_negatives = pd.read_sql_query("""
        SELECT * FROM galactic_census 
        WHERE is_malware = 0 
        AND (raw_danger > 0 OR raw_sec_tainted_injection > 0 OR raw_sec_private_info > 0)
        ORDER BY cog_raw DESC 
        LIMIT 1500
    """, conn)

    print(" 3/3 Extracting Baseline Noise (Standard Safe Code)...")
    df_random_safe = pd.read_sql_query("""
        SELECT * FROM galactic_census 
        WHERE is_malware = 0 
        AND raw_danger = 0 AND raw_sec_tainted_injection = 0 
        ORDER BY RANDOM() 
        LIMIT 8500
    """, conn)

    conn.close()

    # Stack the sandwich together
    master_df = pd.concat([df_malware, df_hard_negatives, df_random_safe], ignore_index=True)
    
    # Shuffle the dataset
    master_df = master_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"📦 Total Dataset Assembled: {len(master_df):,} rows.")
    return master_df

def prepare_features(df):
    print("🧹 Cleaning data and preparing feature matrix...")
    
    # Target variable
    y = df['is_malware']
    
    # Identify non-numeric string columns to drop (IDs, names, dates, text)
    cols_to_drop = [
        'id', 'repo_name', 'commit_date', 'file_name', 'file_path', 
        'constellation', 'archetype', 'logic_loc_bin', 'import_list', 
        'author', 'purpose', 'is_malware', 'confirmed_kill_chain'
    ]
    
    # Drop columns if they exist in the dataframe
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns])
    
    # Fill any null numeric values with 0
    X = X.fillna(0)

    # One-Hot Encode the 'language' column
    print("🔠 Encoding Language variable...")
    X = pd.get_dummies(X, columns=['language'], dummy_na=False)

    return X, y

def train_and_evaluate():
    # 1. Get Data
    df = extract_goldilocks_dataset()
    
    # 2. Prepare Features
    X, y = prepare_features(df)
    
    # 3. Train/Test Split (80% Train, 20% Test)
    print("✂️ Splitting data into 80% Train / 20% Test...")
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # Calculate class imbalance ratio to tell XGBoost to pay extra attention to Malware
    scale_weight = len(y_train[y_train == 0]) / len(y_train[y_train == 1])

    # 4. Initialize and Train XGBoost
    print("🧠 Igniting XGBoost Training Sequence...")
    model = xgb.XGBClassifier(
        n_estimators=300,        # Number of trees
        max_depth=6,             # Maximum depth of a tree
        learning_rate=0.1,       # Step size shrinkage
        scale_pos_weight=scale_weight, # Handle the 1:8 imbalance
        eval_metric='logloss',
        random_state=42,
        n_jobs=-1                # Use all CPU cores
    )
    
    model.fit(X_train, y_train)
    
    # 5. Evaluate
    print("\n" + "="*50)
    print(" 🎯 MODEL EVALUATION (Test Set Performance)")
    print("="*50)
    
    y_pred = model.predict(X_test)
    
    print("\n📊 Confusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"True Negatives (Safe guessed Safe)     : {cm[0][0]}")
    print(f"False Positives (Safe guessed Malware) : {cm[0][1]}  <-- Annoying but okay")
    print(f"False Negatives (Malware guessed Safe) : {cm[1][0]}  <-- DANGEROUS MISS")
    print(f"True Positives (Malware guessed Malware): {cm[1][1]}")
    
    print("\n📈 Classification Report:")
    print(classification_report(y_test, y_pred, target_names=["Safe (0)", "Malware (1)"]))

    # 6. Feature Importance (What did the AI actually care about?)
    importances = pd.DataFrame({
        'Feature': X.columns,
        'Importance': model.feature_importances_
    }).sort_values(by='Importance', ascending=False)

    print("\n🧬 Top 15 Architectural DNA Signatures (Most Predictive Features):")
    for index, row in importances.head(15).iterrows():
        print(f"   - {row['Feature']:<35}: {row['Importance']:.4f}")

    # 7. Save the Model
    model.save_model(MODEL_OUT_PATH)
    print(f"\n💾 Model successfully saved to {MODEL_OUT_PATH.name}")

if __name__ == "__main__":
    train_and_evaluate()