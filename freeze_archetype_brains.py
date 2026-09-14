#!/usr/bin/env python3
"""
Freeze the FILE and REPO archetype models into portable "brains" the engine can
apply to a single scan deterministically.

The file/repo taxonomies are population-relative (percentile-rank transforms over
the whole corpus). To classify one file/repo at scan time, the engine needs the
frozen corpus reference: the rank-transform QUANTILES per aux feature + the KMeans
centroids + names. This script re-fits the chosen models (Variant B / R-B, seeded)
and writes:
  data/file_archetype_brain.json
  data/repo_archetype_brain.json
It then self-validates: re-classifying the population through the frozen brain must
match the KMeans labels (the frozen quantile mapping is a faithful stand-in for rank).
"""
import os
os.environ["OMP_NUM_THREADS"] = "1"
import sqlite3, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

SD = Path(__file__).resolve().parent
DB = SD / "data" / "gitgalaxy_master.db"
NQ = 101  # reference quantiles (0..100th percentile)

# ---- shared ----
def quantile_ref(series):
    return np.percentile(np.asarray(series, float), np.linspace(0, 100, NQ)).tolist()

def rank_via_ref(values, ref):
    # map values -> [0,1] percentile using the frozen reference quantiles
    return np.searchsorted(np.asarray(ref, float), np.asarray(values, float), side="right") / (len(ref) - 1)

# =====================================================================
# FILE BRAIN  (Variant B: 14 stoich + curated structure, k=15)
# =====================================================================
FILE_STOICH = ["Interface Declarations","Type Conversions","State Mutators","Callbacks & Closures",
    "Parameter Forwarders","Compute Cores","C Struct Operations","Many-Argument Workhorses",
    "I/O & Config Routines","Encapsulated Accessors","Annotated Framework Methods",
    "Generic / Templated Code","Defensive Guards","Tests & Verification"]
FILE_STOICH_COL = [f"micro_{i}" for i in range(14)]
FILE_STOICH_WEIGHT = 2.5
FILE_NONCODE = ["plaintext","json","markdown","yaml","csv","xml","text","toml","ini","html"]
FILE_MIN_LOC = 8
FILE_AUX = ["log_coding_loc","log_function_count","log_class_count","log_import_count",
            "encapsulation_ratio","doc_ratio","control_flow_ratio","log_pagerank","log_blast_radius"]

def file_aux_frame(df):
    loc = df["coding_loc"].clip(lower=1)
    return pd.DataFrame({
        "log_coding_loc": np.log1p(df["coding_loc"]),
        "log_function_count": np.log1p(df["function_count"]),
        "log_class_count": np.log1p(df["class_count"]),
        "log_import_count": np.log1p(df["import_count"]),
        "encapsulation_ratio": df["encapsulation_ratio"].clip(0, 1),
        "doc_ratio": (df["doc_loc"] / loc).clip(0, 2),
        "control_flow_ratio": df["control_flow_ratio"].clip(0, 5),
        "log_pagerank": np.log1p(df["pagerank_score"].clip(lower=0)),
        "log_blast_radius": np.log1p(df["normalized_blast_radius"].clip(lower=0)),
    })

def file_name_cluster(sub):
    if (~sub["has_funcs"]).mean() > 0.85: return "Declarative / Non-Code"
    sm = sub[FILE_STOICH_COL].mean().to_numpy(); ti = int(np.argmax(sm))
    if sm[ti] >= 0.55: return f"{FILE_STOICH[ti]} Files"
    if sub["function_count"].median() >= 8 or sub["coding_loc"].median() >= 120: return "Large Core Modules"
    return f"{FILE_STOICH[ti]}-Leaning Mixed"

