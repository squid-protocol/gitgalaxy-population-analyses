import pandas as pd
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import RobustScaler
import plotly.express as px
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
SCRIPT_DIR = Path(__file__).parent.resolve()
INPUT_CSV = SCRIPT_DIR / "kmeans_dna_micro_species.csv"
OUTPUT_HTML = SCRIPT_DIR / "galaxy_pca_3d_map.html"

def generate_3d_map():
    if not INPUT_CSV.exists():
        print(f"❌ Error: Clustering CSV not found at {INPUT_CSV}")
        print("Please run cluster_dna_micro_species.py first.")
        return

    print(f"📡 Loading clustered galaxy data from: {INPUT_CSV}...\n")
    df = pd.read_csv(INPUT_CSV)

    # 1. Feature Extraction (Synced with v6.3.0 Log Network Counts and Mitigated DNA)
    feature_cols = [
        c for c in df.columns 
        if c.startswith('log_density_') or c in [
            'control_flow_ratio', 'log_logic_loc', 
            'log_direct_upstream', 'log_direct_downstream',
            'log_total_upstream', 'log_total_downstream',
            'log_max_func_complexity', 'log_avg_func_args', 'log_churn'
        ]
    ]
    
    # Ensure we only use columns that actually exist in the CSV
    feature_cols = [f for f in feature_cols if f in df.columns]
    
    print(f"🧬 Extracting {len(feature_cols)} dimensions for PCA compression...")

    # Drop rows that are missing the cluster label or core features
    df = df.dropna(subset=feature_cols + ['Cluster_k10']).copy()
    
    X_raw = df[feature_cols]

    # 2. Robust Scaling (Must match the K-Means preprocessing)
    print("⚖️ Applying Robust Scaling...")
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(X_raw)

    # 3. Principal Component Analysis (3D Compression)
    print("🌌 Compressing 67D space into 3D using PCA...")
    pca = PCA(n_components=3)
    pca_features = pca.fit_transform(X_scaled)

    # Attach the 3D coordinates back to the dataframe
    df['PCA_X'] = pca_features[:, 0]
    df['PCA_Y'] = pca_features[:, 1]
    df['PCA_Z'] = pca_features[:, 2]

    # Format the cluster labels as strings so Plotly treats them as discrete categories (colors)
    df['Cluster_Label'] = 'Cluster ' + df['Cluster_k10'].astype(int).astype(str)

    # =========================================================================
    # ---> SPATIAL DOWNSAMPLING (Purest Archetypes Only) <---
    # =========================================================================
    print("✂️ Filtering dataset for the purest architectural representations...")
    MAX_POINTS_PER_CLUSTER = 2000  # 32,000 points total, perfect for WebGL
    
    sampled_dfs = []
    
    for cluster_id in sorted(df['Cluster_k10'].unique()):
        cluster_mask = df['Cluster_k10'] == cluster_id
        cluster_df = df[cluster_mask].copy()
        
        if len(cluster_df) > MAX_POINTS_PER_CLUSTER:
            # Grab the scaled 67D coordinates for just this cluster
            cluster_scaled = X_scaled[cluster_mask]
            
            # Calculate the exact mathematical center of this cluster
            centroid = np.mean(cluster_scaled, axis=0)
            
            # Measure the Euclidean distance of every file to the center
            distances = np.linalg.norm(cluster_scaled - centroid, axis=1)
            cluster_df['centroid_dist'] = distances
            
            # Sort by distance (closest to center = purest archetype) and slice the top N
            cluster_df = cluster_df.sort_values('centroid_dist').head(MAX_POINTS_PER_CLUSTER)
            
        sampled_dfs.append(cluster_df)

    # Recombine into a safe, highly distinct dataset
    plot_df = pd.concat(sampled_dfs, ignore_index=True)
    print(f"📉 Reduced from {len(df):,} to {len(plot_df):,} purest core files for rendering.")

    # Calculate variance explained to show in the UI axes
    variance = pca.explained_variance_ratio_ * 100

    # 4. Generate the Plotly 3D Scatter
    print("🎨 Rendering interactive WebGL UI...")
    fig = px.scatter_3d(
        plot_df, 
        x='PCA_X',
        y='PCA_Y',
        z='PCA_Z',
        color='Cluster_Label',
        hover_name='file_name',
        hover_data={
            'file_path': True,
            'language': True,
            'constellation': True,
            'logic_loc': True,
            'Cluster_Label': False, # Hide the redundant label
            'PCA_X': False,
            'PCA_Y': False,
            'PCA_Z': False
        },
        title='GitGalaxy 3D Architectural Map (v6.3.0 Mitigated PCA)',
        # Alphabet gives a distinct 24-color palette, perfect for k=16
        color_discrete_sequence=px.colors.qualitative.Alphabet 
    )
    
    # Optimize marker rendering for massive repositories
    fig.update_traces(
        marker=dict(
            size=3, 
            opacity=0.7,
            line=dict(width=0) # Remove borders to speed up WebGL rendering
        )
    )
    
    # Clean up the layout and inject the variance data into the axes labels
    fig.update_layout(
        scene=dict(
            xaxis_title=f'PCA 1 ({variance[0]:.1f}% Variance)',
            yaxis_title=f'PCA 2 ({variance[1]:.1f}% Variance)',
            zaxis_title=f'PCA 3 ({variance[2]:.1f}% Variance)',
            bgcolor='rgb(20, 24, 34)', # Deep space background
            xaxis=dict(showgrid=True, gridcolor='rgb(40, 44, 54)', zerolinecolor='rgb(80, 84, 94)'),
            yaxis=dict(showgrid=True, gridcolor='rgb(40, 44, 54)', zerolinecolor='rgb(80, 84, 94)'),
            zaxis=dict(showgrid=True, gridcolor='rgb(40, 44, 54)', zerolinecolor='rgb(80, 84, 94)')
        ),
        paper_bgcolor='rgb(20, 24, 34)',
        font=dict(color='white'),
        margin=dict(l=0, r=0, b=0, t=50),
        legend=dict(
            title="Archetypes",
            itemsizing='constant',
            x=1.05,
            y=0.5
        )
    )

    # 5. Export to HTML
    fig.write_html(str(OUTPUT_HTML))
    print(f"\n✅ 3D Map successfully generated: {OUTPUT_HTML}")
    print("Open this file in any web browser to explore your galaxy.")

if __name__ == "__main__":
    generate_3d_map()