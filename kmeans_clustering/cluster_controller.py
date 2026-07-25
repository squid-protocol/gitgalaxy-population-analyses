import multiprocessing
import argparse
from cluster_files import run_dna_clustering as cluster_file_engine
from cluster_functions import run_dna_clustering as cluster_func_engine
from cluster_repos import cluster_repositories

def auto_calibrate(target='files'):
    print("================================================================================")
    print(f" ⚙️ INITIATING CLUSTER CALIBRATION ({target.upper()})")
    print("================================================================================")
    print(" Objective: Find optimal K value by progressively increasing compute profiles.\n")

    # The full 5-Tier Escalation Ladder
    profiles = ['micro', 'low', 'standard', 'medium', 'high']
    previous_k = None
    previous_sil = 0.0
    total_compute_time = 0.0

    for prof in profiles:
        print(f"\n🚀 Launching {prof.upper()} profile...")
        
        # Route to the requested ML engine
        if target == 'files':
            best_k, max_sil, compute_time = cluster_file_engine(accuracy=prof)
        elif target == 'functions':
            best_k, max_sil, compute_time = cluster_func_engine(accuracy=prof)
        else:
            best_k, max_sil, compute_time = cluster_repositories(accuracy=prof)
            
        if best_k is None:
            print("❌ Calibration aborted due to engine failure.")
            return

        total_compute_time += compute_time

        if previous_k is not None:
            sil_change = abs(max_sil - previous_sil)
            
            print("\n" + "="*80)
            print(" 🧠 CONVERGENCE ANALYSIS")
            print("="*80)
            print(f"   - Previous K: {previous_k} | New K: {best_k}")
            print(f"   - Silhouette Score Shift: {sil_change:.4f}")
            
            if best_k == previous_k and sil_change < 0.01:
                if compute_time < 0.10: # Less than 6 seconds
                    print(f"\n   ⏩ Convergence detected, but compute time is extremely low ({compute_time*60:.2f}s).")
                    print(f"   🔥 Pushing engine to next tier to ensure accuracy...")
                else:
                    print(f"\n   ✅ CONVERGENCE ACHIEVED at the {prof.upper()} tier.")
                    print(f"   🛑 Stopping escalation. Optimal clusters locked in.")
                    break
            else:
                print(f"\n   ⚠️ Math has not settled. Escalating to next profile...")
        
        previous_k = best_k
        previous_sil = max_sil

    print("\n" + "="*80)
    print(f" 🎉 CLUSTERING COMPLETE | Total Compute Spent: {total_compute_time:.2f} minutes")
    print("="*80 + "\n")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    parser = argparse.ArgumentParser(description="GitGalaxy Cluster Controller")
    parser.add_argument('--target', type=str, choices=['files', 'repos', 'functions'], default='files', 
                        help="Which dataset to cluster (default: files)")
    args = parser.parse_args()
    
    auto_calibrate(target=args.target)