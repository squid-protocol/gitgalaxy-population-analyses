#!/usr/bin/env python3
"""
File-archetype clustering experiment (data v2.7.0).

Compares three philosophies for clustering FILES using the under-file information
(the function-archetype stoichiometry from func_cluster_ratios) plus curated
file-level features. See EXPERIMENT.md for the hypothesis and pre-registered plan.

Variants (all: RobustScale aux features, weight, KMeans at a common k):
  A  stoichiometry-pure : 14 function-archetype ratios + file size
  B  compositional+     : A + curated file-level structure (function_count,
                          encapsulation, doc density, class structure, and the
                          dependency-GRAPH role pagerank/blast_radius), with the
                          14 stoichiometry dims up-weighted
  C  governed-hits      : B + the rosetta-surviving architectural hit densities
                          (io/api/concurrency/ui) at low weight -- tests whether
                          raw hits add anything beyond stoichiometry.

Design choices (justified in EXPERIMENT.md):
  * Stoichiometry stays a proper composition: raw fractions in [0,1], NOT
    RobustScaled (scaling a mostly-zero simplex dim blows up rare values); the
    block gets an explicit weight instead.
  * Graph metrics (pagerank, blast_radius) are log1p'd, never divided by LOC
    (they are already normalized -- the transform bug the old cluster_files hit).
  * No-function CODE files (constants/config/__init__ -- "x = ...") are INCLUDED;
    their all-zero stoichiometry lets them self-organize into a declarative cluster.
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sqlite3, argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import RobustScaler
from sklearn.metrics import silhouette_score

SCRIPT_DIR = Path(__file__).resolve().parent
DB = SCRIPT_DIR.parents[2] / "data" / "gitgalaxy_master.db"
STOICH = [f"micro_{i}" for i in range(14)]
# canonical archetype names (index-aligned with func_cluster_ratios / cluster_names)
ARCHE = ["Interface Declarations","Type Conversions","State Mutators","Callbacks & Closures",
         "Parameter Forwarders","Compute Cores","C Struct Operations","Many-Argument Workhorses",
         "I/O & Config Routines","Encapsulated Accessors","Annotated Framework Methods",
         "Generic / Templated Code","Defensive Guards","Tests & Verification"]

def load(sample):
    con = sqlite3.connect(DB)
    q = f"""SELECT file_name, repo_name, language, coding_loc, doc_loc, function_count,
                   class_count, import_count, encapsulation_ratio, control_flow_ratio,
                   pagerank_score, normalized_blast_radius, func_cluster_ratios,
                   arch_io, arch_api, arch_concurrency, arch_ui_framework
            FROM file_data
            WHERE coding_loc >= 8
              AND language NOT IN ('plaintext','json','markdown','yaml','csv','xml','text','toml','ini','html')
            ORDER BY (id*2654435761) % 2147483647 LIMIT {sample}"""
    df = pd.read_sql_query(q, con); con.close()
    # parse stoichiometry -> fractions [0,1]
    def parse(s):
        if not s: return [0.0]*14
        try:
            v = [float(x) for x in str(s).split(",")]
            v = (v + [0.0]*14)[:14]
            return [x/100.0 for x in v]
        except Exception:
            return [0.0]*14
    st = np.array([parse(s) for s in df["func_cluster_ratios"]])
    for i in range(14): df[STOICH[i]] = st[:, i]
    df["has_funcs"] = df[STOICH].sum(axis=1) > 0
    num = ["coding_loc","doc_loc","function_count","class_count","import_count",
           "encapsulation_ratio","control_flow_ratio","pagerank_score","normalized_blast_radius",
           "arch_io","arch_api","arch_concurrency","arch_ui_framework"]
    for c in num: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df

def aux_features(df):
    """Curated non-stoichiometry file-level features (name -> series), transform-correct."""
    loc = df["coding_loc"].clip(lower=1)
    return {
        "log_coding_loc": np.log1p(df["coding_loc"]),
        "log_function_count": np.log1p(df["function_count"]),
        "log_class_count": np.log1p(df["class_count"]),
        "log_import_count": np.log1p(df["import_count"]),
        "encapsulation_ratio": df["encapsulation_ratio"].clip(0, 1),
        "doc_ratio": (df["doc_loc"] / loc).clip(0, 2),
        "control_flow_ratio": df["control_flow_ratio"].clip(0, 5),
        "log_pagerank": np.log1p(df["pagerank_score"].clip(lower=0)),          # GRAPH role
        "log_blast_radius": np.log1p(df["normalized_blast_radius"].clip(lower=0)),  # GRAPH role
    }

def gov_hits(df):
    """Rosetta-surviving architectural hit densities (per-LOC, log1p)."""
    loc = df["coding_loc"].clip(lower=1)
    return {f"log_density_{c}": np.log1p((df[c] / loc) * 100.0)
            for c in ["arch_io","arch_api","arch_concurrency","arch_ui_framework"]}

def build_matrix(df, variant, stoich_weight):
    """Returns (X, feature_names, weights). Stoichiometry: raw fractions (unscaled),
    weighted. Aux/hits: RobustScaled, weighted."""
    blocks = []  # (name, values(np), weight, scale?)
    for i, name in enumerate(STOICH):
        blocks.append((f"stoich[{ARCHE[i]}]", df[name].to_numpy(), stoich_weight, False))
    aux = aux_features(df)
    if variant == "A":
        keep = ["log_coding_loc"]
    else:
        keep = list(aux.keys())
    for k in keep:
        blocks.append((k, np.asarray(aux[k], float), 1.0, True))
    if variant == "C":
        for k, v in gov_hits(df).items():
            blocks.append((k, np.asarray(v, float), 0.5, True))
    names = [b[0] for b in blocks]
    cols, weights = [], []
    for name, vals, w, scale in blocks:
        v = np.asarray(vals, float)
        if scale:
            # v2: percentile-rank -> uniform [0,1]. Distribution-agnostic and bounded,
            # so the heavy-tailed graph metrics (pagerank/blast_radius) can't explode a
            # near-zero-median RobustScaler and dominate (the v1 degeneracy: one 97%
            # mega-cluster + quarantine micro-clusters, pagerank pull ~3495 IQR). Now
            # comparable to the [0,1] stoichiometry block.
            v = pd.Series(v).rank(pct=True).to_numpy()
        cols.append(v * w)
        weights.append(w)
    X = np.vstack(cols).T
    return X, names, np.array(weights)

def fingerprint(df, labels, X, names, k):
    out = []
    for c in range(k):
        m = labels == c
        sub = df[m]
        size = int(m.sum()); pct = 100*size/len(df)
        # dominant stoichiometry archetypes (mean fraction)
        stoich_mean = sub[STOICH].mean().to_numpy()
        top = np.argsort(stoich_mean)[::-1][:3]
        top_arch = ", ".join(f"{ARCHE[i]} {stoich_mean[i]*100:.0f}%" for i in top if stoich_mean[i] > 0.03)
        # aux/hit feature pulls (centroid in scaled space) vs global
        cen = X[m].mean(axis=0)
        pulls = sorted(zip(names, cen), key=lambda x: -abs(x[1]))
        top_feat = ", ".join(f"{n}:{v:+.2f}" for n, v in pulls[:5] if not n.startswith("stoich"))
        langs = sub["language"].value_counts(normalize=True).head(3)
        lang = ", ".join(f"{l} {p*100:.0f}%" for l, p in langs.items())
        nofunc = 100*(~sub["has_funcs"]).mean()
        ex = ", ".join(sub["file_name"].head(3).tolist())
        out.append(dict(cluster=c, size=size, pct=round(pct,1), top_archetypes=top_arch or "(none/non-code)",
                        pct_no_functions=round(nofunc,1), top_features=top_feat, languages=lang, examples=ex))
    return out

def run_variant(df, variant, k, stoich_weight):
    X, names, w = build_matrix(df, variant, stoich_weight)
    km = KMeans(n_clusters=k, random_state=42, n_init=10, max_iter=500)
    labels = km.fit_predict(X)
    sil = silhouette_score(X[np.random.RandomState(42).choice(len(X), min(20000,len(X)), replace=False)],
                           labels[np.random.RandomState(42).choice(len(X), min(20000,len(X)), replace=False)])
    sizes = pd.Series(labels).value_counts(normalize=True)*100
    max_pull = float(np.max(np.abs(km.cluster_centers_)))
    return dict(variant=variant, k=k, dims=X.shape[1], stoich_weight=stoich_weight,
                silhouette=round(float(sil),4), min_cluster_pct=round(float(sizes.min()),2),
                max_feature_pull=round(max_pull,2),
                fingerprints=fingerprint(df, labels, X, names, k))

def pick_k(df, stoich_weight, krange):
    X, _, _ = build_matrix(df, "B", stoich_weight)
    idx = np.random.RandomState(42).choice(len(X), min(20000,len(X)), replace=False)
    best=(None,-1)
    print("k-sweep (variant B):")
    for k in krange:
        km=KMeans(n_clusters=k, random_state=42, n_init=6, max_iter=400).fit(X)
        s=silhouette_score(X[idx], km.labels_[idx])
        print(f"  k={k:<3} silhouette={s:.4f}")
        if s>best[1]: best=(k,s)
    return best[0]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=120000)
    ap.add_argument("--k", type=int, default=0, help="0 = auto (silhouette sweep on B)")
    ap.add_argument("--stoich-weight", type=float, default=2.5)
    args = ap.parse_args()

    df = load(args.sample)
    print(f"loaded {len(df):,} files ({100*(~df['has_funcs']).mean():.1f}% no-function/declarative)")
    k = args.k or pick_k(df, args.stoich_weight, range(8, 17))
    print(f"\n=== common k = {k} ===\n")
    results = [run_variant(df, v, k, args.stoich_weight) for v in ["A","B","C"]]
    out = SCRIPT_DIR / "results.json"
    json.dump({"sample": len(df), "k": k, "stoich_weight": args.stoich_weight, "variants": results},
              open(out,"w"), indent=2)
    print("\n=== SUMMARY ===")
    print(f"{'variant':<8}{'dims':<6}{'silhouette':<12}{'min_clust%':<12}{'max_pull':<10}")
    for r in results:
        print(f"{r['variant']:<8}{r['dims']:<6}{r['silhouette']:<12}{r['min_cluster_pct']:<12}{r['max_feature_pull']:<10}")
    print(f"\nwrote {out}")
