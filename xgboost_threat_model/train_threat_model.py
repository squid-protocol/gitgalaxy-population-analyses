import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split, RandomizedSearchCV, StratifiedKFold
from sklearn.metrics import classification_report
import xgboost as xgb
import warnings
warnings.filterwarnings('ignore')

# --- HELPER FUNCTIONS FOR FUNCTION GEOMETRY ---
def calculate_gini(array):
    if not array: return 0.0
    array = np.array(array, dtype=np.float64)
    if np.sum(array) == 0: return 0.0
    array = np.sort(array)
    index = np.arange(1, array.shape[0] + 1)
    n = array.shape[0]
    return ((np.sum((2 * index - n  - 1) * array)) / (n * np.sum(array)))

def parse_concat_vector(val):
    if not val or pd.isna(val): return []
    try: return [float(x) for x in str(val).split(',')]
    except Exception: return []

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR.parent / "data" / "gitgalaxy_master.db"
MODEL_OUT_PATH = SCRIPT_DIR / "gitgalaxy_malware_xgb_multiclass.json"

def extract_goldilocks_dataset():
    print(f"📡 Connecting to Database at: {DB_PATH.name}...")
    conn = sqlite3.connect(DB_PATH)

    print(" 1/2 Extracting Taxonomical Threats (Classes 1-4)...")
    # Grab all malware, joined with their internal function metrics
    df_malware = pd.read_sql_query("""
        SELECT c.*, 
               COUNT(f.id) as real_function_count,
               AVG(f.loc) as real_avg_func_loc,
               AVG(f.complexity) as real_avg_func_complexity,
               GROUP_CONCAT(f.complexity) as func_complexity_vector
        FROM galactic_census c
        LEFT JOIN galactic_functions f ON c.id = f.file_id
        WHERE c.threat_class > 0
        GROUP BY c.id
    """, conn)

    print(" 2/2 Extracting Downsampled Safe Code (Max 8,000 files per language)...")
    # Grab safe files using a CTE to safely randomize and limit before the heavy join
    df_safe = pd.read_sql_query("""
        WITH SafeSample AS (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER(PARTITION BY language ORDER BY RANDOM()) as rn
                FROM galactic_census 
                WHERE threat_class = 0
            ) WHERE rn <= 8000
        )
        SELECT c.*, 
               COUNT(f.id) as real_function_count,
               AVG(f.loc) as real_avg_func_loc,
               AVG(f.complexity) as real_avg_func_complexity,
               GROUP_CONCAT(f.complexity) as func_complexity_vector
        FROM galactic_census c
        INNER JOIN SafeSample s ON c.id = s.id
        LEFT JOIN galactic_functions f ON c.id = f.file_id
        GROUP BY c.id
    """, conn)
    
    conn.close()

    # Stack the sandwich together
    master_df = pd.concat([df_malware, df_safe], ignore_index=True)
    
    # Shuffle the dataset
    master_df = master_df.sample(frac=1, random_state=42).reset_index(drop=True)
    
    print(f"📦 Total Balanced Dataset Assembled: {len(master_df):,} rows.")
    return master_df

