#!/usr/bin/env python3
"""
Repo-archetype clustering experiment (data v2.7.0).

A repo = its mix of FILE-archetypes (the compositional backbone) + SCALE, with
dependency-COUPLING as a toggled candidate axis. Language is deliberately excluded.
N is small (~368 repos with >=30 files) and every repo is a named, recognizable
project, so clusters are validated by printing the actual repos.

Variants (common small k, composition up-weighted, scale/coupling rank-transformed):
  R-A  composition + scale           : 16 file-archetype ratios + log(file_count), log(total_loc)
  R-B  composition + scale + coupling : R-A + pagerank-gini (hub concentration),
                                        mean dependency_density, mean blast_radius

Design (carried from the file experiment):
  * Composition stays an unscaled distribution [0,1], up-weighted.
  * Scale + coupling are heavy-tailed -> percentile-rank to [0,1], NEVER variance-scaled
    (the pagerank/RobustScaler explosion lesson).
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sqlite3, argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

SCRIPT_DIR = Path(__file__).resolve().parent
DB = SCRIPT_DIR.parents[2] / "data" / "gitgalaxy_master.db"
MIN_FILES = 30
COMP_WEIGHT = 1.5

def gini(x):
    x = np.sort(np.asarray(x, float))
    n = len(x)
    if n == 0 or x.sum() == 0: return 0.0
    return float((np.sum((2*np.arange(1, n+1) - n - 1) * x)) / (n * x.sum()))

def load():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(
        "SELECT repo_name, file_archetype, coding_loc, pagerank_score, dependency_density, "
        "normalized_blast_radius, betweenness_score FROM file_data", con)
    con.close()
    for c in ["coding_loc","pagerank_score","dependency_density","normalized_blast_radius","betweenness_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # v2: composition over CODE files only. The two non-code buckets numerically
    # dominate file counts and washed out the code-structure signal in v1, so they
    # are collapsed into a single `non_code_fraction` feature and the composition is
    # renormalized over code archetypes only ("what kind of CODE does this repo write").
    NONCODE = {"Declarative / Non-Code", "Data / Markup / Trivial"}
    archs = sorted(a for a in df["file_archetype"].dropna().unique() if a not in NONCODE)
    rows = []
    for repo, g in df.groupby("repo_name"):
        if len(g) < MIN_FILES: continue
        code = g[~g["file_archetype"].isin(NONCODE)]
        vc = code["file_archetype"].value_counts(normalize=True) if len(code) else pd.Series(dtype=float)
        rec = {f"comp[{a}]": float(vc.get(a, 0.0)) for a in archs}
        rec["non_code_fraction"] = float(g["file_archetype"].isin(NONCODE).mean())
        rec["repo_name"] = repo
        rec["file_count"] = len(g)
        rec["total_loc"] = float(g["coding_loc"].sum())
        rec["pagerank_gini"] = gini(g["pagerank_score"].values)          # hub concentration
        rec["betweenness_gini"] = gini(g["betweenness_score"].values)    # bottleneck concentration
        rec["mean_dep_density"] = float(g["dependency_density"].mean())  # (diagnostic only)
        rec["mean_blast"] = float(g["normalized_blast_radius"].mean())   # (diagnostic only)
        rows.append(rec)
    return pd.DataFrame(rows), archs

def build(df, archs, variant):
    comp = [f"comp[{a}]" for a in archs]
    names, cols = [], []
    for c in comp:                                  # composition: unscaled, up-weighted
        names.append(c); cols.append(df[c].to_numpy() * COMP_WEIGHT)
    scale = {"log_file_count": np.log1p(df["file_count"]), "log_total_loc": np.log1p(df["total_loc"])}
    for k, v in scale.items():                      # scale: rank -> [0,1]
        names.append(k); cols.append(pd.Series(np.asarray(v, float)).rank(pct=True).to_numpy())
    names.append("non_code_fraction"); cols.append(df["non_code_fraction"].to_numpy())  # already [0,1]
    if variant == "R-B":
        # Refined coupling: pagerank_gini ONLY (hub concentration). The refinement
        # experiment showed it alone delivers the hub-vs-flat separation; adding
        # betweenness_gini BREAKS that separation (0.62-redundant + noise), mean_blast
        # is a -0.76 scale proxy, and mean_dep_density is 0.72-redundant. One honest
        # coupling axis beats piling on.
        names.append("pagerank_gini")
        cols.append(pd.Series(np.asarray(df["pagerank_gini"], float)).rank(pct=True).to_numpy())
    return np.vstack(cols).T, names

def report(df, archs, labels, k, variant):
    out = []
    for c in range(k):
        sub = df[labels == c]
        comp_mean = np.array([sub[f"comp[{a}]"].mean() for a in archs])
        top = np.argsort(comp_mean)[::-1][:3]
        comp_s = ", ".join(f"{archs[i].replace(' Files','')} {comp_mean[i]*100:.0f}%" for i in top if comp_mean[i] > 0.05)
        repos = sub.sort_values("file_count", ascending=False)["repo_name"].tolist()
        out.append(dict(cluster=int(c), n=len(sub),
                        median_files=int(sub["file_count"].median()),
                        median_loc=int(sub["total_loc"].median()),
                        pagerank_gini=round(float(sub["pagerank_gini"].mean()),3),
                        composition=comp_s,
                        repos=repos[:12]))
    return sorted(out, key=lambda x: -x["n"])

def run(df, archs, variant, k):
    X, names = build(df, archs, variant)
    km = KMeans(n_clusters=k, random_state=42, n_init=25, max_iter=800).fit(X)
    sil = silhouette_score(X, km.labels_)
    sizes = pd.Series(km.labels_).value_counts()
    return dict(variant=variant, k=k, dims=X.shape[1], silhouette=round(float(sil),4),
                min_cluster=int(sizes.min()), max_pull=round(float(np.max(np.abs(km.cluster_centers_))),2),
                clusters=report(df, archs, km.labels_, k, variant))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=0, help="0 = sweep on R-B")
    args = ap.parse_args()
    df, archs = load()
    print(f"{len(df)} repos (>= {MIN_FILES} files), {len(archs)} file-archetype composition dims")
    if not args.k:
        X, _ = build(df, archs, "R-B")
        print("k-sweep (R-B):")
        best = (6, -1)
        for k in range(4, 11):
            km = KMeans(n_clusters=k, random_state=42, n_init=15).fit(X)
            s = silhouette_score(X, km.labels_)
            print(f"  k={k}  sil={s:.4f}")
            if s > best[1]: best = (k, s)
        k = best[0]
    else:
        k = args.k
    print(f"\n=== common k={k} ===")
    res = [run(df, archs, v, k) for v in ["R-A", "R-B"]]
    json.dump({"n_repos": len(df), "k": k, "variants": res}, open(SCRIPT_DIR/"results.json","w"), indent=2)
    for r in res:
        print(f"\n########## {r['variant']}  (dims={r['dims']} silhouette={r['silhouette']} min_cluster={r['min_cluster']}) ##########")
        for cl in r["clusters"]:
            print(f"  [{cl['n']} repos] files~{cl['median_files']} loc~{cl['median_loc']:,} gini={cl['pagerank_gini']} | {cl['composition']}")
            print(f"      {', '.join(cl['repos'])}")
    print(f"\nwrote {SCRIPT_DIR/'results.json'}")
