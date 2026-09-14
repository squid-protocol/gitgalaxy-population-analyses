#!/usr/bin/env python3
"""
Label every file with its file-archetype (Variant B, chosen in
experiments/2.7.0/file-archetype-clustering/EXPERIMENT.md).

A file archetype = its function-archetype STOICHIOMETRY (up-weighted, kept as an
unscaled composition) + curated file-level structure (size, function/class/import
counts, encapsulation, doc ratio, control-flow, and the dependency-GRAPH role).
Graph/skewed features are percentile-rank-transformed to [0,1] (NOT variance-scaled
-- pagerank/blast_radius are heavy-tailed and explode a RobustScaler). The 171-dim
raw hit-density bag is intentionally dropped (variant C showed it adds nothing).

Fits KMeans on a sample, assigns file_archetype (auto-named from each cluster's
dominant function composition) + per-cluster distances to ALL qualifying files.
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sqlite3, argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

SCRIPT_DIR = Path(__file__).resolve().parent
DB = SCRIPT_DIR / "data" / "gitgalaxy_master.db"
STOICH = [f"micro_{i}" for i in range(14)]
ARCHE = ["Interface Declarations","Type Conversions","State Mutators","Callbacks & Closures",
         "Parameter Forwarders","Compute Cores","C Struct Operations","Many-Argument Workhorses",
         "I/O & Config Routines","Encapsulated Accessors","Annotated Framework Methods",
         "Generic / Templated Code","Defensive Guards","Tests & Verification"]
STOICH_WEIGHT = 2.5

def load_all():
    con = sqlite3.connect(DB)
    q = """SELECT id, language, coding_loc, doc_loc, function_count, class_count, import_count,
                  encapsulation_ratio, control_flow_ratio, pagerank_score, normalized_blast_radius,
                  func_cluster_ratios
           FROM file_data
           WHERE coding_loc >= 8
             AND language NOT IN ('plaintext','json','markdown','yaml','csv','xml','text','toml','ini','html')"""
    df = pd.read_sql_query(q, con); con.close()
    def parse(s):
        if not s: return [0.0]*14
        try:
            v = [float(x) for x in str(s).split(",")]; v = (v + [0.0]*14)[:14]
            return [x/100.0 for x in v]
        except Exception:
            return [0.0]*14
    st = np.array([parse(s) for s in df["func_cluster_ratios"]])
    for i in range(14): df[STOICH[i]] = st[:, i]
    df["has_funcs"] = df[STOICH].sum(axis=1) > 0
    for c in ["coding_loc","doc_loc","function_count","class_count","import_count",
              "encapsulation_ratio","control_flow_ratio","pagerank_score","normalized_blast_radius"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    return df

def build_matrix(df):
    loc = df["coding_loc"].clip(lower=1)
    aux = {
        "log_coding_loc": np.log1p(df["coding_loc"]),
        "log_function_count": np.log1p(df["function_count"]),
        "log_class_count": np.log1p(df["class_count"]),
        "log_import_count": np.log1p(df["import_count"]),
        "encapsulation_ratio": df["encapsulation_ratio"].clip(0, 1),
        "doc_ratio": (df["doc_loc"] / loc).clip(0, 2),
        "control_flow_ratio": df["control_flow_ratio"].clip(0, 5),
        "log_pagerank": np.log1p(df["pagerank_score"].clip(lower=0)),
        "log_blast_radius": np.log1p(df["normalized_blast_radius"].clip(lower=0)),
    }
    names, cols = [], []
    for i, n in enumerate(STOICH):                       # composition: unscaled [0,1], weighted
        names.append(f"stoich[{ARCHE[i]}]"); cols.append(df[n].to_numpy() * STOICH_WEIGHT)
    for k, v in aux.items():                              # aux: percentile-rank -> [0,1]
        names.append(k); cols.append(pd.Series(np.asarray(v, float)).rank(pct=True).to_numpy())
    return np.vstack(cols).T, names

def name_cluster(sub):
    """Auto-name a file cluster from its composition + structure."""
    nofunc = (~sub["has_funcs"]).mean()
    if nofunc > 0.85:
        return "Declarative / Non-Code"
    stoich_mean = sub[STOICH].mean().to_numpy()
    top_i = int(np.argmax(stoich_mean)); top_v = stoich_mean[top_i]
    # a dominant single function archetype -> "<archetype> Files"
    if top_v >= 0.55:
        return f"{ARCHE[top_i]} Files"
    # otherwise a large mixed module (that's what defines the non-dominant cluster in B)
    if sub["function_count"].median() >= 8 or sub["coding_loc"].median() >= 120:
        return "Large Core Modules"
    return f"{ARCHE[top_i]}-Leaning Mixed"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--fit-sample", type=int, default=200000)
    ap.add_argument("--write", action="store_true", help="write file_archetype to the DB")
    args = ap.parse_args()

    df = load_all()
    print(f"loaded {len(df):,} files ({100*(~df['has_funcs']).mean():.1f}% declarative)")
    X, names = build_matrix(df)

    rs = np.random.RandomState(42)
    fit_idx = rs.choice(len(X), min(args.fit_sample, len(X)), replace=False)
    km = KMeans(n_clusters=args.k, random_state=42, n_init=10, max_iter=500).fit(X[fit_idx])
    labels = km.predict(X)
    dists = km.transform(X)
    df["_label"] = labels

    # auto-name (dedupe collisions with a numeric suffix)
    cluster_names, seen = {}, {}
    for c in range(args.k):
        nm = name_cluster(df[df["_label"] == c])
        seen[nm] = seen.get(nm, 0) + 1
        cluster_names[c] = nm if seen[nm] == 1 else f"{nm} ({seen[nm]})"

    print(f"\n=== FILE ARCHETYPES (Variant B, k={args.k}) ===")
    for c in sorted(range(args.k), key=lambda c: -(df["_label"] == c).sum()):
        sub = df[df["_label"] == c]; pct = 100*len(sub)/len(df)
        sm = sub[STOICH].mean().to_numpy(); top = np.argsort(sm)[::-1][:3]
        comp = ", ".join(f"{ARCHE[i]} {sm[i]*100:.0f}%" for i in top if sm[i] > 0.03) or "(non-code)"
        print(f"  {pct:5.1f}%  {cluster_names[c]:<28} | funcs~{sub['function_count'].median():.0f} "
              f"loc~{sub['coding_loc'].median():.0f} | {comp}")

    if args.write:
        con = sqlite3.connect(DB); cur = con.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(file_data)")]
        if "file_archetype" not in cols:
            cur.execute("ALTER TABLE file_data ADD COLUMN file_archetype TEXT")
        if "file_fingerprint" not in cols:
            cur.execute("ALTER TABLE file_data ADD COLUMN file_fingerprint TEXT")
        upd = [(cluster_names[labels[i]],
                ",".join(f"{d:.3f}" for d in dists[i]),
                int(df["id"].iloc[i])) for i in range(len(df))]
        cur.executemany("UPDATE file_data SET file_archetype=?, file_fingerprint=? WHERE id=?", upd)
        # Full coverage: files outside the clustered set (data/markup formats, tiny
        # files) get one consistent bucket so the taxonomy has no stale/mixed labels.
        keep = set(cluster_names.values()) | {"Data / Markup / Trivial"}
        q = ("UPDATE file_data SET file_archetype=? WHERE file_archetype IS NULL "
             "OR file_archetype NOT IN ({})".format(",".join("?" * len(keep))))
        n_rest = cur.execute(q, ["Data / Markup / Trivial"] + list(keep)).rowcount
        con.commit(); con.close()
        print(f"\n✅ wrote file_archetype for {len(upd):,} clustered + {n_rest:,} data/trivial files")

if __name__ == "__main__":
    main()