def freeze_file_brain():
    con = sqlite3.connect(DB)
    df = pd.read_sql_query(f"""SELECT language, coding_loc, doc_loc, function_count, class_count,
        import_count, encapsulation_ratio, control_flow_ratio, pagerank_score, normalized_blast_radius,
        func_cluster_ratios FROM file_data WHERE coding_loc >= {FILE_MIN_LOC}
        AND language NOT IN ({','.join('?'*len(FILE_NONCODE))})""", con, params=FILE_NONCODE)
    con.close()
    for c in ["coding_loc","doc_loc","function_count","class_count","import_count",
              "encapsulation_ratio","control_flow_ratio","pagerank_score","normalized_blast_radius"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    def parse(s):
        if not s: return [0.0]*14
        try:
            v=[float(x) for x in str(s).split(",")]; v=(v+[0.0]*14)[:14]; return [x/100 for x in v]
        except Exception: return [0.0]*14
    st = np.array([parse(s) for s in df["func_cluster_ratios"]])
    for i in range(14): df[FILE_STOICH_COL[i]] = st[:, i]
    df["has_funcs"] = df[FILE_STOICH_COL].sum(axis=1) > 0

    aux = file_aux_frame(df)
    aux_ref = {f: quantile_ref(aux[f]) for f in FILE_AUX}
    aux_ranked = np.column_stack([rank_via_ref(aux[f], aux_ref[f]) for f in FILE_AUX])
    stoich = df[FILE_STOICH_COL].to_numpy() * FILE_STOICH_WEIGHT
    X = np.hstack([stoich, aux_ranked])
    km = KMeans(n_clusters=15, random_state=42, n_init=10, max_iter=500).fit(X)
    df["_c"] = km.labels_
    names, seen = {}, {}
    for c in range(15):
        nm = file_name_cluster(df[df["_c"] == c]); seen[nm]=seen.get(nm,0)+1
        names[c] = nm if seen[nm]==1 else f"{nm} ({seen[nm]})"
    brain = {"k":15, "stoich_weight":FILE_STOICH_WEIGHT, "stoich_archetypes":FILE_STOICH,
             "aux_features":FILE_AUX, "aux_quantiles":aux_ref,
             "centroids":{names[c]: km.cluster_centers_[c].round(5).tolist() for c in range(15)},
             "noncode_languages":FILE_NONCODE, "min_coding_loc":FILE_MIN_LOC,
             "noncode_bucket":"Data / Markup / Trivial"}
    json.dump(brain, open(SD/"data"/"file_archetype_brain.json","w"), indent=1)
    # self-validate: frozen-brain nearest-centroid vs KMeans label
    cen = np.array(list(brain["centroids"].values())); cn = list(brain["centroids"].keys())
    d = np.linalg.norm(X[:,None,:]-cen[None,:,:], axis=2); pred = d.argmin(1)
    agree = np.mean([cn[pred[i]]==names[km.labels_[i]] for i in range(len(df))])
    print(f"FILE brain: {len(df):,} files, 15 archetypes, {len(FILE_AUX)} aux quantile refs. "
          f"self-consistency={agree*100:.1f}%")
    return brain

# =====================================================================
# REPO BRAIN  (R-B: code-file composition + scale + pagerank_gini, k=7)
# =====================================================================
REPO_MIN_FILES = 30
REPO_COMP_WEIGHT = 1.5
REPO_NONCODE = {"Declarative / Non-Code", "Data / Markup / Trivial"}

def gini(x):
    x=np.sort(np.asarray(x,float)); n=len(x)
    return 0.0 if n==0 or x.sum()==0 else float(np.sum((2*np.arange(1,n+1)-n-1)*x)/(n*x.sum()))

def repo_name_cluster(sub, archs):
    comp={a: sub[f"c_{a}"].mean() for a in archs}; mf=sub["file_count"].median(); gi=sub["pagerank_gini"].mean()
    if comp.get("I/O & Config Routines Files",0)>0.5: return "Mainframe / COBOL & Config"
    if comp.get("Generic / Templated Code Files",0)>0.4: return "Typed Library"
    if comp.get("Defensive Guards Files",0)>0.5: return "Guard/Validation-Heavy"
    if mf>=1000: return "Hub-Coupled Monorepo" if gi>=0.35 else "Flat Modular Platform"
    if mf>=150: return "Hub-Coupled App" if gi>=0.35 else "Mid Flat Project"
    return "Small Flat Repo"

def freeze_repo_brain():
    con=sqlite3.connect(DB)
    df=pd.read_sql_query("SELECT repo_name, file_archetype, coding_loc, pagerank_score FROM file_data", con); con.close()
    for c in ["coding_loc","pagerank_score"]: df[c]=pd.to_numeric(df[c],errors="coerce").fillna(0.0)
    archs=sorted(a for a in df["file_archetype"].dropna().unique() if a not in REPO_NONCODE)
    rows=[]
    for repo,g in df.groupby("repo_name"):
        if len(g)<REPO_MIN_FILES: continue
        code=g[~g["file_archetype"].isin(REPO_NONCODE)]
        vc=code["file_archetype"].value_counts(normalize=True) if len(code) else pd.Series(dtype=float)
        rec={f"c_{a}":float(vc.get(a,0.0)) for a in archs}
        rec.update(file_count=len(g), total_loc=float(g["coding_loc"].sum()),
                   non_code_fraction=float(g["file_archetype"].isin(REPO_NONCODE).mean()),
                   pagerank_gini=gini(g["pagerank_score"].values))
        rows.append(rec)
    r=pd.DataFrame(rows)
    aux_raw={"log_file_count":np.log1p(r["file_count"]),"log_total_loc":np.log1p(r["total_loc"]),
             "pagerank_gini":r["pagerank_gini"]}
    aux_ref={f:quantile_ref(v) for f,v in aux_raw.items()}
    comp=r[[f"c_{a}" for a in archs]].to_numpy()*REPO_COMP_WEIGHT
    scale=np.column_stack([rank_via_ref(aux_raw["log_file_count"],aux_ref["log_file_count"]),
                           rank_via_ref(aux_raw["log_total_loc"],aux_ref["log_total_loc"])])
    ncf=r["non_code_fraction"].to_numpy().reshape(-1,1)
    coup=rank_via_ref(aux_raw["pagerank_gini"],aux_ref["pagerank_gini"]).reshape(-1,1)
    X=np.hstack([comp,scale,ncf,coup])
    km=KMeans(n_clusters=7,random_state=42,n_init=25,max_iter=800).fit(X)
    r["_c"]=km.labels_
    names,seen={},{}
    for c in range(7):
        nm=repo_name_cluster(r[r["_c"]==c],archs); seen[nm]=seen.get(nm,0)+1
        names[c]=nm if seen[nm]==1 else f"{nm} ({seen[nm]})"
    brain={"k":7,"comp_weight":REPO_COMP_WEIGHT,"comp_archetypes":archs,"min_files":REPO_MIN_FILES,
           "scale_features":["log_file_count","log_total_loc"],"coupling_feature":"pagerank_gini",
           "aux_quantiles":aux_ref,"feature_order":["comp*w..","scale_rank..","non_code_fraction","coupling_rank"],
           "centroids":{names[c]:km.cluster_centers_[c].round(5).tolist() for c in range(7)},
           "micro_bucket":"Micro Repo (<30 files)"}
    json.dump(brain, open(SD/"data"/"repo_archetype_brain.json","w"), indent=1)
    cen=np.array(list(brain["centroids"].values())); cn=list(brain["centroids"].keys())
    d=np.linalg.norm(X[:,None,:]-cen[None,:,:],axis=2); pred=d.argmin(1)
    agree=np.mean([cn[pred[i]]==names[km.labels_[i]] for i in range(len(r))])
    print(f"REPO brain: {len(r)} repos, 7 archetypes. self-consistency={agree*100:.1f}%")
    return brain

if __name__ == "__main__":
    freeze_file_brain()
    freeze_repo_brain()
    print("wrote data/file_archetype_brain.json + data/repo_archetype_brain.json")