def prepare_features(df):
    print("🧹 Cleaning data and applying The Context-Aware Blindfold...")
    
    # Target variable is now MULTI-CLASS (0 = Safe, 1-4 = Specific Threats)
    y = df['threat_class']
    
    print("⚙️ Engineering advanced function geometries and DNA densities...")
    # 1. Null Safety for the new joined columns
    null_cols = ['logic_loc', 'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count', 'direct_upstream', 'total_downstream']
    for c in null_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0.0)

    # 2. Function Geometry
    df['parsed_vector'] = df['func_complexity_vector'].apply(parse_concat_vector)
    df['complexity_gini'] = df.apply(lambda row: calculate_gini(row['parsed_vector']) if row['real_function_count'] > 1 else 0.0, axis=1)
    df['func_internal_density'] = df['real_avg_func_complexity'] / df['real_avg_func_loc'].replace(0, 1)
    df['func_density'] = df['real_function_count'] / (df['logic_loc'].replace(0, 1) / 100.0)

    # 3. Log Topological Exposure (The Blast Radius)
    df['log_direct_upstream'] = np.log1p(df['direct_upstream'])
    df['log_total_downstream'] = np.log1p(df['total_downstream'])

    # 4. Core DNA Densities (Trees prefer ratios over raw counts)
    # Grab all raw count columns
    raw_count_cols = [c for c in df.columns if c.startswith('core_') or c.startswith('risk_') or c.startswith('design_') or c.startswith('threat_')]
    raw_count_cols = [c for c in raw_count_cols if c != 'threat_class'] # Exclude target
    
    safe_denom = df['logic_loc'].replace(0, np.nan).fillna(df['coding_loc']).replace(0, 1)    
    for col in raw_count_cols:
        df[f"density_{col}"] = (df[col] / safe_denom) * 100.0
        
    df = df.drop(columns=['parsed_vector', 'func_complexity_vector'])
    
    # 5. SURGICAL PRUNING: Drop all noise, raw counts, spatial coords, and leaks
    cols_to_drop = [
        'id', 'repo_name', 'commit_date', 'file_name', 'file_path', 
        'constellation', 'archetype', 'logic_loc_bin', 'import_list', 
        'author', 'is_malware', 'threat_class', 'confirmed_kill_chain',
        'raw_churn_freq', 'popularity', 'ai_threat_confidence', 'language',
        'purpose', 'pos_x', 'pos_y', 'pos_z', 'parsed_vector', 'func_complexity_vector',
        'total_loc', 'coding_loc', 'comment_loc', 'logic_loc', 'structural_mass',
        'cog_raw', 'ownership_entropy', 'silo_risk', 'function_count', 
        'avg_func_loc', 'avg_func_complexity', 'max_func_complexity', 'avg_func_args',
        'direct_upstream', 'direct_downstream', 'total_upstream', 'total_downstream',
        'direct_upstream_ratio', 'direct_downstream_ratio', 'total_upstream_ratio',
        'total_downstream_ratio', 'global_drift', 'local_drift', 'logic_density',
        'real_avg_func_loc', 'real_avg_func_complexity', 'real_function_count'
    ]
    
    # Dynamically drop any stale arch_cluster Euclidean distances left in the DB
    stale_clusters = [c for c in df.columns if c.startswith('arch_cluster_')] 
    cols_to_drop.extend(stale_clusters)
    
    cols_to_drop.extend(raw_count_cols)
    
    # Drop known columns
    X = df.drop(columns=[c for c in cols_to_drop if c in df.columns])

    if 'repo_z_score' in X.columns:
        X['repo_z_score'] = pd.to_numeric(X['repo_z_score'], errors='coerce')

    print("🔠 Encoding Context variables (Repository Macro-Species)...")
    cols_to_encode = []
    
    # Only encode the Repo Macro Species, drop the "purpose" feature to prevent explosion
    if 'repo_macro_species' in X.columns: cols_to_encode.append('repo_macro_species')
        
    if cols_to_encode:
        X = pd.get_dummies(X, columns=cols_to_encode, dummy_na=False)

    # THE IRON CURTAIN: Automatically detect and drop ANY remaining text strings
    object_cols = X.select_dtypes(include=['object']).columns
    if len(object_cols) > 0:
        print(f"⚠️ Dropping unexpected text string columns: {list(object_cols)}")
        X = X.drop(columns=object_cols)

    # Fill any null numeric values with 0
    X = X.fillna(0)

    # Sanitize any infinite math errors
    X = X.replace([np.inf, -np.inf], 0)

    return X, y

def train_and_evaluate():
    # 1. Get Data
    df = extract_goldilocks_dataset()
    
    # 2. Prepare Features
    X, y = prepare_features(df)
    
    # 3. Train/Test Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

    print("\n" + "="*50)
    print(" 🛠️  MULTI-CLASS TRAINING CONFIGURATION")
    print("="*50)
    print(f"Training Matrix : {X_train.shape[0]:,} rows x {X_train.shape[1]} highly-optimized features")
    
    # 4. Define the Grid Search Parameters
    print("\n🧠 Initiating Hyperparameter Grid Search...")
    
    param_grid = {
        'n_estimators': [200, 300, 500],
        'max_depth': [4, 6, 8],
        'learning_rate': [0.01, 0.05, 0.1, 0.2],
        'subsample': [0.8, 1.0],
        'colsample_bytree': [0.8, 1.0]
    }

    xgb_base = xgb.XGBClassifier(
        objective='multi:softmax',
        num_class=5,
        eval_metric='mlogloss',
        random_state=42,
        n_jobs=-1
    )

    cv_strategy = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

    random_search = RandomizedSearchCV(
        estimator=xgb_base,
        param_distributions=param_grid,
        n_iter=15, 
        scoring='f1_weighted',
        cv=cv_strategy,
        verbose=1,
        random_state=42,
        n_jobs=-1
    )
    
    print("⏳ Training context-aware decision trees...\n")
    random_search.fit(X_train, y_train)

    print("\n🏆 Grid Search Complete! Optimal Parameters Found:")
    for param, value in random_search.best_params_.items():
        print(f"   - {param}: {value}")

    model = random_search.best_estimator_
    
    # 5. Evaluate
    print("\n" + "="*50)
    print(" 🎯 MULTI-CLASS MODEL EVALUATION (Hidden Test Set)")
    print("="*50)
    
    y_pred = model.predict(X_test)
    
    print("\n📈 Classification Report:")
    target_names = [
        "0: Safe Code", 
        "1: Botnet / DDoS", 
        "2: Stealer / Trojan", 
        "3: Dropper / Webshell", 
        "4: Native Infector"
    ]
    print(classification_report(y_test, y_pred, target_names=target_names))

    # 6. Feature Importance
    importances = pd.DataFrame({
        'Feature': X.columns,
        'Importance': model.feature_importances_
    }).sort_values(by='Importance', ascending=False)

    print("\n🧬 TOP 20 ARCHITECTURAL DNA SIGNATURES:")
    for index, row in importances.head(20).iterrows():
        feat_name = row['Feature'].replace('hit_sec_', '[SEC] ').replace('hit_', '[DNA] ').replace('risk_', '[RISK] ').upper()
        print(f"   - {feat_name:<40}: {row['Importance']:.4f}")

    # 7. Save the Model
    model.save_model(MODEL_OUT_PATH)
    print(f"\n💾 Model successfully saved to {MODEL_OUT_PATH.name}\n")

if __name__ == "__main__":
    train_and_evaluate()