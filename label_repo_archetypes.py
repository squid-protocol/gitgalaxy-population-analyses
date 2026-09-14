#!/usr/bin/env python3
"""
Label every repo with its repo-archetype (R-B, chosen in
experiments/2.7.0/repo-archetype-clustering/EXPERIMENT.md).

A repo archetype = its CODE-file-archetype composition + scale + dependency-coupling
(pagerank_gini, the hub-vs-flat axis). Composition over code files only (the two
non-code buckets are collapsed into non_code_fraction); scale and coupling are
percentile-rank transformed (never variance-scaled). Language excluded by design.

Clusters repos with >=30 files (k=7), auto-names each cluster from its scale/coupling/
composition signature, and writes repo_archetype to repo_data. Repos below the file
threshold are labeled "Micro Repo (<30 files)".
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sqlite3, argparse
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

DB = Path(__file__).resolve().parent / "data" / "gitgalaxy_master.db"
MIN_FILES = 30
COMP_WEIGHT = 1.5
NONCODE = {"Declarative / Non-Code", "Data / Markup / Trivial"}

def gini(x):
    x = np.sort(np.asarray(x, float)); n = len(x)
    if n == 0 or x.sum() == 0: return 0.0
    return float(np.sum((2*np.arange(1, n+1) - n - 1) * x) / (n * x.sum()))

def load():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query("SELECT repo_name, file_archetype, coding_loc, pagerank_score FROM file_data", con)
    con.close()
    for c in ["coding_loc", "pagerank_score"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    archs = sorted(a for a in df["file_archetype"].dropna().unique() if a not in NONCODE)
    rows = []
    for repo, g in df.groupby("repo_name"):
        code = g[~g["file_archetype"].isin(NONCODE)]
        vc = code["file_archetype"].value_counts(normalize=True) if len(code) else pd.Series(dtype=float)
        rec = {f"comp[{a}]": float(vc.get(a, 0.0)) for a in archs}
        rec.update(repo_name=repo, file_count=len(g), total_loc=float(g["coding_loc"].sum()),
                   non_code_fraction=float(g["file_archetype"].isin(NONCODE).mean()),
                   pagerank_gini=gini(g["pagerank_score"].values))
        rows.append(rec)
    return pd.DataFrame(rows), archs

def build(df, archs):
    cols = [df[f"comp[{a}]"].to_numpy() * COMP_WEIGHT for a in archs]
    cols.append(pd.Series(np.log1p(df["file_count"])).rank(pct=True).to_numpy())
    cols.append(pd.Series(np.log1p(df["total_loc"])).rank(pct=True).to_numpy())
    cols.append(df["non_code_fraction"].to_numpy())
    cols.append(pd.Series(df["pagerank_gini"]).rank(pct=True).to_numpy())
    return np.vstack(cols).T

def name_cluster(sub, archs):
    comp = {a: sub[f"comp[{a}]"].mean() for a in archs}
    mf = sub["file_count"].median(); gi = sub["pagerank_gini"].mean()
    # content-specialty archetypes first (robust across k)
    if comp.get("I/O & Config Routines Files", 0) > 0.5: return "Mainframe / COBOL & Config"
    if comp.get("Generic / Templated Code Files", 0) > 0.4: return "Typed Library"
    if comp.get("Defensive Guards Files", 0) > 0.5: return "Guard/Validation-Heavy"
    # otherwise scale x coupling band
    if mf >= 1000:
        return "Hub-Coupled Monorepo" if gi >= 0.35 else "Flat Modular Platform"
    if mf >= 150:
        return "Hub-Coupled App" if gi >= 0.35 else "Mid Flat Project"
    return "Small Flat Repo"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=7)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    df, archs = load()
    big = df[df["file_count"] >= MIN_FILES].reset_index(drop=True)
    print(f"{len(df)} repos; {len(big)} clustered (>= {MIN_FILES} files), {len(df)-len(big)} micro")
    X = build(big, archs)
    km = KMeans(n_clusters=args.k, random_state=42, n_init=25, max_iter=800).fit(X)
    big["_c"] = km.labels_

    names, seen = {}, {}
    for c in range(args.k):
        nm = name_cluster(big[big["_c"] == c], archs)
        seen[nm] = seen.get(nm, 0) + 1
        names[c] = nm if seen[nm] == 1 else f"{nm} ({seen[nm]})"
    big["repo_archetype"] = big["_c"].map(names)

    print(f"\n=== REPO ARCHETYPES (R-B, k={args.k}) ===")
    for c in sorted(range(args.k), key=lambda c: -(big["_c"] == c).sum()):
        sub = big[big["_c"] == c]
        comp = sorted(((a, sub[f"comp[{a}]"].mean()) for a in archs), key=lambda x: -x[1])[:2]
        cs = ", ".join(f"{a.replace(' Files','')} {v*100:.0f}%" for a, v in comp if v > 0.05)
        print(f"  [{len(sub):>3}] {names[c]:<26} files~{int(sub['file_count'].median()):<5} "
              f"gini={sub['pagerank_gini'].mean():.2f} | {cs}")
        print(f"        {', '.join(sub.sort_values('file_count', ascending=False)['repo_name'].head(8))}")

    if args.write:
        con = sqlite3.connect(DB); cur = con.cursor()
        if "repo_archetype" not in [r[1] for r in cur.execute("PRAGMA table_info(repo_data)")]:
            cur.execute("ALTER TABLE repo_data ADD COLUMN repo_archetype TEXT")
        label = dict(zip(big["repo_name"], big["repo_archetype"]))
        micro = set(df["repo_name"]) - set(big["repo_name"])
        rows = [(label[r], r) for r in label] + [("Micro Repo (<30 files)", r) for r in micro]
        cur.executemany("UPDATE repo_data SET repo_archetype=? WHERE repo_name=?", rows)
        con.commit(); con.close()
        print(f"\n✅ wrote repo_archetype for {len(big):,} clustered + {len(micro):,} micro repos")

if __name__ == "__main__":
    main()
