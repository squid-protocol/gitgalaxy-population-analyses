#!/usr/bin/env python3
"""Aggregate blocks.csv + labels.csv + defs.csv + files.csv into the report tables.

Writes: per_repo.csv, class_mix.csv, position_mix.csv, length_dist.csv,
technique_vocab.csv, technique_pairs.csv, defs_commented.csv. Prints a digest.
Measurements only (no comment text).
"""
import collections
import csv
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from classify import CODE_TECH_RE  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))
CODE_DIR = "/tmp/gitgalaxy-scratch/claude/code_only"
CLASSES = ["doc/API", "why/rationale", "what/restates", "banner/divider", "algorithm/domain reference",
           "invariant/assumption/units", "TODO/limitation", "commented-out code", "licence/boilerplate", "other"]
POSITIONS = ["header", "preceding_def", "inside_body", "trailing", "other"]


def load(name):
    return list(csv.DictReader(open(os.path.join(OUT, name))))


def write(name, rows):
    if not rows:
        return
    with open(os.path.join(OUT, name), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    blocks = load("blocks.csv")
    labels = {r["block_id"]: r for r in load("labels.csv")}
    files = load("files.csv")
    defs = load("defs.csv")
    for b in blocks:
        b.update({k: v for k, v in labels[b["block_id"]].items() if k != "block_id"})
    groups = {}
    for b in blocks:
        groups.setdefault((b["pair"], b["agent"], b["repo"], b["role"]), []).append(b)
    repos = sorted({(f["pair"], f["agent"], f["repo"], f["role"]) for f in files})

    # ---------------------------------------------------------------- per repo
    per_repo = []
    for key in repos + [("ALL-PAIRS", "claude", "*", "pair"), ("ALL-PAIRS", "codex", "*", "pair")]:
        pair, agent, repo, role = key
        if repo == "*":
            fs = [f for f in files if f["agent"] == agent and f["role"] == "pair"]
            bs = [b for b in blocks if b["agent"] == agent and b["role"] == "pair"]
            ds = [d for d in defs if d["agent"] == agent and d["role"] == "pair"]
        else:
            fs = [f for f in files if f["repo"] == repo]
            bs = groups.get(key, [])
            ds = [d for d in defs if d["repo"] == repo]
        code = sum(int(f["code_lines"]) for f in fs)
        test_code = sum(int(f["code_lines"]) for f in fs if f["test"] == "1")
        conly = sum(int(f["comment_only_lines"]) for f in fs)
        lines = sum(int(b["lines"]) for b in bs)
        words = sum(int(b["words"]) for b in bs)
        fd = [d for d in ds if d["kind"] in ("func", "para", "section") and d["test"] == "0"]
        wl = [int(b["words"]) for b in bs]
        per_repo.append(dict(
            pair=pair, agent=agent, repo=repo, role=role, files=len(fs), code_lines=code, test_code_share=round(test_code / code, 3) if code else 0,
            comment_only_lines=conly, comment_only_per_code=round(conly / code, 4) if code else 0,
            blocks=len(bs), block_lines=lines, words=words,
            blocks_per_100_code=round(100 * len(bs) / code, 2) if code else 0,
            words_per_100_code=round(100 * words / code, 1) if code else 0,
            median_block_words=statistics.median(wl) if wl else 0, mean_block_words=round(statistics.mean(wl), 1) if wl else 0,
            single_line_block_share=round(sum(1 for b in bs if b["lines"] == "1") / len(bs), 3) if bs else 0,
            doc_form_share=round(sum(1 for b in bs if b["doc_form"] == "1") / len(bs), 3) if bs else 0,
            test_block_share=round(sum(1 for b in bs if b["test"] == "1") / len(bs), 3) if bs else 0,
            funcs_or_paras=len(fd), funcs_with_preceding_comment=sum(int(d["commented"]) for d in fd),
            funcs_commented_share=round(sum(int(d["commented"]) for d in fd) / len(fd), 3) if fd else 0,
        ))
    write("per_repo.csv", per_repo)

    # ---------------------------------------------------------------- class / position mix
    def mix(field, cats, name):
        rows = []
        scopes = [("agent", a, None) for a in ("claude", "codex", "claude-redo")] + [("pair", f"{p}|{a}", (p, a)) for (p, a, _r, _role) in repos]
        for kind, label, pa in scopes:
            if kind == "agent":
                bs = [b for b in blocks if b["agent"] == label and (b["role"] == "pair" or label == "claude-redo")]
            else:
                bs = [b for b in blocks if (b["pair"], b["agent"]) == pa]
            n = len(bs)
            w = sum(int(b["words"]) for b in bs)
            for c in cats:
                sel = [b for b in bs if b[field] == c]
                rows.append(dict(scope=kind, group=label, **{field: c}, blocks=len(sel), block_share=round(len(sel) / n, 3) if n else 0,
                                 words=sum(int(b["words"]) for b in sel), word_share=round(sum(int(b["words"]) for b in sel) / w, 3) if w else 0))
        write(name, rows)
        return rows

    cm = mix("primary", CLASSES, "class_mix.csv")
    pm = mix("position", POSITIONS, "position_mix.csv")

    # flags (multi-label cue rates) per agent
    flag_rows = []
    for a in ("claude", "codex", "claude-redo"):
        bs = [b for b in blocks if b["agent"] == a and (b["role"] == "pair" or a == "claude-redo")]
        for fl in ("why", "invariant", "todo", "technique", "domain", "framed"):
            flag_rows.append(dict(agent=a, flag=fl, blocks=sum(int(b[fl]) for b in bs), share=round(sum(int(b[fl]) for b in bs) / len(bs), 3)))
    write("flag_rates.csv", flag_rows)

    # ---------------------------------------------------------------- length distribution
    buckets = [("1", 1, 1), ("2", 2, 2), ("3-5", 3, 5), ("6-10", 6, 10), ("11+", 11, 10 ** 9)]
    wbuckets = [("0-3", 0, 3), ("4-8", 4, 8), ("9-20", 9, 20), ("21-50", 21, 50), ("51+", 51, 10 ** 9)]
    ld = []
    for a in ("claude", "codex", "claude-redo"):
        bs = [b for b in blocks if b["agent"] == a and (b["role"] == "pair" or a == "claude-redo")]
        for nm, lo, hi in buckets:
            k = sum(1 for b in bs if lo <= int(b["lines"]) <= hi)
            ld.append(dict(agent=a, measure="lines", bucket=nm, blocks=k, share=round(k / len(bs), 3)))
        for nm, lo, hi in wbuckets:
            k = sum(1 for b in bs if lo <= int(b["words"]) <= hi)
            ld.append(dict(agent=a, measure="words", bucket=nm, blocks=k, share=round(k / len(bs), 3)))
    write("length_dist.csv", ld)

    # ---------------------------------------------------------------- technique vocabulary
    tv = collections.Counter()
    for b in blocks:
        for t in filter(None, b["techniques"].split(";")):
            tv[(b["agent"], b["pair"], t)] += 1
    vocab = [dict(agent=a, pair=p, technique=t, blocks=n) for (a, p, t), n in sorted(tv.items())]
    write("technique_vocab.csv", vocab)

    code_text = {}
    for fn in os.listdir(CODE_DIR):
        code_text[fn[:-4]] = open(os.path.join(CODE_DIR, fn)).read()
    tp = []
    pairs = sorted({(b["pair"]) for b in blocks if b["role"] == "pair"} | {"chess-rust-redo"})
    pair_repos = collections.defaultdict(dict)
    for (p, a, r, role) in repos:
        pair_repos[p][a] = r
    for p in sorted(pair_repos):
        rp = pair_repos[p]
        named = collections.defaultdict(lambda: collections.Counter())
        for (a, pp, t), n in tv.items():
            if pp == p:
                named[t][a] += n
        for t in sorted(named):
            row = dict(pair=p, technique=t)
            for a in ("claude", "codex", "claude-redo"):
                if a not in rp:
                    continue
                row[f"{a}_comment_blocks"] = named[t][a]
                rx = CODE_TECH_RE.get(t)
                row[f"{a}_in_code"] = ("" if rx is None else len(rx.findall(code_text.get(rp[a], ""))))
            tp.append(row)
    # normalise columns
    cols = ["pair", "technique", "claude_comment_blocks", "claude_in_code", "codex_comment_blocks", "codex_in_code", "claude-redo_comment_blocks", "claude-redo_in_code"]
    tp = [{c: r.get(c, "") for c in cols} for r in tp]
    # loose-regex table superseded by techcheck.py (technique_presence.csv); not written

    # ---------------------------------------------------------------- digest
    print("PER REPO")
    for r in per_repo:
        print(f"{r['pair']:16s} {r['agent']:11s} code={r['code_lines']:5d} blk={r['blocks']:4d} b/100={r['blocks_per_100_code']:5.2f} w/100={r['words_per_100_code']:6.1f} "
              f"conly/code={r['comment_only_per_code']:.3f} medw={r['median_block_words']} 1line={r['single_line_block_share']:.2f} doc={r['doc_form_share']:.2f} "
              f"fncmt={r['funcs_with_preceding_comment']}/{r['funcs_or_paras']}={r['funcs_commented_share']:.2f} test={r['test_block_share']:.2f}")
    print("CLASS MIX (agent)")
    for r in cm:
        if r["scope"] == "agent":
            print(f"  {r['group']:11s} {r['primary']:28s} blocks={r['blocks']:4d} {r['block_share']:.3f} words={r['words']:5d} {r['word_share']:.3f}")
    print("POSITION MIX (agent)")
    for r in pm:
        if r["scope"] == "agent":
            print(f"  {r['group']:11s} {r['position']:14s} blocks={r['blocks']:4d} {r['block_share']:.3f} words {r['word_share']:.3f}")
    print("FLAGS")
    for r in flag_rows:
        print("  ", r)
    print("LENGTH")
    for r in ld:
        print("  ", r)


if __name__ == "__main__":
    main()
